import React, { useState, useEffect, useMemo } from 'react';
import type { BackendStudentProfile, StudentProject } from '../types';
import { fetchStudentProfile, saveStudentProfile } from '../api';

interface MyProfileViewProps {
  onProfileUpdated?: (updated: BackendStudentProfile) => void;
  isOnboarding?: boolean;
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
  'Node.js',
  'PostgreSQL',
];

// Detect known sample/mock identity values so empty profiles don't display fictional identities
const isSampleName = (val?: string | null) => {
  if (!val) return false;
  const v = val.trim().toLowerCase();
  return v === 'alex chen' || v === 'alexchen';
};

const isSampleInstitution = (val?: string | null) => {
  if (!val) return false;
  return val.trim().toLowerCase() === 'stanford university';
};

const isSampleEmail = (val?: string | null) => {
  if (!val) return false;
  return val.trim().toLowerCase() === 'alex.chen@university.edu';
};

const isSampleDegree = (val?: string | null) => {
  if (!val) return false;
  return val.trim().toLowerCase() === 'b.s. symbolic systems & computer science';
};

const isSampleUrl = (val?: string | null) => {
  if (!val) return false;
  const v = val.trim().toLowerCase();
  return (
    v === 'https://github.com/alexchen' ||
    v === 'https://linkedin.com/in/alexchen' ||
    v === 'https://alexchen.dev'
  );
};

const isSampleBio = (val?: string | null) => {
  if (!val) return false;
  return val.trim().toLowerCase() === 'full-stack developer interested in ai systems and hackathons.';
};

const isSampleProjects = (val?: string | null) => {
  if (!val) return false;
  return val.includes('NeuralNote') || val.includes('alexchen/neuralnote');
};

const isSampleIdentityRecord = (data: Partial<BackendStudentProfile>): boolean => {
  return (
    isSampleName(data.student_name) ||
    isSampleInstitution(data.institution) ||
    isSampleEmail(data.student_email)
  );
};

