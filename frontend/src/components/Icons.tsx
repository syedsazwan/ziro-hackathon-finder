import React from 'react';

export interface IconProps extends React.SVGProps<SVGSVGElement> {
  size?: number | string;
  color?: string;
  strokeWidth?: number | string;
}

// 1. My Profile: user-round
export const UserRoundIcon: React.FC<IconProps> = ({
  size = 20,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-user-round ${className}`}
    aria-hidden="true"
    {...props}
  >
    <circle cx="12" cy="8" r="5" />
    <path d="M20 21a8 8 0 0 0-16 0" />
  </svg>
);

// 2. My Criteria: target
export const TargetIcon: React.FC<IconProps> = ({
  size = 20,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-target ${className}`}
    aria-hidden="true"
    {...props}
  >
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="6" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);

// 3. Discover Events: compass
export const CompassIcon: React.FC<IconProps> = ({
  size = 20,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-compass ${className}`}
    aria-hidden="true"
    {...props}
  >
    <circle cx="12" cy="12" r="10" />
    <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
  </svg>
);

// 4. My Registrations: clipboard-list
export const ClipboardListIcon: React.FC<IconProps> = ({
  size = 20,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-clipboard-list ${className}`}
    aria-hidden="true"
    {...props}
  >
    <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <path d="M12 11h4" />
    <path d="M12 16h4" />
    <path d="M8 11h.01" />
    <path d="M8 16h.01" />
  </svg>
);

// 5. Notifications: bell-ring
export const BellRingIcon: React.FC<IconProps> = ({
  size = 20,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-bell-ring ${className}`}
    aria-hidden="true"
    {...props}
  >
    <path d="M10.268 21a2 2 0 0 0 3.464 0" />
    <path d="M22 8c0-2.3-.8-4.3-2-6" />
    <path d="M4 2C2.8 3.7 2 5.7 2 8" />
    <path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.674C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326" />
  </svg>
);

// 6. Settings & Adapters: settings-2
export const Settings2Icon: React.FC<IconProps> = ({
  size = 20,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-settings-2 ${className}`}
    aria-hidden="true"
    {...props}
  >
    <path d="M20 7h-9" />
    <path d="M14 17H5" />
    <circle cx="17" cy="17" r="3" />
    <circle cx="7" cy="7" r="3" />
  </svg>
);

// 7. Light/Dark Mode: sun
export const SunIcon: React.FC<IconProps> = ({
  size = 18,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-sun ${className}`}
    aria-hidden="true"
    {...props}
  >
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2" />
    <path d="M12 20v2" />
    <path d="m4.93 4.93 1.41 1.41" />
    <path d="m17.66 17.66 1.41 1.41" />
    <path d="M2 12h2" />
    <path d="M20 12h2" />
    <path d="m6.34 17.66-1.41 1.41" />
    <path d="m19.07 4.93-1.41 1.41" />
  </svg>
);

// 8. Light/Dark Mode: moon
export const MoonIcon: React.FC<IconProps> = ({
  size = 18,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-moon ${className}`}
    aria-hidden="true"
    {...props}
  >
    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
  </svg>
);

// 9. External Link Icon
export const ExternalLinkIcon: React.FC<IconProps> = ({
  size = 14,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-external-link ${className}`}
    aria-hidden="true"
    {...props}
  >
    <path d="M15 3h6v6" />
    <path d="M10 14 21 3" />
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
  </svg>
);

// 10. Check Check Icon (Mark All Read)
export const CheckCheckIcon: React.FC<IconProps> = ({
  size = 16,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-check-check ${className}`}
    aria-hidden="true"
    {...props}
  >
    <path d="M18 6 7 17l-5-5" />
    <path d="m22 10-7.5 7.5L13 16" />
  </svg>
);

// 11. Refresh CW Icon
export const RefreshCwIcon: React.FC<IconProps> = ({
  size = 16,
  color = 'currentColor',
  strokeWidth = 2,
  className = '',
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`lucide-icon lucide-refresh-cw ${className}`}
    aria-hidden="true"
    {...props}
  >
    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
    <path d="M8 16H3v5" />
  </svg>
);

// ============================================================================
// APPROVED BRAND LOGO: Ziro Lightning-Z
// Minimal, recognizable SaaS mark combining stylized Z, lightning bolt, and discovery accent
// Visual direction: Primary indigo #4F46E5 to secondary purple #7C3AED with crisp white symbol
// ============================================================================
export interface ZiroLogoProps {
  size?: number;
  className?: string;
}

export const ZiroLogo: React.FC<ZiroLogoProps> = ({ size = 32, className = '' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={`ziro-brand-mark ${className}`}
    aria-label="Ziro Logo"
    role="img"
  >
    <defs>
      <linearGradient id="ziroBrandGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#4F46E5" />
        <stop offset="100%" stopColor="#7C3AED" />
      </linearGradient>
    </defs>
    {/* Rounded-square app icon background */}
    <rect width="32" height="32" rx="8" fill="url(#ziroBrandGrad)" />
    
    {/* Stylized Lightning-Z Symbol in pure white */}
    <path
      d="M7 8.5H23.5C24.4 8.5 24.9 9.5 24.3 10.2L15.6 19.5H20.2C20.9 19.5 21.4 20.3 21 20.9L16.2 27.5C15.6 28.3 14.4 27.9 14.7 26.9L16.4 21.5H9.5C8.6 21.5 8.1 20.5 8.7 19.8L16.8 10.5H7C6.4 10.5 6 10.1 6 9.5C6 8.9 6.4 8.5 7 8.5Z"
      fill="#FFFFFF"
    />
  </svg>
);

export const GoogleIcon: React.FC<{ size?: number; className?: string }> = ({ size = 20, className = '' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden="true">
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
    />
  </svg>
);

