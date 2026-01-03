from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from ultralytics import YOLO
import os
import json
import urllib.request
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, auth, db

# Load environment variables (LOCAL ONLY)
load_dotenv()

app = Flask(__name__)
CORS(app)

# ==================== FIREBASE CONFIG (LOCAL + RENDER) ====================
FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if not FIREBASE_DATABASE_URL:
    raise RuntimeError("FIREBASE_DATABASE_URL missing")

try:
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        # Render / production
        service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(service_account_info)
        print("🔐 Firebase auth via ENV")
    else:
        # Local development
        cred = credentials.Certificate("serviceAccountKey.json")
        print("🔐 Firebase auth via local file")

    firebase_admin.initialize_app(cred, {
        "databaseURL": FIREBASE_DATABASE_URL
    })
    print("✅ Firebase initialized")
except Exception as e:
    print("❌ Firebase init failed:", e)
    raise

# ==================== YOLO MODEL (LOCAL + AUTO DOWNLOAD) ====================
MODEL_DIR = "models"
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(MODEL_DIR, "best.pt"))
MODEL_URL = "https://drive.google.com/uc?export=download&id=18U3aCY60Woi1l9Ebm8HaB9QZ7ELEvxV4"

os.makedirs(MODEL_DIR, exist_ok=True)

if not os.path.exists(MODEL_PATH):
    print("⬇️ Model not found. Downloading...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("✅ Model downloaded")

model = YOLO(MODEL_PATH)

# ==================== UPLOAD FOLDER ====================
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== FIREBASE AUTH DECORATOR ====================
def firebase_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()

        if not token:
            return jsonify({"error": "Token is missing!"}), 401

        try:
            decoded = auth.verify_id_token(token)
            request.user = {
                "uid": decoded["uid"],
                "email": decoded.get("email"),
                "name": decoded.get("name")
            }
        except Exception:
            return jsonify({"error": "Token is invalid or expired!"}), 401

        return f(*args, **kwargs)
    return decorated

# ==================== AUTH PLACEHOLDERS ====================
@app.route("/api/register", methods=["POST"])
def register():
    return jsonify({"error": "Use Firebase Auth on frontend"}), 400

@app.route("/api/login", methods=["POST"])
def login():
    return jsonify({"error": "Use Firebase Auth on frontend"}), 400

# ==================== PROFILE ROUTES ====================
@app.route("/api/profile", methods=["GET"])
@firebase_token_required
def get_profile():
    uid = request.user["uid"]
    stored_profile = db.reference(f"users/{uid}/profile").get() or {}
    return jsonify({"user": {**request.user, **stored_profile}})

@app.route("/api/profile", methods=["PUT"])
@firebase_token_required
def update_profile():
    uid = request.user["uid"]
    data = request.json or {}
    data["updated_at"] = datetime.utcnow().isoformat()
    db.reference(f"users/{uid}/profile").update(data)
    return jsonify({"message": "Profile updated"})

# ==================== MAIN ANALYSIS ====================
@app.route("/api/analyze", methods=["POST"])
@firebase_token_required
def analyze_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    uid = request.user["uid"]

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename.replace(' ', '_')}"
    image_path = os.path.join(UPLOAD_FOLDER, filename)
    image.save(image_path)

    results = model.predict(image_path, conf=0.20)

    detected = {}
    for r in results:
        if r.boxes is None:
            continue
        for c in r.boxes.cls:
            name = model.names[int(c)]
            detected[name] = detected.get(name, 0) + 1

    count = sum(detected.values())
    severity = "Good" if count == 0 else "Moderate" if count <= 2 else "Critical"

    penalties = {
        "crack": 12,
        "major_crack": 15,
        "minor_crack": 8,
        "spalling": 20,
        "peeling": 10,
        "algae": 5,
        "stain": 5,
        "normal": 0
    }

    score = 100
    for d, c in detected.items():
        score -= penalties.get(d, 0) * c
    score = max(score, 0)

    precaution_map = {
        "crack": "Seal cracks early to prevent structural weakening.",
        "major_crack": "Immediate structural inspection and repair required.",
        "minor_crack": "Monitor cracks and apply sealant if needed.",
        "spalling": "Repair damaged concrete immediately to avoid further degradation.",
        "peeling": "Remove loose material and reapply protective coating.",
        "algae": "Clean surface and improve drainage to prevent moisture retention.",
        "stain": "Identify moisture source and clean affected area."
    }

    precautions = list({precaution_map[d] for d in detected if d in precaution_map})

    inspection_data = {
        "detected_damages": detected,
        "severity": severity,
        "health_score": score,
        "precautions": precautions,
        "image_url": f"/api/images/{filename}",
        "created_at": datetime.utcnow().isoformat()
    }

    ref = db.reference(f"users/{uid}/inspections").push(inspection_data)

    return jsonify({**inspection_data, "inspection_id": ref.key})

# ==================== INSPECTIONS ====================
@app.route("/api/inspections", methods=["GET"])
@firebase_token_required
def get_inspections():
    uid = request.user["uid"]
    data = db.reference(f"users/{uid}/inspections").get() or {}
    return jsonify({"inspections": [{**v, "id": k} for k, v in data.items()]})

@app.route("/api/inspections/<inspection_id>", methods=["DELETE"])
@firebase_token_required
def delete_inspection(inspection_id):
    uid = request.user["uid"]
    db.reference(f"users/{uid}/inspections/{inspection_id}").delete()
    return jsonify({"message": "Inspection deleted"})

# ==================== IMAGE SERVING ====================
@app.route("/api/images/<filename>")
def serve_image(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path)
    return jsonify({"error": "Image not found"}), 404

# ==================== LEGACY ENDPOINT ====================
@app.route("/analyze", methods=["POST"])
def analyze_legacy():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    image_path = os.path.join(UPLOAD_FOLDER, image.filename)
    image.save(image_path)

    results = model.predict(image_path, conf=0.20)
    detected = {}
    for r in results:
        if r.boxes:
            for c in r.boxes.cls:
                name = model.names[int(c)]
                detected[name] = detected.get(name, 0) + 1

    return jsonify({"detected_damages": detected})

# ==================== ROOT & HEALTH ====================
@app.route("/")
def home():
    return jsonify({
        "message": "Smart Building Inspection Backend (Firebase RTDB)",
        "status": "running"
    })

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "time": datetime.utcnow().isoformat()})

# ==================== MAIN ====================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