// URL validation helper (validates only non-empty strings)
const isValidUrl = (url?: string | null): boolean => {
  if (!url || !url.trim()) return true;
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

// Email validation helper
const isValidEmail = (email?: string | null): boolean => {
  if (!email || !email.trim()) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
};

// Graduation year validation helper (valid 4-digit year)
const isValidGradYear = (year?: string | null): boolean => {
  if (!year || !year.trim()) return false;
  const cleaned = year.trim();
  if (!/^\d{4}$/.test(cleaned)) return false;
  const num = parseInt(cleaned, 10);
  return num >= 1950 && num <= 2040;
};

export const MyProfileView: React.FC<MyProfileViewProps> = ({ onProfileUpdated, isOnboarding: _isOnboarding }) => {
  // Profile State: initialized with clean empty strings
  const [profile, setProfile] = useState<BackendStudentProfile>({
    student_name: '',
    student_email: '',
    skills: [],
    team_size: 2,
    region: 'All',
    start_date: null,
    end_date: null,
    budget: null,
    institution: '',
    degree: '',
    graduation_year: '',
    github_url: '',
    linkedin_url: '',
    portfolio_url: '',
    bio: '',
    collaboration_preference: 'Open to joining teams',
    projects_json: '[]',
    participation_mode: 'All',
    updated_at: null,
  });

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [saveErrorMsg, setSaveErrorMsg] = useState<string | null>(null);

  // Field validation errors state
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saveGuidanceMsg, setSaveGuidanceMsg] = useState<string | null>(null);

  // Skill Input State
  const [skillInput, setSkillInput] = useState<string>('');

  // Project Input State
  const [isAddingProject, setIsAddingProject] = useState<boolean>(false);
  const [projectTitle, setProjectTitle] = useState<string>('');
  const [projectDesc, setProjectDesc] = useState<string>('');
  const [projectTech, setProjectTech] = useState<string>('');
  const [projectLink, setProjectLink] = useState<string>('');

  // Smooth scroll helper accounting for sticky header
  const scrollToElement = (elementId: string) => {
    const el = document.getElementById(elementId);
    if (!el) return;

    const header = document.getElementById('app-header');
    const headerHeight = header ? header.getBoundingClientRect().height : 80;
    const rect = el.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const targetY = rect.top + scrollTop - headerHeight - 24;

    window.scrollTo({
      top: Math.max(0, targetY),
      behavior: 'smooth',
    });

    // Focus input element if focusable, or the first input inside if section card
    setTimeout(() => {
      if (
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el instanceof HTMLSelectElement ||
        el instanceof HTMLButtonElement
      ) {
        el.focus({ preventScroll: true });
      } else {
        const focusable = el.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
          'input, textarea, select'
        );
        if (focusable) {
          focusable.focus({ preventScroll: true });
        }
      }

      // Add temporary highlight effect
      el.classList.add('nav-highlight');
      setTimeout(() => {
        el.classList.remove('nav-highlight');
      }, 1500);
    }, 200);
  };

  // Helper to clear a single field's error when it becomes valid
  const clearFieldError = (key: string) => {
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const copy = { ...prev };
      delete copy[key];
      return copy;
    });
    setSaveGuidanceMsg(null);
  };

  // Load existing profile from backend database
  useEffect(() => {
    let ignore = false;
    async function loadData() {
      try {
        const data = await fetchStudentProfile();
        if (!ignore) {
          const isSample = isSampleIdentityRecord(data);
          const isGenuinelyNew =
            (!data.student_name || !data.student_name.trim()) &&
            (!data.student_email || !data.student_email.trim()) &&
            (!data.skills || data.skills.length === 0);
          setProfile({
            ...data,
            student_name: isSample && isSampleName(data.student_name) ? '' : (data.student_name || ''),
            student_email: isSample && isSampleEmail(data.student_email) ? '' : (data.student_email || ''),
            institution: isSample && isSampleInstitution(data.institution) ? '' : (data.institution || ''),
            degree: isSample && isSampleDegree(data.degree) ? '' : (data.degree || ''),
            graduation_year: isSample ? '' : (data.graduation_year || ''),
            github_url: isSample && isSampleUrl(data.github_url) ? '' : (data.github_url || ''),
            linkedin_url: isSample && isSampleUrl(data.linkedin_url) ? '' : (data.linkedin_url || ''),
            portfolio_url: isSample && isSampleUrl(data.portfolio_url) ? '' : (data.portfolio_url || ''),
            bio: isSample && isSampleBio(data.bio) ? '' : (data.bio || ''),
            collaboration_preference: data.collaboration_preference || 'Open to joining teams',
            projects_json: isSample && isSampleProjects(data.projects_json) ? '[]' : (data.projects_json || '[]'),
            skills: isSample || isGenuinelyNew ? [] : (Array.isArray(data.skills) ? data.skills : []),
          });
        }
      } catch {
        // Fallback to local defaults if backend is unseeded
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    loadData();
    return () => {
      ignore = true;
    };
  }, []);

  // Parse user projects safely
  const projects: StudentProject[] = useMemo(() => {
    try {
      if (!profile.projects_json) return [];
      const parsed = JSON.parse(profile.projects_json);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [profile.projects_json]);

  // Initials for avatar
  const initials = useMemo(() => {
    if (!profile.student_name || !profile.student_name.trim()) return '👤';
    const parts = profile.student_name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }, [profile.student_name]);

  // Skills management
  const addSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (!trimmed) return;
    const alreadyExists = profile.skills.some(
      (s) => s.toLowerCase() === trimmed.toLowerCase()
    );
    if (!alreadyExists) {
      setProfile((prev) => ({
        ...prev,
        skills: [...prev.skills, trimmed],
      }));
      clearFieldError('skills');
    }
  };

  const removeSkill = (skillToRemove: string) => {
    setProfile((prev) => ({
      ...prev,
      skills: prev.skills.filter((s) => s.toLowerCase() !== skillToRemove.toLowerCase()),
    }));
  };

  const handleSkillKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addSkill(skillInput);
      setSkillInput('');
    }
  };

  // Projects management
  const handleAddProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectTitle.trim() || !projectDesc.trim()) return;

    const newProject: StudentProject = {
      id: `proj_${Date.now()}`,
      title: projectTitle.trim(),
      description: projectDesc.trim(),
      tech_stack: projectTech
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      link: projectLink.trim() || undefined,
    };

    const updatedProjects = [...projects, newProject];
    setProfile((prev) => ({
      ...prev,
      projects_json: JSON.stringify(updatedProjects),
    }));

    // Reset inputs
    setProjectTitle('');
    setProjectDesc('');
    setProjectTech('');
    setProjectLink('');
    setIsAddingProject(false);
  };

  const handleRemoveProject = (id: string) => {
    const updated = projects.filter((p) => p.id !== id);
    setProfile((prev) => ({
      ...prev,
      projects_json: JSON.stringify(updated),
    }));
  };

  // Validate required profile fields in logical form order
  const validateForm = () => {
    const errors: Record<string, string> = {};
    const orderedErrors: { key: string; id: string; message: string }[] = [];

    // 1. Full Name (Required)
    if (!profile.student_name || !profile.student_name.trim()) {
      const msg = 'Please enter your full name.';
      errors['student_name'] = msg;
      orderedErrors.push({ key: 'student_name', id: 'student-name-input', message: msg });
    }

    // 2. Student Email (Required & Valid Format)
    if (!profile.student_email || !profile.student_email.trim()) {
      const msg = 'Please enter your student or contact email.';
      errors['student_email'] = msg;
      orderedErrors.push({ key: 'student_email', id: 'student-email-input', message: msg });
    } else if (!isValidEmail(profile.student_email)) {
      const msg = 'Please enter a valid email address (e.g., student@university.edu).';
      errors['student_email'] = msg;
      orderedErrors.push({ key: 'student_email', id: 'student-email-input', message: msg });
    }

    // 3. Institution (Required)
    if (!profile.institution || !profile.institution.trim()) {
      const msg = 'Please enter your institution.';
      errors['institution'] = msg;
      orderedErrors.push({ key: 'institution', id: 'institution-input', message: msg });
    }

    // 4. Degree & Major (Required)
    if (!profile.degree || !profile.degree.trim()) {
      const msg = 'Please enter your degree program and major.';
      errors['degree'] = msg;
      orderedErrors.push({ key: 'degree', id: 'degree-input', message: msg });
    }

    // 5. Graduation Year (Required & 4-digit format)
    if (!profile.graduation_year || !profile.graduation_year.trim()) {
      const msg = 'Please enter your graduation year.';
      errors['graduation_year'] = msg;
      orderedErrors.push({ key: 'graduation_year', id: 'grad-year-input', message: msg });
    } else if (!isValidGradYear(profile.graduation_year)) {
      const msg = 'Please enter a valid 4-digit graduation year (e.g., 2027).';
      errors['graduation_year'] = msg;
      orderedErrors.push({ key: 'graduation_year', id: 'grad-year-input', message: msg });
    }

    // 6. Technical Skills (Required: at least one skill)
    if (!profile.skills || profile.skills.length === 0) {
      const msg = 'Please select or add at least one technical skill.';
      errors['skills'] = msg;
      orderedErrors.push({ key: 'skills', id: 'profile-skill-input', message: msg });
    }

    // 7. GitHub URL (Optional, but validate format if entered)
    if (profile.github_url && profile.github_url.trim() && !isValidUrl(profile.github_url)) {
      const msg = 'Please enter a valid URL (starting with http:// or https://).';
      errors['github_url'] = msg;
      orderedErrors.push({ key: 'github_url', id: 'github-url-input', message: msg });
    }

    // 8. LinkedIn URL (Optional, but validate format if entered)
    if (profile.linkedin_url && profile.linkedin_url.trim() && !isValidUrl(profile.linkedin_url)) {
      const msg = 'Please enter a valid URL (starting with http:// or https://).';
      errors['linkedin_url'] = msg;
      orderedErrors.push({ key: 'linkedin_url', id: 'linkedin-url-input', message: msg });
    }

    // 9. Portfolio URL (Optional, but validate format if entered)
    if (profile.portfolio_url && profile.portfolio_url.trim() && !isValidUrl(profile.portfolio_url)) {
      const msg = 'Please enter a valid URL (starting with http:// or https://).';
      errors['portfolio_url'] = msg;
      orderedErrors.push({ key: 'portfolio_url', id: 'portfolio-url-input', message: msg });
    }

    return { errors, orderedErrors };
  };

  // Save profile to backend database with step-by-step guidance to missing fields
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccessMsg(null);
    setSaveErrorMsg(null);

    // 1. Validate required fields
    const { errors, orderedErrors } = validateForm();

    // 2. If any fields are missing or invalid, do not save; guide to first invalid field
    if (orderedErrors.length > 0) {
      setFieldErrors(errors);
      const firstError = orderedErrors[0];
      setSaveGuidanceMsg(`Please complete the highlighted field: ${firstError.message}`);
      scrollToElement(firstError.id);
      return;
    }

    // Clear validation errors when all are valid
    setFieldErrors({});
    setSaveGuidanceMsg(null);
    setIsSaving(true);

    try {
      const saved = await saveStudentProfile({
        student_name: profile.student_name?.trim() || undefined,
        student_email: profile.student_email?.trim() || undefined,
        skills: profile.skills,
        team_size: profile.team_size,
        region: profile.region,
        start_date: profile.start_date,
        end_date: profile.end_date,
        budget: profile.budget,
        institution: profile.institution?.trim() || undefined,
        degree: profile.degree?.trim() || undefined,
        graduation_year: profile.graduation_year?.trim() || undefined,
        github_url: profile.github_url?.trim() || undefined,
        linkedin_url: profile.linkedin_url?.trim() || undefined,
        portfolio_url: profile.portfolio_url?.trim() || undefined,
        bio: profile.bio?.trim() || undefined,
        collaboration_preference: profile.collaboration_preference || undefined,
        projects_json: profile.projects_json || '[]',
        participation_mode: profile.participation_mode || 'All',
      });

      setProfile((prev) => ({
        ...prev,
        ...saved,
        updated_at: saved.updated_at,
      }));

      setSaveSuccessMsg('Changes saved');
      setSaveErrorMsg(null);

      if (onProfileUpdated) {
        onProfileUpdated(saved);
      }

      setTimeout(() => setSaveSuccessMsg(null), 3000);
    } catch (err: unknown) {
      setSaveSuccessMsg(null);
      setSaveErrorMsg(
        err instanceof Error ? err.message : 'Failed to persist student profile to backend.'
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="state-box" style={{ padding: '3rem 1rem' }} id="profile-loading-state">
        <div className="spinner" />
        <h3 className="state-title">Loading Student Profile...</h3>
        <p className="state-desc">Retrieving your portfolio and academic details from database.</p>
      </div>
    );
  }

  return (
    <div className="profile-view-layout" id="my-profile-view">
      {/* Top Profile Overview Card */}
      <div className="profile-overview-card" id="profile-overview-card">
        <div className="overview-main-row">
          <div className="profile-avatar-circle" aria-label="Student Avatar">
            <span>{initials}</span>
          </div>

          <div className="profile-identity-info">
            <div className="identity-header-row">
              <h2 className="profile-name">
                {profile.student_name?.trim() || 'My Profile'}
              </h2>
              <span className="profile-status-badge">
                {profile.institution?.trim()
                  ? 'Student Verified'
                  : profile.student_name?.trim()
                  ? 'Profile In Progress'
                  : 'New Profile'}
              </span>
            </div>

            <p className="profile-academic-subtitle">
              {profile.institution?.trim()
                ? `${profile.institution}${profile.degree?.trim() ? ` • ${profile.degree}` : ''}${
                    profile.graduation_year?.trim() ? ` (Class of ${profile.graduation_year})` : ''
                  }`
                : 'Configure your academic and developer profile details below'}
            </p>

            {(profile.github_url?.trim() ||
              profile.linkedin_url?.trim() ||
              profile.portfolio_url?.trim()) && (
              <div className="profile-links-preview">
                {profile.github_url?.trim() && (
                  <a
                    href={profile.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="profile-link-chip"
                  >
                    <span aria-hidden="true">💻</span> GitHub
                  </a>
                )}
                {profile.linkedin_url?.trim() && (
                  <a
                    href={profile.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="profile-link-chip"
                  >
                    <span aria-hidden="true">🔗</span> LinkedIn
                  </a>
                )}
                {profile.portfolio_url?.trim() && (
                  <a
                    href={profile.portfolio_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="profile-link-chip"
                  >
                    <span aria-hidden="true">🌐</span> Portfolio
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Subtle Temporary Toast Feedback */}
      {saveSuccessMsg && (
        <div className="profile-toast-success" role="status" id="profile-save-success">
          <span className="toast-icon" aria-hidden="true">✓</span>
          <span>{saveSuccessMsg}</span>
        </div>
      )}

      {saveErrorMsg && (
        <div className="modal-banner banner-error" role="alert" id="profile-save-error" style={{ marginBottom: '1.25rem' }}>
          <span className="banner-icon" aria-hidden="true">⚠️</span>
          <div>{saveErrorMsg}</div>
        </div>
      )}

      {/* Single Column Profile Edit Form */}
      <div className="profile-body-grid">
        <form className="profile-form-column" onSubmit={handleSaveProfile} noValidate>
          {/* Section 1: Academic & Personal Details */}
          <div className="profile-section-card" id="academic-info-card">
            <div className="section-card-header">
              <h3 className="section-title">Academic & Identity Information</h3>
              <p className="section-desc">
                Your personal and academic background used for verification and team rosters.
              </p>
            </div>

            <div className="profile-fields-grid">
              <div className="form-group">
                <label htmlFor="student-name-input" className="form-label">
                  Full Name <span style={{ color: 'var(--color-error, #DC2626)' }}>*</span>
                </label>
                <input
                  id="student-name-input"
                  type="text"
                  className={`form-input ${fieldErrors.student_name ? 'input-error' : ''}`}
                  placeholder="Enter your full name"
                  value={profile.student_name || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, student_name: e.target.value });
                    if (e.target.value.trim()) clearFieldError('student_name');
                  }}
                  aria-invalid={Boolean(fieldErrors.student_name)}
                  aria-describedby={fieldErrors.student_name ? 'student-name-error' : undefined}
                />
                {fieldErrors.student_name && (
                  <div className="field-error-message" id="student-name-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.student_name}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="student-email-input" className="form-label">
                  Student / Contact Email <span style={{ color: 'var(--color-error, #DC2626)' }}>*</span>
                </label>
                <input
                  id="student-email-input"
                  type="email"
                  className={`form-input ${fieldErrors.student_email ? 'input-error' : ''}`}
                  placeholder="Enter your student or contact email"
                  value={profile.student_email || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, student_email: e.target.value });
                    if (isValidEmail(e.target.value)) clearFieldError('student_email');
                  }}
                  aria-invalid={Boolean(fieldErrors.student_email)}
                  aria-describedby={fieldErrors.student_email ? 'student-email-error' : undefined}
                />
                {fieldErrors.student_email && (
                  <div className="field-error-message" id="student-email-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.student_email}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="institution-input" className="form-label">
                  Institution / University <span style={{ color: 'var(--color-error, #DC2626)' }}>*</span>
                </label>
                <input
                  id="institution-input"
                  type="text"
                  className={`form-input ${fieldErrors.institution ? 'input-error' : ''}`}
                  placeholder="e.g. Indian Institute of Technology or University Name"
                  value={profile.institution || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, institution: e.target.value });
                    if (e.target.value.trim()) clearFieldError('institution');
                  }}
                  aria-invalid={Boolean(fieldErrors.institution)}
                  aria-describedby={fieldErrors.institution ? 'institution-error' : undefined}
                />
                {fieldErrors.institution && (
                  <div className="field-error-message" id="institution-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.institution}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="degree-input" className="form-label">
                  Degree & Major <span style={{ color: 'var(--color-error, #DC2626)' }}>*</span>
                </label>
                <input
                  id="degree-input"
                  type="text"
                  className={`form-input ${fieldErrors.degree ? 'input-error' : ''}`}
                  placeholder="e.g. B.Tech Computer Science, B.S. Data Science"
                  value={profile.degree || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, degree: e.target.value });
                    if (e.target.value.trim()) clearFieldError('degree');
                  }}
                  aria-invalid={Boolean(fieldErrors.degree)}
                  aria-describedby={fieldErrors.degree ? 'degree-error' : undefined}
                />
                {fieldErrors.degree && (
                  <div className="field-error-message" id="degree-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.degree}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="grad-year-input" className="form-label">
                  Graduation Year <span style={{ color: 'var(--color-error, #DC2626)' }}>*</span>
                </label>
                <input
                  id="grad-year-input"
                  type="text"
                  className={`form-input ${fieldErrors.graduation_year ? 'input-error' : ''}`}
                  placeholder="e.g. 2026, 2027"
                  value={profile.graduation_year || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, graduation_year: e.target.value });
                    if (isValidGradYear(e.target.value)) clearFieldError('graduation_year');
                  }}
                  aria-invalid={Boolean(fieldErrors.graduation_year)}
                  aria-describedby={fieldErrors.graduation_year ? 'grad-year-error' : undefined}
                />
                {fieldErrors.graduation_year && (
                  <div className="field-error-message" id="grad-year-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.graduation_year}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="collab-pref-input" className="form-label">
                  Team Collaboration Preference
                </label>
                <select
                  id="collab-pref-input"
                  className="form-select"
                  value={profile.collaboration_preference || 'Open to joining teams'}
                  onChange={(e) =>
                    setProfile({ ...profile, collaboration_preference: e.target.value })
                  }
                >
                  <option value="Open to joining teams">Open to joining teams</option>
                  <option value="Have a fixed team">Have a fixed team</option>
                  <option value="Looking for teammates">Looking for teammates</option>
                  <option value="Solo hacker preference">Solo hacker preference</option>
                </select>
              </div>
            </div>

            <div className="form-group" style={{ marginTop: '0.75rem' }}>
              <label htmlFor="bio-input" className="form-label">
                Bio & Developer Summary
              </label>
              <textarea
                id="bio-input"
                className="form-textarea"
                rows={3}
                placeholder="Briefly describe your programming interests, favorite tech stacks, or hackathon focus..."
                value={profile.bio || ''}
                onChange={(e) => setProfile({ ...profile, bio: e.target.value })}
              />
            </div>
          </div>

          {/* Section 2: Technical Skills & Expertise */}
          <div className="profile-section-card" id="skills-expertise-card">
            <div className="section-card-header">
              <h3 className="section-title">Technical Expertise</h3>
              <p className="section-desc">
                Your core technical skills and tools showcased on your developer profile.
              </p>
            </div>

            <div className="form-group">
              <label htmlFor="profile-skill-input" className="form-label">
                Add Technical Skills <span style={{ color: 'var(--color-error, #DC2626)' }}>*</span>
              </label>
              <input
                id="profile-skill-input"
                type="text"
                className={`form-input ${fieldErrors.skills ? 'input-error' : ''}`}
                placeholder="Type skill and press Enter (e.g. PyTorch, React, Go)..."
                value={skillInput}
                onChange={(e) => setSkillInput(e.target.value)}
                onKeyDown={handleSkillKeyDown}
                aria-invalid={Boolean(fieldErrors.skills)}
                aria-describedby={fieldErrors.skills ? 'profile-skills-error' : undefined}
              />
              {fieldErrors.skills && (
                <div className="field-error-message" id="profile-skills-error" role="alert">
                  <span aria-hidden="true">⚠️</span> {fieldErrors.skills}
                </div>
              )}

              <div className="quick-pills">
                {COMMON_SKILLS.filter((skill) => {
                  if (!skillInput.trim()) return true;
                  return skill.toLowerCase().includes(skillInput.trim().toLowerCase());
                }).map((skill) => {
                  const active = profile.skills.some((s) => s.toLowerCase() === skill.toLowerCase());
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
          </div>

          {/* Section 3: Developer Links (Optional) */}
          <div className="profile-section-card" id="developer-links-card">
            <div className="section-card-header">
              <h3 className="section-title">Developer & Portfolio Links (Optional)</h3>
              <p className="section-desc">
                Public links to your code repositories, professional networks, and portfolio.
              </p>
            </div>

            <div className="profile-fields-grid">
              <div className="form-group">
                <label htmlFor="github-url-input" className="form-label">
                  GitHub Profile URL
                </label>
                <input
                  id="github-url-input"
                  type="url"
                  className={`form-input ${fieldErrors.github_url ? 'input-error' : ''}`}
                  placeholder="https://github.com/yourusername"
                  value={profile.github_url || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, github_url: e.target.value });
                    if (isValidUrl(e.target.value)) clearFieldError('github_url');
                  }}
                  aria-invalid={Boolean(fieldErrors.github_url)}
                  aria-describedby={fieldErrors.github_url ? 'github-url-error' : undefined}
                />
                {fieldErrors.github_url && (
                  <div className="field-error-message" id="github-url-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.github_url}
                  </div>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="linkedin-url-input" className="form-label">
                  LinkedIn Profile URL
                </label>
                <input
                  id="linkedin-url-input"
                  type="url"
                  className={`form-input ${fieldErrors.linkedin_url ? 'input-error' : ''}`}
                  placeholder="https://linkedin.com/in/yourprofile"
                  value={profile.linkedin_url || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, linkedin_url: e.target.value });
                    if (isValidUrl(e.target.value)) clearFieldError('linkedin_url');
                  }}
                  aria-invalid={Boolean(fieldErrors.linkedin_url)}
                  aria-describedby={fieldErrors.linkedin_url ? 'linkedin-url-error' : undefined}
                />
                {fieldErrors.linkedin_url && (
                  <div className="field-error-message" id="linkedin-url-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.linkedin_url}
                  </div>
                )}
              </div>

              <div className="form-group" style={{ gridColumn: 'span 2' }}>
                <label htmlFor="portfolio-url-input" className="form-label">
                  Personal Portfolio / Website URL
                </label>
                <input
                  id="portfolio-url-input"
                  type="url"
                  className={`form-input ${fieldErrors.portfolio_url ? 'input-error' : ''}`}
                  placeholder="https://yourportfolio.dev"
                  value={profile.portfolio_url || ''}
                  onChange={(e) => {
                    setProfile({ ...profile, portfolio_url: e.target.value });
                    if (isValidUrl(e.target.value)) clearFieldError('portfolio_url');
                  }}
                  aria-invalid={Boolean(fieldErrors.portfolio_url)}
                  aria-describedby={fieldErrors.portfolio_url ? 'portfolio-url-error' : undefined}
                />
                {fieldErrors.portfolio_url && (
                  <div className="field-error-message" id="portfolio-url-error" role="alert">
                    <span aria-hidden="true">⚠️</span> {fieldErrors.portfolio_url}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Section 4: Projects & Achievements (Optional) */}
          <div className="profile-section-card" id="projects-achievements-card">
            <div className="section-card-header">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 className="section-title">Projects & Achievements (Optional)</h3>
                  <p className="section-desc">
                    Showcase genuine projects and hackathon submissions you have built.
                  </p>
                </div>
                {!isAddingProject && (
                  <button
                    type="button"
                    id="add-project-btn"
                    className="btn-card-secondary"
                    style={{ fontSize: '0.8rem', padding: '0.4rem 0.85rem' }}
                    onClick={() => {
                      setIsAddingProject(true);
                      setTimeout(() => {
                        scrollToElement('new-proj-title');
                      }, 50);
                    }}
                  >
                    + Add Project
                  </button>
                )}
              </div>
            </div>

            {/* Inline Add Project Form */}
            {isAddingProject && (
              <div
                style={{
                  background: 'var(--bg-subtle, #F8FAFC)',
                  border: '1px solid var(--border-color, #E3E8F0)',
                  borderRadius: 'var(--radius-md, 10px)',
                  padding: '1rem',
                  marginBottom: '1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                }}
              >
                <h4 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                  New Project Details
                </h4>

                <div className="profile-fields-grid">
                  <div className="form-group" style={{ margin: 0 }}>
                    <label htmlFor="new-proj-title" className="form-label">Project Title</label>
                    <input
                      id="new-proj-title"
                      type="text"
                      className="form-input"
                      placeholder="e.g. Autonomous Drone Navigation"
                      value={projectTitle}
                      onChange={(e) => setProjectTitle(e.target.value)}
                    />
                  </div>

                  <div className="form-group" style={{ margin: 0 }}>
                    <label htmlFor="new-proj-tech" className="form-label">Technologies (Comma separated)</label>
                    <input
                      id="new-proj-tech"
                      type="text"
                      className="form-input"
                      placeholder="e.g. Python, PyTorch, React, FastAPI"
                      value={projectTech}
                      onChange={(e) => setProjectTech(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-group" style={{ margin: 0 }}>
                  <label htmlFor="new-proj-desc" className="form-label">Project Description</label>
                  <textarea
                    id="new-proj-desc"
                    className="form-textarea"
                    rows={2}
                    placeholder="Briefly describe what you built, problem solved, and key features..."
                    value={projectDesc}
                    onChange={(e) => setProjectDesc(e.target.value)}
                  />
                </div>

                <div className="form-group" style={{ margin: 0 }}>
                  <label htmlFor="new-proj-link" className="form-label">Repository / Demo Link (Optional)</label>
                  <input
                    id="new-proj-link"
                    type="url"
                    className="form-input"
                    placeholder="https://github.com/username/project"
                    value={projectLink}
                    onChange={(e) => setProjectLink(e.target.value)}
                  />
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ padding: '0.45rem 1rem', fontSize: '0.8rem' }}
                    onClick={() => setIsAddingProject(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    style={{ width: 'auto', padding: '0.45rem 1.25rem', fontSize: '0.8rem' }}
                    onClick={handleAddProject}
                  >
                    Save Project to List
                  </button>
                </div>
              </div>
            )}

            {/* Render Projects List or Empty State */}
            {projects.length === 0 && !isAddingProject ? (
              <div
                className="state-box"
                id="projects-empty-state"
                style={{ padding: '2rem 1rem', background: 'transparent', textAlign: 'center' }}
              >
                <div style={{ fontSize: '1.75rem', marginBottom: '0.5rem' }} aria-hidden="true">
                  🚀
                </div>
                <h4
                  style={{
                    margin: '0 0 0.35rem 0',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                  }}
                >
                  No projects added yet
                </h4>
                <p className="state-desc" style={{ margin: '0 0 1rem 0' }}>
                  Showcase genuine projects and hackathon builds to verify technical experience.
                </p>
                <button
                  type="button"
                  id="empty-add-project-btn"
                  className="btn-primary"
                  style={{ width: 'auto', padding: '0.45rem 1.25rem', fontSize: '0.825rem' }}
                  onClick={() => {
                    setIsAddingProject(true);
                    setTimeout(() => {
                      scrollToElement('new-proj-title');
                    }, 50);
                  }}
                >
                  + Add Project
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {projects.map((proj) => (
                  <div
                    key={proj.id}
                    style={{
                      background: 'var(--bg-subtle, #F8FAFC)',
                      border: '1px solid var(--border-color, #E3E8F0)',
                      borderRadius: 'var(--radius-md, 10px)',
                      padding: '1rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.4rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {proj.title}
                      </h4>
                      <button
                        type="button"
                        onClick={() => handleRemoveProject(proj.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--color-error)',
                          cursor: 'pointer',
                          fontSize: '0.8rem',
                        }}
                        aria-label={`Remove ${proj.title}`}
                      >
                        Delete
                      </button>
                    </div>

                    <p style={{ margin: 0, fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      {proj.description}
                    </p>

                    <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                      {proj.tech_stack.map((t) => (
                        <span
                          key={t}
                          style={{
                            fontSize: '0.725rem',
                            padding: '0.15rem 0.5rem',
                            background: 'var(--color-primary-light, #EEF2FF)',
                            color: 'var(--color-primary, #5B4BFA)',
                            borderRadius: 'var(--radius-sm, 6px)',
                            fontWeight: 600,
                          }}
                        >
                          {t}
                        </span>
                      ))}

                      {proj.link && (
                        <a
                          href={proj.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            fontSize: '0.725rem',
                            padding: '0.15rem 0.5rem',
                            background: 'var(--bg-card, #FFFFFF)',
                            border: '1px solid var(--border-color, #E3E8F0)',
                            color: 'var(--color-primary, #5B4BFA)',
                            borderRadius: 'var(--radius-sm, 6px)',
                            fontWeight: 600,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.2rem',
                          }}
                        >
                          <span>🔗</span> Demo / Repo
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Sticky/Clear Save Action Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              gap: '1rem',
              alignItems: 'center',
              padding: '1rem 1.5rem',
              background: 'var(--bg-card, #FFFFFF)',
              border: '1px solid var(--border-color, #E3E8F0)',
              borderRadius: 'var(--radius-lg, 14px)',
              boxShadow: 'var(--shadow-sm)',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: '240px' }}>
              {saveGuidanceMsg ? (
                <span
                  id="save-guidance-notice"
                  role="alert"
                  style={{
                    fontSize: '0.825rem',
                    color: 'var(--color-error, #DC2626)',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                  }}
                >
                  <span aria-hidden="true">⚠️</span> {saveGuidanceMsg}
                </span>
              ) : profile.updated_at ? (
                <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                  Last saved: {new Date(profile.updated_at).toLocaleTimeString()}
                </span>
              ) : (
                <span style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                  Complete required fields to save profile.
                </span>
              )}
            </div>

            <button
              type="submit"
              id="save-profile-btn"
              className="btn-primary"
              style={{ width: 'auto', padding: '0.65rem 1.85rem' }}
              disabled={isSaving}
            >
              {isSaving ? 'Saving to Database...' : 'Save Profile'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
