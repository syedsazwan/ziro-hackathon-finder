import React from 'react';
import type { StudentProfile, EligibilityStatus } from '../types';

interface EligibilitySummaryWidgetProps {
  profile: StudentProfile;
  totalEvents: number;
  eligibleCount: number;
  verifyCount: number;
  notEligibleCount: number;
  activeFilterTab: 'All' | EligibilityStatus;
  onFilterTabChange: (tab: 'All' | EligibilityStatus) => void;
  onOpenProfile: () => void;
}

export const EligibilitySummaryWidget: React.FC<EligibilitySummaryWidgetProps> = ({
  profile,
  totalEvents,
  eligibleCount,
  verifyCount,
  notEligibleCount,
  activeFilterTab,
  onFilterTabChange,
  onOpenProfile,
}) => {
  return (
    <div className="eligibility-summary-panel" id="eligibility-summary-panel">
      <div className="panel-badge-top">
        <span className="panel-kicker">STUDENT CRITERIA & ELIGIBILITY</span>
        <button
          type="button"
          id="summary-edit-profile-btn"
          className="panel-edit-link"
          onClick={onOpenProfile}
          title="Modify student preferences and constraints"
        >
          Edit Criteria ➔
        </button>
      </div>

      <h3 className="panel-heading">Active Match Profile</h3>

      {/* Criteria Grid */}
      <div className="criteria-mini-grid">
        <div className="mini-criterion">
          <span className="criterion-label">Team Size</span>
          <span className="criterion-value">
            👥 {profile.teamSize} {profile.teamSize === 1 ? 'Solo' : 'Members'}
          </span>
        </div>

        <div className="mini-criterion">
          <span className="criterion-label">Region</span>
          <span className="criterion-value">
            📍 {profile.region === 'All' ? 'Global / All' : profile.region}
          </span>
        </div>

        <div className="mini-criterion">
          <span className="criterion-label">Max Budget</span>
          <span className="criterion-value">
            💵 {profile.budget !== '' ? `$${profile.budget} USD` : 'Free / Any'}
          </span>
        </div>

        <div className="mini-criterion">
          <span className="criterion-label">Target Skills</span>
          <span className="criterion-value truncate-skills" title={profile.skills.join(', ')}>
            ⚡ {profile.skills.length > 0 ? profile.skills.slice(0, 3).join(', ') : 'Any'}
            {profile.skills.length > 3 ? ` +${profile.skills.length - 3}` : ''}
          </span>
        </div>
      </div>

      {/* Match Breakdown Pills */}
      <div className="summary-breakdown-row" role="tablist" aria-label="Quick eligibility filters">
        <button
          type="button"
          id="summary-tab-all"
          className={`summary-pill ${activeFilterTab === 'All' ? 'active' : ''}`}
          onClick={() => onFilterTabChange('All')}
        >
          <span className="pill-dot pill-dot-all" aria-hidden="true" />
          <span>All ({totalEvents})</span>
        </button>

        <button
          type="button"
          id="summary-tab-eligible"
          className={`summary-pill pill-eligible ${activeFilterTab === 'Eligible' ? 'active' : ''}`}
          onClick={() => onFilterTabChange('Eligible')}
        >
          <span className="pill-dot pill-dot-eligible" aria-hidden="true" />
          <span>Eligible ({eligibleCount})</span>
        </button>

        <button
          type="button"
          id="summary-tab-verify"
          className={`summary-pill pill-verify ${activeFilterTab === 'Needs verification' ? 'active' : ''}`}
          onClick={() => onFilterTabChange('Needs verification')}
        >
          <span className="pill-dot pill-dot-verify" aria-hidden="true" />
          <span>Verify ({verifyCount})</span>
        </button>

        <button
          type="button"
          id="summary-tab-ineligible"
          className={`summary-pill pill-ineligible ${activeFilterTab === 'Not eligible' ? 'active' : ''}`}
          onClick={() => onFilterTabChange('Not eligible')}
        >
          <span className="pill-dot pill-dot-ineligible" aria-hidden="true" />
          <span>Ineligible ({notEligibleCount})</span>
        </button>
      </div>
    </div>
  );
};
