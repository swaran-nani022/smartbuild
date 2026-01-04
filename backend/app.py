from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import os
import json
import urllib.request
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

# ==================== ENV ====================
load_dotenv()

# ==================== FLASK ====================
app = Flask(__name__)
CORS(app)

# ==================== FIREBASE ====================
import firebase_admin
from firebase_admin import credentials, auth, db

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if not FIREBASE_DATABASE_URL:
    raise RuntimeError("FIREBASE_DATABASE_URL missing")

try:
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
        print("🔐 Firebase auth via ENV")
    else:
        cred = credentials.Certificate("serviceAccountKey.json")
        print("🔐 Firebase auth via local file")

    firebase_admin.initialize_app(cred, {
        "databaseURL": FIREBASE_DATABASE_URL
    })
    print("✅ Firebase initialized")
except Exception as e:
    print("❌ Firebase init failed:", e)
    raise

# ==================== YOLO + TORCH SAFE LOAD ====================
import torch
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel
from ultralytics.nn.modules.block import C2f
from ultralytics.nn.modules.conv import Conv

from torch.nn.modules.container import Sequential
from torch.nn.modules.conv import Conv2d
from torch.nn.modules.batchnorm import BatchNorm2d
from torch.nn.modules.activation import SiLU

# 🔥 REQUIRED for PyTorch ≥ 2.6
torch.serialization.add_safe_globals([
    DetectionModel,
    C2f,
    Conv,
    Sequential,
    Conv2d,
    BatchNorm2d,
    SiLU,
])

# ==================== MODEL ====================
MODEL_DIR = "models"
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(MODEL_DIR, "best.pt"))
MODEL_URL = "https://drive.google.com/uc?export=download&id=18U3aCY60Woi1l9Ebm8HaB9QZ7ELEvxV4"

os.makedirs(MODEL_DIR, exist_ok=True)

if not os.path.exists(MODEL_PATH):
    print("⬇️ Downloading YOLO model...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("✅ Model downloaded")

_model = None

def get_model():
    global _model
    if _model is None:
        _model = YOLO(MODEL_PATH)
        print("🤖 YOLO model loaded")
    return _model

# ==================== UPLOADS ====================
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== AUTH DECORATOR ====================
def firebase_token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Auth token missing"}), 401

        token = header.split(" ", 1)[1].strip()
        try:
            decoded = auth.verify_id_token(token)
            request.user = {
                "uid": decoded["uid"],
                "email": decoded.get("email"),
                "name": decoded.get("name")
            }
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401

        return f(*args, **kwargs)
    return wrapper

# ==================== AUTH PLACEHOLDERS ====================
@app.route("/api/register", methods=["POST"])
def register():
    return jsonify({"error": "Use Firebase Auth on frontend"}), 400

@app.route("/api/login", methods=["POST"])
def login():
    return jsonify({"error": "Use Firebase Auth on frontend"}), 400

# ==================== PROFILE ====================
@app.route("/api/profile", methods=["GET"])
@firebase_token_required
def get_profile():
    uid = request.user["uid"]
    profile = db.reference(f"users/{uid}/profile").get() or {}
    return jsonify({"user": {**request.user, **profile}})

@app.route("/api/profile", methods=["PUT"])
@firebase_token_required
def update_profile():
    uid = request.user["uid"]
    data = request.json or {}
    data["updated_at"] = datetime.utcnow().isoformat()
    db.reference(f"users/{uid}/profile").update(data)
    return jsonify({"message": "Profile updated"})

# ==================== ANALYZE ====================
@app.route("/api/analyze", methods=["POST"])
@firebase_token_required
def analyze_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    uid = request.user["uid"]

    filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{image.filename.replace(' ', '_')}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    image.save(path)

    model = get_model()
    results = model.predict(path, conf=0.20)

    detected = {}
    for r in results:
        if r.boxes:
            for c in r.boxes.cls:
                name = model.names[int(c)]
                detected[name] = detected.get(name, 0) + 1

    total = sum(detected.values())
    severity = "Good" if total == 0 else "Moderate" if total <= 2 else "Critical"

    penalties = {
        "crack": 12,
        "major_crack": 15,
        "minor_crack": 8,
        "spalling": 20,
        "peeling": 10,
        "algae": 5,
        "stain": 5,
    }

    score = max(0, 100 - sum(penalties.get(d, 0) * c for d, c in detected.items()))

    precautions_map = {
        "crack": "Seal cracks early.",
        "major_crack": "Immediate structural inspection required.",
        "minor_crack": "Monitor and seal if needed.",
        "spalling": "Repair damaged concrete immediately.",
        "peeling": "Remove loose material and repaint.",
        "algae": "Clean surface and improve drainage.",
        "stain": "Identify and eliminate moisture source.",
    }

    precautions = list({precautions_map[d] for d in detected if d in precautions_map})

    data = {
        "detected_damages": detected,
        "severity": severity,
        "health_score": score,
        "precautions": precautions,
        "image_url": f"/api/images/{filename}",
        "created_at": datetime.utcnow().isoformat(),
    }

    ref = db.reference(f"users/{uid}/inspections").push(data)
    return jsonify({**data, "inspection_id": ref.key})

# ==================== INSPECTIONS ====================
@app.route("/api/inspections", methods=["GET"])
@firebase_token_required
def get_inspections():
    uid = request.user["uid"]
    data = db.reference(f"users/{uid}/inspections").get() or {}
    return jsonify({"inspections": [{**v, "id": k} for k, v in data.items()]})

@app.route("/api/inspections/<iid>", methods=["DELETE"])
@firebase_token_required
def delete_inspection(iid):
    uid = request.user["uid"]
    db.reference(f"users/{uid}/inspections/{iid}").delete()
    return jsonify({"message": "Inspection deleted"})

# ==================== IMAGE SERVE ====================
@app.route("/api/images/<filename>")
def serve_image(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path)
    return jsonify({"error": "Image not found"}), 404

# ==================== ROOT ====================
@app.route("/")
def home():
    return jsonify({"service": "Smart Building Inspection", "status": "running"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "time": datetime.utcnow().isoformat()})

# ==================== LOCAL ====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
