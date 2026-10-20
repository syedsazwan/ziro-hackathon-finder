import React, { useState } from 'react';
import type { StudentProfile } from '../types';

interface MyCriteriaViewProps {
  criteria: StudentProfile;
  onSaveCriteria: (updated: StudentProfile) => void;
  onFindMatchingEvents: (updated: StudentProfile) => void;
  isLoading?: boolean;
}

const COMMON_SKILLS = [
  'Python',
  'AI/ML',
  'React',
  'TypeScript',
  'Cloud',
  'Web3',
  'Algorithms',
  'FastAPI',
  'PyTorch',
  'Docker',
];

const REGIONS = [
  'All',
  'India',
  'Asia',
  'North America',
  'Europe',
  'Global / Remote',
];

const MODES = [
  'All Modes',
  'Online / Virtual',
  'In-Person / Offline',
  'Hybrid',
];

const CRITERIA_SAVED_KEY = 'ziro_criteria_user_saved_v1';

// Determine initial skills: strictly empty for new users with no saved criteria, preserved if saved
const initializeSkills = (criteriaSkills: string[] | undefined): string[] => {
  const hasSaved = typeof window !== 'undefined' && localStorage.getItem(CRITERIA_SAVED_KEY) === 'true';
  if (!hasSaved) {
    return [];
  }
  return Array.isArray(criteriaSkills) ? criteriaSkills : [];
};

