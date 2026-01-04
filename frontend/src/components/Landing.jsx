import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FaRobot, FaShieldAlt, FaChartLine,
  FaFilePdf, FaArrowRight, FaBuilding
} from 'react-icons/fa';
import '../styles/Landing.css';

import { onAuthStateChanged } from "firebase/auth";
import { auth } from "../firebase"; // adjust path if needed

const Landing = () => {
  const navigate = useNavigate();
  const [isAuthed, setIsAuthed] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    // Wait for Firebase to restore persisted session
    const unsub = onAuthStateChanged(auth, (user) => {
      setIsAuthed(!!user);
      setAuthChecked(true);
    });
    return () => unsub();
  }, []);

  return (
    <div className="landing-page">
      <section className="hero">
        <div className="container">
          <div className="hero-content">
            <div className="hero-text">
              <div className="badge">
                <FaRobot /> AI-Powered Detection
              </div>
              <h1>Smart Building Inspection System</h1>
              <p className="subtitle">
                Detect 7 types of structural damages with 89% accuracy using
                advanced computer vision and machine learning.
              </p>

              <div className="hero-buttons">
                {/* Optional: avoid flicker until Firebase finishes checking */}
                {!authChecked ? (
                  <button className="btn btn-primary" disabled>
                    Loading...
                  </button>
                ) : isAuthed ? (
                  <button
                    onClick={() => navigate('/dashboard')}
                    className="btn btn-primary"
                  >
                    Go to Dashboard <FaArrowRight />
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => navigate('/login')}
                      className="btn btn-primary"
                    >
                      Get Started <FaArrowRight />
                    </button>
                    <button
                      onClick={() => navigate('/signup')}
                      className="btn btn-secondary"
                    >
                      Create Account
                    </button>
                  </>
                )}
              </div>

            </div>

            <div className="hero-image">
              <div className="floating-card">
                <FaBuilding />
                <h3>Real-time Analysis</h3>
                <p>Instant damage detection</p>
              </div>
            </div>

          </div>
        </div>
      </section>

      <section className="features">
        <div className="container">
          <h2 className="section-title">Why Choose Our System?</h2>
          <div className="features-grid">
            <div className="feature-card">
              <div className="feature-icon"><FaRobot /></div>
              <h3>AI-Powered Detection</h3>
              <p>Advanced YOLO model detects 7 types of building damages with high precision</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon"><FaShieldAlt /></div>
              <h3>Safety First</h3>
              <p>Identify potential hazards before they become critical safety issues</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon"><FaChartLine /></div>
              <h3>Health Scoring</h3>
              <p>Get comprehensive building health analysis with detailed scoring</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon"><FaFilePdf /></div>
              <h3>PDF Reports</h3>
              <p>Download professional inspection reports with recommendations</p>
            </div>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="container">
          <p>© 2024 Smart Building Inspection System. Final Year Project.</p>
          <p>Accuracy: 89% mAP | 7 Damage Types | Real-time Processing</p>
        </div>
      </footer>
    </div>
  );
};

export default Landing;
