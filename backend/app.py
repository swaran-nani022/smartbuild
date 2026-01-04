# ==================== PYTORCH FIX (MUST BE FIRST) ====================
import os
os.environ["TORCH_LOAD_WEIGHTS_ONLY"] = "0"

# ==================== IMPORTS ====================
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from ultralytics import YOLO
import torch

import json
import urllib.request
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, auth, db

# ==================== ENV ====================
load_dotenv()

app = Flask(__name__)
CORS(app)

# ==================== FIREBASE CONFIG ====================
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

# ==================== YOLO MODEL ====================
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
            return jsonify({"error": "Token missing"}), 401

        token = header.split(" ", 1)[1]

        try:
            decoded = auth.verify_id_token(token)
            request.user = {
                "uid": decoded["uid"],
                "email": decoded.get("email"),
                "name": decoded.get("name"),
            }
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401

        return f(*args, **kwargs)
    return wrapper

# ==================== PROFILE ====================
@app.route("/api/profile", methods=["GET"])
@firebase_token_required
def get_profile():
    uid = request.user["uid"]
    data = db.reference(f"users/{uid}/profile").get() or {}
    return jsonify({"user": {**request.user, **data}})

@app.route("/api/profile", methods=["PUT"])
@firebase_token_required
def update_profile():
    uid = request.user["uid"]
    payload = request.json or {}
    payload["updated_at"] = datetime.utcnow().isoformat()
    db.reference(f"users/{uid}/profile").update(payload)
    return jsonify({"message": "Profile updated"})

# ==================== ANALYZE ====================
@app.route("/api/analyze", methods=["POST"])
@firebase_token_required
def analyze_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    uid = request.user["uid"]

    filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{image.filename}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    image.save(path)

    model = get_model()
    results = model.predict(path, conf=0.2)

    detected = {}
    for r in results:
        if r.boxes:
            for cls in r.boxes.cls:
                name = model.names[int(cls)]
                detected[name] = detected.get(name, 0) + 1

    total = sum(detected.values())
    severity = "Good" if total == 0 else "Moderate" if total <= 2 else "Critical"

    penalties = {
        "major_crack": 15,
        "crack": 12,
        "minor_crack": 8,
        "spalling": 20,
        "peeling": 10,
        "algae": 5,
        "stain": 5,
    }

    score = max(0, 100 - sum(penalties.get(k, 0) * v for k, v in detected.items()))

    precautions_map = {
        "major_crack": "Immediate structural inspection required.",
        "crack": "Seal cracks early to prevent expansion.",
        "minor_crack": "Monitor and seal if needed.",
        "spalling": "Repair damaged concrete immediately.",
        "peeling": "Remove loose paint and repaint.",
        "algae": "Clean surface and improve drainage.",
        "stain": "Check for moisture leakage.",
    }

    precautions = list({precautions_map[k] for k in detected if k in precautions_map})

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
    ref = db.reference(f"users/{uid}/inspections/{iid}")
    inspection = ref.get()

    if not inspection:
        return jsonify({"error": "Inspection not found"}), 404

    # 🔥 DELETE IMAGE FILE
    image_url = inspection.get("image_url")
    if image_url:
        filename = image_url.split("/")[-1]
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(image_path):
            os.remove(image_path)
            print(f"🗑️ Deleted image: {filename}")

    # 🔥 DELETE DB RECORD
    ref.delete()

    return jsonify({"message": "Inspection and image deleted"})

# ==================== IMAGE SERVE ====================
@app.route("/api/images/<filename>")
def serve_image(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path)
    return jsonify({"error": "Image not found"}), 404

# ==================== HEALTH ====================
@app.route("/")
def root():
    return jsonify({"status": "running"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "time": datetime.utcnow().isoformat()})

# ==================== LOCAL ====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
