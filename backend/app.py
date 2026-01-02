from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from ultralytics import YOLO
import os
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, auth, db

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# -------------------- Firebase Config --------------------
FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT", "serviceAccountKey.json")
FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")

if not FIREBASE_DATABASE_URL:
    raise ValueError("❌ FIREBASE_DATABASE_URL missing in .env")

try:
    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})
    print("✅ Connected to Firebase Realtime Database successfully!")
except Exception as e:
    print(f"❌ Firebase init failed: {e}")
    raise

# -------------------- Load YOLO model --------------------
MODEL_PATH = os.getenv("MODEL_PATH", "../runs/train/final_multidamage/weights/best.pt")
model = YOLO(MODEL_PATH)

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== FIREBASE AUTH FUNCTIONS ====================
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
            decoded = auth.verify_id_token(token)  # verifies signature + expiry
            # decoded has uid, and may have email/name depending on provider
            request.user = {
                "uid": decoded["uid"],
                "email": decoded.get("email"),
                "name": decoded.get("name")
            }
        except Exception:
            return jsonify({"error": "Token is invalid or expired!"}), 401

        return f(*args, **kwargs)
    return decorated

# ==================== (OPTIONAL) AUTH ROUTES ====================
# With Firebase, register/login is typically done on frontend using Firebase Auth SDK.
# Keeping these endpoints as "not supported" to avoid confusion.
@app.route("/api/register", methods=["POST"])
def register():
    return jsonify({
        "error": "Use Firebase Auth on frontend (createUserWithEmailAndPassword / Google sign-in)."
    }), 400

@app.route("/api/login", methods=["POST"])
def login():
    return jsonify({
        "error": "Use Firebase Auth on frontend (signInWithEmailAndPassword / Google sign-in)."
    }), 400

# ==================== PROFILE ROUTES ====================
@app.route("/api/profile", methods=["GET"])
@firebase_token_required
def get_profile():
    """Get user profile from token + optional RTDB profile node"""
    user = request.user
    uid = user["uid"]

    profile_ref = db.reference(f"users/{uid}/profile")
    stored_profile = profile_ref.get() or {}

    profile = {
        "uid": uid,
        "email": user.get("email"),
        "name": user.get("name") or stored_profile.get("name"),
        **stored_profile
    }
    return jsonify({"user": profile})

@app.route("/api/profile", methods=["PUT"])
@firebase_token_required
def update_profile():
    """Update current user's profile details in RTDB"""
    user = request.user
    uid = user["uid"]
    data = request.json or {}

    update_fields = {}
    if "name" in data:
        update_fields["name"] = data["name"]
    if "phone" in data:
        update_fields["phone"] = data["phone"]

    if not update_fields:
        return jsonify({"error": "No fields to update"}), 400

    update_fields["updated_at"] = datetime.utcnow().isoformat()
    db.reference(f"users/{uid}/profile").update(update_fields)

    return jsonify({
        "message": "Profile updated",
        "user": {"uid": uid, **update_fields}
    })

# ==================== MAIN ANALYSIS ENDPOINT (FIREBASE RTDB) ====================
@app.route("/api/analyze", methods=["POST"])
@firebase_token_required
def analyze_image():
    """Analyze image and save to Firebase Realtime Database"""
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    user = request.user
    uid = user["uid"]

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = image.filename.replace(" ", "_")
    filename = f"{timestamp}_{safe_name}"
    image_path = os.path.join(UPLOAD_FOLDER, filename)
    image.save(image_path)

    # YOLO prediction
    results = model.predict(image_path, conf=0.20)

    detected = {}
    for r in results:
        if r.boxes is None:
            continue
        for c in r.boxes.cls:
            class_id = int(c)
            class_name = model.names[class_id]
            detected[class_name] = detected.get(class_name, 0) + 1

    # Severity logic
    count = sum(detected.values())
    if count == 0:
        severity = "Good"
    elif count <= 2:
        severity = "Moderate"
    else:
        severity = "Critical"

    # Health score logic
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

    # Precautions
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
        "user_id": uid,
        "user_email": user.get("email"),
        "image_filename": filename,
        "image_path": image_path,  # local path on server
        "image_url": f"/api/images/{filename}",
        "detected_damages": detected,
        "severity": severity,
        "health_score": score,
        "precautions": precautions,
        "created_at": datetime.utcnow().isoformat()
    }

    # Save to RTDB under users/<uid>/inspections/<pushId>
    new_ref = db.reference(f"users/{uid}/inspections").push(inspection_data)
    inspection_id = new_ref.key

    return jsonify({
        "detected_damages": detected,
        "severity": severity,
        "health_score": score,
        "precautions": precautions,
        "inspection_id": inspection_id,
        "image_url": f"/api/images/{filename}"
    })