export const MyCriteriaView: React.FC<MyCriteriaViewProps> = ({
  criteria,
  onSaveCriteria,
  onFindMatchingEvents,
  isLoading = false,
}) => {
  const [formData, setFormData] = useState<StudentProfile>(() => ({
    ...criteria,
    skills: initializeSkills(criteria.skills),
  }));

  // Direct number entry state for Preferred Team Size
  const [teamSizeInput, setTeamSizeInput] = useState<string>(() =>
    criteria.teamSize ? String(criteria.teamSize) : '2'
  );
  const [teamSizeError, setTeamSizeError] = useState<string | null>(null);

  const [skillInput, setSkillInput] = useState<string>('');
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState<boolean>(false);

  // Skills management
  const addSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (trimmed && !formData.skills.includes(trimmed)) {
      setFormData((prev) => ({
        ...prev,
        skills: [...prev.skills, trimmed],
      }));
    }
  };

  const removeSkill = (skillToRemove: string) => {
    setFormData((prev) => ({
      ...prev,
      skills: prev.skills.filter((s) => s !== skillToRemove),
    }));
  };

  const handleSkillKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addSkill(skillInput);
      setSkillInput('');
    }
  };

  // Direct number entry for team size
  const handleTeamSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setTeamSizeInput(val);

    if (val.trim() === '') {
      // Allow user to clear input freely; do not silently replace with default
      setTeamSizeError('Please enter a team size between 1 and 20.');
      return;
    }

    // Only accept positive whole numbers
    if (!/^\d+$/.test(val.trim())) {
      setTeamSizeError('Team size must be a positive whole number.');
      return;
    }

    const parsed = parseInt(val.trim(), 10);
    if (parsed < 1 || parsed > 20) {
      setTeamSizeError('Team size must be between 1 and 20 members.');
      return;
    }

    // Valid positive whole number within 1-20
    setTeamSizeError(null);
    setFormData((prev) => ({
      ...prev,
      teamSize: parsed,
    }));
  };

  // Validate form state before saving or matching
  const validateAndPrepare = (): StudentProfile | null => {
    const trimmed = teamSizeInput.trim();
    if (!trimmed) {
      setTeamSizeError('Please enter a team size between 1 and 20.');
      document.getElementById('team-size-input')?.focus();
      return null;
    }

    if (!/^\d+$/.test(trimmed)) {
      setTeamSizeError('Team size must be a positive whole number.');
      document.getElementById('team-size-input')?.focus();
      return null;
    }

    const parsed = parseInt(trimmed, 10);
    if (parsed < 1 || parsed > 20) {
      setTeamSizeError('Team size must be between 1 and 20 members.');
      document.getElementById('team-size-input')?.focus();
      return null;
    }

    const updatedProfile: StudentProfile = {
      ...formData,
      teamSize: parsed,
    };

    localStorage.setItem(CRITERIA_SAVED_KEY, 'true');
    return updatedProfile;
  };

  const handleSaveOnly = (e: React.FormEvent) => {
    e.preventDefault();
    const valid = validateAndPrepare();
    if (!valid) return;

    onSaveCriteria(valid);
    setFeedbackMsg('Matching criteria saved successfully.');
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  const handleFindContests = () => {
    const valid = validateAndPrepare();
    if (!valid) return;

    onSaveCriteria(valid);
    onFindMatchingEvents(valid);
  };

  const handleConfirmReset = () => {
    const defaults: StudentProfile = {
      skills: [],
      teamSize: 2,
      region: 'All',
      startDate: '',
      endDate: '',
      budget: '',
      participationMode: 'All Modes',
    };
    setFormData(defaults);
    setTeamSizeInput('2');
    setTeamSizeError(null);
    onSaveCriteria(defaults);
    localStorage.setItem(CRITERIA_SAVED_KEY, 'true');
    setShowResetConfirm(false);
    setFeedbackMsg('Criteria reset. Skills list is now empty.');
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  return (
    <div className="criteria-view-layout" id="my-criteria-view">
      {/* Feedback Banner */}
      {feedbackMsg && (
        <div className="modal-banner banner-success" role="status" id="criteria-feedback-banner">
          <span className="banner-icon" aria-hidden="true">✓</span>
          <div>{feedbackMsg}</div>
        </div>
      )}

      {/* Reset Confirmation Dialog */}
      {showResetConfirm && (
        <div
          style={{
            background: 'var(--color-warning-bg, #FFFBEB)',
            border: '1px solid var(--color-warning-border, #FDE68A)',
            borderRadius: 'var(--radius-md, 10px)',
            padding: '1rem 1.25rem',
            marginBottom: '1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.75rem',
          }}
          role="alert"
        >
          <div style={{ color: 'var(--color-warning-text, #92400E)', fontSize: '0.85rem' }}>
            <strong>Reset Criteria?</strong> This will clear selected skills, reset team size to 2, and clear date/budget filters.
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn-secondary"
              style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}
              onClick={() => setShowResetConfirm(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-danger"
              style={{ padding: '0.4rem 1rem', fontSize: '0.8rem' }}
              onClick={handleConfirmReset}
            >
              Confirm Reset
            </button>
          </div>
        </div>
      )}

      <div className="criteria-content-grid">
        {/* Rebalanced Criteria Configuration Form */}
        <form className="criteria-form-card" onSubmit={handleSaveOnly} noValidate>
          <div className="section-card-header">
            <h2 className="section-title">Contest Eligibility Constraints</h2>
            <p className="section-desc">
              Define the requirements applied when discovering and evaluating hackathons.
            </p>
          </div>

          {/* 1. Matching Skills */}
          <div className="form-group" style={{ marginTop: '1.25rem' }}>
            <label htmlFor="criteria-skill-input" className="form-label">
              Technical Skills for Event Matching
            </label>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0 0 0.4rem 0' }}>
              Contests with matching tags or categories will receive positive eligibility scores.
            </p>
            <input
              id="criteria-skill-input"
              type="text"
              className="form-input"
              placeholder="Add skill (e.g. PyTorch, React, Web3) and press Enter..."
              value={skillInput}
              onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={handleSkillKeyDown}
            />

            <div className="quick-pills">
              {COMMON_SKILLS.map((skill) => {
                const active = formData.skills.includes(skill);
                return (
                  <button
                    key={skill}
                    type="button"
                    className={`quick-pill ${active ? 'active' : ''}`}
                    onClick={() => (active ? removeSkill(skill) : addSkill(skill))}
                  >
                    {active ? `✓ ${skill}` : `+ ${skill}`}
                  </button>
                );
              })}
            </div>

            {formData.skills.length > 0 && (
              <div className="skill-tags">
                {formData.skills.map((skill) => (
                  <span key={skill} className="skill-tag">
                    {skill}
                    <button
                      type="button"
                      className="skill-tag-remove"
                      onClick={() => removeSkill(skill)}
                      aria-label={`Remove ${skill}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* 2. Team Size & Region */}
          <div className="profile-fields-grid" style={{ marginTop: '1.25rem' }}>
            <div className="form-group">
              <label htmlFor="team-size-input" className="form-label">
                Preferred Team Size
                {teamSizeInput.trim() && !teamSizeError
                  ? `: ${teamSizeInput} member${parseInt(teamSizeInput, 10) > 1 ? 's' : ''}`
                  : ''}
              </label>
              <p style={{ fontSize: '0.775rem', color: 'var(--text-secondary)', margin: '0 0 0.35rem 0' }}>
                Evaluated against event [team_min, team_max]. Enter 1 to 20 members.
              </p>
              <input
                id="team-size-input"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                className={`form-input no-spinner ${teamSizeError ? 'input-error' : ''}`}
                placeholder="e.g. 2"
                value={teamSizeInput}
                onChange={handleTeamSizeChange}
                aria-invalid={Boolean(teamSizeError)}
                aria-describedby={teamSizeError ? 'team-size-error' : undefined}
              />
              {teamSizeError && (
                <div className="field-error-message" id="team-size-error" role="alert">
                  <span aria-hidden="true">⚠️</span> {teamSizeError}
                </div>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="region-select" className="form-label">
                Preferred Region
              </label>
              <p style={{ fontSize: '0.775rem', color: 'var(--text-secondary)', margin: '0 0 0.35rem 0' }}>
                Filter hackathons restricted to specific geographical regions.
              </p>
              <select
                id="region-select"
                className="form-select"
                value={formData.region}
                onChange={(e) => setFormData({ ...formData, region: e.target.value })}
              >
                {REGIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 3. Participation Mode & Budget */}
          <div className="profile-fields-grid" style={{ marginTop: '0.5rem' }}>
            <div className="form-group">
              <label htmlFor="mode-select" className="form-label">
                Participation Mode
              </label>
              <p style={{ fontSize: '0.775rem', color: 'var(--text-secondary)', margin: '0 0 0.35rem 0' }}>
                Select virtual, on-site, or hybrid event formats.
              </p>
              <select
                id="mode-select"
                className="form-select"
                value={formData.participationMode || 'All Modes'}
                onChange={(e) =>
                  setFormData({ ...formData, participationMode: e.target.value })
                }
              >
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="budget-input" className="form-label">
                Maximum Entry Fee Budget ($)
              </label>
              <p style={{ fontSize: '0.775rem', color: 'var(--text-secondary)', margin: '0 0 0.35rem 0' }}>
                Leave empty for all events, or set 0 for strictly free contests.
              </p>
              <input
                id="budget-input"
                type="number"
                min={0}
                step="any"
                className="form-input"
                placeholder="e.g. 0 (Free only) or 25"
                value={formData.budget}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    budget: e.target.value === '' ? '' : parseFloat(e.target.value),
                  })
                }
              />
            </div>
          </div>

          {/* 4. Availability Window */}
          <div className="form-group" style={{ marginTop: '0.5rem' }}>
            <label className="form-label">Availability Window (Optional)</label>
            <p style={{ fontSize: '0.775rem', color: 'var(--text-secondary)', margin: '0 0 0.35rem 0' }}>
              Only contests taking place within this date range will be considered eligible.
            </p>
            <div className="date-grid">
              <div>
                <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>Start Date</span>
                <input
                  type="date"
                  className="form-input"
                  value={formData.startDate}
                  onChange={(e) => setFormData({ ...formData, startDate: e.target.value })}
                />
              </div>
              <div>
                <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>End Date</span>
                <input
                  type="date"
                  className="form-input"
                  value={formData.endDate}
                  onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                />
              </div>
            </div>
          </div>

          {/* Action Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
              marginTop: '1.75rem',
              paddingTop: '1.25rem',
              borderTop: '1px solid var(--border-color, #E3E8F0)',
            }}
          >
            <button
              type="button"
              id="reset-criteria-btn"
              className="btn-secondary"
              style={{ fontSize: '0.825rem', padding: '0.55rem 1.15rem' }}
              onClick={() => setShowResetConfirm(true)}
            >
              Reset to Defaults
            </button>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                type="submit"
                id="save-criteria-btn"
                className="btn-card-secondary"
                style={{ fontSize: '0.85rem', padding: '0.6rem 1.25rem' }}
              >
                Save Criteria
              </button>
              <button
                type="button"
                id="find-matching-contests-btn"
                className="btn-primary"
                style={{ width: 'auto', padding: '0.6rem 1.75rem', fontSize: '0.85rem' }}
                onClick={handleFindContests}
                disabled={isLoading}
              >
                {isLoading ? 'Evaluating...' : 'Find & Verify Contests →'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
