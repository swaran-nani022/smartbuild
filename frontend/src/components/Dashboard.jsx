import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  FaSpinner,
  FaRobot,
  FaHistory,
  FaBuilding,
  FaChartPie,
} from "react-icons/fa";
import UploadZone from "./UploadZone";
import "../styles/Dashboard.css";

import { auth } from "../firebase";

const API_BASE = "https://smartbuild-2jzu.onrender.com";

const Dashboard = () => {
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [inspections, setInspections] = useState([]);
  const [stats, setStats] = useState(null);
  const navigate = useNavigate();

  const handleImageUpload = (file, previewUrl) => {
    setImage(file);
    setPreview(previewUrl);
  };

  const getAuthHeader = async () => {
    const user = auth.currentUser;
    if (!user) return null;

    const idToken = await user.getIdToken();
    localStorage.setItem("token", idToken);
    return { Authorization: `Bearer ${idToken}` };
  };

  const computeStats = (list) => {
    if (!list || list.length === 0) {
      setStats(null);
      return;
    }

    const total = list.length;
    const avgScore =
      list.reduce((sum, insp) => sum + (insp.health_score || 0), 0) / total;

    const severityCount = {
      Good: list.filter((i) => i.severity === "Good").length,
      Moderate: list.filter((i) => i.severity === "Moderate").length,
      Critical: list.filter((i) => i.severity === "Critical").length,
    };

    setStats({
      totalInspections: total,
      averageScore: Math.round(avgScore),
      severityCount,
    });
  };

  const fetchInspections = async () => {
    try {
      const authHeader = await getAuthHeader();
      if (!authHeader) {
        navigate("/login");
        return;
      }

      const response = await fetch(`${API_BASE}/api/inspections`, {
        method: "GET",
        headers: {
          ...authHeader,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        if (response.status === 401) navigate("/login");
        return;
      }

      const data = await response.json();
      const list = data.inspections || [];
      setInspections(list);
      computeStats(list);
    } catch (error) {
      console.log("Could not fetch inspection history:", error.message);
    }
  };

  useEffect(() => {
    fetchInspections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAnalyze = async () => {
    if (!image) {
      alert("Please upload an image first");
      return;
    }

    setLoading(true);

    const formData = new FormData();
    formData.append("image", image);

    try {
      const authHeader = await getAuthHeader();
      if (!authHeader) {
        navigate("/login");
        return;
      }

      const response = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        headers: {
          ...authHeader,
          // do NOT set Content-Type for FormData
        },
        body: formData,
      });

      const raw = await response.text();
      console.log(
        "RAW ANALYZE RESPONSE:",
        response.status,
        raw.slice(0, 400)
      );

      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        throw new Error(
          `Server did not return JSON (status ${response.status}).`
        );
      }

      if (!response.ok) {
        if (response.status === 401) navigate("/login");
        throw new Error(data.error || "Analysis failed");
      }

      await fetchInspections();

      navigate("/result", {
        state: {
          analysis: data,
          image: preview,
          filename: image.name,
          inspectionId: data.inspection_id,
        },
      });
    } catch (error) {
      console.error("Analysis error:", error);
      alert(error.message || "Analysis failed");
    } finally {
      setLoading(false);
      setImage(null);
      setPreview(null);
    }
  };

  const handleDeleteInspection = async (id) => {
    try {
      const authHeader = await getAuthHeader();
      if (!authHeader) {
        navigate("/login");
        return;
      }

      const res = await fetch(`${API_BASE}/api/inspections/${id}`, {
        method: "DELETE",
        headers: {
          ...authHeader,
        },
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 401) navigate("/login");
        console.error("Delete failed:", data.error || "Unknown error");
        return;
      }

      const remaining = inspections.filter(
        (insp) => (insp._id || insp.id) !== id
      );
      setInspections(remaining);
      computeStats(remaining);
    } catch (err) {
      console.error("Delete inspection error:", err);
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const getDamageType = (damages) => {
    if (!damages || Object.keys(damages).length === 0) return "No Damage";

    const damageTypes = Object.keys(damages);
    if (damageTypes.includes("major_crack") || damageTypes.includes("spalling")) {
      return "Critical Damage";
    } else if (
      damageTypes.includes("minor_crack") ||
      damageTypes.includes("peeling")
    ) {
      return "Surface Damage";
    } else {
      return "Minor Damage";
    }
  };

  return (
    <div className="dashboard">
      <div className="container">
        <div className="dashboard-header">
          <h1>Building Inspection Dashboard</h1>
          <p>Upload building images for AI-powered damage analysis</p>
        </div>

        <div className="dashboard-grid">
          <div className="dashboard-card main-card">
            <h2>
              <FaRobot /> AI Building Inspector
            </h2>
            <p className="card-description">
              Upload a clear image of building surface. Our AI will detect:
              Cracks, Spalling, Peeling, Algae, Stains, and more.
            </p>

            <UploadZone onImageUpload={handleImageUpload} />

            {preview && (
              <div className="preview-section">
                <h3>Image Preview:</h3>
                <img src={preview} alt="Preview" className="image-preview" />
              </div>
            )}

            <button
              onClick={handleAnalyze}
              className="btn btn-primary analyze-btn"
              disabled={!image || loading}
            >
              {loading ? (
                <>
                  <FaSpinner className="spinner" />
                  Analyzing with AI...
                </>
              ) : (
                <>
                  <FaRobot /> Analyze Building
                </>
              )}
            </button>

            <div className="upload-tips">
              <h4>📸 Tips for Best Results:</h4>
              <ul>
                <li>Use good natural lighting</li>
                <li>Capture clear, focused images</li>
                <li>Include entire damaged area</li>
                <li>Avoid shadows and reflections</li>
              </ul>
            </div>
          </div>

          <div className="sidebar">
            {stats && (
              <div className="dashboard-card">
                <h3>
                  <FaChartPie /> Your Statistics
                </h3>
                <div className="stats-grid">
                  <div className="stat">
                    <div className="stat-value">{stats.totalInspections}</div>
                    <div className="stat-label">Total Inspections</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value">{stats.averageScore}</div>
                    <div className="stat-label">Avg Health Score</div>
                  </div>
                </div>
                <div className="severity-stats">
                  <div className="severity-stat">
                    <span className="severity-dot good"></span>
                    <span>Good: {stats.severityCount.Good || 0}</span>
                  </div>
                  <div className="severity-stat">
                    <span className="severity-dot moderate"></span>
                    <span>Moderate: {stats.severityCount.Moderate || 0}</span>
                  </div>
                  <div className="severity-stat">
                    <span className="severity-dot critical"></span>
                    <span>Critical: {stats.severityCount.Critical || 0}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="dashboard-card">
              <h3>
                <FaHistory /> Inspection History
              </h3>

              {inspections.length > 0 ? (
                <div className="recent-list">
                  {inspections.slice(0, 5).map((inspection) => {
                    const id = inspection._id || inspection.id;

                    return (
                      <div key={id} className="recent-item">
                        <div
                          className="recent-main"
                          onClick={() =>
                            navigate("/result", {
                              state: {
                                analysis: {
                                  detected_damages:
                                    inspection.detected_damages,
                                  severity: inspection.severity,
                                  health_score: inspection.health_score,
                                  precautions: inspection.precautions,
                                },
                                inspectionId: id,
                              },
                            })
                          }
                          style={{ cursor: "pointer" }}
                        >
                          <div className="recent-type">
                            <FaBuilding />
                            <div>
                              <span className="damage-type-name">
                                {getDamageType(inspection.detected_damages)}
                              </span>
                              <span className="inspection-date">
                                {formatDate(inspection.created_at)}
                              </span>
                            </div>
                          </div>

                          <div
                            className={`recent-severity severity-${(
                              inspection.severity || "Moderate"
                            ).toLowerCase()}`}
                          >
                            {inspection.severity || "Moderate"}
                          </div>

                          <div className="recent-score">
                            {inspection.health_score || 75}
                          </div>
                        </div>

                        <button
                          className="history-delete-btn"
                          type="button"
                          onClick={() => handleDeleteInspection(id)}
                          title="Delete this inspection"
                        >
                          ✕
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="no-history">
                  <p>No inspections yet. Upload your first image!</p>
                </div>
              )}
            </div>

            <div className="dashboard-card">
              <h3>Damage Types Detected</h3>
              <div className="damage-types">
                <div className="damage-type">
                  <span className="damage-badge critical">Major Crack</span>
                  <span className="damage-desc">Structural damage</span>
                </div>
                <div className="damage-type">
                  <span className="damage-badge moderate">Minor Crack</span>
                  <span className="damage-desc">Surface-level</span>
                </div>
                <div className="damage-type">
                  <span className="damage-badge critical">Spalling</span>
                  <span className="damage-desc">Concrete damage</span>
                </div>
                <div className="damage-type">
                  <span className="damage-badge moderate">Peeling</span>
                  <span className="damage-desc">Paint damage</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
