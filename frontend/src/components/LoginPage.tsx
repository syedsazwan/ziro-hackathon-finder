import React, { useState } from 'react';
import { ZiroLogo, GoogleIcon } from './Icons';
import { fetchGoogleAuthUrl } from '../api';

interface LoginPageProps {
  onSuccess?: () => void;
  returnTo?: string;
}

export const LoginPage: React.FC<LoginPageProps> = ({ returnTo }) => {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    const params = new URLSearchParams(window.location.search);
    const err = params.get('error');
    const errDesc = params.get('error_description');

    if (err) {
      if (err === 'access_denied') {
        return 'Google authentication was cancelled or access was denied. Please try again.';
      } else if (err === 'invalid_state') {
        return 'Authentication session expired or security state check failed. Please retry.';
      } else if (err === 'missing_callback_params') {
        return 'Invalid authentication response from Google. Please retry.';
      } else {
        return decodeURIComponent(errDesc || err);
      }
    }
    return null;
  });

  const handleGoogleSignIn = async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);

      // Determine return destination
      const destination = returnTo || window.location.pathname !== '/login' ? returnTo || window.location.pathname : '/events';
      const authData = await fetchGoogleAuthUrl(destination);

      if (authData?.url) {
        // Redirect to Google's official authorization endpoint
        window.location.href = authData.url;
      } else {
        throw new Error('Google authorization URL was not received from the server.');
      }
    } catch (err: unknown) {
      setIsLoading(false);
      const msg = err instanceof Error ? err.message : 'Failed to connect to Google authentication service.';
      setErrorMessage(msg);
    }
  };

  return (
    <div className="ziro-login-container" id="ziro-login-page">
      {/* LEFT PANEL: Ziro Brand & Storytelling */}
      <div className="login-story-panel" aria-label="Ziro Platform Story">
        {/* Subtle Constellation Background Graphic */}
        <div className="constellation-bg" aria-hidden="true">
          <svg className="constellation-svg" viewBox="0 0 800 800" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <radialGradient id="glowPurple" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#818cf8" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#4338ca" stopOpacity="0" />
              </radialGradient>
            </defs>
            <circle cx="200" cy="180" r="140" fill="url(#glowPurple)" />
            <circle cx="620" cy="540" r="180" fill="url(#glowPurple)" />
            
            {/* Connected node network */}
            <path
              d="M 120 180 L 240 120 L 380 200 L 460 140 L 620 220 L 520 340 L 380 300 L 280 420 L 140 380 Z"
              stroke="rgba(165, 180, 252, 0.18)"
              strokeWidth="1.5"
              strokeDasharray="4 4"
            />
            <path
              d="M 280 420 L 420 520 L 560 480 L 680 580 L 540 660 L 360 620 L 220 560 Z"
              stroke="rgba(196, 181, 253, 0.14)"
              strokeWidth="1.5"
            />

            {/* Glowing nodes */}
            <circle cx="120" cy="180" r="3.5" fill="#a5b4fc" />
            <circle cx="240" cy="120" r="4.5" fill="#818cf8" />
            <circle cx="380" cy="200" r="4" fill="#c084fc" />
            <circle cx="460" cy="140" r="3" fill="#a5b4fc" />
            <circle cx="620" cy="220" r="5" fill="#818cf8" />
            <circle cx="520" cy="340" r="3.5" fill="#c084fc" />
            <circle cx="380" cy="300" r="4" fill="#a5b4fc" />
            <circle cx="280" cy="420" r="5" fill="#818cf8" />
            <circle cx="420" cy="520" r="4" fill="#c084fc" />
            <circle cx="560" cy="480" r="4.5" fill="#818cf8" />
            <circle cx="680" cy="580" r="4" fill="#a5b4fc" />
          </svg>
        </div>

        <div className="login-story-content">
          {/* Brand Header */}
          <div className="login-brand-header">
            <ZiroLogo size={42} className="login-brand-logo" />
            <div className="login-brand-titles">
              <span className="login-brand-name">Ziro</span>
              <span className="login-brand-subtitle">Hackathon & Contest Finder</span>
            </div>
          </div>

          {/* Headline & Mission */}
          <div className="login-hero-text">
            <h1 className="login-headline">
              Your next big idea <span className="headline-gradient">starts here.</span>
            </h1>
            <p className="login-subtext">
              Discover hackathons, find your team, and turn your skills into real-world opportunities.
            </p>
          </div>

          {/* 3 Core Product Benefits */}
          <div className="login-benefits-list">
            <div className="benefit-item">
              <div className="benefit-icon-badge">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
                  <path d="M2 12h20" />
                </svg>
              </div>
              <div className="benefit-text">
                <div className="benefit-title">Global hackathons</div>
                <div className="benefit-desc">
                  Curated, verified competitions from Devpost, Unstop, MLH, and leading universities.
                </div>
              </div>
            </div>

            <div className="benefit-item">
              <div className="benefit-icon-badge">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
              </div>
              <div className="benefit-text">
                <div className="benefit-title">Smart deadline alerts</div>
                <div className="benefit-desc">
                  Never miss registration cutoffs with automated 7-day, 48-hour, and 24-hour IST reminders.
                </div>
              </div>
            </div>

            <div className="benefit-item">
              <div className="benefit-icon-badge">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <circle cx="12" cy="12" r="6" />
                  <circle cx="12" cy="12" r="2" />
                </svg>
              </div>
              <div className="benefit-text">
                <div className="benefit-title">Skill-based matches</div>
                <div className="benefit-desc">
                  Instant eligibility calculation tailored to your exact tech stack and team preferences.
                </div>
              </div>
            </div>
          </div>

          <div className="login-story-footer">
            <span className="story-pill">Built for ambitious developers</span>
            <span className="story-pill">Strict identity verification</span>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL: Centered Authentication Card */}
      <div className="login-auth-panel">
        <div className="login-auth-card" role="region" aria-label="Sign in to Ziro">
          {/* Mobile-only logo */}
          <div className="mobile-brand-mark">
            <ZiroLogo size={36} />
            <div className="mobile-brand-text">
              <span className="brand-name">Ziro</span>
              <span className="brand-sub">Hackathon Finder</span>
            </div>
          </div>

          <div className="auth-card-header">
            <h2 className="auth-card-title">Welcome to Ziro</h2>
            <p className="auth-card-subtitle">Sign in to discover your next opportunity.</p>
          </div>

          {/* Accessible Error State Banner */}
          {errorMessage && (
            <div className="auth-error-banner" role="alert" aria-live="polite">
              <div className="error-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <div className="error-content">
                <div className="error-title">Authentication Note</div>
                <div className="error-text">{errorMessage}</div>
              </div>
              <button
                type="button"
                className="error-dismiss-btn"
                onClick={() => setErrorMessage(null)}
                aria-label="Dismiss error message"
              >
                ×
              </button>
            </div>
          )}

          {/* Google OAuth Action Button */}
          <div className="auth-action-box">
            <button
              type="button"
              id="google-signin-btn"
              className={`google-signin-button ${isLoading ? 'loading' : ''}`}
              onClick={handleGoogleSignIn}
              disabled={isLoading}
              aria-label="Continue with Google"
            >
              {isLoading ? (
                <div className="google-btn-loading">
                  <span className="auth-spinner" aria-hidden="true"></span>
                  <span>Connecting to Google...</span>
                </div>
              ) : (
                <div className="google-btn-content">
                  <GoogleIcon size={20} className="google-btn-icon" />
                  <span className="google-btn-text">Continue with Google</span>
                </div>
              )}
            </button>
          </div>

          {/* Terms & Privacy */}
          <div className="auth-card-footer">
            <p className="legal-notice">
              By continuing, you agree to Ziro's hackathon discovery guidelines and privacy terms.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