# ==================== GET USER INSPECTIONS ====================
@app.route("/api/inspections", methods=["GET"])
@firebase_token_required
def get_inspections():
    """Get all inspections for current user from RTDB"""
    try:
        uid = request.user["uid"]
        data = db.reference(f"users/{uid}/inspections").get() or {}

        inspections = []
        for k, v in data.items():
            if isinstance(v, dict):
                v["id"] = k
                inspections.append(v)

        inspections.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jsonify({"inspections": inspections[:50]})
    except Exception as e:
        print(f"Error getting inspections: {e}")
        return jsonify({"error": "Failed to get inspections"}), 500

@app.route("/api/inspections/<inspection_id>", methods=["DELETE"])
@firebase_token_required
def delete_inspection(inspection_id):
    """Delete a single inspection for the current user from RTDB"""
    try:
        uid = request.user["uid"]
        ref = db.reference(f"users/{uid}/inspections/{inspection_id}")
        existing = ref.get()
        if existing is None:
            return jsonify({"error": "Inspection not found"}), 404

        ref.delete()
        return jsonify({"message": "Inspection deleted"})
    except Exception as e:
        print("Delete inspection error:", e)
        return jsonify({"error": "Failed to delete inspection"}), 500

# ==================== IMAGE SERVING ====================
@app.route("/api/images/<filename>", methods=["GET"])
def serve_image(filename):
    """Serve uploaded images from local uploads folder"""
    try:
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(image_path):
            return send_file(image_path)
        return jsonify({"error": "Image not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==================== KEEP OLD ENDPOINT FOR COMPATIBILITY ====================
@app.route("/analyze", methods=["POST"])
def analyze_image_legacy():
    """Legacy endpoint for backward compatibility (no auth required)"""
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    filename = f"legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename.replace(' ','_')}"
    image_path = os.path.join(UPLOAD_FOLDER, filename)
    image.save(image_path)

    results = model.predict(image_path, conf=0.20)

    detected = {}
    for r in results:
        if r.boxes is None:
            continue
        for c in r.boxes.cls:
            class_id = int(c)
            class_name = model.names[class_id]
            detected[class_name] = detected.get(class_name, 0) + 1

    count = sum(detected.values())
    if count == 0:
        severity = "Good"
    elif count <= 2:
        severity = "Moderate"
    else:
        severity = "Critical"

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

    return jsonify({
        "detected_damages": detected,
        "severity": severity,
        "health_score": score,
        "precautions": precautions
    })

# ==================== ROOT ROUTES ====================
@app.route("/")
def home():
    return jsonify({
        "message": "Smart Building Inspection Backend (Firebase RTDB)",
        "version": "3.0",
        "database": "firebase_realtime_database",
        "endpoints": {
            "auth": [
                "Frontend handles Firebase Auth",
                "GET /api/profile",
                "PUT /api/profile"
            ],
            "inspections": ["POST /api/analyze", "GET /api/inspections", "DELETE /api/inspections/<id>"],
            "legacy": ["POST /analyze"]
        }
    })

@app.route("/test")
def test_page():
    return render_template("test.html")

# ==================== HEALTH CHECK ====================
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "database": "firebase_realtime_database",
        "model_loaded": True,
        "timestamp": datetime.utcnow().isoformat()
    })

if __name__ == "__main__":
    print("🚀 Starting Smart Building Inspection Backend with Firebase RTDB...")
    print(f"📁 Upload folder: {UPLOAD_FOLDER}")
    print(f"🔗 RTDB: {FIREBASE_DATABASE_URL}")
    print(f"🤖 Model loaded: {model.names}")
    print("🌐 Server running on http://localhost:5000")
    print("\n📋 Available endpoints:")
    print("  GET  /api/profile            - Get profile (Firebase auth)")
    print("  PUT  /api/profile            - Update profile")
    print("  POST /api/analyze             - Analyze image (Firebase auth)")
    print("  GET  /api/inspections         - Get user inspections")
    print("  DELETE /api/inspections/<id>  - Delete inspection")
    print("  POST /analyze                 - Legacy analyze (no auth)")
    app.run(debug=True, host="0.0.0.0", port=5000)
