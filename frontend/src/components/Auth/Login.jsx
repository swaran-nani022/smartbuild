import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FaBuilding, FaEnvelope, FaLock, FaSignInAlt, FaArrowLeft, FaCheckCircle } from 'react-icons/fa';
import '../../styles/Auth.css';

import { signInWithEmailAndPassword } from "firebase/auth";
import { auth } from "../../firebase"; // adjust path if needed

const Login = ({ onLogin }) => {
  const [formData, setFormData] = useState({
    email: 'swaran.nani022@gmail.com',
    password: '123456'
  });
  const [loading, setLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // 1) Firebase login (replaces POST /api/login)
      const cred = await signInWithEmailAndPassword(auth, formData.email, formData.password); // email+password auth
      const user = cred.user;

      // 2) Get Firebase ID token (this replaces your old JWT token)
      const idToken = await user.getIdToken(); // send this to Flask in Authorization header

      // Keep same key name so other API calls work with minimal changes
      localStorage.setItem("token", idToken);

      if (onLogin) {
        onLogin({
          id: user.uid,
          email: user.email,
          name: user.displayName || "",
          isAdmin: false
        });
      }

      setIsSuccess(true);
      setLoading(false);

      setTimeout(() => navigate('/dashboard'), 2500);
    } catch (error) {
      console.error('Login error:', error);
      alert(error.message || 'Login failed. Please try again.');
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        {!isSuccess && (
          <button onClick={() => navigate('/')} className="back-btn">
            <FaArrowLeft /> Back to Home
          </button>
        )}

        {isSuccess ? (
          <div className="success-message">
            <FaCheckCircle className="success-icon" />
            <h2 className="success-title">Logged In Successfully!</h2>
            <p className="success-text">Redirecting to Dashboard...</p>
          </div>
        ) : (
          <>
            <div className="auth-header">
              <FaBuilding className="auth-logo" />
              <h1>Welcome Back</h1>
              <p>Sign in to continue building inspection</p>
            </div>

            <form onSubmit={handleSubmit} className="auth-form">
              <div className="form-group">
                <label className="form-label">
                  <FaEnvelope /> Email Address
                </label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  className="form-control"
                  placeholder="Enter email"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  <FaLock /> Password
                </label>
                <input
                  type="password"
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  className="form-control"
                  placeholder="Enter your password"
                  required
                />
              </div>

              <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
                {loading ? (
                  <>
                    <div className="spinner" />
                    Checking...
                  </>
                ) : (
                  <>
                    <FaSignInAlt /> Sign In
                  </>
                )}
              </button>
            </form>

            <div className="auth-footer">
              <p>
                Don't have an account? <Link to="/signup">Sign up here</Link>
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default Login;
