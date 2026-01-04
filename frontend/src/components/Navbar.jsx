import React, { useState, useRef } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { FaBuilding, FaUser, FaSignOutAlt, FaHome } from 'react-icons/fa';
import '../styles/Navbar.css';

import { auth } from "../firebase"; // adjust path if needed
import { signOut, updateProfile } from "firebase/auth"; // signOut is the Firebase logout method [web:47]

const Navbar = ({ user, onLogout, onUserUpdate }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [openMenu, setOpenMenu] = useState(false);
  const [openSettings, setOpenSettings] = useState(false);
  const hoverTimeoutRef = useRef(null);

  if (location.pathname === '/') return null;

  const handleLogout = async () => {
    try {
      await signOut(auth); // Firebase sign out [web:47]
    } catch (e) {
      console.error("Firebase signOut error:", e);
    }

    localStorage.removeItem('token'); // optional cleanup
    localStorage.removeItem('buildingInspectionUser');

    if (onLogout) onLogout();
    navigate('/');
  };

  return (
    <>
      <nav className="navbar">
        <div className="navbar-content">
          <Link to="/dashboard" className="navbar-brand">
            <FaBuilding className="navbar-logo" />
            <div>
              <h1>Smart Building Inspector</h1>
              <p>AI-Powered Damage Detection</p>
            </div>
          </Link>

          <div className="navbar-menu">
            <Link
              to="/dashboard"
              className={`nav-link ${location.pathname === '/dashboard' ? 'active' : ''}`}
            >
              <FaHome /> Dashboard
            </Link>

            {user && (
              <div
                className="user-menu-wrapper"
                onMouseEnter={() => {
                  if (hoverTimeoutRef.current) {
                    clearTimeout(hoverTimeoutRef.current);
                    hoverTimeoutRef.current = null;
                  }
                  setOpenMenu(true);
                }}
                onMouseLeave={() => {
                  hoverTimeoutRef.current = setTimeout(() => {
                    setOpenMenu(false);
                  }, 400);
                }}
              >
                <button className="user-info-btn" type="button">
                  <div className="user-avatar">
                    <FaUser />
                  </div>
                  <div className="user-text">
                    <strong>{user.name || "User"}</strong>
                    <small>{user.email || ""}</small>
                  </div>
                </button>

                {openMenu && (
                  <div className="user-dropdown">
                    <div className="user-dropdown-header">
                      <div className="user-avatar large">
                        <FaUser />
                      </div>
                      <div>
                        <div className="user-name">{user.name || "User"}</div>
                        <div className="user-email">{user.email || ""}</div>
                      </div>
                    </div>

                    <button
                      className="dropdown-item"
                      type="button"
                      onClick={() => setOpenSettings(true)}
                    >
                      Profile &amp; Settings
                    </button>

                    <button
                      className="dropdown-item logout"
                      type="button"
                      onClick={handleLogout}
                    >
                      <FaSignOutAlt /> Logout
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </nav>

      {openSettings && (
        <ProfileSettingsModal
          user={user}
          onClose={() => setOpenSettings(false)}
          onUserUpdate={onUserUpdate}
        />
      )}
    </>
  );
};

const ProfileSettingsModal = ({ user, onClose, onUserUpdate }) => {
  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');

    try {
      // Must be logged in with Firebase
      const fbUser = auth.currentUser;
      if (!fbUser) {
        setMessage('You are not logged in.');
        return;
      }

      // (A) Update Firebase Auth displayName (real auth profile)
      if (name?.trim() && fbUser.displayName !== name.trim()) {
        await updateProfile(fbUser, { displayName: name.trim() }); // updateProfile supported for displayName [web:227]
      }

      // (B) Update your backend profile record (optional)
      // Send a valid Firebase ID token to your Flask backend (verified server-side). [web:27]
      const idToken = await fbUser.getIdToken();

      // at top of file or inside modal:
const API_BASE = "https://smartbuild-2jzu.onrender.com";

// ...

const res = await fetch(`${API_BASE}/api/profile`, {
  method: "PUT",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${idToken}`,
  },
  body: JSON.stringify({ name: name.trim(), email }),
});


      const data = await res.json();

      if (!res.ok) {
        setMessage(data.error || 'Failed to update profile');
        return;
      }

      setMessage('Profile updated successfully!');

      // Update UI user state
      const updatedUser = {
        ...data.user,
        name: name.trim(),
        email: email
      };

      if (onUserUpdate) onUserUpdate(updatedUser);
      localStorage.setItem('buildingInspectionUser', JSON.stringify(updatedUser));

      setTimeout(onClose, 1000);
    } catch (err) {
      console.error('Profile update error:', err);
      setMessage('Something went wrong. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="profile-modal-backdrop">
      <div className="profile-modal">
        <h2>Profile &amp; Settings</h2>
        <form onSubmit={handleSave} className="profile-form">
          <label>
            Full Name
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              required
            />
          </label>

          <label>
            Email Address
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </label>

          {message && <div className="profile-message">{message}</div>}

          <div className="profile-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Navbar;
