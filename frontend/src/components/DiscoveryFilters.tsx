import React from 'react';

export type SortOption =
  | 'deadline-asc'
  | 'deadline-desc'
  | 'event-date-asc'
  | 'relevance'
  | 'team-min'
  | 'team-max'
  | 'title-asc';

export type SyntheticFilter = 'all' | 'real-only' | 'synthetic-only';

interface DiscoveryFiltersProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  sourceFilter: string;
  onSourceChange: (source: string) => void;
  syntheticFilter?: SyntheticFilter;
  onSyntheticFilterChange?: (f: SyntheticFilter) => void;
  countryFilter: string;
  onCountryChange: (c: string) => void;
  availableCountries: string[];
  availableRegions?: string[];
  formatFilter: string;
  onFormatChange: (fmt: string) => void;
  deadlineFilter?: string;
  onDeadlineFilterChange?: (df: string) => void;
  statusFilter: string;
  onStatusChange: (s: string) => void;
  sortBy: SortOption;
  onSortChange: (sort: SortOption) => void;
  totalFiltered: number;
  totalEvents: number;
  onResetFilters: () => void;
  onTriggerLiveSearch?: () => void;
  isSearchingLive?: boolean;
}

export const DiscoveryFilters: React.FC<DiscoveryFiltersProps> = ({
  searchQuery,
  onSearchChange,
  sourceFilter,
  onSourceChange,
  countryFilter,
  onCountryChange,
  availableCountries,
  availableRegions = [],
  formatFilter,
  onFormatChange,
  deadlineFilter = 'all',
  onDeadlineFilterChange,
  statusFilter,
  onStatusChange,
  sortBy,
  onSortChange,
  totalFiltered,
  totalEvents,
  onResetFilters,
  onTriggerLiveSearch,
  isSearchingLive = false,
}) => {
  const isAnyFilterActive =
    searchQuery.trim() !== '' ||
    sourceFilter !== 'All' ||
    countryFilter !== 'All' ||
    formatFilter !== 'All' ||
    statusFilter !== 'upcoming' ||
    deadlineFilter !== 'all';

  return (
    <div className="discovery-filters-bar" id="discovery-filters-bar">
      {/* Search Bar with live search trigger */}
      <div className="search-box-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div style={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'center' }}>
          <span className="search-icon" aria-hidden="true" style={{ position: 'absolute', left: '0.75rem' }}>🔍</span>
          <input
            id="event-search-input"
            type="search"
            className="search-input"
            style={{ width: '100%', paddingLeft: '2.25rem', paddingRight: searchQuery ? '2rem' : '0.75rem' }}
            placeholder="Search internet for hackathons (e.g. AI, Python, Web3, In-Person)..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                onTriggerLiveSearch?.();
              }
            }}
            aria-label="Search hackathons and contests"
          />
          {searchQuery && (
            <button
              type="button"
              className="clear-search-btn"
              id="clear-search-query-btn"
              onClick={() => onSearchChange('')}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>
        {onTriggerLiveSearch && (
          <button
            type="button"
            id="live-search-submit-btn"
            className="btn-card-primary"
            onClick={onTriggerLiveSearch}
            disabled={isSearchingLive}
            style={{ whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', padding: '0.55rem 1rem' }}
            title="Query public internet sources (Devfolio, MLH, Devpost) with selected filters"
          >
            {isSearchingLive ? (
              <>
                <span className="spinner-sm" aria-hidden="true" />
                <span>Searching Web...</span>
              </>
            ) : (
              <>
                <span aria-hidden="true">🌐</span>
                <span>Search Web</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* Filter Controls Row */}
      <div className="filter-controls-group">
        {/* Source Dropdown */}
        <div className="filter-control-item">
          <label htmlFor="source-filter-select" className="filter-label">
            Source
          </label>
          <select
            id="source-filter-select"
            className="filter-select"
            value={sourceFilter}
            onChange={(e) => onSourceChange(e.target.value)}
          >
            <option value="All">All Sources</option>
            <option value="Devfolio">Devfolio (Official API)</option>
            <option value="Devpost">Devpost (Official Public API)</option>
            <option value="MLH">Major League Hacking (Official Schedule)</option>
            <option value="Unstop">Unstop (Public Opportunities)</option>
          </select>
        </div>

        {/* Country / Region Filter */}
        <div className="filter-control-item">
          <label htmlFor="country-filter-select" className="filter-label">
            Country / Region
          </label>
          <select
            id="country-filter-select"
            className="filter-select"
            value={countryFilter}
            onChange={(e) => onCountryChange(e.target.value)}
          >
            <option value="All">All Countries / Regions</option>
            {availableCountries.length > 0 && (
              <optgroup label="Countries">
                {availableCountries.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </optgroup>
            )}
            {availableRegions.length > 0 && (
              <optgroup label="Regions / Online">
                {availableRegions.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </div>

        {/* Format Filter */}
        <div className="filter-control-item">
          <label htmlFor="format-filter-select" className="filter-label">
            Format
          </label>
          <select
            id="format-filter-select"
            className="filter-select"
            value={formatFilter}
            onChange={(e) => onFormatChange(e.target.value)}
          >
            <option value="All">All Formats</option>
            <option value="Online / Virtual">Online / Virtual</option>
            <option value="In-Person">In-Person</option>
            <option value="Hybrid">Hybrid</option>
          </select>
        </div>

        {/* Event Status Filter */}
        <div className="filter-control-item">
          <label htmlFor="status-filter-select" className="filter-label">
            Event Status
          </label>
          <select
            id="status-filter-select"
            className="filter-select"
            value={statusFilter}
            onChange={(e) => onStatusChange(e.target.value)}
          >
            <option value="upcoming">🟢 Upcoming & Open (Default)</option>
            <option value="closed">🏁 Ended / Closed Contests</option>
            <option value="all">📋 All Contests (Active + Ended)</option>
          </select>
        </div>

        {/* Deadline Urgency Filter */}
        {onDeadlineFilterChange && (
          <div className="filter-control-item">
            <label htmlFor="deadline-filter-select" className="filter-label">
              Deadline Urgency
            </label>
            <select
              id="deadline-filter-select"
              className="filter-select"
              value={deadlineFilter}
              onChange={(e) => onDeadlineFilterChange(e.target.value)}
            >
              <option value="all">All Deadlines</option>
              <option value="Due Today">Due Today</option>
              <option value="Due Tomorrow">Due Tomorrow</option>
              <option value="Due in the Next 7 Days">Due in Next 7 Days</option>
              <option value="Later">Later</option>
              <option value="Needs Verification">Needs Verification / Unavailable</option>
              <option value="Deadline Passed">Deadline Passed</option>
            </select>
          </div>
        )}

        {/* Sort Dropdown */}
        <div className="filter-control-item">
          <label htmlFor="sort-by-select" className="filter-label">
            Sort By
          </label>
          <select
            id="sort-by-select"
            className="filter-select"
            value={sortBy}
            onChange={(e) => onSortChange(e.target.value as SortOption)}
          >
            <option value="relevance">⭐ Best Match (My Skills & Criteria)</option>
            <option value="deadline-asc">⏱️ Deadline (Soonest First)</option>
            <option value="deadline-desc">⏱️ Deadline (Furthest First)</option>
            <option value="event-date-asc">📅 Event Date (Soonest First)</option>
            <option value="team-min">👥 Team Size (Smallest first)</option>
            <option value="team-max">👥 Team Size (Largest first)</option>
            <option value="title-asc">🔤 Title (A – Z)</option>
          </select>
        </div>
      </div>

      {/* Filter summary status line */}
      {isAnyFilterActive && (
        <div className="filter-active-summary" id="filter-active-summary">
          <span>
            Active filters matched <strong>{totalFiltered}</strong> of {totalEvents} contests
          </span>
          <button
            type="button"
            id="reset-discovery-filters-btn"
            className="filter-reset-link"
            onClick={onResetFilters}
          >
            Clear All Active Filters
          </button>
        </div>
      )}
    </div>
  );
};
