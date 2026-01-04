import axios from "axios";
import { auth } from "../firebase"; // adjust path if needed

const API_BASE_URL = "https://smartbuild-2jzu.onrender.com";

const api = axios.create({
  baseURL: API_BASE_URL,
  // Don't set a global Content-Type, because FormData uploads need axios/browser to set boundary.
  // JSON requests will still work because axios sets it automatically when data is a plain object.
});

// Attach Firebase ID token automatically to every request (if logged in)
api.interceptors.request.use(
  async (config) => {
    const user = auth.currentUser;

    if (user) {
      // returns cached token; refreshes when needed
      const idToken = await user.getIdToken();
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${idToken}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// ---------------- API calls ----------------

// Authenticated analyze (YOLO + save to RTDB)
// Pass a FormData object that includes: formData.append("image", file)
export const analyzeImage = async (formData) => {
  try {
    const response = await api.post("/api/analyze", formData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Analysis failed" };
  }
};

// Get history
export const getInspections = async () => {
  try {
    const response = await api.get("/api/inspections");
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to fetch inspections" };
  }
};

// Delete one inspection
export const deleteInspection = async (id) => {
  try {
    const response = await api.delete(`/api/inspections/${id}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to delete inspection" };
  }
};

// Get profile (optional)
export const getProfile = async () => {
  try {
    const response = await api.get("/api/profile");
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to fetch profile" };
  }
};

// Update profile (optional)
export const updateProfileApi = async (payload) => {
  try {
    const response = await api.put("/api/profile", payload);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Failed to update profile" };
  }
};

// ---- Demo mode (unchanged) ----
export const mockAnalyzeImage = (imageData) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      const mockDamages = [
        "minor_crack",
        "major_crack",
        "spalling",
        "peeling",
        "algae",
        "stain",
        "normal",
      ];
      const detected = {};

      const numDamages = Math.floor(Math.random() * 3) + 1;
      for (let i = 0; i < numDamages; i++) {
        const damage = mockDamages[Math.floor(Math.random() * mockDamages.length)];
        detected[damage] = (detected[damage] || 0) + 1;
      }

      const count = Object.values(detected).reduce((a, b) => a + b, 0);
      let severity = "Good";
      let score = 100;

      if (count > 0) {
        const penalties = {
          major_crack: 15,
          minor_crack: 8,
          spalling: 20,
          peeling: 10,
          algae: 5,
          stain: 5,
          normal: 0,
        };

        Object.keys(detected).forEach((d) => {
          score -= (penalties[d] || 0) * detected[d];
        });

        score = Math.max(score, 0);

        if (count <= 2) severity = "Moderate";
        else severity = "Critical";
      }

      const precautions = [
        "Regular inspection recommended",
        "Monitor damaged areas monthly",
        "Consider professional assessment",
      ];

      resolve({
        detected_damages: detected,
        severity,
        health_score: score,
        precautions,
      });
    }, 1500);
  });
};

export default api;
