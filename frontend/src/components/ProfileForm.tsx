import React, { useState } from 'react';
import type { StudentProfile } from '../types';

interface ProfileFormProps {
  profile: StudentProfile;
  onChange: (updated: StudentProfile) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

const COMMON_SKILLS = [
  'Python',
  'AI/ML',
  'React',
  'TypeScript',
  'Cloud',
  'Web3',
  'Algorithms',
  'FastApi',
];

export const ProfileForm: React.FC<ProfileFormProps> = ({
  profile,
  onChange,
  onSubmit,
  isLoading,
}) => {
  const [skillInput, setSkillInput] = useState('');

  const addSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (trimmed && !profile.skills.includes(trimmed)) {
      onChange({
        ...profile,
        skills: [...profile.skills, trimmed],
      });
    }
  };

  const removeSkill = (skillToRemove: string) => {
    onChange({
      ...profile,
      skills: profile.skills.filter((s) => s !== skillToRemove),
    });
  };

  const handleSkillKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addSkill(skillInput);
      setSkillInput('');
    }
  };

  const handleReset = () => {
    onChange({
      skills: [],
      teamSize: 2,
      region: 'All',
      startDate: '',
      endDate: '',
      budget: '',
    });
  };

  return (
    <div className="profile-panel" id="student-profile-panel">
      <div className="panel-header">
        <h2 className="panel-title">
          <span>🎯</span> Student Criteria
        </h2>
        <p className="panel-desc">
          Set team size, skills, budget, and dates to verify contest eligibility.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        id="profile-form"
      >
        {/* Skills */}
        <div className="form-group">
          <label htmlFor="skill-input-field" className="form-label">
            Skills & Interests
          </label>
          <input
            id="skill-input-field"
            type="text"
            className="form-input"
            placeholder="Type skill and press Enter (e.g. PyTorch)..."
            value={skillInput}
            onChange={(e) => setSkillInput(e.target.value)}
            onKeyDown={handleSkillKeyDown}
          />

          <div className="quick-pills">
            {COMMON_SKILLS.map((skill) => {
              const active = profile.skills.includes(skill);
              return (
                <button
                  key={skill}
                  type="button"
                  id={`skill-pill-${skill.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
                  className={`quick-pill ${active ? 'active' : ''}`}
                  onClick={() => (active ? removeSkill(skill) : addSkill(skill))}
                >
                  {active ? `✓ ${skill}` : `+ ${skill}`}
                </button>
              );
            })}
          </div>

          {profile.skills.length > 0 && (
            <div className="skill-tags">
              {profile.skills.map((skill) => (
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

        {/* Team Size */}
        <div className="form-group">
          <label htmlFor="team-size-input" className="form-label">
            Team Size ({profile.teamSize} {profile.teamSize === 1 ? 'member (Solo)' : 'members'})
          </label>
          <input
            id="team-size-input"
            type="number"
            min="1"
            max="10"
            className="form-input"
            value={profile.teamSize}
            onChange={(e) =>
              onChange({
                ...profile,
                teamSize: Math.max(1, parseInt(e.target.value, 10) || 1),
              })
            }
          />
        </div>

        {/* Preferred Region */}
        <div className="form-group">
          <label htmlFor="region-select" className="form-label">
            Preferred Region
          </label>
          <select
            id="region-select"
            className="form-select"
            value={profile.region}
            onChange={(e) =>
              onChange({
                ...profile,
                region: e.target.value,
              })
            }
          >
            <option value="All">All / Global / Remote</option>
            <option value="Global">Global / Online</option>
            <option value="India">India</option>
            <option value="North America">North America</option>
            <option value="Europe">Europe / Remote</option>
          </select>
        </div>

        {/* Availability Dates */}
        <div className="form-group">
          <label className="form-label">Availability Window</label>
          <div className="date-grid">
            <div>
              <input
                id="start-date-input"
                type="date"
                className="form-input"
                aria-label="Start date"
                value={profile.startDate}
                onChange={(e) =>
                  onChange({
                    ...profile,
                    startDate: e.target.value,
                  })
                }
              />
            </div>
            <div>
              <input
                id="end-date-input"
                type="date"
                className="form-input"
                aria-label="End date"
                value={profile.endDate}
                onChange={(e) =>
                  onChange({
                    ...profile,
                    endDate: e.target.value,
                  })
                }
              />
            </div>
          </div>
        </div>

        {/* Budget */}
        <div className="form-group">
          <label htmlFor="budget-input" className="form-label">
            Max Entry Fee Budget ($ USD)
          </label>
          <input
            id="budget-input"
            type="number"
            min="0"
            step="5"
            placeholder="e.g. 0 for Free only, or leave blank"
            className="form-input"
            value={profile.budget}
            onChange={(e) => {
              const val = e.target.value;
              onChange({
                ...profile,
                budget: val === '' ? '' : Math.max(0, parseFloat(val) || 0),
              });
            }}
          />
        </div>

        <button
          type="submit"
          id="find-matches-btn"
          className="btn-primary"
          disabled={isLoading}
        >
          {isLoading ? 'Checking Eligibility...' : 'Find & Verify Contests'}
        </button>

        <button
          type="button"
          id="reset-form-btn"
          className="btn-secondary"
          onClick={handleReset}
        >
          Reset to Sample Profile
        </button>
      </form>
    </div>
  );
};
