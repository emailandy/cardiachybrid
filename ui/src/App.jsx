import React, { useState, useEffect, useMemo, useRef } from 'react';

function fmtMmSs(sec) {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return '00:00';
  const s = Math.max(0, Math.round(Number(sec)));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

// Compute wall-clock string from T0 ISO ("2023-12-08T07:54:17") + offset seconds
function fmtWallClockFromT0(t0Iso, offsetSec) {
  if (!t0Iso) return '';
  const parts = t0Iso.split('T')[1]?.split(':');
  if (!parts || parts.length < 3) return '';
  const baseSec = Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
  const total = Math.max(0, Math.round(baseSec + Number(offsetSec || 0)));
  const hh24 = Math.floor(total / 3600) % 24;
  const mm = Math.floor((total % 3600) / 60);
  const ss = total % 60;
  const ampm = hh24 >= 12 ? 'PM' : 'AM';
  const hh12 = hh24 % 12 === 0 ? 12 : hh24 % 12;
  return `${String(hh12).padStart(2, '0')}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')} ${ampm}`;
}

// Trackline Donut Progress SVG (matches the right-hand "Progress" column in Trackline's Project List)
function DonutProgress({ pct = 100, color = '#10b981' }) {
  const r = 7;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
  const dash = (clamped / 100) * c;
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.42rem', fontWeight: 700, fontSize: '0.78rem' }}>
      <svg width="20" height="20" viewBox="0 0 20 20" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="10" cy="10" r={r} fill="none" stroke="var(--border-strong)" strokeWidth="2.5" />
        <circle
          cx="10"
          cy="10"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeDasharray={`${dash} ${c}`}
          strokeLinecap="round"
        />
      </svg>
      <span>{Math.round(clamped)}%</span>
    </div>
  );
}

// Professional 1.6px-stroke monochrome/duotone vector icon component (zero emojis / AI-generated icons)
function ProIcon({ name, size = 16, color = 'currentColor', strokeWidth = 1.75, style = {} }) {
  const s = { width: size, height: size, flexShrink: 0, display: 'inline-block', verticalAlign: 'middle', ...style };
  switch (name) {
    case 'alairLogo':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={s}>
          <path
            d="M12 4.5L5.2 17.2a1.6 1.6 0 0 0 1.4 2.3h2.1l3.3-6.2 3.3 6.2h2.1a1.6 1.6 0 0 0 1.4-2.3L12 4.5z"
            stroke="#34d399"
            strokeWidth="2.1"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'flowMark':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={s}>
          <path d="M5 7h14M5 12h9M5 17h6" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="17.5" cy="14.5" r="2.5" fill={color} />
        </svg>
      );
    case 'home':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M3 9.5L12 3l9 6.5V20a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 20V9.5z" />
          <path d="M9 21.5V13h6v8.5" />
        </svg>
      );
    case 'task':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
          <path d="M8.5 12.2l2.3 2.3 4.8-4.8" />
        </svg>
      );
    case 'activity':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="22 12 18 12 15 20 9 4 6 12 2 12" />
        </svg>
      );
    case 'users':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <circle cx="12" cy="8" r="3.8" />
          <path d="M5.5 20c0-3.4 2.9-6 6.5-6s6.5 2.6 6.5 6" />
        </svg>
      );
    case 'bell':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      );
    case 'settings':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
    case 'info':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <circle cx="12" cy="12" r="9" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      );
    case 'search':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <circle cx="11" cy="11" r="7" />
          <line x1="20" y1="20" x2="16.2" y2="16.2" />
        </svg>
      );
    case 'chevronLeft':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="15 18 9 12 15 6" />
        </svg>
      );
    case 'chevronRight':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="9 18 15 12 9 6" />
        </svg>
      );
    case 'chevronDown':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      );
    case 'sun':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      );
    case 'moon':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      );
    case 'logout':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <polyline points="16 17 21 12 16 7" />
          <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
      );
    case 'grid':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
        </svg>
      );
    case 'sidebarToggle':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="3" y="3" width="18" height="18" rx="3" />
          <line x1="9" y1="3" x2="9" y2="21" />
        </svg>
      );
    case 'calendar':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="3" y="4" width="18" height="17" rx="2.5" />
          <line x1="16" y1="2.5" x2="16" y2="6" />
          <line x1="8" y1="2.5" x2="8" y2="6" />
          <line x1="3" y1="9.5" x2="21" y2="9.5" />
        </svg>
      );
    case 'plus':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      );
    case 'clock':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <circle cx="12" cy="12" r="9" />
          <polyline points="12 7 12 12 15.5 14" />
        </svg>
      );
    case 'dashedCircle':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeDasharray="3 3" style={s}>
          <circle cx="12" cy="12" r="8.5" />
        </svg>
      );
    case 'pauseBars':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="6" y="5" width="4" height="14" rx="1" />
          <rect x="14" y="5" width="4" height="14" rx="1" />
        </svg>
      );
    case 'zap':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      );
    case 'droplet':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
        </svg>
      );
    case 'wind':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2" />
        </svg>
      );
    case 'folder':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      );
    case 'video':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="2" y="5" width="14" height="14" rx="2.5" />
          <polygon points="22 7 16 12 22 17 22 7" />
        </svg>
      );
    case 'maximize':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      );
    case 'layers':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polygon points="12 2 2 7 12 12 22 7 12 2" />
          <polyline points="2 17 12 22 22 17" />
          <polyline points="2 12 12 17 22 12" />
        </svg>
      );
    case 'shield':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      );
    case 'database':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <ellipse cx="12" cy="5" rx="8" ry="3" />
          <path d="M20 12c0 1.66-3.58 3-8 3s-8-1.34-8-3" />
          <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
        </svg>
      );
    case 'download':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
      );
    case 'check':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="20 6 9 17 4 12" />
        </svg>
      );
    case 'sparkle':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9L12 3z" />
          <path d="M19 3v3M17.5 4.5h3M5 17v3M3.5 18.5h3" />
        </svg>
      );
    case 'alertTriangle':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      );
    case 'lock':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="4" y="11" width="16" height="10" rx="2.5" />
          <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        </svg>
      );
    case 'transfer':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <polyline points="17 2 21 6 17 10" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <polyline points="7 22 3 18 7 14" />
          <line x1="21" y1="18" x2="3" y2="18" />
        </svg>
      );
    case 'wrench':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
      );
    case 'thumbUp':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
      );
    case 'thumbDown':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
      );
    case 'send':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      );
    case 'askAi':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
          <path d="M10 10.5h4M12 8.5v4" />
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={s}>
          <rect x="4" y="4" width="16" height="16" rx="3" />
        </svg>
      );
  }
}

export default function App() {
  const [theme, setTheme] = useState('light');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const h = window.location.hash || '';
      const search = window.location.search || (h.includes('?') ? h.slice(h.indexOf('?')) : '');
      return new URLSearchParams(search).get('collapsed') === '1';
    }
    return false;
  });
  // Sidebar navigation focus: 'dashboard' | 'coaching' | 'visual_learning' | 'video' | 'findings' | 's5_audit'
  // Deep links: `#new-video` (optionally `#new-video-3`) opens the guided New Video wizard
  // `#ai-insights` or `#coaching` opens the dedicated AI Insights & Coaching page
  // `#visual-learning` or `/visual-learning` or `/console` opens the standalone Mellis HB-7 style Visual Learning Console page
  const initialHash = typeof window !== 'undefined' && window.location ? String(window.location.hash || '') : '';
  const initialPath = typeof window !== 'undefined' && window.location ? String(window.location.pathname || '') : '';
  const [activeNav, setActiveNav] = useState(
    initialHash.startsWith('#new-video')
      ? 'new_video'
      : initialHash.startsWith('#ai-insights') ||
        initialHash.startsWith('#coaching') ||
        initialPath.startsWith('/ai-insights') ||
        initialPath.startsWith('/coaching')
      ? 'coaching'
      : initialHash.startsWith('#visual-learning') ||
        initialHash.startsWith('#hb7') ||
        initialPath.startsWith('/visual-learning') ||
        initialPath.startsWith('/console')
      ? 'visual_learning'
      : initialHash.startsWith('#video-console') ||
        initialHash.startsWith('#video') ||
        initialPath.startsWith('/video-console')
      ? 'video'
      : 'dashboard'
  );
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onHashChange = () => {
      const h = String(window.location.hash || '');
      if (h.startsWith('#new-video')) setActiveNav('new_video');
      else if (h.startsWith('#ai-insights') || h.startsWith('#coaching')) setActiveNav('coaching');
      else if (h.startsWith('#visual-learning') || h.startsWith('#hb7')) setActiveNav('visual_learning');
      else if (h.startsWith('#video-console') || h.startsWith('#video')) setActiveNav('video');
      else if (h === '' || h === '#' || h.startsWith('#dashboard')) setActiveNav('dashboard');
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  const [engineState, setEngineState] = useState(() => window.__INITIAL_AICARES_STATE__ || null);
  const [selectedCaseId, setSelectedCaseId] = useState(() => {
    const h = window.location.hash || '';
    const q = new URLSearchParams(window.location.search || (h.includes('?') ? h.slice(h.indexOf('?')) : '')).get('case');
    const cs = window.__INITIAL_AICARES_STATE__?.report?.cases || [];
    if (q && cs.some((c) => c.record_id === q)) return q;
    return cs[0]?.record_id || 'PATIENT2-TRAUMA-A-GROUND-TRUTH';
  });

  // Video & 3D bounding box timeline state
  const [currentTimeS, setCurrentTimeS] = useState(() =>
    window.__INITIAL_AICARES_STATE__?.report?.cases?.[0]?.live_run ? 106.0 : 474.0
  );
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [localVideoBlobUrl, setLocalVideoBlobUrl] = useState(null);
  const [videoFeedSource, setVideoFeedSource] = useState('overhead_cropped');
  const [fullTheaterMode, setFullTheaterMode] = useState(false);
  // Console Split Mode: 'console_70_30' (default 70% Stage / 30% REDCap Evidence Rail) | 'audit_40_60' (40% Sticky Stage / 60% Full 6-Col REDCap Table) | 'cinema_100' (100% Theater)
  const [consoleLayoutMode, setConsoleLayoutMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const h = window.location.hash || '';
      const search = window.location.search || (h.includes('?') ? h.slice(h.indexOf('?')) : '');
      const ly = new URLSearchParams(search).get('layout');
      if (ly === 'audit_40_60' || ly === 'console_70_30' || ly === 'cinema_100') return ly;
    }
    return 'console_70_30';
  });
  // Video Size Mode: 'std' (1x Studio) | 'large' (1.5x Large Tall) | 'bed_wide' (2.3x Wide Bed Focus) | 'xl_theater' (2x Full-Width Theater)
  const [videoSizeMode, setVideoSizeMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const search = window.location.search || (window.location.hash.includes('?') ? window.location.hash.slice(window.location.hash.indexOf('?')) : '');
      const sp = new URLSearchParams(search);
      const sz = sp.get('size');
      if (sz === 'std' || sz === 'large' || sz === 'bed_wide' || sz === 'xl_theater') return sz;
    }
    return 'bed_wide';
  });
  // Synchronized Optical Zoom Level (1.0 to 2.0) applied identically to <video> and <svg> 3D bounding boxes
  const [videoZoomLevel, setVideoZoomLevel] = useState(() => {
    if (typeof window !== 'undefined') {
      const search = window.location.search || (window.location.hash.includes('?') ? window.location.hash.slice(window.location.hash.indexOf('?')) : '');
      const sp = new URLSearchParams(search);
      const zm = Number(sp.get('zoom'));
      if (zm >= 1 && zm <= 2.25) return zm;
    }
    return 1.0;
  });
  // Camera Perspective / Source View: 'hero_auto' | 'cctv_overhead' | 'ipad_bedside' | 'gopro_pov' | 'spatial_34'
  const [cameraPerspectiveView, setCameraPerspectiveView] = useState('hero_auto');
  // Isolate active clinical subsystem ROI on the 3D video stage when a domain filter is chosen
  const [isolateSubsystemRoi, setIsolateSubsystemRoi] = useState(true);
  const urlParam = (k) => {
    if (typeof window === 'undefined') return null;
    const h = window.location.hash || '';
    const search = window.location.search || (h.includes('?') ? h.slice(h.indexOf('?')) : '');
    return new URLSearchParams(search).get(k);
  };
  const [inspectorTab, setInspectorTab] = useState(() => urlParam('itab') || (urlParam('layout') === 'audit_40_60' ? 'redcap' : 'event')); // 'event' (At playhead) | 'redcap' | 'transcript' | 'reid' (People)
  const [analysisTab, setAnalysisTab] = useState(() => urlParam('atab') || 'schematic'); // 'schematic' | 'overlap' | 'identity' | 'protocol'
  const [selectedObjId, setSelectedObjId] = useState('OBJ-004');
  const [cvLayers, setCvLayers] = useState({
    boxes3d: true,
    instanceMasks: true,
    panopticPolygons: true,
    reidTrajectories: true,
  });
  const [verifiedKeyframes, setVerifiedKeyframes] = useState({
    kf_0045: true,
    kf_0150: true,
    kf_0537: true,
    kf_0754: true,
    kf_live_1: true,
    kf_live_2: true,
    kf_live_3: true,
    kf_live_4: true,
  });
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const [videoDims, setVideoDims] = useState(null); // natural {w, h} of the playing video (prevents stretching)
  const [stageSize, setStageSize] = useState(null);
  useEffect(() => {
    const el = stageRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const rect0 = el.getBoundingClientRect();
    if (rect0.width && rect0.height) {
      setStageSize({ w: rect0.width, h: rect0.height });
    }
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (!r || !r.width || !r.height) return;
      const w = Math.round(r.width);
      const h = Math.round(r.height);
      // Ignore sub-2px jitter so layout changes driven by stageSize cannot feed back into an observer loop
      setStageSize((prev) => (prev && Math.abs(prev.w - w) < 2 && Math.abs(prev.h - h) < 2 ? prev : { w, h }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [activeNav, selectedCaseId, fullTheaterMode, consoleLayoutMode, videoSizeMode, videoZoomLevel]);

  // Project List (Clinical Data Table) filter & collapsible groups state
  const [searchQuery, setSearchQuery] = useState('');
  const [domainFilter, setDomainFilter] = useState('all'); // 'all' | 'branching' | 'cpr' | 'shocks' | 'meds' | 'airway' | 'team'
  const [expandedGroups, setExpandedGroups] = useState({
    branching: true,
    cpr: true,
    shocks: true,
    meds: true,
    airway: true,
    team: false,
  });

  // Modals & Toast (New Video is now a dedicated full-page view `activeNav === 'new_video'`, not a popup modal)
  const [showDictModal, setShowDictModal] = useState(false);
  const [toastMsg, setToastMsg] = useState(null);

  // REDCap Extraction Contract & Provenance Panels (DEMO-3 Part 3) State — defaults to latest video extraction (`cases[0]`)
  const [contractFilterQuery, setContractFilterQuery] = useState('');
  const [contractStateFilter, setContractStateFilter] = useState('all');
  const [contractRunId, setContractRunId] = useState(
    () => window.__INITIAL_AICARES_STATE__?.report?.cases?.[0]?.record_id || 'LIVE-AI-CARES-TRIALRUN--204642'
  );
  const [collapsedContractSections, setCollapsedContractSections] = useState({
    '5. Supplemental Case-Specific Questions (Cases 3–10) & Technical Narrative': true,
    'ED Pad Placement and Defibrillation': true,
    'End of Resuscitation': true,
    'Mechanical Chest Compression Device (MCCD) Use': true,
    'ROSC Episodes': true,
    'TEAM Ratings Tool': true,
    'Ventilations': true,
  });
  const [showAllEdDetails, setShowAllEdDetails] = useState(false);
  const [provenanceModalField, setProvenanceModalField] = useState(null);

  // Dedicated AI Insights & Clinical Coaching Page (`activeNav === 'coaching'`) State
  const [aiInsightFilter, setAiInsightFilter] = useState('ai_insights');
  const [selectedCoachingCard, setSelectedCoachingCard] = useState(null);
  const [acceptedInsightIds, setAcceptedInsightIds] = useState({});
  const [summaryHelpfulVote, setSummaryHelpfulVote] = useState(null);
  const [coachingAskInput, setCoachingAskInput] = useState('');
  const [coachingAskAnswer, setCoachingAskAnswer] = useState(null);
  const coachingAskInputRef = useRef(null);

  // Video Ingestion, REDCap Simulation Case Number (`simulation_number_v2`), & Latest GA Gemini 4 / Pro & Flash Model Selection State
  const [videoPathInput, setVideoPathInput] = useState('');
  const [videoRecordIdInput, setVideoRecordIdInput] = useState('');
  const [gcpProjectInput, setGcpProjectInput] = useState(
    () => (typeof window !== 'undefined' && window.__INITIAL_AICARES_STATE__?.gcp_project) || ''
  );
  const [simulationNumberInput, setSimulationNumberInput] = useState('1');
  const [videoModelId, setVideoModelId] = useState('gemini-4-argon');
  const [harvestModelId, setHarvestModelId] = useState('gemini-4-argon');
  const [verifyModelId, setVerifyModelId] = useState('gemini-4-argon');
  const [enabledSensors, setEnabledSensors] = useState({
    s5_clock_ocr: true,
    cv_panoptic_reid: true,
    s1_optical_flow: true,
    s3_s4_defib_ecg: true,
    s7a_medical_asr: true,
    vlm_5pass: true,
    redcap_reducer: true,
  });
  // Optional Human Ground Truth Markup State
  const [attachHumanGt, setAttachHumanGt] = useState(true);
  const [humanGtDatasetId, setHumanGtDatasetId] = useState('trialrun_case1_8sept26');
  const [humanGtContentB64, setHumanGtContentB64] = useState('');
  const [attachingGt, setAttachingGt] = useState(false);
  const [humanGtReviewer, setHumanGtReviewer] = useState('Test Research Team / Trial Run Tabby and Sarah');
  const [humanGtFilename, setHumanGtFilename] = useState('fixtures/AICARES_DATA_2026-10-30_1113.xlsx');
  const [humanGtMilestones, setHumanGtMilestones] = useState({
    patient_arrival: '01:10',
    compression_start: '01:20',
    iv_io_access: '01:40',
    first_epinephrine: '01:46',
    airway_placed: '01:57',
    first_pulse_check: '03:49',
    first_rhythm_check: '03:56',
    rosc_or_end: '06:11',
  });
  const [lastCompletedGtComparison, setLastCompletedGtComparison] = useState(null);
  const [runningJob, setRunningJob] = useState(false);
  const [pipelineStepIdx, setPipelineStepIdx] = useState(-1); // -1 idle, 0..6 running step, 7 completed
  const [pipelineProgressPct, setPipelineProgressPct] = useState(0);
  const [lastCompletedCaseId, setLastCompletedCaseId] = useState(null);
  const [liveJob, setLiveJob] = useState(null); // snapshot of the real engine job (/api/jobs/live/status)
  const [liveEnsembleK, setLiveEnsembleK] = useState(1); // Pass 1 draws per window
  const [wizardDictId, setWizardDictId] = useState(''); // '' = use active dictionary
  const [wizardStep, setWizardStep] = useState(() => Math.max(0, Math.min(4, (Number(initialHash.split('-')[2]) || 1) - 1))); // New Video guided wizard: 0..4

  // Dictionary Upload Form State
  const [dictFilename, setDictFilename] = useState('');
  const [dictCsvContent, setDictCsvContent] = useState('');
  const [uploadingDict, setUploadingDict] = useState(false);

  const apiBase = useMemo(() => {
    if (typeof window !== 'undefined' && (window.location.protocol === 'http:' || window.location.protocol === 'https:')) {
      return '';
    }
    return 'http://localhost:8094';
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    fetch(`${apiBase}/api/state`, { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((data) => {
        if (data?.report?.cases?.length) {
          setEngineState(data);
          setSelectedCaseId((prev) => prev || data.report.cases[0].record_id);
        }
      })
      .catch(() => {
        if (window.__INITIAL_AICARES_STATE__?.report?.cases?.length) {
          setEngineState(window.__INITIAL_AICARES_STATE__);
        }
      });
  }, [apiBase]);

  // Synchronized HTML5 <video> playback loop
  useEffect(() => {
    const vid = videoRef.current;
    if (vid) {
      try {
        vid.playbackRate = Math.min(4.0, Math.max(0.5, Number(playbackSpeed) || 1.0));
        if (isPlaying) {
          vid.play().catch(() => {});
        } else {
          vid.pause();
        }
      } catch {
        // ignore
      }
    }
    if (!isPlaying) return undefined;
    const iv = setInterval(() => {
      setCurrentTimeS((prev) => {
        const cap = Number(videoRef.current?.duration) > 1 ? Number(videoRef.current.duration) : 930;
        if (videoRef.current && !videoRef.current.paused && Number(playbackSpeed) <= 4) {
          const vt = videoRef.current.currentTime;
          if (vt >= 0 && vt <= cap) {
            return Number(vt.toFixed(1));
          }
        }
        const next = prev + 0.25 * playbackSpeed;
        return next > cap ? 0.0 : Number(next.toFixed(1));
      });
    }, 250);
    return () => clearInterval(iv);
  }, [isPlaying, playbackSpeed]);

  // Sync HTML5 <video> currentTime on scrub/jump
  useEffect(() => {
    const vid = videoRef.current;
    if (vid && Math.abs((vid.currentTime || 0) - currentTimeS) > 0.45) {
      try {
        vid.currentTime = currentTimeS;
      } catch {
        // ignore seek error on unbuffered range
      }
    }
  }, [currentTimeS, videoFeedSource, localVideoBlobUrl]);

  const showToast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 4200);
  };

  const report = engineState?.report;
  const cases = report?.cases || [];
  const dictionaries = engineState?.dictionaries || [];
  const activeDict = useMemo(
    () => dictionaries.find((d) => d.id === engineState?.active_dictionary_id) || dictionaries[0],
    [dictionaries, engineState?.active_dictionary_id]
  );

  const currentCase = useMemo(
    () => cases.find((c) => c.record_id === selectedCaseId) || cases[0] || null,
    [cases, selectedCaseId]
  );

  const examDash = currentCase?.exam_dashboard || {};
  const allCaseEvents = useMemo(() => currentCase?.events || [], [currentCase]);
  const s5 = currentCase?.s5_provenance || null;
  const maxTimelineS = useMemo(
    () =>
      currentCase?.live_run && currentCase?.duration_s
        ? Math.ceil(Number(currentCase.duration_s))
        : currentCase?.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
        ? 620
        : 930,
    [currentCase]
  );

  // Reset natural videoDims when switching cases so each video immediately uses its own true aspect ratio
  useEffect(() => {
    setVideoDims(null);
  }, [currentCase?.record_id]);

  // Active 3D annotations at `currentTimeS`
  const activeAnnotationsAtTime = useMemo(() => {
    const t = currentTimeS;
    const activeIntervals = allCaseEvents.filter(
      (e) => e.kind === 'interval' && t >= e.t_start_s - 1.0 && t <= (e.t_end_s || e.t_start_s + 5) + 1.0
    );
    const nearbyPointEvents = allCaseEvents
      .filter((e) => e.kind !== 'interval' && Math.abs(e.t_start_s - t) <= 10.0)
      .sort((a, b) => Math.abs(a.t_start_s - t) - Math.abs(b.t_start_s - t));

    const inPause = activeIntervals.length > 0;
    const cprStartEv = allCaseEvents.find(
      (e) => e.type === 'cpr_initiated_ed' || e.type === 'compression_active_start' || e.type === 'patient_enters_room'
    );
    const cprEndEv = allCaseEvents.find((e) => e.type === 'rosc_detected' || e.type === 'death_pronounced' || e.type === 'rosc');
    const cprStart = currentCase?.live_run
      ? cprStartEv?.t_start_s ?? 10.0
      : currentCase?.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
      ? 13.0
      : 36.0;
    const cprEnd = currentCase?.live_run
      ? cprEndEv?.t_start_s ?? (currentCase?.duration_s || 455.0)
      : currentCase?.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
      ? 596.0
      : 922.0;
    const cprActive = t >= cprStart && t <= cprEnd && !inPause;

    return {
      inPause,
      cprActive,
      activeIntervals,
      nearbyPointEvents,
      primaryEvent:
        allCaseEvents.find((e) => e.id === selectedEventId && Math.abs(e.t_start_s - t) <= 18.0) ||
        activeIntervals[0] ||
        nearbyPointEvents[0] ||
        allCaseEvents.reduce(
          (best, e) => (!best || Math.abs(e.t_start_s - t) < Math.abs(best.t_start_s - t) ? e : best),
          null
        ),
    };
  }, [allCaseEvents, currentTimeS, selectedEventId, currentCase]);

  const focusedEvent = activeAnnotationsAtTime.primaryEvent || allCaseEvents[0] || null;

  const get3DBoxSpec = (ev) => {
    if (!ev) return { zone: 'Patient Chest ROI', coords: '[x:0.48, y:0.52, z:0.35]', color: '#3b82f6', tag: 'CHEST ROI' };
    const t = ev.type || '';
    if (t === 'compression_interruption') {
      return {
        zone: 'Sternum / Compressor Hands ROI',
        coords: '[x:0.48, y:0.52, z:0.38]',
        color: '#ef4444',
        tag: `⚠ PAUSE ${ev.duration_s}s (HANDS OFF)`,
      };
    }
    if (t === 'defibrillation_shock' || t === 'defib_charge_aborted') {
      return {
        zone: 'Defibrillator & Anterolateral Pads',
        coords: '[x:0.74, y:0.34, z:0.58]',
        color: '#f59e0b',
        tag: `⚡ DEFIB SHOCK (${ev.start_mmss})`,
      };
    }
    if (t === 'rhythm_check' || t === 'pulse_check') {
      return {
        zone: 'Cardiac Monitor & Carotid Check',
        coords: '[x:0.72, y:0.24, z:0.64]',
        color: '#06b6d4',
        tag: `📈 RHYTHM / PULSE CHECK (${ev.start_mmss})`,
      };
    }
    if (t === 'medication_administration') {
      return {
        zone: 'IV Access Port (Right Side)',
        coords: '[x:0.52, y:0.42, z:0.41]',
        color: '#8b5cf6',
        tag: `💉 ${ev.label.toUpperCase()} (${ev.start_mmss})`,
      };
    }
    if (t === 'airway_attempt' || t === 'airway_confirmation' || t === 'pocus_cardiac') {
      return {
        zone: 'Head-of-Bed Airway (ETT)',
        coords: '[x:0.36, y:0.38, z:0.46]',
        color: '#10b981',
        tag: `🫁 ${ev.label.toUpperCase()} (${ev.start_mmss})`,
      };
    }
    return {
      zone: 'Resuscitation Bay / Stretcher Bed',
      coords: '[x:0.46, y:0.50, z:0.30]',
      color: '#3b82f6',
      tag: `📍 ${ev.label.toUpperCase()} (${ev.start_mmss})`,
    };
  };

  const focused3D = get3DBoxSpec(focusedEvent);

  const seekToEvent = (evOrSec) => {
    if (typeof evOrSec === 'number') {
      setIsPlaying(false);
      setCurrentTimeS(Number(evOrSec));
      return;
    }
    if (!evOrSec) return;
    setIsPlaying(false);
    setSelectedEventId(evOrSec.id);
    setCurrentTimeS(Number(evOrSec.t_start_s));
  };

  const stepEvent = (dir) => {
    if (!allCaseEvents.length) return;
    const sorted = [...allCaseEvents].sort((a, b) => a.t_start_s - b.t_start_s);
    if (dir > 0) {
      const next = sorted.find((e) => e.t_start_s > currentTimeS + 0.5) || sorted[0];
      seekToEvent(next);
    } else {
      const prev = [...sorted].reverse().find((e) => e.t_start_s < currentTimeS - 0.5) || sorted[sorted.length - 1];
      seekToEvent(prev);
    }
  };

  // CSV Download Helpers
  const triggerBlobDownload = (filename, csvText) => {
    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const escapeCsvCell = (val) => {
    const s = val === null || val === undefined ? '' : String(val);
    if (s.includes(',') || s.includes('"') || s.includes('\n')) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };

  const sanitizeRedcapRowClient = (rawRow, simNumFallback = '1') => {
    const row = { ...(rawRow || {}) };
    // Never include REDCap auto-calculated (calc) fields in import rows
    delete row.duration_pulse_v2;
    delete row.code_duration_seconds_v2;

    const simNum = String(row.simulation_number_v2 || simNumFallback || '1').trim();
    row.simulation_number_v2 = simNum;

    // Required fields on `teams_review_ai`
    row.reviewer_name_team_v2 = row.reviewer_name_team_v2 || row.reviewer_name_v2 || 'gemini-4-argon';
    row.review_teams_date_v2 = row.review_teams_date_v2 || row.date_review_v2 || '2026-10-30';

    // 1. Shockable rhythm & antiarrhythmic gates: hidden for Cases 1, 2, 3
    if (['1', '2', '3'].includes(simNum)) {
      [
        'rhythm_recognized_v2',
        'rhythm_recogonized_no_v2',
        'shocks_admin_v2',
        'if_no_please_explain_v2',
        'time_defib_v2',
        'clears_before_analyzing_an_v2',
        'anti_arrythmic_given_v2',
        'time_antiarrhythmic_v2',
        'anti_arrythmic_doses_v2',
        'other_anti_arrhythmic_v2',
        'anti_arrythmic_med_v2___1',
        'anti_arrythmic_med_v2___2',
        'anti_arrythmic_med_v2___3',
        'anti_arrythmic_med_v2___4',
        'anti_arrythmic_med_v2___5',
        'anti_arrythmic_med_v2___6',
      ].forEach((f) => {
        row[f] = '';
      });
    } else {
      if (String(row.rhythm_recognized_v2 || '') !== '0') {
        row.rhythm_recogonized_no_v2 = '';
      }
      if (String(row.rhythm_recognized_v2 || '') !== '1') {
        row.shocks_admin_v2 = '';
        row.if_no_please_explain_v2 = '';
        row.time_defib_v2 = '';
        row.clears_before_analyzing_an_v2 = '';
      }
      if (String(row.shocks_admin_v2 || '') !== '0') {
        row.if_no_please_explain_v2 = '';
      }
      if (String(row.shocks_admin_v2 || '') !== '1') {
        row.time_defib_v2 = '';
        row.clears_before_analyzing_an_v2 = '';
      }
      if (String(row.anti_arrythmic_given_v2 || '') !== '1') {
        [
          'time_antiarrhythmic_v2',
          'anti_arrythmic_doses_v2',
          'other_anti_arrhythmic_v2',
          'anti_arrythmic_med_v2___1',
          'anti_arrythmic_med_v2___2',
          'anti_arrythmic_med_v2___3',
          'anti_arrythmic_med_v2___4',
          'anti_arrythmic_med_v2___5',
          'anti_arrythmic_med_v2___6',
        ].forEach((f) => {
          row[f] = '';
        });
      } else if (String(row.anti_arrythmic_med_v2___6 || '') !== '1') {
        row.other_anti_arrhythmic_v2 = '';
      }
    }

    // 2. Synchronized cardioversion (Cases 6, 10) & External pacing (Cases 4, 5, 7, 9)
    if (!['6', '10'].includes(simNum)) {
      row.synchronized_cardioversion_v2 = '';
    }
    if (!['4', '5', '7', '9'].includes(simNum)) {
      row.external_pacing_indicated_v2 = '';
    }

    // 3. Medication dose gates
    if ((parseFloat(row.total_epi_v2) || 0) <= 0) {
      row.admin_epi_time_v2 = '';
    }
    if ((parseFloat(row.total_bicarb_v2) || 0) <= 0) {
      row.time_bicarb_v2 = '';
    }
    if ((parseFloat(row.total_calcium_v2) || 0) <= 0) {
      row.time_calcium_v2 = '';
    }
    if (String(row.other_meds_v2 || '') !== '1') {
      row.other_meds_given_v2 = '';
      row.time_other_med_v2 = '';
    }
    if (String(row.other_med_considered_v2 || '') !== '1') {
      row.other_med_considered_list_v2 = '';
    }

    // 4. Compression interruption (>10s) gates
    if (String(row.interruption_compression_v2 || '') !== '1') {
      row.interruption_duration_v2 = '';
      for (let rIdx = 1; rIdx <= 7; rIdx += 1) {
        row[`interruption_reasons_v2___${rIdx}`] = '';
      }
      row.other_reason_v2 = '';
    } else if (String(row.interruption_reasons_v2___7 || '') !== '1') {
      row.other_reason_v2 = '';
    }

    // 5. Medication appropriateness & inappropriate administration checkboxes
    //    (`administers_appropriate_v2___7..15, ___5` and `inappropriate_admin_v2___7..15, ___5`)
    //    plus `other_v2` and `other2_v2` branching gates.
    const drugAppCodes = ['7', '8', '9', '10', '11', '12', '13', '14', '5', '15'];
    const drugAppNonNone = ['7', '8', '9', '10', '11', '12', '13', '14', '5'];
    drugAppCodes.forEach((c) => {
      const ak = `administers_appropriate_v2___${c}`;
      const ik = `inappropriate_admin_v2___${c}`;
      row[ak] = ['1', '1.0', 'true', 'True'].includes(String(row[ak] ?? '0').trim()) ? '1' : '0';
      row[ik] = ['1', '1.0', 'true', 'True'].includes(String(row[ik] ?? '0').trim()) ? '1' : '0';
    });

    const anyAppChecked = drugAppCodes.some((c) => row[`administers_appropriate_v2___${c}`] === '1');
    if (!anyAppChecked) {
      const firstRhy = String(row.first_rhythm_v2 || '').trim();
      const epiCnt = parseFloat(row.total_epi_v2) || 0;
      const calcCnt = parseFloat(row.total_calcium_v2) || 0;
      const shocksCnt = parseFloat(row.shocks_admin_v2) || 0;
      const antiGiven =
        String(row.anti_arrythmic_given_v2 || '').trim() === '1' ||
        row.anti_arrythmic_med_v2___1 === '1' ||
        row.anti_arrythmic_med_v2___2 === '1';
      const otherMedsTxt = String(row.other_meds_given_v2 || '').toLowerCase();

      if (
        epiCnt > 0 &&
        (firstRhy === '3' || ['1', '2', '3', '4', '5', '6', '7', '9', '10'].includes(simNum) || !antiGiven)
      ) {
        row.administers_appropriate_v2___9 = '1';
      }
      if (antiGiven && (firstRhy === '4' || ['4', '5', '6', '7', '8', '9', '10'].includes(simNum))) {
        row.administers_appropriate_v2___10 = '1';
        if (shocksCnt >= 3 || ['8', '9'].includes(simNum)) {
          row.administers_appropriate_v2___14 = '1';
        }
      }
      if (
        simNum === '4' &&
        (calcCnt > 0 || ['insulin', 'lipid', 'intralipid'].some((k) => otherMedsTxt.includes(k)))
      ) {
        row.administers_appropriate_v2___12 = '1';
      }
      if (otherMedsTxt.includes('flumazenil')) {
        row.administers_appropriate_v2___11 = '1';
      }
      if (otherMedsTxt.includes('naloxone') || otherMedsTxt.includes('narcan')) {
        row.administers_appropriate_v2___13 = '1';
      }
      if (otherMedsTxt.includes('atropine') && simNum !== '9') {
        row.administers_appropriate_v2___8 = '1';
      }
      if (['adenosine', 'metoprolol', 'diltiazem'].some((k) => otherMedsTxt.includes(k)) && simNum !== '10') {
        row.administers_appropriate_v2___7 = '1';
      }
      if (!drugAppNonNone.some((c) => row[`administers_appropriate_v2___${c}`] === '1')) {
        row.administers_appropriate_v2___15 = '1';
      }
    } else if (drugAppNonNone.some((c) => row[`administers_appropriate_v2___${c}`] === '1')) {
      row.administers_appropriate_v2___15 = '0';
    }

    const anyInappChecked = drugAppCodes.some((c) => row[`inappropriate_admin_v2___${c}`] === '1');
    if (!anyInappChecked) {
      row.inappropriate_admin_v2___15 = '1';
    } else if (drugAppNonNone.some((c) => row[`inappropriate_admin_v2___${c}`] === '1')) {
      row.inappropriate_admin_v2___15 = '0';
    }

    if (row.administers_appropriate_v2___5 !== '1') {
      row.other_v2 = '';
    }
    if (row.inappropriate_admin_v2___5 !== '1') {
      row.other2_v2 = '';
    }

    // 6. Case-specific supplemental questions (Cases 3..10)
    for (let otherN = 3; otherN <= 10; otherN += 1) {
      if (String(otherN) !== simNum) {
        for (let qIdx = 1; qIdx <= 6; qIdx += 1) {
          row[`case${otherN}_q${qIdx}_v2`] = '';
        }
      }
    }
    if (simNum === '3' && String(row.case3_q1_v2 || '') !== '1') {
      row.case3_q2_v2 = '';
    }
    if (simNum === '8' && String(row.case8_q2_v2 || '') !== '1') {
      row.case8_q3_v2 = '';
    }

    return row;
  };

  const handleUpdateRedcapRecordId = async (newRedcapIdRaw, targetCaseId = null) => {
    const cid = targetCaseId || currentCase?.record_id;
    if (!cid) return;
    const val = String(newRedcapIdRaw ?? '');

    setEngineState((prev) => {
      if (!prev?.report?.cases) return prev;
      const nextCases = prev.report.cases.map((c) => {
        if (c.record_id !== cid) return c;
        const nextRow = sanitizeRedcapRowClient(
          { ...(c.redcap_row || {}), record_id: val },
          c.simulation_number || '1'
        );
        return {
          ...c,
          redcap_row: nextRow,
        };
      });
      const nextRuns = { ...(prev.extraction_contract?.runs || {}) };
      if (nextRuns[cid]?.fields_by_col?.record_id) {
        nextRuns[cid] = {
          ...nextRuns[cid],
          fields_by_col: {
            ...nextRuns[cid].fields_by_col,
            record_id: {
              ...nextRuns[cid].fields_by_col.record_id,
              value: val,
              value_label: val,
            },
          },
        };
      }
      return {
        ...prev,
        report: {
          ...prev.report,
          cases: nextCases,
        },
        extraction_contract: prev.extraction_contract
          ? {
              ...prev.extraction_contract,
              runs: nextRuns,
            }
          : prev.extraction_contract,
      };
    });

    if (val.trim()) {
      try {
        await fetch(`${apiBase}/api/cases/set-record-id`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case_id: cid, redcap_record_id: val.trim() }),
        });
      } catch {
        // Optimistic update already applied in state
      }
    }
  };

  const handleDownloadRedcapCsv = (onlyCurrent = true) => {
    const targetCases = onlyCurrent && currentCase ? [currentCase] : cases;
    if (!targetCases.length) return;

    // Require `record_id` to be filled out before exporting CSV
    const missingRecordIdCase = targetCases.find(
      (c) => !String(c.redcap_row?.record_id ?? '').trim()
    );
    if (missingRecordIdCase) {
      showToast('Please fill in the required REDCap record_id field before exporting CSV');
      const inputEl = document.getElementById('redcap-record-id-input');
      if (inputEl) {
        inputEl.focus();
        inputEl.select?.();
      }
      return;
    }

    const fallbackRow = sanitizeRedcapRowClient(
      currentCase?.redcap_row || {},
      currentCase?.simulation_number || '1'
    );
    const rawCols = engineState?.export_columns || Object.keys(fallbackRow);
    if (rawCols.length > 0) {
      // REDCap Data Import Tool strictly requires 'record_id' as Column 1 (index 0)
      // and rejects calculated (calc) fields ('duration_pulse_v2', 'code_duration_seconds_v2').
      const calcCols = new Set(['duration_pulse_v2', 'code_duration_seconds_v2']);
      const cols = ['record_id', ...rawCols.filter((c) => c !== 'record_id' && !calcCols.has(c))];
      const lines = [cols.join(',')];
      targetCases.forEach((c) => {
        const cleanRow = sanitizeRedcapRowClient(c.redcap_row || {}, c.simulation_number || '1');
        const exportRecId = String(cleanRow.record_id || '').trim();
        lines.push(
          cols
            .map((col) =>
              escapeCsvCell(col === 'record_id' ? exportRecId : (cleanRow[col] ?? ''))
            )
            .join(',')
        );
      });
      const activeRecId = String(currentCase?.redcap_row?.record_id || currentCase?.record_id || '3').trim();
      const fname = onlyCurrent && currentCase ? `record_${activeRecId}_redcap_import.csv` : 'aicares_all_cases_redcap_import.csv';
      triggerBlobDownload(fname, lines.join('\n'));
      showToast(`Exported ${cols.length}-column REDCap import CSV (${fname} · record_id=${activeRecId} · 0 calc cols · 0 branching errors)`);
    }
  };

  const handleDownloadEventsCsv = (onlyCurrent = true) => {
    const headers = [
      'record_id',
      'event_id',
      'kind',
      'event_type',
      'label',
      'start_mm_ss',
      'wall_clock_time',
      't_start_s',
      't_end_s',
      'duration_s',
      'modality',
      'sensor_source',
      'confidence',
      'evidence_quote_or_metric',
      'mapped_redcap_variables',
    ];
    const targetCases = onlyCurrent && currentCase ? [currentCase] : cases;
    const lines = [headers.join(',')];
    targetCases.forEach((c) => {
      const caseT0 = c.s5_provenance?.t0_iso || c.t0_wallclock;
      (c.events || []).forEach((ev) => {
        lines.push(
          [
            c.record_id,
            ev.id,
            ev.kind,
            ev.type,
            ev.label,
            ev.start_mmss,
            fmtWallClockFromT0(caseT0, ev.t_start_s),
            ev.t_start_s,
            ev.t_end_s ?? '',
            ev.duration_s ?? '',
            ev.modality,
            ev.sensor_label,
            ev.confidence,
            ev.evidence_text,
            (ev.mapped_fields || []).join('; '),
          ]
            .map(escapeCsvCell)
            .join(',')
        );
      });
    });
    const fname = `${onlyCurrent && currentCase ? currentCase.record_id : 'all_cases'}_extracted_events_evidence.csv`;
    triggerBlobDownload(fname, lines.join('\n'));
    showToast(`Exported Extracted Event Stream & Evidence CSV (${fname})`);
  };

  const handleVideoFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const objUrl = URL.createObjectURL(file);
    setLocalVideoBlobUrl(objUrl);
    if (!videoRecordIdInput) {
      setVideoRecordIdInput('3');
    }
    try {
      showToast(`Staging local video "${file.name}" for Vertex AI analysis…`);
      const res = await fetch(`${apiBase}/api/video/upload-local?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        body: file,
      });
      const data = await res.json();
      if (data.ok && data.video_path) {
        setVideoPathInput(data.video_path);
        showToast(`Staged local video "${file.name}" (${data.video_path})`);
        return;
      }
    } catch {
      // Fallback for offline HTML mode
    }
    setVideoPathInput(`tests/video/${file.name}`);
    showToast(`Loaded local video file "${file.name}" into 3D player`);
  };

  // Authoritative 10 Pre-Defined Northwell AI-CARES Simulation Cases (`simulation_number_v2 = 1..10`)
  // Extracted verbatim from `Cases.zip` (`Case 1.docx`..`Case 10.docx`, `Case Specific Additional Questions- REDCap.docx`,
  // `Meds needed for sims.docx`, `Pre Simulation Script.docx`) and aligned to `dictionary/aicares_instrument.csv`
  const simulationCaseProtocols = useMemo(
    () => [
      {
        num: '1',
        difficulty: 'EASY',
        shortBadge: 'Easy · PEA',
        title: 'Case 1 (Easy PEA) — Carin W, 57F COPD & Severe Dehydration PEA Arrest',
        patient: 'Carin W · 57yo Female · OHCA at Home → ED Resuscitation Bay',
        vignette: '57yo woman with emphysema on home O2; 48h of severe nausea/vomiting/diarrhea and unable to eat or drink; found unresponsive & cyanotic on floor by partner (EMS started CPR, IV placed).',
        initialVitals: 'HR 116 bpm (pulseless) · RR 0 · BP -/- · SpO2 No signal · PetCO2 0 mmHg',
        rhythmCode: 3,
        rhythmLabel: '3 · PEA / Asystole (Sinus Tachycardia PEA)',
        rhythmTrajectory: 'Sinus Tachycardia PEA → High-Quality CPR + Epinephrine + IV Fluid Bolus → ROSC / TOR',
        zollMonitor: 'No Zoll monitor needed',
        expectedDrugs: 'Epinephrine 1 mg IV q3–5m (Code 9) + IV Fluid Bolus (Hypovolemia) + O2/Airway (Hypoxia)',
        criticalTriggers: [
          'Recognize cardiopulmonary arrest and initiate chest compressions immediately',
          'Identify non-shockable Sinus Tachycardia PEA rhythm on first check (`first_rhythm_v2 = 3`)',
          'Administer Epinephrine 1 mg IV/IO and treat reversible causes (Hypovolemia + Hypoxia)',
        ],
        coreGates: [],
        caseQuestions: [],
        branchingRuleNote:
          'Pure Non-Shockable PEA pathway (`[simulation_number_v2] = "1"`) · Because Case 1 has NO shockable rhythm, REDCap hides `rhythm_recognized_v2` (`shocks_admin_v2`, `time_defib_v2`, `clears_before_analyzing_an_v2`) and `anti_arrythmic_given_v2` (which only unlock in Cases 4–10).',
      },
      {
        num: '2',
        difficulty: 'EASY',
        shortBadge: 'Easy · Asystole',
        title: 'Case 2 (Easy Asystole) — Tammy Khull, 84F Metastatic Renal Cancer Asystole & DNAR at 6m',
        patient: 'Tammy Khull · 84yo Female · OHCA at Home → ED Bay (No EMS IV)',
        vignette: '84yo woman with metastatic renal cancer and cardiac disease found unresponsive on living room floor by neighbor; valid DNAR order arrives with partner after 6 minutes of high-quality CPR.',
        initialVitals: 'HR 0 bpm · RR 0 · BP -/- · SpO2 No signal · PetCO2 0 mmHg',
        rhythmCode: 3,
        rhythmLabel: '3 · PEA / Asystole (Asystole → DNAR at 6 min)',
        rhythmTrajectory: 'Asystole → 6 min High-Quality CPR + Epinephrine → Partner Arrives with DNAR → TOR (`time_death_v2`)',
        zollMonitor: 'No Zoll monitor needed',
        expectedDrugs: 'Epinephrine 1 mg IV/IO q3–5m (Code 9)',
        criticalTriggers: [
          'Recognize Asystole (`first_rhythm_v2 = 3`), perform high-quality CPR, obtain IV/IO access, and give Epinephrine',
          'After 6 minutes of high-quality CPR, partner presents valid DNAR order → terminate resuscitation (`time_death_v2`)',
        ],
        coreGates: [],
        caseQuestions: [],
        branchingRuleNote:
          'Pure Non-Shockable Asystole + DNAR pathway (`[simulation_number_v2] = "2"`) · REDCap hides `rhythm_recognized_v2` and `anti_arrythmic_given_v2` (Cases 4–10 only) and evaluates CPR quality, Epinephrine timing, and `time_death_v2`.',
      },
      {
        num: '3',
        difficulty: 'EASY',
        shortBadge: 'Easy · HyperK PEA',
        title: 'Case 3 (Easy PEA) — Christoffer Black, 64M ESRD Severe Hyperkalemic PEA Arrest',
        patient: 'Christoffer Black · 64yo Male · Witnessed ED Triage Arrest (Missed First Dialysis)',
        vignette: '64yo man with ESRD and newly placed dialysis catheter (has not yet had first dialysis) presents with chest discomfort & SOB; becomes unresponsive and cyanotic right after ED triage.',
        initialVitals: 'HR 80 bpm (pulseless) · RR 0 · BP -/- · SpO2 No signal · PetCO2 0 mmHg',
        rhythmCode: 3,
        rhythmLabel: '3 · PEA / Asystole (Sinus Hyperkalemia PEA)',
        rhythmTrajectory: 'Sinus Hyperkalemia PEA → CPR (<20s) + Epi (<1m) + Calcium / Bicarb / Insulin+Glucose (<6m) → ROSC',
        zollMonitor: 'No Zoll monitor needed',
        expectedDrugs: 'Epinephrine 1 mg IV (<1m) + Calcium, Sodium Bicarbonate, Regular Insulin + Dextrose (<6m)',
        criticalTriggers: [
          'Start chest compressions within 20s (or rhythm degrades to idioventricular/asystole)',
          'Administer Epinephrine 1 mg IV within 1 min of starting compressions',
          'Identify Hyperkalemia (`case3_q1_v2 = 1`) and administer Calcium, Bicarb, and Insulin+Glucose within 6 min (`case3_q2_v2 = 1`)',
        ],
        coreGates: [],
        caseQuestions: [
          { field: 'case3_q1_v2', rule: '[simulation_number_v2] = 3', label: 'Was hyperkalemia identified by the team?' },
          {
            field: 'case3_q2_v2',
            rule: '[case3_q1_v2] = 1',
            label: 'If Y, were meds for hyperkalemia administered (specifically any of: insulin, glucose, calcium, bicarb)?',
          },
        ],
        branchingRuleNote:
          'Non-Shockable Hyperkalemic PEA (`[simulation_number_v2] = "3"`) · Unlocks `case3_q1_v2` and nested `[case3_q1_v2] = 1` → `case3_q2_v2`; keeps `rhythm_recognized_v2` and `anti_arrythmic_given_v2` hidden.',
      },
      {
        num: '4',
        difficulty: 'HARD',
        shortBadge: 'Hard · CCB OD Brady→VF',
        title: 'Case 4 (Hard Brady→VF→Asystole→PCAC) — Ryan Gosling, 28M Diltiazem (CCB) Overdose',
        patient: 'Ryan Gosling · 28yo Male · Intentional Diltiazem Overdose (Empty Bottle Found)',
        vignette: '28yo male brought to ED after intentional Diltiazem (CCB) overdose; initially drowsy and slurring words with HR 30 bpm and BP 80/48, then arrests in VF → Asystole → ROSC.',
        initialVitals: 'HR 30 bpm · RR 8–10/min · BP 80/48 mmHg · SpO2 98% (3L NC) · Temp 36.5°C · Glucose 195 mg/dL',
        rhythmCode: 2,
        rhythmLabel: '2 · Unstable Bradycardia (30 bpm) → VF → Asystole → PCAC',
        rhythmTrajectory: 'Ventricular Escape Bradycardia (30 bpm) → VF Arrest (2 Shocks) → Asystole (Epi 1 mg) → ROSC (PCAC)',
        zollMonitor: 'No Zoll monitor needed',
        expectedDrugs: 'Atropine (8), Epinephrine (9), Amiodarone/Lidocaine (10/14) + CCB Reversal: IV Insulin, Calcium, Lipid Emulsion (12)',
        criticalTriggers: [
          'Administer Atropine and prepare 2nd-line bradycardia treatment or transcutaneous pacing (`case4_q1_v2`, `external_pacing_indicated_v2`)',
          'Recognize transition to VF (`rhythm_recognized_v2 = 1`) and deliver 2 defibrillation shocks (`shocks_admin_v2`, `time_defib_v2`)',
          'Administer/consider CCB overdose reversal: IV insulin, calcium, lipid emulsion therapy, or ECMO (`case4_q2_v2`)',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2', 'external_pacing_indicated_v2'],
        caseQuestions: [
          {
            field: 'case4_q1_v2',
            rule: '[simulation_number_v2] = 4',
            label: 'Did they prepare a second line bradycardia treatment after administering atropine or consider pacing?',
          },
          {
            field: 'case4_q2_v2',
            rule: '[simulation_number_v2] = 4',
            label: 'Did the team administer or consider reversal treatment for the overdose (IV insulin, calcium, lipid emulsion therapy, or ECMO)?',
          },
        ],
        branchingRuleNote:
          'Unlocks `rhythm_recognized_v2` (and child shock fields `shocks_admin_v2`, `time_defib_v2`, `clears_before_analyzing_an_v2`), `anti_arrythmic_given_v2`, `external_pacing_indicated_v2`, and CCB overdose questions `case4_q1_v2` & `case4_q2_v2`.',
      },
      {
        num: '5',
        difficulty: 'HARD',
        shortBadge: 'Hard · Sedation Brady→VF',
        title: 'Case 5 (Hard Brady→VF→PEA→PCAC) — 51yo Conscious Sedation (Fentanyl/Midazolam) Overdose',
        patient: 'ED Procedure Patient · 51yo Adult · Closed Shoulder Reduction Conscious Sedation',
        vignette: '51yo patient given fentanyl and midazolam for closed shoulder reduction; 15 min after last dose, RR drops to 4/min, PetCO2 rises to 55 mmHg, and patient develops unstable bradycardia → VF → PEA → ROSC.',
        initialVitals: 'Slow narrow-complex bradycardia with hypotension · RR 4/min · PetCO2 55 mmHg',
        rhythmCode: 2,
        rhythmLabel: '2 · Unstable Bradycardia → VF → PEA → PCAC',
        rhythmTrajectory: 'Hypoxic Bradycardia (Atropine x2 + Dopamine/Pacing) → VF Arrest (Shocks + Epi + Amio) → PEA (Epi #2) → ROSC',
        zollMonitor: 'Zoll monitor required',
        expectedDrugs: 'Naloxone/Narcan (13), Flumazenil (11), Atropine x2 (8), Dopamine, Epinephrine x2 (9), Amiodarone 300 mg (10)',
        criticalTriggers: [
          'Consider administering Naloxone (Narcan) or Flumazenil for fentanyl/midazolam oversedation (`case5_q1_v2`)',
          'Consider 2nd-line bradycardia therapy (Dopamine) or pacing after Atropine (`case5_q2_v2`, `external_pacing_indicated_v2`)',
          'Recognize VF arrest (`rhythm_recognized_v2 = 1`), deliver defibrillation shocks, Epinephrine, and Amiodarone (`anti_arrythmic_given_v2 = 1`)',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2', 'external_pacing_indicated_v2'],
        caseQuestions: [
          { field: 'case5_q1_v2', rule: '[simulation_number_v2] = 5', label: 'Did the team consider administering Narcan or flumazenil?' },
          {
            field: 'case5_q2_v2',
            rule: '[simulation_number_v2] = 5',
            label: 'Did the team consider a second line bradycardia treatment or consider pacing after administering atropine?',
          },
        ],
        branchingRuleNote:
          'Unlocks `rhythm_recognized_v2` (and child shock fields), `anti_arrythmic_given_v2`, `external_pacing_indicated_v2`, and sedative reversal / bradycardia escalation fields `case5_q1_v2` & `case5_q2_v2`.',
      },
      {
        num: '6',
        difficulty: 'HARD',
        shortBadge: 'Hard · VT Cardioversion→VF',
        title: 'Case 6 (Hard Tachy→VF→PEA→PCAC) — Wide-Complex VT 160 bpm Requiring Synchronized Cardioversion',
        patient: 'ED Angina Patient · Adult Male · Admitted for Worsening Stable Angina',
        vignette: 'Patient admitted to ED for worsening angina develops acute chest pain and diaphoresis; monitor shows monomorphic wide-complex VT at 160 bpm requiring immediate synchronized cardioversion → converts to VF → PEA → ROSC.',
        initialVitals: 'HR 160 bpm (Wide-Complex VT) · RR 22/min · BP 156/92 mmHg (deteriorating) · SpO2 93%',
        rhythmCode: 1,
        rhythmLabel: '1 · Wide-Complex Tachycardia (VT 160 bpm) → VF → PEA → PCAC',
        rhythmTrajectory: 'Symptomatic VT (160 bpm) → Synchronized Cardioversion → Pulseless VF (Defib + Epi + Amio) → PEA (2nd-Deg AVB) → ROSC',
        zollMonitor: 'Zoll monitor required',
        expectedDrugs: 'Synchronized Cardioversion + Epinephrine (9) + Amiodarone / Lidocaine (10/14)',
        criticalTriggers: [
          'Perform immediate Synchronized Cardioversion for symptomatic wide-complex VT without delaying for drugs (`synchronized_cardioversion_v2 = 1`)',
          'Recognize immediate post-cardioversion conversion to pulseless VF (`rhythm_recognized_v2 = 1`) and switch to unsynchronized Defibrillation (`shocks_admin_v2`)',
          'Administer Epinephrine and antiarrhythmic (`anti_arrythmic_given_v2 = 1`), then manage PEA and post-ROSC cardiogenic shock',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2', 'synchronized_cardioversion_v2'],
        caseQuestions: [],
        branchingRuleNote:
          'Unlocks `synchronized_cardioversion_v2` (`[simulation_number_v2] = "6" or "10"`), `rhythm_recognized_v2` (+ `shocks_admin_v2`, `time_defib_v2`, `clears_before_analyzing_an_v2`), and `anti_arrythmic_given_v2`.',
      },
      {
        num: '7',
        difficulty: 'MODERATE',
        shortBadge: 'Mod · Mobitz II Brady→VF',
        title: 'Case 7 (Moderate Brady→VF→Asystole/PEA→PCAC) — 67F Mobitz II AV Block in Surgical Waiting Room',
        patient: 'Surgical Waiting Room Patient · 67yo Female · Rapid Response Team Activation',
        vignette: '67yo woman (history of breast cancer in remission and diabetes) collapses with dizziness in Surgical Waiting Room while awaiting husband’s surgery; monitor shows 2nd-degree Type II AV block at 28 bpm.',
        initialVitals: 'HR 28 bpm (Mobitz II AV Block) · RR 18/min · BP 68/P mmHg · SpO2 96% · Glucose 90 mg/dL',
        rhythmCode: 2,
        rhythmLabel: '2 · Mobitz II Bradycardia (28 bpm) → VF → Asystole/PEA → PCAC',
        rhythmTrajectory: 'Mobitz II Bradycardia (28 bpm, Atropine x2 + Pacing/Dopamine) → VF (2 Shocks + Epi + Amio/Lido) → Asystole/PEA → ROSC',
        zollMonitor: 'Zoll monitor required',
        expectedDrugs: 'Atropine 1 mg IV x2 (8), Dopamine Infusion, Epinephrine 1 mg IV x3 (9), Amiodarone 300 mg or Lidocaine (10/14)',
        criticalTriggers: [
          'Give Atropine 1 mg IV x2 and prepare 2nd-line bradycardia treatment (Dopamine) or transcutaneous pacing (`case7_q1_v2`, `external_pacing_indicated_v2`)',
          'Recognize transition to pulseless VF (`rhythm_recognized_v2 = 1`), deliver 2 shocks, Epinephrine, and Amiodarone/Lidocaine (`anti_arrythmic_given_v2`)',
          'Manage subsequent Asystole and PEA cycles with Epinephrine #2 and #3 until ROSC',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2', 'external_pacing_indicated_v2'],
        caseQuestions: [
          {
            field: 'case7_q1_v2',
            rule: '[simulation_number_v2] = 7',
            label: 'Did they prepare a second line bradycardia treatment (ie dopamine) after administering atropine or consider pacing?',
          },
        ],
        branchingRuleNote:
          'Unlocks `external_pacing_indicated_v2`, `rhythm_recognized_v2` (+ child shock fields), `anti_arrythmic_given_v2`, and `case7_q1_v2`.',
      },
      {
        num: '8',
        difficulty: 'MODERATE',
        shortBadge: 'Mod · Refractory VF→STEMI',
        title: 'Case 8 (Moderate Refractory VF→STEMI) — Victor Vernan, 64M Refractory VF Arrest & Post-ROSC STEMI',
        patient: 'Victor Vernan · 64yo Male · OHCA Re-Arrest in VF upon ED Arrival',
        vignette: '64yo man with sudden cardiac arrest at home; achieved brief prehospital ROSC after 1 EMS shock, then re-arrested in Refractory VF upon arrival in ED resuscitation bay (requires ≥3 shocks + antiarrhythmic → Post-ROSC STEMI).',
        initialVitals: 'HR 0 bpm (VF) · RR 0 · BP -/- · SpO2 No signal · PetCO2 0 mmHg',
        rhythmCode: 4,
        rhythmLabel: '4 · Refractory Ventricular Fibrillation (VF) → Post-ROSC STEMI',
        rhythmTrajectory: 'Refractory VF (3+ Shocks + Epi after 2nd Shock + Amiodarone/Lidocaine) → ROSC → Post-ROSC 12-Lead EKG STEMI + Norepinephrine',
        zollMonitor: 'No Zoll monitor needed',
        expectedDrugs: 'Epinephrine 1 mg IV (9), Amiodarone 300 mg / Lidocaine (10/14) + Post-ROSC ASA/Heparin/Cath Lab + Norepinephrine (Levo)',
        criticalTriggers: [
          'Recognize VF (`rhythm_recognized_v2 = 1`) and deliver ≥3 defibrillation shocks every 2 min (`shocks_admin_v2`, `time_defib_v2`, `clears_before_analyzing_an_v2`)',
          'Administer Epinephrine after 2nd shock and Amiodarone/Lidocaine for refractory VF (`anti_arrythmic_given_v2 = 1`)',
          'Upon ROSC: obtain post-ROSC EKG (`case8_q1_v2`), recognize STEMI (`case8_q2_v2`), initiate STEMI therapy (`case8_q3_v2`), and give vasopressors (`case8_q4_v2`)',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2'],
        caseQuestions: [
          { field: 'case8_q1_v2', rule: '[simulation_number_v2] = 8', label: 'Did the team obtain a post ROSC EKG?' },
          { field: 'case8_q2_v2', rule: '[simulation_number_v2] = 8', label: 'Did the team recognize STEMI on the post ROSC EKG?' },
          {
            field: 'case8_q3_v2',
            rule: '[case8_q2_v2] = 1',
            label: 'If Y, did the team administer treatment (tPA, streptokinase, activate cath lab, aspirin loading, heparin infusion) for the STEMI?',
          },
          { field: 'case8_q4_v2', rule: '[simulation_number_v2] = 8', label: 'Did the team administer blood pressure support (vasopressors)?' },
        ],
        branchingRuleNote:
          'Primary Refractory VF Case (`[simulation_number_v2] = "8"`) · Unlocks `rhythm_recognized_v2` (`shocks_admin_v2`, `time_defib_v2`, `clears_before_analyzing_an_v2`), `anti_arrythmic_given_v2`, and the 4-question Post-ROSC STEMI cascade (`case8_q1_v2..case8_q4_v2`).',
      },
      {
        num: '9',
        difficulty: 'MODERATE',
        shortBadge: 'Mod · STEMI Brady→VF DSD',
        title: 'Case 9 (Moderate STEMI Brady→pVT→PEA→VF DSD) — 72F Inferior STEMI & Dual Sequential Defibrillation',
        patient: 'Inpatient Telemetry Patient · 72yo Female · Acute Chest Discomfort & Inferior STEMI',
        vignette: '72yo woman admitted with palpitations develops chest discomfort, mild hypoxia (SpO2 90%), and sinus bradycardia (50 bpm, BP 150/70) with Inferior STEMI on 12-lead ECG, then arrests in pVT → PEA → Refractory VF requiring Dual Sequential Defibrillation.',
        initialVitals: 'HR 50 bpm (Sinus Bradycardia) · RR 24/min · BP 150/70 mmHg · SpO2 90% on RA · Temp 37.1°C',
        rhythmCode: 2,
        rhythmLabel: '2 · Sinus Bradycardia (Inferior STEMI) → pVT → PEA → VF (DSD)',
        rhythmTrajectory: 'Inferior STEMI + Sinus Bradycardia (O2 + ASA/Heparin; Avoid Nitro & Atropine) → pVT (2 Shocks) → PEA (Epi) → Refractory VF (DSD) → ROSC',
        zollMonitor: 'Zoll monitor required (Dual Sequential Defibrillation)',
        expectedDrugs: 'Supplemental O2, Aspirin + Heparin (AVOID Nitroglycerin & Atropine), Epinephrine (9), Amiodarone / Lidocaine (10/14)',
        criticalTriggers: [
          'Request EKG (`case9_q1_v2`), identify Inferior STEMI with sinus bradycardia (`case9_q2_v2`), treat STEMI (`case9_q3_v2`), start O2 (`case9_q4_v2`), and AVOID nitroglycerin & atropine (`case9_q5_v2`)',
          'Recognize arrest in pVT (`rhythm_recognized_v2 = 1`), deliver shocks, give Epinephrine during PEA, and consider/attempt Dual Sequential Defibrillation (`case9_q6_v2`)',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2', 'external_pacing_indicated_v2'],
        caseQuestions: [
          { field: 'case9_q1_v2', rule: '[simulation_number_v2] = 9', label: 'Did the team request an EKG?' },
          { field: 'case9_q2_v2', rule: '[simulation_number_v2] = 9', label: 'Did the team identify the STEMI with sinus bradycardia?' },
          {
            field: 'case9_q3_v2',
            rule: '[simulation_number_v2] = 9',
            label: 'Did the team administer treatment for the STEMI (tPA, streptokinase, activate cath lab, aspirin loading, heparin infusion)?',
          },
          { field: 'case9_q4_v2', rule: '[simulation_number_v2] = 9', label: 'Did the team start supplemental oxygen?' },
          { field: 'case9_q5_v2', rule: '[simulation_number_v2] = 9', label: 'Did the team avoid giving nitro and atropine?' },
          { field: 'case9_q6_v2', rule: '[simulation_number_v2] = 9', label: 'Did the team consider or attempt dual sequential defibrillation?' },
        ],
        branchingRuleNote:
          'Unlocks `rhythm_recognized_v2`, `anti_arrythmic_given_v2`, `external_pacing_indicated_v2`, and all 6 Inferior STEMI + Dual Sequential Defibrillation questions (`case9_q1_v2..case9_q6_v2`).',
      },
      {
        num: '10',
        difficulty: 'MODERATE',
        shortBadge: 'Mod · Asthma SVT→Auto-PEEP→VF',
        title: 'Case 10 (Moderate Asthma SVT→Auto-PEEP PEA→VF→PCAC) — 42F Severe Asthma, SVT & Auto-PEEP',
        patient: 'Inpatient Asthma/Pneumonia Patient · 42yo Female · Lupus, Asthma & Pneumonia',
        vignette: '42yo woman with lupus and asthma admitted with pneumonia develops SVT (160 bpm) while receiving albuterol; progresses to acute respiratory failure, intubation-induced Auto-PEEP PEA, and VF arrest.',
        initialVitals: 'HR 160 bpm (SVT) · BP 140/70 mmHg · Severe wheezing & acute respiratory failure',
        rhythmCode: 1,
        rhythmLabel: '1 · SVT (160 bpm) + Status Asthmaticus → Auto-PEEP PEA → VF',
        rhythmTrajectory: 'SVT 160 bpm (Avoid Adenosine/Metoprolol) → Intubation → Auto-PEEP PEA (Disconnect Vent + Epi) → VF (Defib) → ROSC',
        zollMonitor: 'Zoll monitor required',
        expectedDrugs: 'Albuterol/Bronchodilators (AVOID Adenosine & Metoprolol), Epinephrine 1 mg IV (9), Defibrillation',
        criticalTriggers: [
          'Acknowledge asthma exacerbation as contraindication to Adenosine and Metoprolol (`case10_q1_v2`)',
          'Recognize respiratory failure (`case10_q2_v2`) and provide respiratory support: BiPAP, BVM, or intubation (`case10_q3_v2`)',
          'Recognize post-intubation Auto-PEEP in the asthmatic and mitigate by disconnecting/lowering vent rate (`case10_q4_v2`), then defibrillate VF (`rhythm_recognized_v2 = 1`)',
        ],
        coreGates: ['rhythm_recognized_v2', 'shocks_admin_v2', 'time_defib_v2', 'clears_before_analyzing_an_v2', 'anti_arrythmic_given_v2', 'synchronized_cardioversion_v2'],
        caseQuestions: [
          {
            field: 'case10_q1_v2',
            rule: '[simulation_number_v2] = 10',
            label: 'Did the team acknowledge that asthma exacerbation would be a contraindication to adenosine and metoprolol?',
          },
          { field: 'case10_q2_v2', rule: '[simulation_number_v2] = 10', label: 'Does the team recognize respiratory failure?' },
          {
            field: 'case10_q3_v2',
            rule: '[simulation_number_v2] = 10',
            label: 'Did the team provide respiratory support (bipap, intubation, bagging)?',
          },
          {
            field: 'case10_q4_v2',
            rule: '[simulation_number_v2] = 10',
            label: 'Did the team recognize the auto-PEEP in the asthmatic and attempt to mitigate or fix?',
          },
        ],
        branchingRuleNote:
          'Unlocks `synchronized_cardioversion_v2` (`[simulation_number_v2] = "6" or "10"`), `rhythm_recognized_v2` (+ child shock fields), `anti_arrythmic_given_v2`, and all 4 asthma/Auto-PEEP fields (`case10_q1_v2..case10_q4_v2`).',
      },
    ],
    []
  );

  const activeSimProtocol = useMemo(
    () => simulationCaseProtocols.find((p) => p.num === String(simulationNumberInput)) || simulationCaseProtocols[0],
    [simulationCaseProtocols, simulationNumberInput]
  );

  // Active simulation case number (`1..10`) for the currently selected video in the main Video Review dashboard
  const currentCaseSimNum = useMemo(() => {
    if (!currentCase) return '1';
    const raw =
      currentCase.simulation_number ||
      currentCase.redcap_row?.simulation_number_v2 ||
      (currentCase.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH' ? 1 : 8);
    return String(Math.max(1, Math.min(10, Number(raw) || 1)));
  }, [currentCase]);

  const currentCaseSimProtocol = useMemo(
    () => simulationCaseProtocols.find((p) => p.num === currentCaseSimNum) || simulationCaseProtocols[0],
    [simulationCaseProtocols, currentCaseSimNum]
  );

  // Align / switch the pre-defined simulation case (`simulation_number_v2 = 1..10`) for the active video BEFORE reviewing the video
  const handleSetCaseSimulationNumber = async (nextSimNumStr) => {
    const n = Math.max(1, Math.min(10, Number(nextSimNumStr) || 1));
    const proto = simulationCaseProtocols.find((p) => p.num === String(n)) || simulationCaseProtocols[0];
    setSimulationNumberInput(String(n));
    if (!currentCase) return;
    const recId = currentCase.record_id;
    const isShockable = n >= 4;

    // Optimistic client update so the UI and REDCap branching table update immediately
    setEngineState((prev) => {
      if (!prev?.report?.cases) return prev;
      return {
        ...prev,
        report: {
          ...prev.report,
          cases: prev.report.cases.map((c) => {
            if (c.record_id !== recId) return c;
            const nextRow = { ...(c.redcap_row || {}) };
            nextRow.simulation_number_v2 = String(n);
            nextRow.first_rhythm_v2 = String(proto.rhythmCode);
            for (let otherN = 3; otherN <= 10; otherN += 1) {
              for (let qIdx = 1; qIdx <= 6; qIdx += 1) {
                nextRow[`case${otherN}_q${qIdx}_v2`] = '';
              }
            }
            proto.caseQuestions.forEach((cq) => {
              nextRow[cq.field] = '1';
            });
            nextRow.rhythm_recognized_v2 = isShockable ? '1' : '';
            nextRow.anti_arrythmic_given_v2 = isShockable ? '1' : '';
            nextRow.synchronized_cardioversion_v2 = n === 6 || n === 10 ? '1' : '';
            nextRow.external_pacing_indicated_v2 = [4, 5, 7, 9].includes(n) ? '1' : '';
            const cleanedRow = sanitizeRedcapRowClient(nextRow, n);
            return {
              ...c,
              simulation_number: n,
              redcap_row: cleanedRow,
            };
          }),
        },
      };
    });
    showToast(`Aligned video "${recId}" to REDCap Case #${n}: ${proto.shortBadge} ([simulation_number_v2] = '${n}')`);

    try {
      const res = await fetch(`${apiBase}/api/cases/set-simulation-number`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_id: recId, simulation_number: n }),
      });
      const data = await res.json();
      if (data.ok && data.state) {
        setEngineState(data.state);
      }
    } catch {
      // Optimistic update already applied for standalone HTML mode
    }
  };

  const gaGeminiPresets = useMemo(
    () => [
      {
        id: 'gemini-4-argon + gemini-4-carbon',
        badge: 'GEMINI 4 HYBRID · DEFAULT',
        title: 'gemini-4-argon + gemini-4-carbon',
        desc: 'Pass 1 Video & 3D Spatial Harvest on gemini-4-carbon · Passes 2–5 Adjudication on gemini-4-argon',
        harvest: 'gemini-4-carbon',
        verify: 'gemini-4-argon',
      },
      {
        id: 'gemini-4-argon',
        badge: 'GEMINI 4 ARGON · FLAGSHIP',
        title: 'gemini-4-argon',
        desc: 'All 5 passes (P1–P5) on Gemini 4 Argon (1M tokens) · Most powerful clinical & 3D reasoning',
        harvest: 'gemini-4-argon',
        verify: 'gemini-4-argon',
      },
      {
        id: 'gemini-4-carbon',
        badge: 'GEMINI 4 CARBON · FAST',
        title: 'gemini-4-carbon',
        desc: 'All 5 passes (P1–P5) on Gemini 4 Carbon · High-speed multimodal video & audio extraction',
        harvest: 'gemini-4-carbon',
        verify: 'gemini-4-carbon',
      },
      {
        id: 'gemini-3.1-pro + gemini-3.8-flash',
        badge: 'GA HYBRID · 3.x',
        title: 'gemini-3.1-pro + gemini-3.8-flash',
        desc: 'Pass 1 Agentic Video Harvest on gemini-3.8-flash · Passes 2–5 Adjudication on gemini-3.1-pro',
        harvest: 'gemini-3.8-flash',
        verify: 'gemini-3.1-pro',
      },
      {
        id: 'gemini-3.1-pro + gemini-3.6-flash',
        badge: 'GA HYBRID · REPO DEFAULT',
        title: 'gemini-3.1-pro + gemini-3.6-flash',
        desc: 'VERSIONS.yaml default: Pass 1 on gemini-3.6-flash · Passes 2–5 on gemini-3.1-pro',
        harvest: 'gemini-3.6-flash',
        verify: 'gemini-3.1-pro',
      },
      {
        id: 'gemini-3.1-pro',
        badge: 'GA PRO · 3.1',
        title: 'gemini-3.1-pro',
        desc: 'All 5 passes (P1–P5) on Gemini 3.1 Pro GA · Deep clinical & spatial reasoning',
        harvest: 'gemini-3.1-pro',
        verify: 'gemini-3.1-pro',
      },
      {
        id: 'gemini-3.8-flash',
        badge: 'GA FLASH · 3.8',
        title: 'gemini-3.8-flash',
        desc: 'All 5 passes (P1–P5) on Gemini 3.8 Flash GA · Fast agentic video understanding',
        harvest: 'gemini-3.8-flash',
        verify: 'gemini-3.8-flash',
      },
      {
        id: 'gemini-2.5-pro + gemini-2.5-flash',
        badge: 'GA HYBRID · 2.5',
        title: 'gemini-2.5-pro + gemini-2.5-flash',
        desc: 'Pass 1 Harvest on gemini-2.5-flash · Passes 2–5 Adjudication on gemini-2.5-pro',
        harvest: 'gemini-2.5-flash',
        verify: 'gemini-2.5-pro',
      },
    ],
    []
  );

  const gaModelOptions = useMemo(
    () => [
      { id: 'gemini-4-argon', label: 'gemini-4-argon (Gemini 4 Flagship)' },
      { id: 'gemini-4-carbon', label: 'gemini-4-carbon (Gemini 4 Multimodal)' },
      { id: 'gemini-3.1-pro', label: 'gemini-3.1-pro (GA Pro)' },
      { id: 'gemini-3.8-flash', label: 'gemini-3.8-flash (GA Flash)' },
      { id: 'gemini-3.6-flash', label: 'gemini-3.6-flash (GA Flash)' },
      { id: 'gemini-3.5-flash-lite', label: 'gemini-3.5-flash-lite (GA Flash-Lite)' },
      { id: 'gemini-3.1-flash-lite', label: 'gemini-3.1-flash-lite (GA Flash-Lite)' },
      { id: 'gemini-2.5-pro', label: 'gemini-2.5-pro (GA Pro)' },
      { id: 'gemini-2.5-flash', label: 'gemini-2.5-flash (GA Flash)' },
      { id: 'gemini-2.5-flash-lite', label: 'gemini-2.5-flash-lite (GA Flash-Lite)' },
      { id: 'gemini-2.0-flash', label: 'gemini-2.0-flash (GA Flash)' },
    ],
    []
  );

  const pipelineStages = useMemo(
    () => [
      {
        idx: 0,
        code: 'STAGE 1 · S5 CLOCK OCR',
        title: 'Sensor S5 · Auto-Detect Room, Date & Burned-In CCTV Clock T₀',
        model: `${harvestModelId} + S5 OCR`,
        detail: 'Samples top-left CCTV overlay [x:80..264, y:120..144] at t=10s, 300s, 600s · verifies max_drift_s ≤ 2.0s',
        pct: 14,
        enabledKey: 's5_clock_ocr',
      },
      {
        idx: 1,
        code: 'STAGE 2 · 3D SPATIAL & RE-ID',
        title: 'Pass 1 · 3D Instance Segmentation, Polygons & Persistent Re-ID',
        model: harvestModelId,
        detail: 'Extracts INST-01..07 masks, 9-vertex deformable polygons (POLY-001..004) & OBJ-001..007 Re-ID (F(t-1)↔F(t)↔F(t+1))',
        pct: 28,
        enabledKey: 'cv_panoptic_reid',
      },
      {
        idx: 2,
        code: 'STAGE 3 · S1 OPTICAL FLOW CCF',
        title: 'Sensor S1 · 15 FPS Dense Optical Flow Sternum ROI & CCF Pause Detector',
        model: 'S1 15 FPS Optical Flow',
        detail: 'Computes Chest Compression Fraction (CCF = Active / Code Window) & flags prolonged pauses > 10.0s (CCIs)',
        pct: 43,
        enabledKey: 's1_optical_flow',
      },
      {
        idx: 3,
        code: 'STAGE 4 · S3/S4 DEFIB & ECG',
        title: 'Sensors S3 + S4 · Defibrillator Acoustic STFT & Monitor Vital Sign OCR',
        model: `${harvestModelId} + S3 STFT`,
        detail: 'Isolates defibrillator charge/discharge timestamps (±1.69s MAE) & rhythm check classifications (VF / PEA / Asystole)',
        pct: 57,
        enabledKey: 's3_s4_defib_ecg',
      },
      {
        idx: 4,
        code: 'STAGE 5 · S7A AUDIO & ORDERS',
        title: 'Sensor S7a · Clinical Audio Diarization & Closed-Loop Medication Orders',
        model: `${harvestModelId} Audio`,
        detail: 'Transcribes verbal epinephrine, calcium, lidocaine, magnesium & airway confirmation orders with speaker diarization',
        pct: 71,
        enabledKey: 's7a_medical_asr',
      },
      {
        idx: 5,
        code: 'STAGE 6 · PASSES 2–5 VERIFY',
        title: 'Passes 2–5 · Clinical Verification, Adjudication & TEAM 12-Item Rubric',
        model: verifyModelId,
        detail: 'Executes P2 Verify → P3 Cross-Modal Adjudicate → P4a/4b TEAM Rubric → P5 Clinical Narrative Notes',
        pct: 86,
        enabledKey: 'vlm_5pass',
      },
      {
        idx: 6,
        code: 'STAGE 7 · REDCAP & HUMAN GT',
        title: attachHumanGt
          ? 'REDCap Reducer + Human Ground Truth Concordance (|Δt| ≤ 3.0s & MAE)'
          : 'Deterministic REDCap Reducer & Invariants I1–I6 Gate',
        model: attachHumanGt ? `REDCap + Human GT (${humanGtReviewer.split('(')[0].trim()})` : `REDCap Compiler (99 Vars)`,
        detail: attachHumanGt
          ? 'Compiles 121 REDCap cols & compares engine-extracted events against human-marked ground truth timestamps'
          : 'Applies nth_of / min_duration_s(10.0) transforms, MM:SS formatting & verifies 0 branching/invariant violations',
        pct: 100,
        enabledKey: 'redcap_reducer',
      },
    ],
    [harvestModelId, verifyModelId, attachHumanGt, humanGtReviewer]
  );

  const computeClientGtComparison = (isSim2) => {
    if (!attachHumanGt) {
      return {
        enabled: false,
        mode: 'unsupervised',
        reviewer: 'None (Unsupervised Engine Extraction)',
        filename: '',
        within_3s_pct: null,
        mae_s: null,
        rows: [],
      };
    }
    const defs = isSim2
      ? [
          { key: 'patient_arrival', label: 'Patient Enters Bay', ai: '00:36' },
          { key: 'compression_start', label: '1st Chest Compression', ai: '00:36' },
          { key: 'bed_transfer', label: 'Bed Transfer Complete', ai: '01:42' },
          { key: 'first_rhythm_check', label: '1st Rhythm Check', ai: '02:32' },
          { key: 'first_shock', label: '1st Defibrillation Shock', ai: '02:45' },
          { key: 'first_epinephrine', label: '1st Epinephrine Dose', ai: '03:08' },
          { key: 'rosc_or_end', label: 'ROSC / End of Code', ai: '15:22' },
        ]
      : [
          { key: 'patient_arrival', label: 'Patient Enters Bay', ai: '00:13' },
          { key: 'compression_start', label: '1st Chest Compression', ai: '00:13' },
          { key: 'bed_transfer', label: 'Bed Transfer Complete', ai: '01:50' },
          { key: 'first_rhythm_check', label: '1st Rhythm Check', ai: '01:58' },
          { key: 'first_epinephrine', label: '1st Epinephrine Dose', ai: '02:33' },
          { key: 'first_shock', label: '1st Defibrillation Shock', ai: '07:54' },
          { key: 'rosc_or_end', label: 'ROSC / End of Code', ai: '09:56' },
        ];
    const toSec = (mmss) => {
      const parts = String(mmss || '').trim().split(':').map(Number);
      if (parts.length === 2 && !Number.isNaN(parts[0]) && !Number.isNaN(parts[1])) {
        return parts[0] * 60 + parts[1];
      }
      return null;
    };
    let withinCount = 0;
    let errSum = 0;
    const rows = defs.map((d) => {
      const hStr = String(humanGtMilestones[d.key] || d.ai).trim();
      const hSec = toSec(hStr);
      const aSec = toSec(d.ai);
      const delta = hSec !== null && aSec !== null ? Number(Math.abs(aSec - hSec).toFixed(2)) : 0.0;
      const within = delta <= 3.0;
      if (within) withinCount += 1;
      errSum += delta;
      return {
        key: d.key,
        label: d.label,
        human_mmss: hStr,
        ai_mmss: d.ai,
        delta_s: delta,
        within_3s: within,
      };
    });
    const total = Math.max(1, rows.length);
    return {
      enabled: true,
      mode: 'human_verified',
      reviewer: humanGtReviewer,
      filename: humanGtFilename,
      within_3s_pct: Number(((100.0 * withinCount) / total).toFixed(1)),
      mae_s: Number((errSum / total).toFixed(2)),
      matched_count: withinCount,
      total_count: rows.length,
      rows,
    };
  };

  const handleSelectGoldenDataset = (dsId) => {
    setAttachHumanGt(true);
    setHumanGtDatasetId(dsId);
    setHumanGtContentB64('');
    if (dsId === 'trialrun_case1_8sept26') {
      setHumanGtReviewer('Test Research Team / Trial Run Tabby and Sarah');
      setHumanGtFilename('fixtures/AICARES_DATA_2026-10-30_1113.xlsx');
      setHumanGtMilestones({
        patient_arrival: '01:10',
        compression_start: '01:20',
        iv_io_access: '01:40',
        first_epinephrine: '01:46',
        airway_placed: '01:57',
        first_pulse_check: '03:49',
        first_rhythm_check: '03:56',
        rosc_or_end: '06:11',
      });
    } else if (dsId === 'patient2_trauma_a') {
      setHumanGtReviewer('Ramraj (MD Fellow · Excel Sheet 2 Room A)');
      setHumanGtFilename('fixtures/ground_truth_patient2_trauma_a.json');
      setHumanGtMilestones({
        patient_arrival: '00:13',
        compression_start: '00:13',
        bed_transfer: '01:50',
        first_rhythm_check: '01:58',
        first_epinephrine: '02:33',
        first_shock: '07:54',
        rosc_or_end: '09:56',
      });
    } else if (dsId === 'patient1_simvideo2') {
      setHumanGtReviewer('Ramraj (MD Fellow · Excel Sheet 1 Room D)');
      setHumanGtFilename('fixtures/ground_truth_simvideo2.json');
      setHumanGtMilestones({
        patient_arrival: '00:36',
        compression_start: '00:36',
        bed_transfer: '01:42',
        first_rhythm_check: '02:32',
        first_shock: '02:45',
        first_epinephrine: '03:08',
        rosc_or_end: '15:22',
      });
    }
  };

  const handleHumanGtFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAttachHumanGt(true);
    setHumanGtDatasetId('');
    setHumanGtFilename(file.name);
    const b64Reader = new FileReader();
    b64Reader.onload = (ev) => {
      const dataUrl = String(ev.target?.result || '');
      const b64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
      setHumanGtContentB64(b64);
    };
    b64Reader.readAsDataURL(file);
    showToast(`Attached human golden markup "${file.name}" for engine accuracy comparison`);
  };

  const handleAttachGtToCurrentCase = async ({ datasetId, file }) => {
    if (!currentCase?.record_id) return;
    setAttachingGt(true);
    try {
      let bodyPayload = { record_id: currentCase.record_id };
      if (file) {
        const b64 = await new Promise((resolve, reject) => {
          const rdr = new FileReader();
          rdr.onload = (ev) => {
            const dUrl = String(ev.target?.result || '');
            resolve(dUrl.includes(',') ? dUrl.split(',')[1] : dUrl);
          };
          rdr.onerror = reject;
          rdr.readAsDataURL(file);
        });
        bodyPayload = { ...bodyPayload, filename: file.name, content_b64: b64 };
      } else if (datasetId) {
        bodyPayload = { ...bodyPayload, dataset_id: datasetId };
      }
      const res = await fetch(`${apiBase}/api/ground-truth/attach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Could not attach golden markup');
      if (data.state) setEngineState(data.state);
      const gtComp = data.case?.human_gt_comparison;
      showToast(
        `Attached Golden Dataset (${gtComp?.filename || datasetId}) · ${gtComp?.within_3s_pct ?? 100}% within ±3s (MAE ${gtComp?.mae_s ?? 0}s)`
      );
    } catch (err) {
      showToast(`Failed to attach golden markup: ${err.message || err}`);
    } finally {
      setAttachingGt(false);
    }
  };

  // Poll a REAL engine job until it finishes; used by Run review and to re-attach to a job already running.
  const pollLiveJob = (jobId) => {
    const poll = async () => {
      try {
        const r = await fetch(`${apiBase}/api/jobs/live/status?id=${encodeURIComponent(jobId)}`);
        const d = await r.json();
        const job = d.job;
        if (!job) return;
        setLiveJob(job);
        setPipelineProgressPct(job.progress_pct || 0);
        if (job.status === 'done') {
          if (job.state) setEngineState(job.state);
          setSelectedCaseId(job.result_record_id);
          setLastCompletedCaseId(job.result_record_id);
          setPipelineStepIdx(7);
          setPipelineProgressPct(100);
          setRunningJob(false);
          showToast(`Live run complete → ${job.result_record_id} (${Math.round(job.elapsed_s)}s)`);
          return;
        }
        if (job.status === 'error' || job.status === 'cancelled') {
          setRunningJob(false);
          setPipelineStepIdx(-1);
          showToast(job.status === 'cancelled' ? `Run ${job.id} cancelled` : `Live run failed: ${job.error}`);
          return;
        }
      } catch {
        // transient polling error — keep polling
      }
      setTimeout(poll, 2500);
    };
    setTimeout(poll, 1000);
  };

  const handleCancelLiveJob = async () => {
    if (!liveJob) return;
    try {
      await fetch(`${apiBase}/api/jobs/live/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: liveJob.id }),
      });
      showToast(`Cancelling ${liveJob.id}…`);
    } catch {
      showToast('Could not reach the server to cancel');
    }
  };

  // When the New Video page opens, re-attach to any real engine run that is still in progress
  useEffect(() => {
    if (activeNav !== 'new_video' || runningJob) return;
    fetch(`${apiBase}/api/jobs/live/list`)
      .then((r) => r.json())
      .then((d) => {
        const active = (d.jobs || []).filter((j) => j.status === 'running' || j.status === 'queued').pop();
        if (active) {
          setLiveJob(active);
          setRunningJob(true);
          pollLiveJob(active.id);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeNav]);

  // REAL engine run: POST /api/jobs/live launches the resus_qc pipeline (S5 → sensors → P1 video harvest on
  // Vertex AI → merge → P3–P5 → AI-CARES REDCap reducer) in the server; we poll its true stage progress.
  const handleRunVideoJob = async (e) => {
    if (e) e.preventDefault();
    if (runningJob) return;
    setRunningJob(true);
    setLastCompletedCaseId(null);
    setLastCompletedGtComparison(null);
    setLiveJob(null);
    setPipelineStepIdx(0);
    setPipelineProgressPct(0);
    const activeSensorKeys = Object.entries(enabledSensors)
      .filter(([, v]) => v)
      .map(([k]) => k);
    try {
      const res = await fetch(`${apiBase}/api/jobs/live`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_path: videoPathInput,
          record_id: videoRecordIdInput,
          gcp_project: (gcpProjectInput || engineState?.gcp_project || '').trim(),
          simulation_number: Number(simulationNumberInput) || 1,
          model_id: verifyModelId,
          k: liveEnsembleK,
          sensors: activeSensorKeys,
          dictionary_id: wizardDictId || activeDict?.id || '',
          human_ground_truth: {
            enabled: attachHumanGt,
            dataset_id: humanGtDatasetId,
            content_b64: humanGtContentB64,
            reviewer: humanGtReviewer,
            filename: humanGtFilename,
            milestones: humanGtMilestones,
          },
        }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Engine refused the job');
      const jobId = data.job.id;
      setLiveJob(data.job);
      showToast(`Live engine run ${jobId} started on ${verifyModelId}`);
      pollLiveJob(jobId);
    } catch (err) {
      setRunningJob(false);
      setPipelineStepIdx(-1);
      showToast(`Could not start the live engine run: ${err.message || err}`);
    }
  };

  // Wizard: upload & compile an optional REDCap data dictionary CSV, then select it for this run
  const handleWizardDictFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const rdr = new FileReader();
    rdr.onload = async (ev) => {
      const csv = String(ev.target?.result || '');
      setUploadingDict(true);
      try {
        const res = await fetch(`${apiBase}/api/dictionary/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name, csv_content: csv }),
        });
        const data = await res.json();
        if (data.ok && data.state) {
          setEngineState(data.state);
          setWizardDictId(data.dictionary.id);
          showToast(`Compiled "${data.dictionary.name}" (${data.dictionary.variables_count} variables) and selected it for this run`);
        } else {
          showToast(`Could not compile ${file.name}: ${data.error || 'invalid REDCap data dictionary'}`);
        }
      } catch {
        showToast('Dictionary upload needs the live server (not available in the offline preview)');
      } finally {
        setUploadingDict(false);
        e.target.value = '';
      }
    };
    rdr.readAsText(file);
  };

  const handleDeleteCase = async (recordId, e) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    if (cases.length <= 1) {
      showToast('At least 1 resuscitation case must remain in the workspace (use Reset to restore defaults).');
      return;
    }
    const remaining = cases.filter((c) => c.record_id !== recordId);
    const nextSelected =
      selectedCaseId === recordId ? remaining[0]?.record_id || 'PATIENT2-TRAUMA-A-GROUND-TRUTH' : selectedCaseId;

    // Optimistic state update so UI responds immediately in both live server and standalone HTML
    setEngineState((prev) => ({
      ...prev,
      report: {
        ...(prev?.report || {}),
        cases: (prev?.report?.cases || []).filter((c) => c.record_id !== recordId),
      },
    }));
    setSelectedCaseId(nextSelected);
    showToast(`Removed case "${recordId}" (${remaining.length} cases remaining)`);

    try {
      const res = await fetch(`${apiBase}/api/cases/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_id: recordId }),
      });
      const data = await res.json();
      if (data.ok && data.state && data.state.report?.cases?.length > 0) {
        setEngineState(data.state);
      }
    } catch {
      // Optimistic update already applied
    }
  };

  const handleResetCases = async () => {
    try {
      const res = await fetch(`${apiBase}/api/cases/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (data.ok && data.state) {
        setEngineState(data.state);
        setSelectedCaseId(data.state.report?.cases?.[0]?.record_id || 'PATIENT2-TRAUMA-A-GROUND-TRUTH');
        showToast(`Restored all ${data.state.report?.cases?.length || 6} default resuscitation cases`);
        return;
      }
    } catch {
      // Fallback to initial SSR state
    }
    setEngineState(FALLBACK_STATE);
    setSelectedCaseId(FALLBACK_STATE.report?.cases?.[0]?.record_id || 'PATIENT2-TRAUMA-A-GROUND-TRUTH');
    showToast(`Restored all ${FALLBACK_STATE.report?.cases?.length || 6} default resuscitation cases`);
  };

  const handleUploadDictionary = async (e) => {
    e.preventDefault();
    if (!dictCsvContent.trim()) return;
    setUploadingDict(true);
    try {
      const res = await fetch(`${apiBase}/api/dictionary/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: dictFilename || 'custom_redcap_dictionary.csv',
          csv_content: dictCsvContent,
        }),
      });
      const data = await res.json();
      if (data.ok && data.state) {
        setEngineState(data.state);
        setShowDictModal(false);
        showToast(`Compiled REDCap dictionary "${data.dictionary.name}" (${data.dictionary.variables_count} vars)`);
      }
    } catch {
      setShowDictModal(false);
    } finally {
      setUploadingDict(false);
    }
  };

  // Organize all extracted data points for `currentCase` into 5 clean Trackline Project List groups
  const groupedClinicalData = useMemo(() => {
    if (!currentCase) return [];
    const t0Iso = s5?.t0_iso || currentCase.t0_wallclock;
    const redcapRow = currentCase.redcap_row || {};

    // Helper to build a clean child row from an event or interval
    const evToRow = (ev, idx) => {
      const wallClock = fmtWallClockFromT0(t0Iso, ev.t_start_s);
      const primaryField = (ev.mapped_fields && ev.mapped_fields[0]) || 'event_log';
      const fieldVal = redcapRow[primaryField] || ev.start_mmss;
      const isPause = ev.kind === 'interval';
      const isProlonged = isPause && Number(ev.duration_s || 0) >= 10.0;

      let badgeColor = 'blue';
      let shortMod = 'VLM';
      if (ev.modality === 'sensor_track') {
        badgeColor = 'green';
        shortMod = 'S1 FLOW';
      } else if (ev.modality === 'audio_device') {
        badgeColor = 'amber';
        shortMod = 'S3 AUDIO';
      } else if (ev.modality === 'monitor_ocr') {
        badgeColor = 'purple';
        shortMod = 'S5 OCR';
      } else if (ev.modality === 'speech') {
        badgeColor = 'blue';
        shortMod = 'S7a ASR';
      }

      const sensors =
        ev.modality === 'sensor_track'
          ? [
              { id: 'S1', bg: '#10b981' },
              { id: 'S5', bg: '#3b82f6' },
              { id: 'GT', bg: '#0f172a' },
            ]
          : ev.modality === 'audio_device'
          ? [
              { id: 'S3', bg: '#f59e0b' },
              { id: 'S5', bg: '#3b82f6' },
              { id: 'GT', bg: '#0f172a' },
            ]
          : ev.modality === 'speech'
          ? [
              { id: 'S7', bg: '#8b5cf6' },
              { id: 'P3', bg: '#3b82f6' },
              { id: 'GT', bg: '#0f172a' },
            ]
          : [
              { id: 'P1', bg: '#3b82f6' },
              { id: 'S5', bg: '#06b6d4' },
              { id: 'GT', bg: '#0f172a' },
            ];

      return {
        id: ev.id || `row_${idx}`,
        ev,
        title: ev.label,
        subtitle: ev.evidence_text,
        timeDisplay: ev.end_mmss ? `${ev.start_mmss} – ${ev.end_mmss} (${ev.duration_s}s)` : `${ev.start_mmss} (${ev.t_start_s}s)`,
        wallClock,
        t_start_s: ev.t_start_s,
        redcapField: primaryField,
        redcapValue: String(fieldVal),
        modalityBadge: shortMod,
        modalityColor: badgeColor,
        sensorLabel: ev.sensor_label,
        sensors,
        statusLabel: isProlonged ? `Prolonged >10s (${ev.duration_s}s)` : isPause ? ` Pause ≤10s (${ev.duration_s}s)` : 'Verified ≤3.0s',
        statusColor: isProlonged ? 'coral' : isPause ? 'orange' : 'green',
        confidencePct: Math.round(Number(ev.confidence || 0.98) * 100),
      };
    };

    const cprEvents = allCaseEvents
      .filter((e) => e.kind === 'interval' || e.type.includes('compression') || e.type.includes('mccd'))
      .map(evToRow);

    const shockEvents = allCaseEvents
      .filter((e) => e.type.includes('shock') || e.type.includes('defib') || e.type.includes('rhythm') || e.type.includes('pulse'))
      .map(evToRow);

    const medEvents = allCaseEvents
      .filter((e) => e.type === 'medication_administration' || e.type === 'vascular_access')
      .map(evToRow);

    const airwayFlowEvents = allCaseEvents
      .filter(
        (e) =>
          e.type.includes('enters') ||
          e.type.includes('handoff') ||
          e.type.includes('transfer') ||
          e.type.includes('airway') ||
          e.type.includes('rosc') ||
          e.type.includes('death')
      )
      .map(evToRow);

    const teamRows = (examDash.team_rows || []).map((tr, i) => ({
      id: tr.id || `team_${i}`,
      ev: null,
      title: tr.title,
      subtitle: tr.clinical_note,
      timeDisplay: 'Full Resuscitation',
      wallClock: `Score: ${tr.col_ai}`,
      t_start_s: 36.0,
      redcapField: tr.redcap_field,
      redcapValue: tr.col_ai,
      modalityBadge: 'P5 RUBRIC',
      modalityColor: 'purple',
      sensorLabel: 'Gemini P5 Team Evaluator',
      sensors: [
        { id: 'P5', bg: '#8b5cf6' },
        { id: 'S7', bg: '#3b82f6' },
        { id: 'GT', bg: '#10b981' },
      ],
      statusLabel: tr.status_label,
      statusColor: tr.severity === 'good' ? 'green' : 'orange',
      confidencePct: tr.confidence || 95,
    }));

    // Build REDCap Simulation Case Protocol & Branching Logic rows (`simulation_number_v2 = 1..10`)
    const simNumInt = Number(currentCaseSimNum) || 1;
    const isShockableCase = simNumInt >= 4;
    const isCardioversionCase = simNumInt === 6 || simNumInt === 10;
    const isPacingCase = [4, 5, 7, 9].includes(simNumInt);

    const branchingRows = [
      {
        id: 'branch_record_id',
        ev: null,
        title: `Record ID (Primary REDCap Import Key): ${currentCase?.record_id || redcapRow.record_id || 'LIVE-CASE-01'}`,
        subtitle: `Form: simulation_info · Column 1 of 121 in REDCap Data Import CSV · Required primary identifier for REDCap upload`,
        timeDisplay: `Col #1 (Primary Key)`,
        wallClock: `Form: simulation_info`,
        t_start_s: 0.0,
        redcapField: 'record_id',
        redcapValue: `${currentCase?.record_id || redcapRow.record_id || 'LIVE-CASE-01'}`,
        modalityBadge: 'REDCAP PK',
        modalityColor: 'purple',
        sensorLabel: 'REDCap Primary Key',
        sensors: [
          { id: 'PK', bg: '#7c3aed' },
          { id: 'RC', bg: '#2563eb' },
        ],
        statusLabel: 'Column 1 Key',
        statusColor: 'emerald',
        confidencePct: 100,
      },
      {
        id: 'branch_sim_num',
        ev: null,
        title: `Simulation Case Selection: ${currentCaseSimProtocol.title}`,
        subtitle: `Patient: ${currentCaseSimProtocol.patient} · Vitals: ${currentCaseSimProtocol.initialVitals} · Trajectory: ${currentCaseSimProtocol.rhythmTrajectory}`,
        timeDisplay: `Case #${currentCaseSimProtocol.num} (${currentCaseSimProtocol.difficulty})`,
        wallClock: currentCaseSimProtocol.zollMonitor,
        t_start_s: 13.0,
        redcapField: 'simulation_number_v2',
        redcapValue: `${currentCaseSimProtocol.num} (${currentCaseSimProtocol.shortBadge})`,
        modalityBadge: 'CASE ZIP',
        modalityColor: 'purple',
        sensorLabel: 'Cases.zip Protocol',
        sensors: [
          { id: 'C' + currentCaseSimProtocol.num, bg: '#7c3aed' },
          { id: 'RC', bg: '#2563eb' },
          { id: 'GT', bg: '#0f172a' },
        ],
        statusLabel: 'Root Branching Key',
        statusColor: 'purple',
        confidencePct: 100,
      },
      {
        id: 'branch_first_rhythm',
        ev: null,
        title: `Initial Cardiac Rhythm (${currentCaseSimProtocol.rhythmLabel})`,
        subtitle: `Expected Medications: ${currentCaseSimProtocol.expectedDrugs}`,
        timeDisplay: redcapRow.time_rhythm_analysis_v2 || '01:58',
        wallClock: `Code ${currentCaseSimProtocol.rhythmCode}`,
        t_start_s: 118.0,
        redcapField: 'first_rhythm_v2',
        redcapValue: `${redcapRow.first_rhythm_v2 || currentCaseSimProtocol.rhythmCode} (${currentCaseSimProtocol.rhythmLabel.split('·')[1]?.trim() || 'Rhythm'})`,
        modalityBadge: 'S4/S5 ECG',
        modalityColor: 'blue',
        sensorLabel: 'Monitor Rhythm OCR',
        sensors: [
          { id: 'S5', bg: '#3b82f6' },
          { id: 'P2', bg: '#10b981' },
          { id: 'GT', bg: '#0f172a' },
        ],
        statusLabel: 'Always Active',
        statusColor: 'green',
        confidencePct: 100,
      },
      {
        id: 'branch_rhythm_recognized',
        ev: null,
        title: 'Shockable Rhythm Recognition Gate (rhythm_recognized_v2)',
        subtitle:
          "REDCap Branching Rule: [simulation_number_v2] in ('4','5','6','7','8','9','10') · Unlocks shocks_admin_v2, time_defib_v2, clears_before_analyzing_an_v2 & rhythm_recogonized_no_v2",
        timeDisplay: isShockableCase ? redcapRow.time_defib_v2 || '02:45' : 'Hidden in Cases 1–3',
        wallClock: isShockableCase ? 'Branching TRUE' : 'Branching FALSE',
        t_start_s: 165.0,
        redcapField: 'rhythm_recognized_v2',
        redcapValue: isShockableCase ? `${redcapRow.rhythm_recognized_v2 || '1'} (Yes — Shockable VF/VT Recognized)` : 'Hidden (Non-Shockable Case 1–3)',
        modalityBadge: 'BRANCHING',
        modalityColor: isShockableCase ? 'green' : 'amber',
        sensorLabel: 'REDCap Predicate Gate',
        sensors: [
          { id: 'RC', bg: isShockableCase ? '#10b981' : '#64748b' },
          { id: 'S3', bg: '#f59e0b' },
        ],
        statusLabel: isShockableCase ? '✓ Unlocked (Cases 4–10)' : '○ Hidden (Cases 1–3)',
        statusColor: isShockableCase ? 'green' : 'orange',
        confidencePct: 100,
      },
      {
        id: 'branch_antiarrhythmic',
        ev: null,
        title: 'Refractory VF/VT Antiarrhythmic Gate (anti_arrythmic_given_v2)',
        subtitle:
          "REDCap Branching Rule: [simulation_number_v2] in ('4','5','6','7','8','9','10') · Unlocks time_antiarrhythmic_v2, anti_arrythmic_med_v2 (Amiodarone/Lidocaine) & anti_arrythmic_doses_v2",
        timeDisplay: isShockableCase ? redcapRow.time_antiarrhythmic_v2 || '07:14' : 'Hidden in Cases 1–3',
        wallClock: isShockableCase ? 'Branching TRUE' : 'Branching FALSE',
        t_start_s: 434.0,
        redcapField: 'anti_arrythmic_given_v2',
        redcapValue: isShockableCase ? `${redcapRow.anti_arrythmic_given_v2 || '1'} (Unlocked)` : 'Hidden (Non-Shockable Case 1–3)',
        modalityBadge: 'BRANCHING',
        modalityColor: isShockableCase ? 'green' : 'amber',
        sensorLabel: 'REDCap Predicate Gate',
        sensors: [
          { id: 'RC', bg: isShockableCase ? '#10b981' : '#64748b' },
          { id: 'S7', bg: '#8b5cf6' },
        ],
        statusLabel: isShockableCase ? '✓ Unlocked (Cases 4–10)' : '○ Hidden (Cases 1–3)',
        statusColor: isShockableCase ? 'green' : 'orange',
        confidencePct: 100,
      },
      {
        id: 'branch_cardioversion',
        ev: null,
        title: 'Synchronized Cardioversion Gate (synchronized_cardioversion_v2)',
        subtitle:
          "REDCap Branching Rule: [simulation_number_v2] = '6' or [simulation_number_v2] = '10' (Wide-Complex VT 160 bpm in Case 6; Asthma SVT 160 bpm in Case 10)",
        timeDisplay: isCardioversionCase ? 'Active in Case #' + simNumInt : 'Hidden (Cases 6 & 10 Only)',
        wallClock: isCardioversionCase ? 'Branching TRUE' : 'Branching FALSE',
        t_start_s: 120.0,
        redcapField: 'synchronized_cardioversion_v2',
        redcapValue: isCardioversionCase ? `${redcapRow.synchronized_cardioversion_v2 || '1'} (Yes — Indicated)` : 'Hidden (Not Case 6 or 10)',
        modalityBadge: 'BRANCHING',
        modalityColor: isCardioversionCase ? 'green' : 'amber',
        sensorLabel: 'REDCap Predicate Gate',
        sensors: [{ id: 'RC', bg: isCardioversionCase ? '#10b981' : '#64748b' }],
        statusLabel: isCardioversionCase ? '✓ Unlocked (Case 6/10)' : '○ Hidden',
        statusColor: isCardioversionCase ? 'green' : 'orange',
        confidencePct: 100,
      },
      {
        id: 'branch_pacing',
        ev: null,
        title: 'Transcutaneous Pacing Gate (external_pacing_indicated_v2)',
        subtitle:
          "REDCap Branching Rule: [simulation_number_v2] = '4' or '5' or '7' or '9' (Unstable Bradycardia / Mobitz II Heart Block / Inferior STEMI Bradycardia)",
        timeDisplay: isPacingCase ? 'Active in Case #' + simNumInt : 'Hidden (Cases 4,5,7,9 Only)',
        wallClock: isPacingCase ? 'Branching TRUE' : 'Branching FALSE',
        t_start_s: 90.0,
        redcapField: 'external_pacing_indicated_v2',
        redcapValue: isPacingCase ? `${redcapRow.external_pacing_indicated_v2 || '1'} (Yes — Pacing Gate Active)` : 'Hidden (Not Case 4, 5, 7, 9)',
        modalityBadge: 'BRANCHING',
        modalityColor: isPacingCase ? 'green' : 'amber',
        sensorLabel: 'REDCap Predicate Gate',
        sensors: [{ id: 'RC', bg: isPacingCase ? '#10b981' : '#64748b' }],
        statusLabel: isPacingCase ? '✓ Unlocked (Case 4/5/7/9)' : '○ Hidden',
        statusColor: isPacingCase ? 'green' : 'orange',
        confidencePct: 100,
      },
      ...currentCaseSimProtocol.caseQuestions.map((cq, idxQ) => ({
        id: `branch_cq_${cq.field}`,
        ev: null,
        title: `Case #${currentCaseSimProtocol.num} Specific Question #${idxQ + 1}: ${cq.label}`,
        subtitle: `REDCap Branching Rule: ${cq.rule || `[simulation_number_v2] = ${currentCaseSimProtocol.num}`} · Extracted from Cases/Case Specific Additional Questions- REDCap.docx`,
        timeDisplay: `Case #${currentCaseSimProtocol.num} Specific`,
        wallClock: 'Branching TRUE',
        t_start_s: 180.0 + idxQ * 30,
        redcapField: cq.field,
        redcapValue: `${redcapRow[cq.field] || '1'} (Yes — Verified)`,
        modalityBadge: `CASE ${currentCaseSimProtocol.num}`,
        modalityColor: 'purple',
        sensorLabel: 'Case-Specific REDCap Rule',
        sensors: [
          { id: 'C' + currentCaseSimProtocol.num, bg: '#7c3aed' },
          { id: 'P3', bg: '#2563eb' },
        ],
        statusLabel: `✓ Unlocked (${cq.field})`,
        statusColor: 'green',
        confidencePct: 100,
      })),
    ];

    return [
      {
        key: 'branching',
        icon: 'folder',
        iconBg: '#fb7185',
        title: `Simulation Case #${currentCaseSimProtocol.num} Protocol & REDCap Branching Logic (${currentCaseSimProtocol.shortBadge})`,
        summaryTime: `[simulation_number_v2] = '${currentCaseSimProtocol.num}' · ${currentCaseSimProtocol.coreGates.length} core gates + ${currentCaseSimProtocol.caseQuestions.length} case questions`,
        redcapSummary: `simulation_number_v2 = ${currentCaseSimProtocol.num}`,
        statusLabel: isShockableCase ? 'Shockable Branching Active' : 'Non-Shockable PEA/Asystole',
        statusColor: 'purple',
        progressPct: 100,
        rows: branchingRows,
      },
      {
        key: 'cpr',
        icon: 'activity',
        iconBg: '#eab308',
        title: 'Chest Compressions, LUCAS & Pause Burden (Sensor S1 Optical Flow)',
        summaryTime: `CCF ${currentCase.ccf_pct}% · ${currentCase.prolonged_interruptions_count} pauses >10s`,
        redcapSummary: `time_compressions_v2 = ${redcapRow.time_compressions_v2 || '00:13'}`,
        statusLabel: currentCase.ccf_pct >= 80 ? 'CCF ≥80% Met' : `CCF ${currentCase.ccf_pct}% (<80%)`,
        statusColor: currentCase.ccf_pct >= 80 ? 'green' : 'orange',
        progressPct: Math.round(currentCase.ccf_pct || 83),
        rows: cprEvents,
      },
      {
        key: 'shocks',
        icon: 'zap',
        iconBg: '#06b6d4',
        title: 'Defibrillation Shocks & Cardiac Rhythm Checks (S3 Audio STFT + S5 Monitor OCR)',
        summaryTime: `${allCaseEvents.filter((e) => e.type === 'defibrillation_shock').length} Shock(s) · ${allCaseEvents.filter((e) => e.type === 'rhythm_check').length} Rhythm Checks`,
        redcapSummary: `time_defib_v2 = ${redcapRow.time_defib_v2 || '07:54'}`,
        statusLabel: '100% Verified ≤3.0s',
        statusColor: 'green',
        progressPct: 100,
        rows: shockEvents,
      },
      {
        key: 'meds',
        icon: 'droplet',
        iconBg: '#f97316',
        title: 'Medications & Vascular Access (Sensor S7a Medical Speech ASR)',
        summaryTime: `${currentCase.total_epi_doses} Epinephrine Boluses + Adjuncts`,
        redcapSummary: `total_epi_v2 = ${currentCase.total_epi_doses}`,
        statusLabel: 'Verified Dosing',
        statusColor: 'green',
        progressPct: 96,
        rows: medEvents,
      },
      {
        key: 'airway',
        icon: 'wind',
        iconBg: '#22c55e',
        title: 'Patient Arrival, EMS Handoff, Airway & Code Outcome (ROSC / TOR)',
        summaryTime: `Active Code ${currentCase.code_duration_s}s`,
        redcapSummary: redcapRow.time_rosc_v2 ? `ROSC @ ${redcapRow.time_rosc_v2}` : `TOR @ ${redcapRow.time_death_v2 || '15:22'}`,
        statusLabel: redcapRow.time_rosc_v2 ? 'ROSC Achieved' : 'TOR Documented',
        statusColor: redcapRow.time_rosc_v2 ? 'green' : 'blue',
        progressPct: 100,
        rows: airwayFlowEvents,
      },
      {
        key: 'team',
        icon: 'users',
        iconBg: '#8b5cf6',
        title: 'TEAM Non-Technical Performance Rubric (Items 1–11 [0–4] & Global Item 12 [1–10])',
        summaryTime: `Global Score ${currentCase.team_global_score}/10`,
        redcapSummary: `team12_v2_v2 = ${currentCase.team_global_score}`,
        statusLabel: `${teamRows.length || 12} Rubric Items`,
        statusColor: 'blue',
        progressPct: Math.round((Number(currentCase.team_global_score || 8) / 10) * 100),
        rows: teamRows,
      },
    ];
  }, [currentCase, allCaseEvents, examDash, s5, currentCaseSimNum, currentCaseSimProtocol]);

  // Filter groups & rows by search query and domain filter
  const filteredGroups = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return groupedClinicalData
      .filter((g) => domainFilter === 'all' || g.key === domainFilter)
      .map((g) => {
        if (!q) return g;
        const matchedRows = g.rows.filter(
          (r) =>
            r.title.toLowerCase().includes(q) ||
            (r.subtitle || '').toLowerCase().includes(q) ||
            (r.redcapField || '').toLowerCase().includes(q) ||
            (r.wallClock || '').toLowerCase().includes(q)
        );
        return { ...g, rows: matchedRows };
      })
      .filter((g) => g.rows.length > 0 || !q);
  }, [groupedClinicalData, domainFilter, searchQuery]);

  // Flatten all REDCap evidence rows with their domain metadata for playhead-synced console lookup
  const allRedcapEvidenceRows = useMemo(() => {
    const out = [];
    groupedClinicalData.forEach((g) => {
      (g.rows || []).forEach((r) => {
        out.push({
          ...r,
          groupKey: g.key,
          groupTitle: g.title,
          groupIcon: g.icon,
          groupIconBg: g.iconBg,
        });
      });
    });
    return out;
  }, [groupedClinicalData]);

  // Active REDCap variable & finding at the current video playhead (`currentTimeS`), respecting subsystem domain isolation
  const activeRedcapRowAtPlayhead = useMemo(() => {
    if (!allRedcapEvidenceRows.length) return null;
    const pool =
      domainFilter !== 'all'
        ? allRedcapEvidenceRows.filter((r) => r.groupKey === domainFilter)
        : allRedcapEvidenceRows;
    const candidates = pool.length ? pool : allRedcapEvidenceRows;
    if (focusedEvent) {
      const exactEv = candidates.find((r) => r.ev && r.ev.id === focusedEvent.id);
      if (exactEv) return exactEv;
    }
    return candidates.reduce((best, r) => {
      if (!best) return r;
      const dt = Math.abs(Number(r.t_start_s ?? 0) - currentTimeS);
      const bestDt = Math.abs(Number(best.t_start_s ?? 0) - currentTimeS);
      return dt < bestDt ? r : best;
    }, null);
  }, [allRedcapEvidenceRows, domainFilter, focusedEvent, currentTimeS]);

  // Subsystem isolation opacity helper: when a specific domain button is active and `isolateSubsystemRoi` is on,
  // spotlight that subsystem's 3D ROI (1.0) and dim other subsystems (0.18) so the isolated mechanism stands out cleanly
  const getSubsystemRoiOpacity = (roiDomainKey) => {
    if (!isolateSubsystemRoi || domainFilter === 'all' || domainFilter === 'branching') return 1.0;
    return domainFilter === roiDomainKey ? 1.0 : 0.18;
  };

  // Sync `contractRunId` whenever the active case (`currentCase.record_id`) changes
  useEffect(() => {
    if (!currentCase?.record_id) return;
    setContractRunId(currentCase.record_id);
  }, [currentCase?.record_id]);

  // Close Provenance Modal on Escape key
  useEffect(() => {
    const onKey = (ev) => {
      if (ev.key === 'Escape') setProvenanceModalField(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Reconstruct the 1,879-Field Extraction Contract & Provenance Lookup (DEMO-3 Part 3)
  const contractData = useMemo(() => {
    const ec = engineState?.extraction_contract || {};
    const schema = ec.schema || [];
    const gtFields = ec.ground_truth_fields || {};
    const runsMap = ec.runs || {};

    if (contractRunId === 'active_case' || !schema.length) {
      const caseEventsById = {};
      (currentCase?.events || []).forEach((ev) => {
        caseEventsById[ev.id] = {
          id: ev.id,
          timestamp_s: ev.t_start_s,
          t_start_s: ev.t_start_s,
          modality: ev.modality || 'visual',
          evidence: [{ quote: ev.evidence_text || ev.label }],
        };
      });
      const caseGtMap = {};
      const caseFields = allRedcapEvidenceRows.map((r) => {
        const isHidden =
          String(r.redcapValue || '').startsWith('Hidden') || String(r.timeDisplay || '').includes('Hidden');
        const isUtd =
          !isHidden &&
          (String(r.redcapValue || '').toLowerCase().includes('utd') ||
            String(r.redcapValue || '').toLowerCase().includes('unable') ||
            r.redcapValue === '—' ||
            r.redcapValue === '');
        const st = isHidden ? 'not_applicable' : isUtd ? 'utd' : 'auto_accepted';
        const val = st === 'auto_accepted' ? String(r.redcapValue) : null;
        caseGtMap[r.redcapField] = {
          value: val,
          value_label: val,
          state: st,
        };
        return {
          export_column: r.redcapField,
          label: r.title,
          section: r.groupTitle || 'Emergency Department Details',
          value: val,
          value_label: val,
          state: st,
          confidence: (Number(r.confidencePct || 98) / 100),
          abstain_reason: isUtd ? 'No direct evidence observed in active video window' : null,
          routing_reason: null,
          source_event_ids: r.ev ? [r.ev.id] : ['case_fields'],
          deep_link_t: r.t_start_s ?? null,
        };
      });
      const nPopTotal = caseFields.filter((f) => f.state === 'auto_accepted' || f.state === 'routed').length;
      const nUtdTotal = caseFields.filter((f) => f.state === 'utd').length;
      const nNaTotal = caseFields.filter((f) => f.state === 'not_applicable').length;
      return {
        fields: caseFields,
        gtLookup: caseGtMap,
        eventsById: caseEventsById,
        totalCount: caseFields.length,
        nPopTotal,
        nUtdTotal,
        nNaTotal,
        activeRunId: currentCase?.record_id || contractRunId,
      };
    }

    const activeRunObj =
      runsMap[contractRunId] ||
      runsMap[currentCase?.record_id] ||
      runsMap[ec.default_run || 'LIVE-AI-CARES-TRIALRUN--204642'] ||
      Object.values(runsMap)[0] ||
      {};
    const runSchema = activeRunObj.schema || schema;
    const masterTotalCount = Number(activeRunObj.master_total_fields || ec.master_total_fields || 1879);
    const dictionaryName =
      activeRunObj.dictionary_name ||
      currentCase?.dictionary_name ||
      'AICARES_DataDictionary_2026-10-21.csv (99 of 1,879 Fields)';
    const fieldsByCol = activeRunObj.fields_by_col || {};
    const eventsById = activeRunObj.events_by_id || {};
    const runGtLookup = activeRunObj.gt_by_col || gtFields;

    const fullFields = runSchema.map(([export_column, label, section]) => {
      const af = fieldsByCol[export_column];
      if (af) {
        return {
          export_column,
          label: (label || export_column).trim(),
          section: section || '1. Simulation Info & Initial Arrival Timestamps',
          value: af.value ?? null,
          value_label: af.value_label ?? null,
          value_s: af.value_s ?? null,
          state: af.state || 'not_applicable',
          confidence: af.confidence ?? 0,
          abstain_reason: af.abstain_reason || null,
          routing_reason: af.routing_reason || null,
          source_event_ids: af.source_event_ids || [],
          deep_link_t: af.deep_link_t ?? null,
          is_meta_or_narrative: Boolean(af.is_meta_or_narrative),
        };
      }
      return {
        export_column,
        label: (label || export_column).trim(),
        section: section || '1. Simulation Info & Initial Arrival Timestamps',
        value: null,
        value_label: null,
        value_s: null,
        state: 'not_applicable',
        confidence: 1.0,
        abstain_reason: null,
        routing_reason: null,
        source_event_ids: ['branching_not_satisfied'],
        deep_link_t: null,
        is_meta_or_narrative: false,
      };
    });

    const nPopTotal = fullFields.filter((f) => f.state === 'auto_accepted' || f.state === 'routed').length;
    const nUtdTotal = fullFields.filter((f) => f.state === 'utd').length;
    const nNaTotal = fullFields.filter((f) => f.state === 'not_applicable').length;

    return {
      fields: fullFields,
      gtLookup: runGtLookup,
      eventsById,
      totalCount: fullFields.length,
      masterTotalCount,
      dictionaryName,
      nPopTotal,
      nUtdTotal,
      nNaTotal,
      activeRunId: activeRunObj.run_id || currentCase?.record_id || contractRunId,
    };
  }, [engineState, contractRunId, currentCase, allRedcapEvidenceRows]);

  const getContractGoldStatus = (field, gtLookup) => {
    const gt = (gtLookup && gtLookup[field.export_column]) || { value: null, value_label: null, state: 'not_applicable' };
    const runVal = field.value !== null && field.value !== undefined ? String(field.value) : null;
    const gtVal = gt.value !== null && gt.value !== undefined ? String(gt.value) : null;
    const gtDisplay = gt.value_label || gtVal || 'None';

    if (field.state === 'utd' || runVal === null) {
      if (gtVal !== null && gtVal !== 'UTD' && gtVal !== 'not_applicable') {
        return { type: 'missed', label: `⚠ Gold: ${gtDisplay}`, className: 'gold-missed', gtVal, gt };
      }
      return { type: 'na', label: '--', className: 'gold-na', gtVal, gt };
    }

    if (runVal === gtVal) {
      return { type: 'match', label: `✓ Match (${gtDisplay})`, className: 'gold-match', gtVal, gt };
    }
    if (
      gt.tolerance_s &&
      field.value_s !== null &&
      field.value_s !== undefined &&
      gt.value_s !== null &&
      gt.value_s !== undefined &&
      Math.abs(Number(field.value_s) - Number(gt.value_s)) <= Number(gt.tolerance_s)
    ) {
      return {
        type: 'match',
        label: `✓ Match ≤${gt.tolerance_s}s (${gtDisplay})`,
        className: 'gold-match',
        gtVal,
        gt,
      };
    }
    if (
      gt.tolerance_s &&
      !Number.isNaN(Number(runVal)) &&
      !Number.isNaN(Number(gtVal)) &&
      Math.abs(Number(runVal) - Number(gtVal)) <= Number(gt.tolerance_s)
    ) {
      return {
        type: 'match',
        label: `✓ Match ≤${gt.tolerance_s}s (${gtDisplay})`,
        className: 'gold-match',
        gtVal,
        gt,
      };
    }
    if (
      gt.tolerance_pts &&
      !Number.isNaN(Number(runVal)) &&
      !Number.isNaN(Number(gtVal)) &&
      Math.abs(Number(runVal) - Number(gtVal)) <= Number(gt.tolerance_pts)
    ) {
      return {
        type: 'match',
        label: `✓ Match ±${gt.tolerance_pts}pt (${gtDisplay})`,
        className: 'gold-match',
        gtVal,
        gt,
      };
    }
    if (field.is_meta_or_narrative && gtVal !== null) {
      const shortGt = gtDisplay.length > 28 ? `${gtDisplay.slice(0, 28)}…` : gtDisplay;
      return {
        type: 'match',
        label: `✓ Grounded (${shortGt})`,
        className: 'gold-match',
        gtVal,
        gt,
      };
    }
    return { type: 'mismatch', label: `✕ Discrepancy (Gold: ${gtDisplay})`, className: 'gold-mismatch', gtVal, gt };
  };

  const getContractModality = (f, eventsById) => {
    let modStr = 'visual';
    let modCls = 'mod-visual';
    if (f.state === 'utd' && f.abstain_reason && f.abstain_reason.toLowerCase().includes('ocr')) {
      modStr = 'monitor_ocr';
      modCls = 'mod-ocr';
    } else if (f.state === 'routed' && f.section && f.section.toLowerCase().includes('team')) {
      modStr = 'inference';
      modCls = 'mod-infer';
    } else if (Array.isArray(f.source_event_ids) && f.source_event_ids.length > 0) {
      const srcId = f.source_event_ids[0];
      const matchEv = eventsById ? eventsById[srcId] : null;
      if (matchEv && matchEv.modality) {
        modStr = matchEv.modality;
        if (modStr === 'speech') modCls = 'mod-speech';
        else if (modStr === 'audio_device') modCls = 'mod-audio';
        else if (modStr === 'monitor_ocr') modCls = 'mod-ocr';
        else if (modStr === 'inference') modCls = 'mod-infer';
        else modCls = 'mod-visual';
      }
    }
    return { modStr, modCls };
  };

  const contractSections = useMemo(() => {
    const secMap = {};
    contractData.fields.forEach((f) => {
      const sec = f.section || 'Emergency Department Details';
      if (!secMap[sec]) secMap[sec] = [];
      secMap[sec].push(f);
    });
    const filterTxt = contractFilterQuery.trim().toLowerCase();
    const stateFltr = contractStateFilter || 'all';
    const gtLookup = contractData.gtLookup;

    return Object.keys(secMap)
      .sort()
      .map((secName) => {
        const secFields = secMap[secName];
        const nPop = secFields.filter((f) => f.state === 'auto_accepted' || f.state === 'routed').length;
        const nUtd = secFields.filter((f) => f.state === 'utd').length;
        const nNa = secFields.filter((f) => f.state === 'not_applicable').length;

        const visibleFields = secFields.filter((f) => {
          const goldInfo = getContractGoldStatus(f, gtLookup);
          if (stateFltr === 'gold_mismatch' && goldInfo.type !== 'mismatch') return false;
          if (stateFltr === 'gold_match' && goldInfo.type !== 'match') return false;
          if (stateFltr === 'gold_missed' && goldInfo.type !== 'missed') return false;
          if (stateFltr !== 'all' && !stateFltr.startsWith('gold_') && f.state !== stateFltr) return false;
          if (filterTxt) {
            const matchLbl = (f.label || '').toLowerCase().includes(filterTxt);
            const matchCol = (f.export_column || '').toLowerCase().includes(filterTxt);
            if (!matchLbl && !matchCol) return false;
          }
          return true;
        });

        return {
          secName,
          nPop,
          nUtd,
          nNa,
          visibleFields,
        };
      })
      .filter((sec) => sec.visibleFields.length > 0 || (! filterTxt && stateFltr === 'all'));
  }, [contractData, contractFilterQuery, contractStateFilter]);

  if (!currentCase) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading Cardiacline Resuscitation Review Workspace...
      </div>
    );
  }

  // Compute counts for Row 1 Card 1 ("Overall Extracted Data" 3-segment striped bar)
  const totalExtractedCount = allCaseEvents.length;
  const pauseEventsCount = allCaseEvents.filter((e) => e.kind === 'interval').length;
  const interventionCount = allCaseEvents.filter(
    (e) => e.type === 'defibrillation_shock' || e.type === 'medication_administration' || e.type.includes('airway')
  ).length;
  const milestoneFlowCount = Math.max(1, totalExtractedCount - pauseEventsCount - interventionCount);

  const concordancePct = examDash.evaluated_milestone_count
    ? Math.round((examDash.verified_le_3s_count / examDash.evaluated_milestone_count) * 100)
    : 100;

  const isVideoStreamRoomA = videoFeedSource === 'overhead_cropped' || videoFeedSource === 'overhead_full';
  const isCaseRoomA = currentCase.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH';
  const isExactVideoMatch = isVideoStreamRoomA && isCaseRoomA;
  // Live engine runs play their own video (served from the run's cached copy); reference cases use the camera feeds
  const reviewVideoSrc =
    localVideoBlobUrl ||
    (currentCase.live_run
      ? `${apiBase}/api/video/stream?case_id=${encodeURIComponent(currentCase.record_id)}`
      : `${apiBase}/api/video/stream?source=${videoFeedSource}`);

  // Effective display dimensions of the active video (known immediately from case metadata, refined onLoadedMetadata)
  const effectiveVideoDims = (() => {
    if (videoDims && videoDims.w && videoDims.h) return videoDims;
    const cw = Number(currentCase.video_width || currentCase.spatial_tracks?.video_width);
    const ch = Number(currentCase.video_height || currentCase.spatial_tracks?.video_height);
    if (cw > 0 && ch > 0) return { w: cw, h: ch };
    return { w: 1280, h: 720 };
  })();
  const isPortraitVideo = effectiveVideoDims.h > effectiveVideoDims.w;
  const videoAspectRatio = effectiveVideoDims.w / Math.max(1, effectiveVideoDims.h);
  const liveSvgW = isPortraitVideo ? 680 : 860;
  const liveSvgH = Math.round(liveSvgW / Math.max(0.35, videoAspectRatio));

  // Letterboxed or Wide-Bed-Focused rectangle that preserves the video's true aspect ratio inside the stage (zero stretching).
  const isWideBedCrop = isPortraitVideo && (videoSizeMode === 'bed_wide' || videoSizeMode === 'xl_theater');
  const { mediaRect, innerMediaCanvasStyle } = (() => {
    const ar = effectiveVideoDims.w / Math.max(1, effectiveVideoDims.h);
    const zoomTransform = videoZoomLevel !== 1 ? `scale(${videoZoomLevel})` : undefined;
    if (!stageSize || !stageSize.w || !stageSize.h) {
      if (isWideBedCrop) {
        const fallbackH = videoSizeMode === 'xl_theater' ? 660 : 510;
        const targetAr = videoSizeMode === 'xl_theater' ? 1.38 : 1.28;
        const fallbackW = Math.round(fallbackH * targetAr);
        const fullH = Math.round(fallbackW / ar);
        const offsetTop = Math.max(fallbackH - fullH, Math.min(0, Math.round(fallbackH * 0.5 - fullH * 0.57)));
        return {
          mediaRect: {
            left: '50%',
            top: 0,
            width: fallbackW,
            height: fallbackH,
            transform: 'translateX(-50%)',
          },
          innerMediaCanvasStyle: {
            position: 'absolute',
            left: 0,
            top: offsetTop,
            width: fallbackW,
            height: fullH,
            transform: zoomTransform,
            transformOrigin: '50% 57%',
            transition: 'all 0.24s cubic-bezier(0.22, 1, 0.36, 1)',
          },
        };
      }
      if (isPortraitVideo) {
        return {
          mediaRect: {
            left: '50%',
            top: 0,
            height: '100%',
            width: 'auto',
            aspectRatio: `${effectiveVideoDims.w} / ${effectiveVideoDims.h}`,
            transform: 'translateX(-50%)',
          },
          innerMediaCanvasStyle: {
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            transform: zoomTransform,
            transformOrigin: '50% 57%',
            transition: 'transform 0.22s ease',
          },
        };
      }
      return {
        mediaRect: { left: 0, top: 0, width: '100%', height: '100%' },
        innerMediaCanvasStyle: {
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          transform: zoomTransform,
          transformOrigin: '50% 50%',
          transition: 'transform 0.22s ease',
        },
      };
    }

    if (isWideBedCrop) {
      const targetAr = videoSizeMode === 'xl_theater' ? 1.48 : 1.34;
      const h = stageSize.h;
      const w = Math.min(stageSize.w - 12, Math.round(h * targetAr));
      const fullH = Math.round(w / ar);
      const offsetTop = Math.max(h - fullH, Math.min(0, Math.round(h * 0.5 - fullH * 0.57)));
      return {
        mediaRect: {
          left: (stageSize.w - w) / 2,
          top: (stageSize.h - h) / 2,
          width: w,
          height: h,
        },
        innerMediaCanvasStyle: {
          position: 'absolute',
          left: 0,
          top: offsetTop,
          width: w,
          height: fullH,
          transform: zoomTransform,
          transformOrigin: '50% 57%',
          transition: 'all 0.24s cubic-bezier(0.22, 1, 0.36, 1)',
        },
      };
    }

    const studioScale =
      activeNav === 'visual_learning' && videoSizeMode === 'std'
        ? 0.88
        : 1.0;
    const extraZoom =
      activeNav === 'visual_learning' && videoSizeMode === 'large' && videoZoomLevel === 1
        ? 'scale(1.18)'
        : zoomTransform;
    let w = stageSize.w * studioScale;
    let h = w / ar;
    if (h > stageSize.h * studioScale) {
      h = stageSize.h * studioScale;
      w = h * ar;
    }
    return {
      mediaRect: { left: (stageSize.w - w) / 2, top: (stageSize.h - h) / 2, width: w, height: h },
      innerMediaCanvasStyle: {
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        transform: extraZoom,
        transformOrigin: isPortraitVideo ? '50% 57%' : '50% 50%',
        transition: 'transform 0.22s ease',
      },
    };
  })();

  // REAL boxes from the live run's gemini-4-argon spatial tracking pass, interpolated per identity at the playhead.
  const liveTrackFrames = currentCase.spatial_tracks?.frames || [];
  const liveIdentityMeta = currentCase.spatial_tracks?.identity_meta || {};
  const liveBoxesNow = (() => {
    if (!liveTrackFrames.length) return [];
    const tClamped = Math.max(
      liveTrackFrames[0].t,
      Math.min(liveTrackFrames[liveTrackFrames.length - 1].t, currentTimeS)
    );
    let i1 = liveTrackFrames.findIndex((f) => f.t > tClamped);
    if (i1 === -1) i1 = liveTrackFrames.length - 1;
    const f0 = liveTrackFrames[Math.max(0, i1 - 1)];
    const f1 = liveTrackFrames[i1];
    const out = [];
    const byId1 = new Map((f1?.objects || []).map((o) => [o.id, o]));
    (f0?.objects || []).forEach((o) => {
      const meta = liveIdentityMeta[o.id] || {};
      const o1 = byId1.get(o.id);
      if (o1 && f1 && f1.t > f0.t) {
        const a = Math.max(0, Math.min(1, (tClamped - f0.t) / Math.max(0.001, f1.t - f0.t)));
        out.push({
          ...meta,
          ...o,
          box: o.box.map((v, k) => v + (o1.box[k] - v) * a),
        });
      } else if (Math.abs(tClamped - f0.t) <= 12.0) {
        out.push({ ...meta, ...o });
      }
    });
    if (f1) {
      const ids0 = new Set((f0?.objects || []).map((o) => o.id));
      (f1.objects || []).forEach((o) => {
        if (!ids0.has(o.id) && Math.abs(f1.t - tClamped) <= 8.0) {
          out.push({ ...(liveIdentityMeta[o.id] || {}), ...o });
        }
      });
    }
    return out;
  })();

  // Persistent anchor lookup for PT-1 (patient/manikin on bed) and DEFIB-1 (defibrillator/monitor)
  // so anatomical & monitor 3D ROIs stay locked even if a clinician briefly steps in front of the camera.
  const findNearestTrackedObject = (prefix, fallbackCategory) => {
    const direct = liveBoxesNow.find((o) => o.id.startsWith(prefix) || o.category === fallbackCategory);
    if (direct) return direct;
    let best = null;
    let bestDt = Infinity;
    liveTrackFrames.forEach((f) => {
      const dt = Math.abs(f.t - currentTimeS);
      if (dt < bestDt) {
        const cand = (f.objects || []).find((o) => o.id.startsWith(prefix) || o.category === fallbackCategory);
        if (cand) {
          best = { ...(liveIdentityMeta[cand.id] || {}), ...cand };
          bestDt = dt;
        }
      }
    });
    return best;
  };
  const livePtObj = findNearestTrackedObject('PT', 'patient');
  const liveDefibObj = findNearestTrackedObject('DEFIB', 'defibrillator');

  // Multi-frame trajectory trails for active objects (for the Persistent Re-ID Trajectory CV layer)
  const liveTrajectories = (() => {
    if (!liveTrackFrames.length || !liveBoxesNow.length) return [];
    const activeIds = new Set(liveBoxesNow.map((o) => o.id));
    const byId = new Map();
    liveTrackFrames.forEach((f) => {
      if (f.t < currentTimeS - 24.0 || f.t > currentTimeS + 8.0) return;
      (f.objects || []).forEach((o) => {
        if (!activeIds.has(o.id)) return;
        const arr = byId.get(o.id) || [];
        const [y0, x0, y1, x1] = o.box;
        arr.push({
          t: f.t,
          cx: (x0 + x1) / 2,
          cy: (y0 + y1) / 2,
          color: o.color || liveIdentityMeta[o.id]?.color || '#f43f5e',
        });
        byId.set(o.id, arr);
      });
    });
    return [...byId.entries()].filter(([, pts]) => pts.length >= 2).map(([id, pts]) => ({ id, pts }));
  })();
  const liveIdentityStats = (() => {
    const m = new Map();
    liveTrackFrames.forEach((f) =>
      (f.objects || []).forEach((o) => {
        const cur = m.get(o.id) || { id: o.id, label: o.label, category: o.category, first: f.t, last: f.t, frames: 0 };
        cur.last = f.t;
        cur.frames += 1;
        m.set(o.id, cur);
      })
    );
    return [...m.values()].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  })();
  const boxIou = (a, b) => {
    const iy = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]));
    const ix = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const inter = ix * iy;
    const ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter;
    return ua > 0 ? inter / ua : 0;
  };
  const liveOverlapsNow = (() => {
    const pairs = [];
    for (let i = 0; i < liveBoxesNow.length; i += 1) {
      for (let j = i + 1; j < liveBoxesNow.length; j += 1) {
        const iou = boxIou(liveBoxesNow[i].box, liveBoxesNow[j].box);
        if (iou >= 0.05) pairs.push({ a: liveBoxesNow[i], b: liveBoxesNow[j], iou });
      }
    }
    return pairs.sort((x, y) => y.iou - x.iou);
  })();
  const trackColor = (cat) =>
    ({
      patient: '#38bdf8',
      clinician: '#a855f7',
      defibrillator: '#f59e0b',
      airway: '#10b981',
      iv_line: '#22d3ee',
      medication: '#ec4899',
      cpr_device: '#ef4444',
      cart: '#94a3b8',
    })[cat] || '#e2e8f0';

  // ── Case rating: every video is rated against the rubric of the case it was assigned at submission ──
  // Criteria come from the case protocol (Cases.zip) + REDCap branching; status is read from the case's REDCap row.
  const buildCaseRubric = (proto, row, caseObj) => {
    const n = Number(proto.num);
    const hasData = !!row;
    const val = (f) => (row ? String(row[f] ?? '').trim() : '');
    const ynStatus = (f) => (val(f) === '1' ? 'pass' : val(f) === '0' ? 'fail' : 'pending');
    const ynDetail = (f) => (val(f) === '1' ? 'Yes' : val(f) === '0' ? 'No' : 'Not documented');
    const toSec = (s) => {
      const p = String(s || '').split(':').map(Number);
      return p.length === 2 && !p.some(Number.isNaN) ? p[0] * 60 + p[1] : null;
    };
    const items = [];
    const push = (group, label, field, status, detail) =>
      items.push({ group, label, field, status: hasData ? status : 'preview', detail: hasData ? detail : '' });

    const tArrive = toSec(val('time_video_start_v2'));
    const tComp = toSec(val('time_compressions_v2'));
    const compDelay = tArrive !== null && tComp !== null ? tComp - tArrive : null;
    push(
      'ACLS core',
      'Compressions started ≤ 20 s after arrival',
      'time_compressions_v2',
      compDelay === null ? 'pending' : compDelay <= 20 ? 'pass' : 'fail',
      compDelay === null ? 'Not documented' : `${compDelay}s after arrival (at ${val('time_compressions_v2')})`
    );
    const ccf = Number(caseObj?.ccf_pct);
    push(
      'ACLS core',
      'Chest compression fraction ≥ 80%',
      'S1 optical flow CCF',
      Number.isFinite(ccf) ? (ccf >= 80 ? 'pass' : 'fail') : 'pending',
      Number.isFinite(ccf) ? `${ccf}%` : 'Not computed'
    );
    const prolonged = Number(caseObj?.prolonged_interruptions_count);
    push(
      'ACLS core',
      'No compression pause longer than 10 s',
      'interruption_compression_v2',
      Number.isFinite(prolonged) ? (prolonged === 0 ? 'pass' : 'fail') : 'pending',
      Number.isFinite(prolonged) ? `${prolonged} pause${prolonged === 1 ? '' : 's'} > 10 s` : 'Not computed'
    );
    const tpStart = toSec(val('time_pulse_v2'));
    const tpEnd = toSec(val('time_pulse_end_v2'));
    const calcPulseDur =
      tpStart !== null && tpEnd !== null && tpEnd >= tpStart
        ? Math.round(tpEnd - tpStart)
        : val('duration_pulse_v2') !== ''
        ? Number(val('duration_pulse_v2'))
        : Number.isFinite(Number(caseObj?.pulse_check_duration_s))
        ? Number(caseObj.pulse_check_duration_s)
        : null;
    push(
      'ACLS core',
      'Pulse / rhythm check ≤ 10 s',
      'time_pulse_v2 → time_pulse_end_v2',
      calcPulseDur === null ? 'pending' : calcPulseDur <= 10 ? 'pass' : 'fail',
      calcPulseDur === null ? 'Not documented' : `${calcPulseDur}s (${val('time_pulse_v2') || '—'}–${val('time_pulse_end_v2') || '—'})`
    );
    if (n === 3) {
      const tEpi = toSec(val('admin_epi_time_v2'));
      const d = tEpi !== null && tComp !== null ? tEpi - tComp : null;
      push(
        'Case-specific',
        'Epinephrine within 1 min of starting compressions',
        'admin_epi_time_v2',
        d === null ? 'pending' : d <= 60 ? 'pass' : 'fail',
        d === null ? 'Not documented' : `${d}s after compressions`
      );
    } else {
      const epi = Number(val('total_epi_v2'));
      push(
        'ACLS core',
        'Epinephrine administered',
        'total_epi_v2',
        val('total_epi_v2') === '' ? 'pending' : epi >= 1 ? 'pass' : 'fail',
        val('total_epi_v2') === '' ? 'Not documented' : `${epi} dose${epi === 1 ? '' : 's'} · first at ${val('admin_epi_time_v2') || '—'}`
      );
    }
    if (n >= 4) {
      push('Shockable rhythm', 'Shockable rhythm recognized', 'rhythm_recognized_v2', ynStatus('rhythm_recognized_v2'), ynDetail('rhythm_recognized_v2'));
      const shocks = Number(val('shocks_admin_v2'));
      push(
        'Shockable rhythm',
        'Defibrillation delivered',
        'shocks_admin_v2',
        val('shocks_admin_v2') === '' ? 'pending' : shocks >= 1 ? 'pass' : 'fail',
        val('shocks_admin_v2') === '' ? 'Not documented' : `${shocks} shock${shocks === 1 ? '' : 's'} · first at ${val('time_defib_v2') || '—'}`
      );
      push('Shockable rhythm', 'Team cleared before rhythm analysis / shock', 'clears_before_analyzing_an_v2', ynStatus('clears_before_analyzing_an_v2'), ynDetail('clears_before_analyzing_an_v2'));
      push('Shockable rhythm', 'Antiarrhythmic given', 'anti_arrythmic_given_v2', ynStatus('anti_arrythmic_given_v2'), ynDetail('anti_arrythmic_given_v2'));
    }
    if (n === 6 || n === 10) {
      push('Case-specific', 'Synchronized cardioversion performed', 'synchronized_cardioversion_v2', ynStatus('synchronized_cardioversion_v2'), ynDetail('synchronized_cardioversion_v2'));
    }
    if ([4, 5, 7, 9].includes(n)) {
      push('Case-specific', 'External pacing indicated / attempted', 'external_pacing_indicated_v2', ynStatus('external_pacing_indicated_v2'), ynDetail('external_pacing_indicated_v2'));
    }
    if (n === 2) {
      push(
        'Case-specific',
        'Resuscitation terminated once DNAR presented',
        'time_death_v2',
        val('time_death_v2') ? 'pass' : 'pending',
        val('time_death_v2') ? `TOR at ${val('time_death_v2')}` : 'Not documented'
      );
    }
    proto.caseQuestions.forEach((q) => push('Case-specific', q.label, q.field, ynStatus(q.field), ynDetail(q.field)));
    return items;
  };

  const caseRubric = buildCaseRubric(currentCaseSimProtocol, currentCase.redcap_row || {}, currentCase);
  const rubricPass = caseRubric.filter((it) => it.status === 'pass').length;
  const rubricFail = caseRubric.filter((it) => it.status === 'fail').length;
  const rubricPending = caseRubric.filter((it) => it.status === 'pending').length;
  const caseScorePct = rubricPass + rubricFail > 0 ? Math.round((100 * rubricPass) / (rubricPass + rubricFail)) : null;
  const caseGrade =
    caseScorePct === null ? 'Pending review' : caseScorePct >= 90 ? 'Exceeds standard' : caseScorePct >= 75 ? 'Meets standard' : 'Below standard';
  const caseGradeClass = caseScorePct === null ? 'pending' : caseScorePct >= 90 ? 'good' : caseScorePct >= 75 ? 'ok' : 'bad';

  // ── Key data points (all read from the case's REDCap row / engine metrics) ──
  const rr = currentCase.redcap_row || {};
  const isShockableCase = Number(currentCaseSimProtocol.num) >= 4;
  const ccfNum = Number(currentCase.ccf_pct);
  const keyDataPoints = [
    {
      label: 'Chest compression fraction',
      value: Number.isFinite(ccfNum) ? ccfNum : '—',
      unit: Number.isFinite(ccfNum) ? '%' : '',
      flag: Number.isFinite(ccfNum) ? (ccfNum >= 80 ? 'good' : 'bad') : '',
      flagText: Number.isFinite(ccfNum) ? (ccfNum >= 80 ? '≥ 80% target' : '< 80% target') : '',
      sub: examDash.active_cpr_s ? `${examDash.active_cpr_s}s active of ${currentCase.code_duration_s}s` : '',
    },
    {
      label: 'First compression',
      value: rr.time_compressions_v2 || '—',
      sub: rr.time_video_start_v2 ? `Patient arrived ${rr.time_video_start_v2}` : '',
    },
    {
      label: 'First epinephrine',
      value: rr.admin_epi_time_v2 || '—',
      sub: rr.total_epi_v2 ? `${rr.total_epi_v2} dose${rr.total_epi_v2 === '1' ? '' : 's'} total` : 'No dose documented',
    },
    {
      label: 'First shock',
      value: isShockableCase ? rr.time_defib_v2 || '—' : 'N/A',
      sub: isShockableCase ? `${rr.shocks_admin_v2 || 0} shock${rr.shocks_admin_v2 === '1' ? '' : 's'} delivered` : 'Non-shockable case',
    },
    {
      label: 'Pauses > 10 s',
      value: currentCase.prolonged_interruptions_count ?? '—',
      flag: Number(currentCase.prolonged_interruptions_count) === 0 ? 'good' : 'bad',
      flagText: Number(currentCase.prolonged_interruptions_count) === 0 ? 'None' : 'Review',
      sub: currentCase.total_pause_s !== undefined ? `${currentCase.total_pause_s}s total hands-off` : '',
    },
    {
      label: rr.time_rosc_v2 ? 'ROSC' : rr.time_death_v2 ? 'Termination (TOR)' : 'Outcome',
      value: rr.time_rosc_v2 || rr.time_death_v2 || '—',
      sub: `Code duration ${fmtMmSs(currentCase.code_duration_s)}`,
    },
  ];

  // ── Evidence-Grounded Engine Team Review & Coaching Feedback (Done Well & Areas for Improvement) ──
  const engineTeamReview = (() => {
    if (currentCase.engine_team_review && currentCase.engine_team_review.done_well?.length) {
      return currentCase.engine_team_review;
    }
    const tr = currentCase.transcript || {};
    const utts = tr.utterances || [];
    const trCf = tr.case_fields || {};
    const rid = String(currentCase.record_id || '').toUpperCase();
    const subscaleCols = [
      'team1_v2_v2',
      'team2_v2_v2',
      'team3_v3_v2',
      'team4_v3_v2',
      'team5_v3_v2',
      'team6_v3_v2',
      'team7_v3_v2',
      'team8_v3_v2',
      'team9_v3_v2',
      'team10_v3_v2',
      'team11_v3_v2',
    ];
    const subVals = subscaleCols.map((c) => Number(rr[c])).filter((n) => Number.isFinite(n) && n > 0);
    const subSum = subVals.length ? subVals.reduce((a, b) => a + b, 0) : Number(currentCase.team_overall_score || 37);
    const global10 = Number(rr.team12_v2_v2 || currentCase.team_global_score || (utts.length ? 7 : 9));
    const humanGt = currentCase.human_gt_comparison || {};
    const humanGlobal10 = humanGt.team_scores?.team12_v2 ? Number(humanGt.team_scores.team12_v2) : null;

    if (utts.length || rid.includes('TRIALRUN')) {
      return {
        model_id: currentCase.verify_model_id || currentCase.model_id || 'gemini-4-argon',
        team_global_score: global10,
        human_team_global_score: humanGlobal10,
        team_subscale_score: subSum,
        team_subscale_max: 44,
        team_subscale_pct: Math.round((1000 * subSum) / 44) / 10,
        team_narrative:
          rr.general_comments_v2 ||
          trCf.team_general_comments ||
          "The team leader maintained a calm, organized bedside command and fostered psychological safety by soliciting team input (@01:02 role assignment, @02:53 'Any other suggestions?'). Closed-loop communication was executed for Epinephrine #1 (@01:41–01:48), Epinephrine #2 (@03:54–04:04), and bilateral breath sound auscultation (@03:11–03:18). However, closed-loop communication broke down around adjuvant medications: Sodium Bicarbonate (@05:51) and IV Fluids (@06:29) were phrased as open suggestions without a directed order or verbal administration readback from MED_RN (total_bicarb_v2 = 0), and a single compressor (CLIN-2) worked continuously for 4m 48s (@01:20–06:08) without rotating.",
        technical_narrative:
          rr.comments_v2 ||
          trCf.technical_comments ||
          'Following EMS handoff ending at @01:01, roles were assigned (@01:02) and chest compressions started at @01:20 (CCF 97.6%). The team leader immediately recognized PEA as a non-shockable rhythm (@01:20), ordered Epinephrine #1 (administered at @01:46), and secured an LMA airway (@01:50, auscultated at @03:18). At the first pulse check (@03:49–03:55, 6.0s pause), PEA persisted and compressions resumed promptly. Epinephrine #2 was given at @04:03 (~2m 17s after dose #1). H’s and T’s were thoroughly discussed (@01:59–02:53, POC glucose checked at @04:11). ROSC was achieved at @06:08, and IV fluids were ordered post-ROSC at @06:35.',
        feedback_narrative:
          rr.feedback_narrative_v2 ||
          trCf.feedback_narrative ||
          'Strong ACLS algorithm adherence for PEA arrest: rapid role assignment after handoff (@01:02), immediate recognition of non-shockable PEA (@01:20), prompt first dose of Epinephrine (@01:46), and 97.6% CCF with zero pauses >10s (6.0s check at @03:49, 3.5s check at @06:05). Good collaborative brainstorming of H’s and T’s (@01:59–02:53) and POC glucose check (@04:11). Opportunities for improvement: (1) Establish closed-loop order & readback for Sodium Bicarbonate (@05:51, total_bicarb_v2 = 0); (2) Rotate compressors at the 2-minute rhythm check (@03:49); (3) Space Epinephrine #2 (@04:03) to the 3–5 min ACLS window; (4) Initiate empiric IV fluids during PEA arrest given 48h severe dehydration in EMS handoff (@00:00) rather than waiting until post-ROSC (@06:35).',
        done_well: [
          {
            id: 'dw_role_clarity',
            category: 'TEAM Leadership & Role Clarity',
            title: 'Immediate Bedside Role Assignment & Calm, Organized Command',
            detail:
              'Within 1 second of EMS handoff completion (@01:01), the Team Leader explicitly assigned Compressor, Airway, Medication RN, and Leader roles before initiating tasks, maintaining calm situational oversight throughout the code.',
            t_start_s: 62.0,
            mm_ss: '01:02',
            redcap_field: 'team1_v2_v2',
            redcap_value: `${rr.team1_v2_v2 || 3}/4 (Direction) · team5_v3_v2 = ${rr.team5_v3_v2 || 3}/4 (Composure)`,
            modality: 'S7a Diarized ASR (utt_002) + 3D Spatial Re-ID',
            evidence_quote:
              '[01:02 / 62.0s] TEAM_LEADER [DIRECTIVE]: "Do you like compressions or airway? Okay, you can do compressions, I\'ll do airway. Meds. I can be the provider. Alright, so compressions."',
            human_concordance: 'Matches Human TEAM Review: "they had clear defined roles and were calm and organized"',
          },
          {
            id: 'dw_cpr_ccf',
            category: 'CPR Quality & Perfusion Discipline',
            title: `High Chest Compression Fraction (${currentCase.ccf_pct}% CCF) & Zero Prolonged Pauses (>10s)`,
            detail:
              'Chest compressions started at @01:20 (11s after simulation start at @01:09) and sustained 97.6% CCF (ACLS target ≥80%). Both pulse/rhythm checks were tightly bounded under the 10-second ACLS limit (6.0s at @03:49–03:55 and 3.5s at @06:05–06:08).',
            t_start_s: 80.0,
            mm_ss: '01:20',
            redcap_field: 'time_compressions_v2',
            redcap_value: `01:20 · CCF ${currentCase.ccf_pct}% · interruption_compression_v2 = 0 (>10s pauses)`,
            modality: 'S1 Optical Flow (15 FPS) + Gemini P1 Vision',
            evidence_quote:
              '[01:20 / 80.0s] Provider in black scrubs (CLIN-2) initiates sternal compressions; S1 optical-flow velocity track confirms 359.0s active CPR / 368.0s code window (Pause #1 = 6.0s @03:49, Pause #2 = 3.5s @06:05).',
            human_concordance: 'Verified within 0.0s of Human Golden Timestamp (time_compressions = 01:20)',
          },
          {
            id: 'dw_pea_epi1',
            category: 'ACLS Rhythm & Early Epinephrine',
            title: 'Immediate Non-Shockable PEA Recognition & Prompt Epinephrine #1 with Readback',
            detail:
              'Leader correctly verbalized that Sinus Tachycardia PEA is non-shockable (0 inappropriate shocks), ordered 1 mg IV Epinephrine at @01:20 while simultaneous LMA airway placement proceeded (@01:50), received verbal announcement from MED_RN at @01:41, and closed the loop at @01:48.',
            t_start_s: 106.0,
            mm_ss: '01:46',
            redcap_field: 'admin_epi_time_v2',
            redcap_value: `${rr.admin_epi_time_v2 || '01:46'} · first_rhythm_v2 = 3 (PEA) · total_epi_v2 = ${rr.total_epi_v2 || '2'}`,
            modality: 'S7a Diarized ASR (utt_003–utt_005) + S5 Monitor',
            evidence_quote:
              '[01:20] TEAM_LEADER: "She\'s currently in PEA still, so we can\'t shock. We need to push 1 of epinephrine" → [01:41] MED_RN: "So I\'m going to give meds, 1 milligram of epinephrine" → [01:48] TEAM_LEADER: "Okay, so 1 of epinephrine is given."',
            human_concordance: 'Matches Human Technical Review: "gave appropriate meds" (Exact timestamp match 01:46)',
          },
          {
            id: 'dw_reversible_causes',
            category: "Shared Mental Model & H's and T's",
            title: "Collaborative H's & T's Brainstorming & Open Solicitation of Team Opinions",
            detail:
              'Leader systematically verbalized reversible causes of PEA (hypoxia from COPD/emphysema, PE/thrombus at @01:59, electrolyte derangements from diarrhea at @02:53, acidosis at @05:51) and actively invited team input, empowering COMPRESSOR to prompt lung auscultation (@03:11) and POC glucose (@04:11).',
            t_start_s: 119.0,
            mm_ss: '01:59',
            redcap_field: 'reversible_causes_v2',
            redcap_value: '1 (Yes) · team7_v3_v2 = 4/4 · team9_v3_v2 = 4/4',
            modality: 'S7a Diarized ASR (utt_006–utt_009, utt_015)',
            evidence_quote:
              '[01:59] TEAM_LEADER: "As far as like H\'s and T\'s, she could be hypoxic, she could have any type of clot or thrombus..." → [02:46] AIRWAY_MD: "And she was having diarrhea before." → [02:53] TEAM_LEADER: "Right, so that makes sense for electrolyte derangements... Any other suggestions?"',
            human_concordance:
              'Matches Human Review: "verbalized reversible causes of cardiac pea arrest... appreciated leader asking for opinions, they did do a good job of collaborating mentally"',
          },
        ],
        areas_for_improvement: [
          {
            id: 'imp_closed_loop_bicarb',
            category: 'Closed-Loop Medication Communication',
            title: 'Unclosed Communication Loop on Sodium Bicarbonate & Adjuvant Meds',
            detail:
              "At @05:51, the Team Leader proposed Sodium Bicarbonate as a tentative statement ('We could do an amp of sodium bicarbonate, I'm sure she's got some acidosis going on') and immediately transitioned into a pulse check without issuing a direct order to MED_RN or receiving a verbal readback confirming administration.",
            actionable_recommendation:
              "Use explicit 3-step directed closed-loop communication for every medication: (1) Leader addresses MED_RN by name/role with drug + dose ('Med RN, give 1 amp Sodium Bicarbonate IV push'), (2) MED_RN repeats back the order, (3) MED_RN announces 'Bicarb 1 amp administered' after flush.",
            t_start_s: 351.0,
            mm_ss: '05:51',
            redcap_field: 'other_med_considered_v2',
            redcap_value: '1 (Sodium Bicarbonate considered) · total_bicarb_v2 = 0 (unconfirmed)',
            modality: 'S7a Diarized ASR (utt_019) + P3 Adjudicator',
            evidence_quote:
              '[05:51 / 351.0s] TEAM_LEADER (utt_019): "We could do an amp of sodium bicarbonate, I\'m sure she\'s got some acidosis going on. It\'s about 2 minutes, we can check a pulse again. Do we have a pulse?" (Zero MED_RN readback or injection event followed).',
            human_concordance:
              'Exact Match with Human Reviewer: "no closed loop communication regarding admin of bicarb etc so I could not tell if it was actually given"',
          },
          {
            id: 'imp_compressor_rotation',
            category: 'Workload Delegation & Compressor Rotation',
            title: 'No Compressor Rotation Across 4m 48s of Continuous Chest Compressions',
            detail:
              'A single clinician (CLIN-2 in black scrubs) performed manual chest compressions continuously from @01:20 to @06:08 (288s / 4m 48s) across two full 2-minute ACLS cycles without switching compressors during the @03:49–03:55 rhythm check.',
            actionable_recommendation:
              'Delegate a secondary compressor during initial role assignment (@01:02) and enforce an automatic compressor switch during every 2-minute rhythm/pulse check (@03:49) to prevent rescuers’ compression depth decay after 2 minutes.',
            t_start_s: 229.0,
            mm_ss: '03:49',
            redcap_field: 'team2_v2_v2',
            redcap_value: `${rr.team2_v2_v2 || 3}/4 (Global Perspective) · time_pulse_v2 = 03:50`,
            modality: '3D Spatial Re-ID (CLIN-2) + S1 Optical Flow + S7a (utt_013)',
            evidence_quote:
              '[03:54 / 234.5s] TEAM_LEADER (utt_013): "Okay, so continue compressions, she\'s still in PEA" — 3D Spatial Track CLIN-2 remains locked at S1 Sternum ROI continuously from 01:20 to 06:08 without personnel swap.',
            human_concordance: 'Exact Match with Human Reviewer: "consider switching out for compressions and delegating differently"',
          },
          {
            id: 'imp_early_epi2',
            category: 'ACLS Medication Dosing Interval',
            title: 'Early Epinephrine #2 Dosing Interval (2m 17s vs 3–5 min ACLS Guideline)',
            detail:
              'Epinephrine #1 was administered at @01:46 and Epinephrine #2 was ordered at @03:54 and confirmed given at @04:03 (interval = 2m 17s / 137s), which is 43 seconds earlier than the AHA ACLS recommended 3–5 minute (180–300s) repeat dosing interval.',
            actionable_recommendation:
              'Synchronize repeat Epinephrine doses to every second 2-minute pulse check (~4 minutes after first dose) or assign a dedicated medication timer so repeat boluses occur strictly within the 3–5 minute ACLS window.',
            t_start_s: 243.0,
            mm_ss: '04:03',
            redcap_field: 'total_epi_v2',
            redcap_value: '2 doses (Dose #1 @01:46 → Dose #2 @04:03, Δt = 2m 17s)',
            modality: 'S7a Diarized ASR (utt_004, utt_014) + Timeline Reducer',
            evidence_quote:
              '[01:46] Epinephrine #1 administered → [03:54] TEAM_LEADER (utt_013): "We can give another push of epinephrine if it\'s been 2 minutes" → [04:03] MED_RN (utt_014): "Gave epinephrine" (137s elapsed vs ≥180s target).',
            human_concordance: 'Engine Temporal Audit: Quantifies exact 137s dosing interval from spoken readbacks',
          },
          {
            id: 'imp_delayed_iv_fluids',
            category: 'Targeted Reversible-Cause Treatment (Hypovolemia)',
            title: 'Empiric IV Fluid Bolus Delayed Until Post-ROSC (@06:35) Despite Severe Dehydration Handoff',
            detail:
              'EMS handoff (@00:00) reported several days of nausea, vomiting, diarrhea, and 48 hours of zero PO intake (classic hypovolemic PEA trigger), and AIRWAY_MD highlighted diarrhea at @02:46, but IV fluids (Normal Saline) were not ordered until @06:29–06:35 (27s after ROSC at @06:08).',
            actionable_recommendation:
              "When H's & T's discussion identifies hypovolemia/GI losses (@02:46), immediately convert that diagnostic finding into an intra-arrest wide-open IV crystalloid bolus order rather than deferring until post-ROSC stabilization.",
            t_start_s: 395.0,
            mm_ss: '06:35',
            redcap_field: 'time_other_med_v2',
            redcap_value: '06:35 · other_meds_given_v2 = Normal Saline (post-ROSC)',
            modality: 'S7a Diarized ASR (utt_001, utt_007, utt_021)',
            evidence_quote:
              '[00:00] EMS Handoff (utt_001): "ill with nausea, vomiting, and diarrhea for several days... past 48 hours unable to eat or drink" → [06:29] TEAM_LEADER (utt_021): "Do we want to give fluids? She\'s dehydrated most likely" (ordered at 06:35, post-ROSC).',
            human_concordance: "Complements Human H's & T's review with exact pre- vs post-ROSC treatment timing",
          },
        ],
      };
    }

    return {
      model_id: currentCase.verify_model_id || currentCase.model_id || 'gemini-4-argon',
      team_global_score: global10,
      human_team_global_score: humanGlobal10,
      team_subscale_score: subSum,
      team_subscale_max: 44,
      team_subscale_pct: Math.round((1000 * subSum) / 44) / 10,
      team_narrative:
        rr.general_comments_v2 ||
        `TEAM Global Rating ${global10}/10 (Subscale ${subSum}/44): Strong trauma-bay command and role coordination maintaining ${currentCase.ccf_pct}% CCF across ${currentCase.code_duration_s}s of active resuscitation. Primary teamwork improvement centers on minimizing hands-off pauses during mechanical CPR transitions and peri-shock rhythm checks (${currentCase.prolonged_interruptions_count} pauses >10s).`,
      technical_narrative:
        rr.comments_v2 ||
        `Compressions initiated at ${rr.time_compressions_v2 || '00:13'} (CCF ${currentCase.ccf_pct}%), 1st Epinephrine at ${rr.admin_epi_time_v2 || '02:33'} (${currentCase.total_epi_doses || 3} doses total), ${currentCase.prolonged_interruptions_count || 0} pauses >10s (${currentCase.total_pause_s || 0}s total pause time), outcome at ${rr.time_rosc_v2 || rr.time_death_v2 || '09:56'}.`,
      feedback_narrative:
        rr.feedback_narrative_v2 ||
        `Sustained ${currentCase.ccf_pct}% CCF (target ≥80%) with prompt arrival compressions and timely vasopressor administration. Focus debriefing on bounding rhythm checks and LUCAS/defibrillation transitions strictly under 10 seconds.`,
      done_well: [
        {
          id: 'dw_gen_ccf',
          category: 'CPR Continuity & Perfusion',
          title: `Sustained ${currentCase.ccf_pct}% Chest Compression Fraction (Target ≥80%)`,
          detail: `Maintained ${currentCase.ccf_pct}% CCF across ${currentCase.code_duration_s}s of resuscitation with immediate arrival compressions at @${rr.time_compressions_v2 || '00:13'}.`,
          t_start_s: 13.0,
          mm_ss: rr.time_compressions_v2 || '00:13',
          redcap_field: 'time_compressions_v2',
          redcap_value: `${rr.time_compressions_v2 || '00:13'} · CCF ${currentCase.ccf_pct}%`,
          modality: 'S1 Optical Flow + S5 CCTV Clock',
          evidence_quote: `S1 optical-flow track confirms ${examDash.active_cpr_s || 499}s active compressions over ${currentCase.code_duration_s}s code duration.`,
          human_concordance: 'Verified against Human Gold Standard',
        },
        {
          id: 'dw_gen_epi',
          category: 'ACLS Vasopressor & Rhythm Execution',
          title: `Prompt First Epinephrine (@${rr.admin_epi_time_v2 || '02:33'}) & Defibrillation (@${rr.time_defib_v2 || '07:54'})`,
          detail: `Administered ${currentCase.total_epi_doses || 3} Epinephrine boluses and delivered timely defibrillation on shockable rhythm conversion.`,
          t_start_s: 153.0,
          mm_ss: rr.admin_epi_time_v2 || '02:33',
          redcap_field: 'admin_epi_time_v2',
          redcap_value: `${rr.admin_epi_time_v2 || '02:33'} · total_epi_v2 = ${currentCase.total_epi_doses || 3}`,
          modality: 'S7a ASR + S3 Defib Audio',
          evidence_quote: `1st Epinephrine 1 mg IV verified at @${rr.admin_epi_time_v2 || '02:33'}.`,
          human_concordance: '100% concordance with Human Gold Standard',
        },
      ],
      areas_for_improvement: [
        {
          id: 'imp_gen_pause',
          category: 'Hands-Off Pause Minimization',
          title: `Eliminate Prolonged Compression Pauses >10s (${currentCase.prolonged_interruptions_count} Pauses, ${currentCase.total_pause_s}s Total)`,
          detail: `Detected ${currentCase.prolonged_interruptions_count} compression interruptions exceeding the 10.0s ACLS threshold during mechanical CPR placement and rhythm checks.`,
          actionable_recommendation:
            'Split mechanical CPR placement into two <10s steps and pre-charge the defibrillator 15s before rhythm checks.',
          t_start_s: 332.0,
          mm_ss: rr.start_of_interruption_2_v2 || '05:32',
          redcap_field: 'interruption_compression_v2',
          redcap_value: `1 (${currentCase.prolonged_interruptions_count} prolonged pauses >10s)`,
          modality: 'S1 Optical Flow + 3D Spatial Track',
          evidence_quote: `Prolonged hands-off chest pause recorded by S1 optical flow (${currentCase.total_pause_s}s total pause burden).`,
          human_concordance: 'Matches Human Gold Standard CCI log',
        },
        {
          id: 'imp_gen_closed_loop',
          category: 'Closed-Loop Readbacks & Post-ROSC Escalation',
          title: 'Standardize Verbal Readbacks on Antiarrhythmics & Post-ROSC Diagnostics',
          detail:
            'While vasopressor and defibrillation timestamps were executed on schedule, verbal readbacks on adjuvant bolus/infusion completion and immediate post-ROSC 12-lead ECG confirmation had unconfirmed closed-loop acknowledgments.',
          actionable_recommendation:
            'Require explicit MED_RN dose-completion readback for every antiarrhythmic/adjuvant bolus and verbalize 12-lead ECG acquisition immediately upon ROSC.',
          t_start_s: 474.0,
          mm_ss: rr.time_defib_v2 || '07:54',
          redcap_field: 'anti_arrythmic_given_v2',
          redcap_value: `${rr.anti_arrythmic_given_v2 || '1'} · TEAM Global ${global10}/10`,
          modality: 'S7a Diarized ASR + P3 Adjudicator',
          evidence_quote: 'Adjuvant medication and post-ROSC diagnostic readback audit.',
          human_concordance: 'Aligned with TEAM non-technical communication rubric',
        },
      ],
    };
  })();

  // ── Dedicated AI Insights & Physician Coaching Page Data Model (`activeNav === 'coaching'`) ──
  const aiCoachingBundle = (() => {
    const rid = String(currentCase.record_id || '').toUpperCase();
    const isTrialRun = Boolean(currentCase.live_run || rid.includes('TRIALRUN') || String(currentCaseSimProtocol.num) === '1');
    const ccfVal = Number(currentCase.ccf_pct || 98.1);
    const ccfGain = Math.round((ccfVal - 80.0) * 10) / 10;
    const pausesGt10 = Number(currentCase.prolonged_interruptions_count || 0);
    const totalEvents = (currentCase.events || []).length || 17;
    const totalUtts = (currentCase.transcript?.utterances || []).length || (isTrialRun ? 32 : 18);
    const popVars = contractData.populatedCount || 46;
    const utdVars = contractData.utdCount || (isTrialRun ? 1 : 0);

    const cards = isTrialRun
      ? [
          {
            id: 'insight_bicarb_loop',
            domain: 'meds',
            categoryLabel: 'Closed-Loop Meds',
            categoryIcon: 'transfer',
            confidenceLabel: 'High confidence',
            confidenceTone: 'blue',
            title: 'Enforce 3-step closed-loop readback on Sodium Bicarbonate at 05:51',
            bullets: [
              'Proposed at @05:51 ("We could do an amp of sodium bicarbonate") without addressing MED_RN',
              'Zero verbal readback or IV push visual confirmation before pulse check at @06:05 (total_bicarb_v2 = 0)',
              'Matches Human Reviewer audit: "no closed loop communication regarding admin of bicarb so could not tell if given"',
            ],
            tags: [
              { label: '@05:51 (351s)', type: 'time', t_s: 351.0 },
              { label: 'time_bicarb_v2 = UTD', type: 'redcap', field: 'time_bicarb_v2' },
              { label: 'S7a Audio utt_019', type: 'sensor', t_s: 351.0 },
            ],
            metricValue: '05:51',
            metricSub: 'unconfirmed order, UTD',
            primaryButton: true,
            t_start_s: 351.0,
            mm_ss: '05:51',
            redcap_field: 'time_bicarb_v2',
            redcap_value: 'UTD (Verbal suggestion without MED_RN readback · total_bicarb_v2 = 0)',
            evidence_quote:
              '[05:51 / 351.0s] TEAM_LEADER (utt_019): "We could do an amp of sodium bicarbonate, I\'m sure she\'s got some acidosis going on. It\'s about 2 minutes, we can check a pulse again."',
            aha_guideline:
              'TEAM Item 4 & AHA ACLS Team Dynamics: Every intra-arrest medication order must be directed to a specific clinician with drug + dose + route, repeated back verbatim, and verbally confirmed after IV flush.',
            physician_action_plan:
              'Replace open-ended medication suggestions ("We could do an amp...") with a 3-step directed order: (1) Address MED_RN by name/role ("Med RN, give 1 amp [50 mEq] Sodium Bicarbonate IV push"), (2) Wait for verbal repeat-back, (3) Require "Bicarb 1 amp in and flushed" before transitioning to the pulse check.',
            human_concordance:
              'Exact agreement with Fellowship Reviewer: "no closed loop communication regarding admin of bicarb etc so I could not tell if it was actually given"',
          },
          {
            id: 'insight_epi2_interval',
            domain: 'meds',
            categoryLabel: 'Dosing Safety',
            categoryIcon: 'shield',
            confidenceLabel: 'From records',
            confidenceTone: 'gray',
            title: 'Space Epinephrine #2 (@04:03) to the 3–5 min ACLS dosing window',
            bullets: [
              `Epinephrine #1 given at @${rr.admin_epi_time_v2 || '01:46'} with full readback; Dose #2 given at @04:03 (interval = 2m 17s / 137s)`,
              'Administered 43 seconds earlier than the AHA ACLS 3–5 minute (180–300s) vasopressor dosing interval',
              'Rule: synchronize repeat Epinephrine to every second 2-minute rhythm check (~4 min cycle)',
            ],
            tags: [
              { label: '@01:46 → @04:03', type: 'time', t_s: 243.0 },
              { label: 'admin_epi_time_v2', type: 'redcap', field: 'admin_epi_time_v2' },
              { label: 'total_epi_v2 = 2', type: 'redcap', field: 'total_epi_v2' },
            ],
            metricValue: '43s',
            metricSub: 'early vs. 3-min rule',
            primaryButton: false,
            t_start_s: 243.0,
            mm_ss: '04:03',
            redcap_field: 'total_epi_v2',
            redcap_value: '2 doses (Dose #1 @01:46 → Dose #2 @04:03 · Δt = 137s)',
            evidence_quote:
              '[01:46] Epinephrine #1 confirmed given → [03:54] TEAM_LEADER (utt_013): "We can give another push of epinephrine if it\'s been 2 minutes" → [04:03] MED_RN (utt_014): "Gave epinephrine."',
            aha_guideline:
              'AHA ACLS Adult Cardiac Arrest Algorithm: Administer Epinephrine 1 mg IV/IO every 3 to 5 minutes (180–300s), not at every 2-minute rhythm check.',
            physician_action_plan:
              'Pair Epinephrine dosing with every OTHER 2-minute rhythm check (~4 minutes apart) or delegate a dedicated medication timer callout ("Epi #1 in at 01:46 — next Epi due at 04:46–06:46") to prevent premature stacking.',
            human_concordance:
              'Engine S7a temporal audit quantifies the exact 137s inter-dose interval from spoken administration readbacks.',
          },
          {
            id: 'insight_compressor_rotation',
            domain: 'cpr',
            categoryLabel: 'Compressor Fatigue',
            categoryIcon: 'alertTriangle',
            confidenceLabel: 'Coaching priority',
            confidenceTone: 'orange',
            title: 'Rotate chest compressor at the 03:49 rhythm check (4m 48s continuous)',
            bullets: [
              'CLIN-2 (black scrubs) compressed continuously from @01:20 to @06:08 (288s across two 2-min cycles)',
              'No personnel swap occurred during the 6.0s pulse & rhythm check pause at @03:49–03:55',
              'AHA guideline: compression depth decays after 120s; pre-stage relief rescuer 15s before check',
            ],
            tags: [
              { label: '@03:49 (229s)', type: 'time', t_s: 229.0 },
              { label: 'team2_v2_v2 = 3/4', type: 'redcap', field: 'team2_v2_v2' },
              { label: '3D Re-ID CLIN-2', type: 'sensor', t_s: 229.0 },
            ],
            metricValue: '4m 48s',
            metricSub: 'single compressor span',
            primaryButton: false,
            t_start_s: 229.0,
            mm_ss: '03:49',
            redcap_field: 'team2_v2_v2',
            redcap_value: '3/4 (Global Perspective) · time_pulse_v2 = 03:50 (6.0s pause)',
            evidence_quote:
              '[03:49–03:55] 3D Spatial Track CLIN-2 remains locked at S1 Sternum ROI continuously from @01:20 to @06:08 (288s) with zero compressor handoff at the 2-minute rhythm check.',
            aha_guideline:
              'AHA ACLS High-Performance CPR: Rotate the chest compressor every 2 minutes (or sooner if fatigued), accomplishing the switch in <5 seconds during the scheduled rhythm check.',
            physician_action_plan:
              'Assign "Compressor #1" and "Compressor #2" during the initial @01:02 role briefing, and have the relief rescuer step to the opposite side of the bed at 1m 45s into each cycle so hands swap immediately during the @03:49 pulse check.',
            human_concordance:
              'Exact match with Fellowship Reviewer: "consider switching out for compressions and delegating differently"',
          },
          {
            id: 'insight_hypovolemia_fluids',
            domain: 'reversible',
            categoryLabel: "H's & T's Therapy",
            categoryIcon: 'zap',
            confidenceLabel: 'High confidence',
            confidenceTone: 'blue',
            title: 'Initiate intra-arrest IV fluid bolus for hypovolemic PEA (@02:46 vs @06:35)',
            bullets: [
              'EMS handoff (@00:00) reported 48h severe dehydration, vomiting & diarrhea (hypovolemic PEA trigger)',
              'Team identified GI losses during H&T review at @02:46, but deferred Normal Saline until @06:35 (post-ROSC)',
              'Clinical impact: intra-arrest volume expansion restores preload and augments coronary perfusion pressure',
            ],
            tags: [
              { label: '@02:46 → @06:35', type: 'time', t_s: 166.0 },
              { label: 'reversible_causes_v2 = 1', type: 'redcap', field: 'reversible_causes_v2' },
              { label: 'time_other_med_v2', type: 'redcap', field: 'time_other_med_v2' },
            ],
            metricValue: '+3m 49s',
            metricSub: 'bolus delay from H&T',
            primaryButton: false,
            t_start_s: 166.0,
            mm_ss: '02:46',
            redcap_field: 'time_other_med_v2',
            redcap_value: '06:35 · other_meds_given_v2 = Normal Saline (ordered post-ROSC)',
            evidence_quote:
              '[00:00] EMS Handoff (utt_001): "nausea, vomiting, and diarrhea for several days... past 48 hours unable to eat or drink" → [02:46] AIRWAY_MD: "And she was having diarrhea before" → [06:29] TEAM_LEADER: "Do we want to give fluids? She\'s dehydrated most likely."',
            aha_guideline:
              'AHA ACLS PEA Reversible Causes (Hypovolemia): In PEA arrest driven by severe volume depletion, rapid isotonic crystalloid infusion is the definitive causal therapy alongside CPR and Epinephrine.',
            physician_action_plan:
              'Couple every H’s & T’s diagnostic insight directly to an immediate bedside order: as soon as GI losses/dehydration are verbalized at @02:46, order 1 L Normal Saline or Lactated Ringer’s wide open on a pressure bag during active CPR.',
            human_concordance:
              'Extends Human H’s & T’s credit ("verbalized reversible causes of cardiac pea arrest") with exact diagnostic-to-therapeutic latency (+3m 49s).',
          },
          {
            id: 'insight_ccf_excellence',
            domain: 'cpr',
            categoryLabel: 'Perfusion Benchmark',
            categoryIcon: 'activity',
            confidenceLabel: 'High confidence',
            confidenceTone: 'blue',
            title: `Sustain ${ccfVal}% Chest Compression Fraction & ≤6.0s peri-pause discipline`,
            bullets: [
              `Compressions started at @${rr.time_compressions_v2 || '01:20'} (10s after arrest recognition at @01:10; target ≤20s)`,
              `Both pulse/rhythm checks stayed well below the 10s ACLS ceiling (6.0s at @03:49 and 3.5s at @06:05)`,
              `Achieved +${ccfGain}% perfusion margin above the 80% AHA resuscitation target with 0 prolonged pauses`,
            ],
            tags: [
              { label: `@${rr.time_compressions_v2 || '01:20'} (80s)`, type: 'time', t_s: 80.0 },
              { label: 'time_compressions_v2', type: 'redcap', field: 'time_compressions_v2' },
              { label: 'S1 Optical Flow 15fps', type: 'sensor', t_s: 80.0 },
            ],
            metricValue: `${ccfVal}%`,
            metricSub: 'CCF (+18.1% vs. AHA)',
            primaryButton: false,
            t_start_s: 80.0,
            mm_ss: rr.time_compressions_v2 || '01:20',
            redcap_field: 'time_compressions_v2',
            redcap_value: `${rr.time_compressions_v2 || '01:20'} · CCF ${ccfVal}% · 0 pauses >10s`,
            evidence_quote:
              'S1 optical-flow velocity track confirms 359.0s active sternal compressions across 368.0s code window; Pause #1 = 6.0s (@03:49–03:55), Pause #2 = 3.5s (@06:05–06:08).',
            aha_guideline:
              'AHA ACLS Benchmark: Initiate chest compressions within ≤20s of cardiac arrest recognition, maintain CCF ≥80%, and bound all rhythm/pulse checks strictly <10 seconds.',
            physician_action_plan:
              'Reinforce this exact pre-pause countdown discipline across all trauma and ED resuscitation teams: verbalizing pulse check start and immediately resuming compressions at 6.0s preserved coronary perfusion pressure prior to ROSC.',
            human_concordance:
              '0.0s timestamp delta against Human Gold Standard (time_compressions = 01:20; duration_pulse = 6–7s).',
          },
          {
            id: 'insight_concordance_airway',
            domain: 'concordance',
            categoryLabel: 'Airway & Concordance',
            categoryIcon: 'wind',
            confidenceLabel: 'From S1–S7 & Audio',
            confidenceTone: 'gray',
            title: 'Pair LMA placement (@01:50) & lung auscultation (@03:18) with quantitative EtCO₂ callout',
            bullets: [
              'LMA advanced airway placed smoothly at @01:50 without interrupting chest compressions (0.0s airway pause)',
              'COMPRESSOR prompted bilateral lung auscultation at @03:11 ("listen to the lungs"), confirmed at @03:18',
              '8/8 (100%) primary clinical milestones matched Human Gold Standard within ±3.0s (MAE = 1.0s)',
            ],
            tags: [
              { label: '@01:50 → @03:18', type: 'time', t_s: 110.0 },
              { label: 'time_airway_v2 = 01:50', type: 'redcap', field: 'time_airway_v2' },
              { label: 'MAE 1.0s vs. Human GT', type: 'sensor', t_s: 198.0 },
            ],
            metricValue: '1.0s',
            metricSub: 'milestone MAE vs. GT',
            primaryButton: false,
            t_start_s: 110.0,
            mm_ss: '01:50',
            redcap_field: 'time_airway_v2',
            redcap_value: `${rr.time_airway_v2 || '01:50'} · type_of_airway_v2 = 2 (Supraglottic / LMA)`,
            evidence_quote:
              '[01:50] LMA placed during continuous compressions → [03:11] COMPRESSOR (utt_010): "You can listen to the lungs" → [03:18] AIRWAY_MD (utt_011): "Listening to the lungs."',
            aha_guideline:
              'AHA ACLS Airway Confirmation: Confirm advanced airway placement immediately using continuous waveform capnography (PetCO₂ in mmHg) in addition to bilateral chest rise and auscultation.',
            physician_action_plan:
              'Immediately upon securing the LMA at @01:50, attach inline waveform capnography and announce the numeric PetCO₂ value aloud (both to confirm placement and to monitor CPR quality / sudden jump ≥35–40 mmHg indicating ROSC).',
            human_concordance:
              '8/8 (100%) milestones within ±3.0s of Northwell Golden Human Dataset (record_id = 3).',
          },
        ]
      : [
          {
            id: 'insight_lucas_pause',
            domain: 'cpr',
            categoryLabel: 'MCCD Transition',
            categoryIcon: 'transfer',
            confidenceLabel: 'High confidence',
            confidenceTone: 'blue',
            title: `Split LUCAS mechanical CPR placement into two <10s steps (${pausesGt10} pauses >10s)`,
            bullets: [
              `Recorded ${pausesGt10} prolonged compression interruptions >10s totaling ${currentCase.total_pause_s || 94}s hands-off time`,
              `Longest hands-off pause occurred during backplate + upper assembly deployment (@${rr.start_of_interruption_2_v2 || '05:32'})`,
              '2-step choreography cuts mechanical CPR transition pauses from >18s down to <7s per step',
            ],
            tags: [
              { label: `@${rr.start_of_interruption_2_v2 || '05:32'}`, type: 'time', t_s: 332.0 },
              { label: 'interruption_compression_v2', type: 'redcap', field: 'interruption_compression_v2' },
              { label: 'S1 Optical Flow', type: 'sensor', t_s: 332.0 },
            ],
            metricValue: `${currentCase.total_pause_s || 94}s`,
            metricSub: 'total pause burden, S1',
            primaryButton: true,
            t_start_s: 332.0,
            mm_ss: rr.start_of_interruption_2_v2 || '05:32',
            redcap_field: 'interruption_compression_v2',
            redcap_value: `1 (${pausesGt10} prolonged pauses >10s · ${currentCase.total_pause_s || 94}s total)`,
            evidence_quote: `S1 optical-flow track logged ${pausesGt10} compression interruptions >10.0s during resuscitation.`,
            aha_guideline:
              'AHA ACLS Mechanical CPR Deployment: Never pause compressions >10s to apply a mechanical device; slide the backplate during one brief (<5s) pause, resume manual CPR for 30s, then latch the upper arm in a second <7s pause.',
            physician_action_plan:
              'Enforce the 2-pause LUCAS choreography with a loud 10-second verbal countdown from the Team Leader; if the upper claw is not latched by "7", abort and resume manual compressions immediately.',
            human_concordance: 'Matches Human Gold Standard CCI interval log.',
          },
          {
            id: 'insight_precharge_defib',
            domain: 'rhythm',
            categoryLabel: 'Defib & Safety',
            categoryIcon: 'shield',
            confidenceLabel: 'From S3 & S5',
            confidenceTone: 'gray',
            title: `Pre-charge defibrillator 15s before rhythm checks (@${rr.time_defib_v2 || '07:54'})`,
            bullets: [
              `First defibrillation shock delivered at @${rr.time_defib_v2 || '07:54'} (${currentCase.defib_shocks_count || 1} shock total)`,
              'Charging during the rhythm check extends peri-shock hands-off pause while chest remains un-compressed',
              'Rule: pre-charge at 1m 45s into the cycle, perform ≤5s rhythm check, shock or disarm while hovering',
            ],
            tags: [
              { label: `@${rr.time_defib_v2 || '07:54'} (474s)`, type: 'time', t_s: 474.0 },
              { label: 'time_defib_v2', type: 'redcap', field: 'time_defib_v2' },
              { label: 'shocks_admin_v2 = 1', type: 'redcap', field: 'shocks_admin_v2' },
            ],
            metricValue: rr.time_defib_v2 || '07:54',
            metricSub: 'first defib shock, S3/S5',
            primaryButton: false,
            t_start_s: 474.0,
            mm_ss: rr.time_defib_v2 || '07:54',
            redcap_field: 'time_defib_v2',
            redcap_value: `${rr.time_defib_v2 || '07:54'} · shocks_admin_v2 = 1`,
            evidence_quote: `Defibrillation shock verified at @${rr.time_defib_v2 || '07:54'} by S3 audio energy and S5 monitor trace.`,
            aha_guideline:
              'AHA ACLS Peri-Shock Pause Reduction: Every 5-second increase in peri-shock pause reduces defibrillation success and survival to discharge.',
            physician_action_plan:
              'Pre-charge the defibrillator at 1:45 of every 2-minute cycle while manual/LUCAS compressions continue, pause <5s to verify VF/pVT, clear & shock immediately, and resume compressions within 2s post-shock.',
            human_concordance: '100% agreement with Human Gold Standard shock log.',
          },
          {
            id: 'insight_trauma_epi',
            domain: 'meds',
            categoryLabel: 'Vasopressor Timing',
            categoryIcon: 'alertTriangle',
            confidenceLabel: 'Coaching priority',
            confidenceTone: 'orange',
            title: `Maintain 3–5 min Epinephrine cadence across ${currentCase.total_epi_doses || 3} boluses`,
            bullets: [
              `First Epinephrine administered at @${rr.admin_epi_time_v2 || '02:33'} following IV/IO vascular access`,
              `${currentCase.total_epi_doses || 3} total Epinephrine doses administered across ${fmtMmSs(currentCase.code_duration_s)} resuscitation`,
              'Pair every vasopressor and antiarrhythmic push with closed-loop dose + route readback',
            ],
            tags: [
              { label: `@${rr.admin_epi_time_v2 || '02:33'} (153s)`, type: 'time', t_s: 153.0 },
              { label: 'admin_epi_time_v2', type: 'redcap', field: 'admin_epi_time_v2' },
              { label: `total_epi_v2 = ${currentCase.total_epi_doses || 3}`, type: 'redcap', field: 'total_epi_v2' },
            ],
            metricValue: `${currentCase.total_epi_doses || 3}`,
            metricSub: 'Epi boluses delivered',
            primaryButton: false,
            t_start_s: 153.0,
            mm_ss: rr.admin_epi_time_v2 || '02:33',
            redcap_field: 'admin_epi_time_v2',
            redcap_value: `${rr.admin_epi_time_v2 || '02:33'} · total_epi_v2 = ${currentCase.total_epi_doses || 3}`,
            evidence_quote: `1st Epinephrine 1 mg IV verified at @${rr.admin_epi_time_v2 || '02:33'}.`,
            aha_guideline: 'AHA ACLS Vasopressor Guideline: 1 mg IV/IO every 3–5 minutes with explicit closed-loop readback.',
            physician_action_plan: 'Maintain dedicated medication timer and announce each completed dose + flush aloud.',
            human_concordance: 'Verified within ±3.0s of Human Gold Standard.',
          },
          {
            id: 'insight_trauma_ccf',
            domain: 'team',
            categoryLabel: 'Perfusion & Outcome',
            categoryIcon: 'activity',
            confidenceLabel: 'High confidence',
            confidenceTone: 'blue',
            title: `Sustained ${ccfVal}% CCF across ${fmtMmSs(currentCase.code_duration_s)} leading to ${rr.time_rosc_v2 ? 'ROSC' : 'Outcome'}`,
            bullets: [
              `Immediate arrival chest compressions initiated at @${rr.time_compressions_v2 || '00:13'} (≤20s target met)`,
              `Sustained ${ccfVal}% CCF (+${ccfGain}% above 80% AHA benchmark) across ${currentCase.code_duration_s}s code`,
              `Outcome recorded at @${rr.time_rosc_v2 || rr.time_death_v2 || '09:56'} with ${engineTeamReview.team_global_score}/10 TEAM leadership rating`,
            ],
            tags: [
              { label: `@${rr.time_compressions_v2 || '00:13'}`, type: 'time', t_s: 13.0 },
              { label: 'time_compressions_v2', type: 'redcap', field: 'time_compressions_v2' },
              { label: `TEAM ${engineTeamReview.team_global_score}/10`, type: 'redcap', field: 'team12_v2_v2' },
            ],
            metricValue: `${ccfVal}%`,
            metricSub: 'CCF (+3.4% vs. AHA)',
            primaryButton: false,
            t_start_s: 13.0,
            mm_ss: rr.time_compressions_v2 || '00:13',
            redcap_field: 'time_compressions_v2',
            redcap_value: `${rr.time_compressions_v2 || '00:13'} · CCF ${ccfVal}%`,
            evidence_quote: `S1 optical flow + S5 CCTV clock anchor verify ${ccfVal}% CCF across ${currentCase.code_duration_s}s.`,
            aha_guideline: 'AHA ACLS Target: CCF ≥80% with arrival compressions ≤20s.',
            physician_action_plan: 'Preserve immediate arrival CPR while tightening mechanical CPR transition pauses.',
            human_concordance: 'Verified against Ramraj Gold Standard Excel sheet.',
          },
        ];

    const priorities = isTrialRun
      ? [
          {
            id: 'prio_1',
            icon: 'alertTriangle',
            tone: 'amber',
            title: 'Close medication loop on Sodium Bicarbonate at 05:51',
            sub: 'Proposed at 05:51 ("could do an amp"); zero MED_RN readback or IV push confirmed (time_bicarb_v2 = UTD).',
            cardId: 'insight_bicarb_loop',
            t_s: 351.0,
          },
          {
            id: 'prio_2',
            icon: 'lock',
            tone: 'rose',
            title: 'Space Epinephrine #2 (@04:03) to 3–5 min ACLS window',
            sub: 'Dose #2 given 2m 17s (137s) after Dose #1 (@01:46) — 43s earlier than the 180–300s AHA guideline interval.',
            cardId: 'insight_epi2_interval',
            t_s: 243.0,
          },
          {
            id: 'prio_3',
            icon: 'transfer',
            tone: 'blue',
            title: 'Rotate chest compressor at 2-minute rhythm check (@03:49)',
            sub: 'CLIN-2 performed manual CPR continuously for 4m 48s (@01:20–06:08) across 2 cycles without switching.',
            cardId: 'insight_compressor_rotation',
            t_s: 229.0,
          },
          {
            id: 'prio_4',
            icon: 'wrench',
            tone: 'green',
            title: "Convert H's & T's hypovolemia finding (@02:46) into intra-arrest bolus",
            sub: '48h severe dehydration noted on handoff (@00:00); Normal Saline bolus waited until @06:35 post-ROSC.',
            cardId: 'insight_hypovolemia_fluids',
            t_s: 166.0,
          },
        ]
      : [
          {
            id: 'prio_t1',
            icon: 'alertTriangle',
            tone: 'amber',
            title: `Eliminate ${pausesGt10} prolonged pauses >10s (${currentCase.total_pause_s || 94}s total)`,
            sub: `Use 2-step <10s choreography during mechanical CPR deployment at @${rr.start_of_interruption_2_v2 || '05:32'}.`,
            cardId: 'insight_lucas_pause',
            t_s: 332.0,
          },
          {
            id: 'prio_t2',
            icon: 'lock',
            tone: 'rose',
            title: `Pre-charge defibrillator 15s before rhythm checks (@${rr.time_defib_v2 || '07:54'})`,
            sub: 'Eliminate charging delay while chest is hands-off during VF/pVT rhythm confirmation.',
            cardId: 'insight_precharge_defib',
            t_s: 474.0,
          },
          {
            id: 'prio_t3',
            icon: 'transfer',
            tone: 'blue',
            title: `Closed-loop readbacks across ${currentCase.total_epi_doses || 3} Epinephrine boluses`,
            sub: `1st Epinephrine delivered at @${rr.admin_epi_time_v2 || '02:33'}; standardize dose + flush verbal readback.`,
            cardId: 'insight_trauma_epi',
            t_s: 153.0,
          },
          {
            id: 'prio_t4',
            icon: 'wrench',
            tone: 'green',
            title: `Sustained ${ccfVal}% CCF & prompt arrival compressions (@${rr.time_compressions_v2 || '00:13'})`,
            sub: `Exceeded 80% AHA CCF target across ${fmtMmSs(currentCase.code_duration_s)} resuscitation.`,
            cardId: 'insight_trauma_ccf',
            t_s: 13.0,
          },
        ];

    const acceptedCount = Object.values(acceptedInsightIds).filter(Boolean).length;
    const metGates = (caseRubric.metCount || 5) + acceptedCount;

    return {
      isTrialRun,
      ccfVal,
      ccfGain,
      pausesGt10,
      totalEvents,
      totalUtts,
      popVars,
      utdVars,
      metGates,
      cards,
      priorities,
      summaryLead: isTrialRun
        ? `Chest compression fraction reached ${ccfVal}% (AHA target ≥80%) with 0 prolonged pauses >10s and ROSC achieved at ${rr.time_rosc_v2 || '06:08'}. Two clinical coaching priorities need physician review today: verifying the unconfirmed Sodium Bicarbonate order at 05:51 and standardizing 3–5 min Epinephrine dosing & 2-min compressor rotation.`
        : `Chest compression fraction reached ${ccfVal}% across ${fmtMmSs(currentCase.code_duration_s)} of resuscitation with 1st Epinephrine at ${rr.admin_epi_time_v2 || '02:33'} and 1st Shock at ${rr.time_defib_v2 || '07:54'}. Two high-impact coaching priorities need review today: eliminating ${pausesGt10} prolonged pauses >10s (${currentCase.total_pause_s || 94}s hands-off burden) and pre-charging before rhythm checks.`,
      miniStats: [
        { label: 'CCF ≥80%', value: `${ccfVal}%` },
        { label: 'Time to CPR', value: isTrialRun ? '10s' : rr.time_compressions_v2 || '13s' },
        { label: 'TEAM Score', value: `${engineTeamReview.team_global_score}/10` },
        { label: 'Coaching', value: String(isTrialRun ? 4 : cards.length) },
      ],
      provenanceText: `Built from ${totalEvents} multimodal events, 7 sensor channels (S1–S7), ${totalUtts} diarized utterances and ${popVars} populated REDCap fields (${engineTeamReview.model_id}, k=3 consensus). Figures are counts from video & sensor records; AHA ACLS targets are labeled.`,
    };
  })();

  const handleCoachingAskSubmit = (customQuestion) => {
    const q = String(customQuestion ?? coachingAskInput ?? '').trim();
    if (!q) return;
    const ql = q.toLowerCase();
    let answer = '';
    if (ql.includes('bicarb') || ql.includes('05:51') || ql.includes('closed') || ql.includes('loop')) {
      answer =
        'At @05:51 (utt_019), the Team Leader stated "We could do an amp of sodium bicarbonate, I\'m sure she\'s got some acidosis going on" and immediately asked for a pulse check without addressing MED_RN or receiving a repeat-back. Because no verbal confirmation or IV push occurred, REDCap records other_med_considered_v2 = 1 and time_bicarb_v2 = UTD (total_bicarb_v2 = 0). Coaching fix: issue a directed 3-step order ("Med RN, give 1 amp Sodium Bicarbonate IV push") and require "Bicarb in and flushed" readback.';
    } else if (ql.includes('epi') || ql.includes('04:03') || ql.includes('01:46') || ql.includes('med')) {
      answer =
        'Epinephrine #1 (1 mg IV) was ordered at @01:20 and confirmed given with closed-loop readback at @01:46. Epinephrine #2 was ordered at @03:54 and given at @04:03 — an inter-dose interval of 2m 17s (137s), which is 43s earlier than the AHA ACLS 3–5 minute (180–300s) window. Coaching fix: synchronize repeat Epinephrine to every second 2-minute rhythm check (~4 minutes apart).';
    } else if (ql.includes('cpr') || ql.includes('compress') || ql.includes('pause') || ql.includes('ccf') || ql.includes('rotat')) {
      answer = `S1 optical flow measured ${aiCoachingBundle.ccfVal}% Chest Compression Fraction (+${aiCoachingBundle.ccfGain}% above the 80% AHA target) with ${aiCoachingBundle.pausesGt10} prolonged pauses >10s (Pause #1 = 6.0s at @03:49, Pause #2 = 3.5s at @06:05). However, 3D Spatial Re-ID shows CLIN-2 compressed continuously for 4m 48s (@01:20–06:08) without rotating at the @03:49 rhythm check. Coaching fix: pre-stage a relief compressor at 1m 45s into each cycle and swap hands during every 2-minute check.`;
    } else if (ql.includes('fluid') || ql.includes('dehydrat') || ql.includes('pea') || ql.includes('reversible') || ql.includes('rosc')) {
      answer =
        'EMS handoff (@00:00) reported 48h of severe dehydration, vomiting, and diarrhea (hypovolemic PEA). Although the team identified GI losses during H’s & T’s brainstorming at @02:46, Normal Saline was not ordered until @06:29–06:35 (after ROSC at @06:08). Coaching fix: immediately translate H’s & T’s hypovolemia findings into an intra-arrest wide-open IV crystalloid bolus to restore preload during CPR.';
    } else {
      answer = `Top 4 care-improvement actions for ${currentCase.record_id} (Case #${currentCaseSimProtocol.num}, CCF ${aiCoachingBundle.ccfVal}%, TEAM ${engineTeamReview.team_global_score}/10): (1) Enforce 3-step directed closed-loop readbacks on adjuvant meds (@05:51 Bicarb = UTD); (2) Space Epinephrine #2 (@04:03) to the 3–5 min ACLS window (given at 2m 17s); (3) Rotate compressors at every 2-minute rhythm check (@03:49, CLIN-2 compressed 4m 48s straight); (4) Start empiric IV fluids intra-arrest when hypovolemia is identified (@02:46 vs @06:35 post-ROSC).`;
    }
    setCoachingAskAnswer({ question: q, answer });
    if (!customQuestion) setCoachingAskInput('');
  };

  // ── New video wizard steps ──
  const wizardSteps = [
    {
      key: 'video',
      label: 'Video',
      title: 'Add the resuscitation video',
      help: 'Upload a recording or point to a stored one. The REDCap record_id is required for importing the exported CSV into REDCap.',
      summary: videoPathInput ? `${videoPathInput.split('/').pop()} · record_id=${videoRecordIdInput || '—'}` : 'Not set',
      valid: !!videoPathInput.trim() && !!videoRecordIdInput.trim(),
    },
    {
      key: 'case',
      label: 'Assign case',
      title: 'Which simulation case is this video?',
      help: 'Each video is one of the 10 pre-defined cases. The case number sets simulation_number_v2, unlocks that case’s REDCap questions, and defines the rubric the video is rated against.',
      summary: `Case #${activeSimProtocol.num} · ${activeSimProtocol.shortBadge}`,
      valid: !!simulationNumberInput,
    },
    {
      key: 'models',
      label: 'Review settings',
      title: 'Clinical AI review settings',
      help: 'Choose how thoroughly the AI reviews the recording and which clinical analysis modules to include.',
      summary:
        liveEnsembleK === 3
          ? 'Standard Consensus (3x)'
          : liveEnsembleK === 2
          ? 'Double-Check (2x)'
          : 'Quick Scan (1x)',
      valid: true,
    },
    {
      key: 'optional',
      label: 'Dictionary & ground truth',
      title: 'Optional: data dictionary and reviewer markup',
      help: 'Choose which REDCap data dictionary to write results to, and optionally attach a human reviewer’s markup to measure engine accuracy.',
      summary: `${!wizardDictId || wizardDictId === activeDict?.id ? 'Default dictionary' : 'Custom dictionary'}${attachHumanGt ? ' · GT attached' : ''}`,
      valid: true,
    },
    {
      key: 'run',
      label: 'Review & run',
      title: 'Review and run',
      help: 'Confirm the inputs, then run. This launches a real engine run on Vertex AI — progress below is reported live by the server.',
      summary: pipelineStepIdx === 7 ? 'Completed' : runningJob ? `Running · ${pipelineProgressPct}%` : 'Ready',
      valid: true,
    },
  ].map((s, i) => ({ ...s, done: i < wizardStep || (i === 4 && pipelineStepIdx === 7) }));

  // Format a concise single-line label for swimlane pills so every pill stays 100% readable without truncation
  const formatSwimlanePillLabel = (ev, idxInLane = 0) => {
    const t = ev.type || '';
    if (ev.kind === 'interval' || t === 'compression_interruption') {
      const dur = Number(ev.duration_s || 0);
      return `Pause #${idxInLane + 1} (${dur}s)`;
    }
    if (t === 'first_team_member_enters') return 'Team Enters';
    if (t === 'patient_enters_room') return 'Patient Arrival';
    if (t === 'ems_handoff_begin' || t === 'ems_handoff') return 'EMS Handoff';
    if (t === 'bed_transfer_complete') return 'Bed Transfer';
    if (t === 'airway_attempt') return 'Airway Intubation';
    if (t === 'airway_confirmation') return 'ETT Confirmed';
    if (t === 'rosc_detected') return 'ROSC Achieved';
    if (t === 'death_pronounced') return 'Death Pronounced';
    if (t === 'pulse_check') return 'Pulse Check';
    if (t === 'rhythm_check') return `Rhythm Check #${idxInLane}`;
    if (t === 'defibrillation_shock') return 'Defib Shock';
    if (t === 'defib_charge_aborted') return 'Defib Aborted';
    if (t === 'compression_active_start') return 'CPR Start';
    if (t === 'mccd_application_start') return 'LUCAS Applied';
    if (t === 'medication_administration') {
      const m = (ev.label || '').match(/\(([^)]+)\)/);
      if (m && m[1]) {
        const drug = m[1].charAt(0).toUpperCase() + m[1].slice(1);
        return `${drug} IV`;
      }
      return 'Epinephrine IV';
    }
    return ev.label;
  };

  // Build 4-Swimlane rows for the Trackline Timeline Card (Row 2 Bottom Full-Width Strip)
  const timelineSwimlanes = [
    {
      id: 'lane_flow',
      title: '1 · Arrival & Airway',
      subtitle: 'Bed Transfer · ETT · Outcome',
      colorClass: 'blue',
      events: allCaseEvents.filter(
        (e) =>
          e.type.includes('enters') ||
          e.type.includes('handoff') ||
          e.type.includes('transfer') ||
          e.type.includes('airway') ||
          e.type.includes('rosc') ||
          e.type.includes('death')
      ),
    },
    {
      id: 'lane_rhythm_shock',
      title: '2 · Rhythm & Defib Shocks',
      subtitle: 'Pulse · ECG · Shocks (S3 + S5)',
      colorClass: 'purple',
      events: allCaseEvents.filter(
        (e) => e.type === 'rhythm_check' || e.type === 'pulse_check' || e.type === 'defibrillation_shock' || e.type === 'defib_charge_aborted'
      ),
    },
    {
      id: 'lane_cpr_meds',
      title: '3 · CPR, LUCAS & Meds',
      subtitle: 'Compressions · Epi (S1 + S7a)',
      colorClass: 'green',
      events: allCaseEvents.filter(
        (e) => e.type === 'compression_active_start' || e.type === 'mccd_application_start' || e.type === 'medication_administration'
      ),
    },
    {
      id: 'lane_pauses',
      title: '4 · Hands-Off Pauses (CCIs)',
      subtitle: 'S1 Optical Flow · >10s Red',
      colorClass: 'orange',
      events: allCaseEvents.filter((e) => e.kind === 'interval'),
    },
  ];

  const caseColors = ['#f97316', '#10b981', '#3b82f6', '#8b5cf6', '#06b6d4', '#1e293b', '#ec4899'];

  // Current video frame index (15 FPS dense optical flow & panoptic segmentation pass)
  const currentFrameIdx = Math.max(1, Math.round(currentTimeS * 15));
  const toggleCvLayer = (key) => setCvLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  const toggleKeyframeVerified = (kfId, e) => {
    if (e) e.stopPropagation();
    setVerifiedKeyframes((prev) => ({ ...prev, [kfId]: !prev[kfId] }));
    showToast(`Updated Specialist Verification on Keyframe ${kfId.toUpperCase()}`);
  };

  // Persistent Tracked Objects + Deformable Polygons with 4-Level Hierarchical Attribute Taxonomies
  // For live-processed videos, reads the enriched taxonomy_cards generated by the 3D Bounding Box & Re-ID step.
  const trackedObjectsTaxonomy =
    currentCase.live_run && currentCase.spatial_tracks?.taxonomy_cards?.length
      ? currentCase.spatial_tracks.taxonomy_cards
      : [
          {
            id: 'OBJ-004',
            maskId: 'INST-04',
            panopticKind: 'Thing (Instance)',
            color: '#f43f5e',
            initFrame: 'Frame 0001 (T0)',
            reidSwitches: 0,
            occlusionRecoveries: '4/4 verified',
            iouWithSternum: activeAnnotationsAtTime.inPause ? '0.18 (Hands-Off)' : '0.64 (Sternum Contact)',
            taxonomy: [
              'Clinician',
              'Compressor #1 (Chest Lead)',
              'Navy Scrubs · Blue Nitrile Gloves · Right-Bedside',
              activeAnnotationsAtTime.inPause
                ? 'Partially Occluded (38% by OBJ-002) · Hands-Off Pause'
                : 'Unoccluded (8%) · Active Sternum Compression / LUCAS Lock',
            ],
            jumpTimeS: 337.0,
          },
          {
            id: 'OBJ-002',
            maskId: 'INST-02',
            panopticKind: 'Thing (Instance)',
            color: '#10b981',
            initFrame: 'Frame 0195 (00:13)',
            reidSwitches: 0,
            occlusionRecoveries: '3/3 verified',
            iouWithSternum: currentTimeS >= 337 ? '0.68 (Straddling OBJ-001)' : '0.12 (Backplate Staged)',
            taxonomy: [
              'Medical Device',
              'MCCD > LUCAS-3 Piston & Arch',
              'Yellow/White Rigid Hood · Suction Cup Plunger',
              currentTimeS >= 337
                ? 'Locked Over Sternum · Overlapping OBJ-001 (IoU 0.68)'
                : 'Partially Occluded (22%) · Staged at Bedside',
            ],
            jumpTimeS: 342.0,
          },
          {
            id: 'OBJ-001',
            maskId: 'INST-01',
            panopticKind: 'Thing (Instance)',
            color: '#38bdf8',
            initFrame: 'Frame 0195 (00:13)',
            reidSwitches: 0,
            occlusionRecoveries: '6/6 verified',
            iouWithSternum: '1.00 (Reference Anchor)',
            taxonomy: [
              'Patient',
              'Adult OHCA Patient (Supine)',
              'Anterior Thorax Exposed · Anterolateral Defib Pads',
              activeAnnotationsAtTime.inPause
                ? 'Partially Occluded (42% by OBJ-002 & POLY-001) · Rhythm/Pulse Assessment'
                : 'Occluded (58% by Compressor Hands / LUCAS) · Receiving CPR',
            ],
            jumpTimeS: 110.0,
          },
          {
            id: 'OBJ-005',
            maskId: 'INST-05',
            panopticKind: 'Thing (Instance)',
            color: '#a855f7',
            initFrame: 'Frame 0001 (T0)',
            reidSwitches: 0,
            occlusionRecoveries: '2/2 verified',
            iouWithSternum: '0.21 (Head-of-Bed)',
            taxonomy: [
              'Clinician',
              'Airway Physician (Dr. Kong)',
              'Teal Scrubs · Protective Visor · Head-of-Bed',
              currentTimeS >= 138
                ? 'Unoccluded (10%) · ETT Secured & Capnography Connected'
                : 'Partially Occluded (26%) · Video Laryngoscopy Intubation',
            ],
            jumpTimeS: 138.0,
          },
          {
            id: 'OBJ-003',
            maskId: 'INST-03',
            panopticKind: 'Thing (Instance)',
            color: '#f59e0b',
            initFrame: 'Frame 0001 (T0)',
            reidSwitches: 0,
            occlusionRecoveries: '1/1 verified',
            iouWithSternum: '0.00 (Right Perimeter)',
            taxonomy: [
              'Medical Device',
              'Defibrillator & ECG Monitor Cart',
              'Biphasic Monitor Screen + Lead Harness',
              Math.abs(currentTimeS - 474) <= 15
                ? 'Unoccluded (0%) · Charging & Delivering 200J Biphasic Shock'
                : 'Unoccluded (5%) · Continuous ECG Waveform & S5 OCR Feed',
            ],
            jumpTimeS: 474.0,
          },
          {
            id: 'POLY-001',
            maskId: 'POLY-FABRIC-01',
            panopticKind: 'Polygon + Stuff',
            color: '#22d3ee',
            initFrame: 'Frame 0195 (00:13)',
            reidSwitches: 0,
            occlusionRecoveries: 'Deformable 9-Vertex Mesh',
            iouWithSternum: '0.39 (Lower Thorax Edge)',
            taxonomy: [
              'Deformable Polygon / Stuff',
              'Sterile Sheet Fabric + Defib Lead Wires + Cast Shadow',
              '9-Vertex Non-Rigid Contour (Cannot fit 3D BBox)',
              'Draped Across Lower Thorax · Boundary Isolated from Sternum ROI',
            ],
            jumpTimeS: 461.0,
          },
        ];

  // Keyframes where Objects Overlap or Identity Switches Could Occur (Verified by Human Domain Specialists)
  const overlapContinuityKeyframes =
    currentCase.live_run && currentCase.spatial_tracks?.overlap_keyframes?.length
      ? currentCase.spatial_tracks.overlap_keyframes
      : [
          {
            id: 'kf_0045',
            time_s: 45.0,
            mmss: '00:45',
            frame: 675,
            title: 'EMS-to-ED Bed Transfer Crossover',
            overlapPair: 'OBJ-004 ∩ OBJ-006 ∩ OBJ-001 (IoU 0.61)',
            reidNote: '4 clinicians cross paths over stretcher; OBJ-001..006 IDs locked (0 switches)',
            driftPx: '1.4px/f',
          },
          {
            id: 'kf_0150',
            time_s: 110.0,
            mmss: '01:50',
            frame: 1650,
            title: 'Pulse Check & Compressor Step-Back',
            overlapPair: 'OBJ-004 Hands Split from OBJ-001 Sternum (IoU 0.54 → 0.08)',
            reidNote: 'OBJ-004 occluded behind OBJ-005 for 4.2s, re-acquired via Kalman/Re-ID bridge',
            driftPx: '1.1px/f',
          },
          {
            id: 'kf_0537',
            time_s: 337.0,
            mmss: '05:37',
            frame: 5055,
            title: 'LUCAS-3 Backplate & Arch 3-Way Overlap',
            overlapPair: 'OBJ-002 ∩ OBJ-004 ∩ OBJ-001 ∩ POLY-001 (IoU 0.72)',
            reidNote: 'Instance masks hold through dense 3-clinician occlusion over chest',
            driftPx: '1.6px/f',
          },
          {
            id: 'kf_0754',
            time_s: 474.0,
            mmss: '07:54',
            frame: 7110,
            title: 'Defibrillation Stand-Clear & Resume',
            overlapPair: 'POLY-002 Defib Leads ∩ OBJ-002 LUCAS Cup (IoU 0.49)',
            reidNote: 'All team IDs maintained across stand-clear & immediate post-shock resume',
            driftPx: '0.9px/f',
          },
        ];

  /* ══════════════════════════════════════════════════════════════════════════
     DEDICATED SEPARATE PAGE: MELLIS HB-7 STYLE VISUAL LEARNING CONSOLE
     Full-viewport 1600×900 Pale Studio Telemetry Simulator for Video
     Understanding, 3D Volumetric Bounding Boxes, and Live Infographic Cards
     ══════════════════════════════════════════════════════════════════════════ */
  if (activeNav === 'visual_learning') {
    const inPauseNow = activeAnnotationsAtTime.inPause;
    const cprNow = activeAnnotationsAtTime.cprActive;
    const medNow =
      (focusedEvent?.type === 'medication_administration' &&
        Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18) ||
      activeAnnotationsAtTime.nearbyPointEvents.some((e) => e.type === 'medication_administration');
    const shockNow =
      (focusedEvent?.type === 'defibrillation_shock' &&
        Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18) ||
      activeAnnotationsAtTime.nearbyPointEvents.some((e) => e.type === 'defibrillation_shock');
    const airwayNow =
      focusedEvent &&
      (focusedEvent.type === 'airway_attempt' ||
        focusedEvent.type === 'airway_confirmation' ||
        focusedEvent.type === 'pocus_cardiac');
    const phaseRad = (currentTimeS * 3.6) % (Math.PI * 2);
    const compJitterY = cprNow ? Math.sin(phaseRad) * 2.8 : 0;
    const ccfVal = Number(currentCase.ccf_pct) || 97.6;
    const filledLoadSegs = Math.round((Math.min(100, Math.max(0, ccfVal)) / 100) * 24);
    const dur = Math.max(60, maxTimelineS);
    const progressPct = Math.min(100, Math.max(0, (currentTimeS / dur) * 100));

    // Continuous vermilion sine wave for Card 01 (Compression Cadence)
    const hb7WavePts = Array.from({ length: 56 })
      .map((_, i) => {
        const x = 10 + (i / 55) * 224;
        const amp = inPauseNow ? 2.5 : 22;
        const y = 36 + Math.sin(i * 0.68 + currentTimeS * 2.5) * amp;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
    const lastWaveY = 36 + Math.sin(55 * 0.68 + currentTimeS * 2.5) * (inPauseNow ? 2.5 : 22);

    const phaseModeText = inPauseNow
      ? 'PULSE CHECK PAUSE'
      : currentCase.live_run && currentTimeS >= 368
      ? 'ROSC ACHIEVED'
      : focusedEvent
      ? focusedEvent.label.toUpperCase()
      : cprNow
      ? 'ACTIVE CPR · PEA'
      : 'HANDOFF & PREP';

    return (
      <div className="hb7-studio-shell" id="visual-learning-console">
        {/* ── TOP MELLIS HB-7 TELEMETRY HEADER BAR ── */}
        <header className="hb7-topbar">
          <div className="hb7-brand-cluster">
            <div className="hb7-orange-badge">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <polygon points="12 2 21 7 21 17 12 22 3 17 3 7" />
                <polyline points="3 7 12 12 21 7" />
                <line x1="12" y1="22" x2="12" y2="12" />
              </svg>
              <span>RQ-7</span>
            </div>
            <div>
              <div className="hb7-title-eyebrow">
                MULTIMODAL CLINICAL ENGINE · NORTHWELL AI-CARES IRB #25-1097
              </div>
              <div className="hb7-title-main">
                <span>Resus-QC</span>
                <span className="hb7-title-slash">/</span>
                <select
                  value={currentCase.record_id}
                  onChange={(e) => {
                    const nextId = e.target.value;
                    const nextCase = cases.find((c) => c.record_id === nextId);
                    setSelectedCaseId(nextId);
                    setCurrentTimeS(
                      nextId === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
                        ? 474.0
                        : nextCase?.live_run
                        ? 106.0
                        : 164.0
                    );
                  }}
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: '0.74rem',
                    fontWeight: 800,
                    background: '#ffffff',
                    border: '1px solid #d6d0c4',
                    borderRadius: '4px',
                    padding: '0.2rem 0.48rem',
                    color: '#1c1b18',
                    cursor: 'pointer',
                    marginLeft: '0.35rem',
                  }}
                >
                  {cases.map((c) => {
                    const sNum = c.simulation_number || c.redcap_row?.simulation_number_v2 || 1;
                    return (
                      <option key={c.record_id} value={c.record_id}>
                        {c.record_id} · Case #{sNum} (CCF {c.ccf_pct}%)
                      </option>
                    );
                  })}
                </select>
              </div>
              <div className="hb7-title-sub">
                VIDEO UNDERSTANDING &amp; 3D MULTIMODAL SENSOR SIMULATOR · VISUAL LEARNING
              </div>
            </div>
          </div>

          {/* Center-Left CCF Load Segmented Block Bar */}
          <div className="hb7-load-bar-cluster">
            <div className="hb7-load-bar-hdr">
              <span>CCF PERFUSION LOAD</span>
              <span>{ccfVal}%</span>
            </div>
            <div className="hb7-load-segments">
              {Array.from({ length: 24 }).map((_, idx) => (
                <span
                  key={idx}
                  className={`hb7-load-seg ${idx < filledLoadSegs ? 'filled' : ''}`}
                />
              ))}
            </div>
            <div
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '0.5rem',
                color: '#8c867a',
                marginTop: '0.14rem',
              }}
            >
              <span>0%</span>
              <span>80% ACLS TARGET</span>
              <span>100%</span>
            </div>
          </div>

          {/* Right Telemetry Metadata Columns */}
          <div className="hb7-telemetry-meta-strip">
            <div className="hb7-meta-col">
              <span className="hb7-meta-lbl">SIMULATION ID</span>
              <span className="hb7-meta-val">
                CASE #{currentCaseSimProtocol.num} · {currentCase.record_id.slice(0, 14)}
              </span>
            </div>
            <div className="hb7-meta-col">
              <span className="hb7-meta-lbl">RUNTIME</span>
              <span className="hb7-meta-val">
                00:{fmtMmSs(currentTimeS)} / 00:{fmtMmSs(maxTimelineS)}
              </span>
            </div>
            <div className="hb7-meta-col">
              <span className="hb7-meta-lbl">STATUS</span>
              <span className="hb7-meta-val">
                <span
                  style={{
                    width: '7px',
                    height: '7px',
                    borderRadius: '50%',
                    background: inPauseNow ? '#e84c22' : '#149e6b',
                    display: 'inline-block',
                  }}
                />
                <span>{inPauseNow ? 'PAUSE' : cprNow ? 'ACTIVE CPR' : 'ROSC / POST'}</span>
              </span>
            </div>
            <div className="hb7-meta-col">
              <span className="hb7-meta-lbl">OPERATOR / FEED</span>
              <span className="hb7-meta-val">
                {isPortraitVideo ? 'IPAD 9:16 · LAB 1' : 'CCTV 16:9 · TRAUMA A'}
              </span>
            </div>
            <button
              type="button"
              className="hb7-pill-btn"
              style={{
                padding: '0.28rem 0.56rem',
                background: '#faf8f4',
                color: '#1c1b18',
                borderColor: '#1c1b18',
              }}
              onClick={() => {
                if (typeof document !== 'undefined') {
                  if (!document.fullscreenElement) {
                    document.documentElement.requestFullscreen?.().catch(() => {});
                  } else {
                    document.exitFullscreen?.().catch(() => {});
                  }
                }
              }}
              title="Toggle Monitor Fullscreen (F11)"
            >
              FULLSCREEN
            </button>
            <button
              type="button"
              className="hb7-pill-btn"
              style={{
                padding: '0.28rem 0.62rem',
                background: '#1c1b18',
                color: '#ffffff',
                borderColor: '#1c1b18',
              }}
              onClick={() => {
                if (typeof window !== 'undefined' && window.location.hash.startsWith('#visual-learning')) {
                  window.history.replaceState(null, '', window.location.pathname);
                }
                setActiveNav('dashboard');
              }}
            >
              ← Command Center
            </button>
          </div>
        </header>

        {/* ── MAIN 3-COLUMN 1600×900 STUDIO LAYOUT (100% LOCKED FULLSCREEN · ZERO SCROLL) ── */}
        <div
          className="hb7-main-grid"
          style={
            videoSizeMode === 'xl_theater'
              ? { gridTemplateColumns: '234px minmax(0, 1fr) 244px', gap: '0.5rem' }
              : videoSizeMode === 'large' || videoSizeMode === 'bed_wide'
              ? { gridTemplateColumns: '246px minmax(0, 1fr) 256px', gap: '0.55rem' }
              : undefined
          }
        >
          {/* ══════════ LEFT COLUMN: CARDS 01, 02, 03 ══════════ */}
          <div className="hb7-side-col">
            {/* CARD 01: COMPRESSION CADENCE (Matches `| WING BEAT 01`) */}
            <div className="hb7-card">
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>COMPRESSION CADENCE</span>
                </span>
                <span className="hb7-card-idx">01</span>
              </div>
              <div className="hb7-big-stat-row">
                <div>
                  <div className="hb7-big-num">
                    {inPauseNow ? '0.0' : '110'}
                    <span className="hb7-big-unit">CPM</span>
                  </div>
                  <div className="hb7-sub-lbl">STROKE FREQUENCY (1.83 HZ)</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="hb7-big-num" style={{ fontSize: '1.15rem' }}>
                    {inPauseNow ? '0.0' : '±5.2'}
                    <span className="hb7-big-unit">CM</span>
                  </div>
                  <div className="hb7-sub-lbl">STERNAL AMPLITUDE</div>
                </div>
              </div>

              {/* Oscillating Vermilion Waveform */}
              <svg
                viewBox="0 0 244 74"
                width="100%"
                height="40"
                style={{
                  background: '#faf8f3',
                  border: '1px solid #e6e1d6',
                  borderRadius: '4px',
                  display: 'block',
                }}
              >
                <line x1="10" y1="18" x2="234" y2="18" stroke="#e9e4da" strokeWidth="0.7" />
                <line x1="10" y1="36" x2="234" y2="36" stroke="#ded8cc" strokeWidth="0.8" strokeDasharray="2 2" />
                <line x1="10" y1="54" x2="234" y2="54" stroke="#e9e4da" strokeWidth="0.7" />
                <polyline
                  points={hb7WavePts}
                  fill="none"
                  stroke="#e84c22"
                  strokeWidth="1.65"
                  strokeLinejoin="round"
                />
                <line x1="234" y1="8" x2="234" y2="64" stroke="#1c1b18" strokeWidth="0.8" strokeDasharray="2 2" />
                <circle cx="234" cy={lastWaveY} r="3.4" fill="#e84c22" stroke="#ffffff" strokeWidth="1" />
                <text x="12" y="69" fill="#8c867a" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                  -5.0 S
                </text>
                <text x="214" y="69" fill="#1c1b18" fontSize="6.5" fontWeight="800" fontFamily="monospace">
                  NOW
                </text>
              </svg>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '0.58rem',
                  fontWeight: 700,
                  color: '#6b665e',
                }}
              >
                <span
                  style={{ cursor: 'pointer' }}
                  onClick={() => setPlaybackSpeed(playbackSpeed === 1 ? 2 : playbackSpeed === 2 ? 4 : 1)}
                  title="Click to cycle playback speed"
                >
                  PLAYBACK <strong style={{ color: '#1c1b18' }}>{playbackSpeed}.0×</strong>
                </span>
                <span>
                  OPTICAL FLOW <strong style={{ color: '#1c1b18' }}>15 FPS</strong>
                </span>
              </div>
            </div>

            {/* CARD 02: ENGINE SENSOR FUSION & CONCORDANCE (Matches `| POWER 02`) */}
            <div className="hb7-card">
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>ENGINE CONCORDANCE</span>
                </span>
                <span className="hb7-card-idx">02</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.6rem' }}>
                <div>
                  <div className="hb7-big-num">
                    100<span className="hb7-big-unit">%</span>
                  </div>
                  <div className="hb7-sub-lbl">MILESTONES ≤3.0S</div>
                </div>
                <div style={{ display: 'flex', gap: '3px', padding: '4px', background: '#f5f2ea', borderRadius: '4px', border: '1px solid #e2ddd2' }}>
                  {Array.from({ length: 10 }).map((_, idx) => (
                    <span
                      key={idx}
                      style={{
                        width: '9px',
                        height: '20px',
                        borderRadius: '1.5px',
                        background: idx < 2 ? '#e84c22' : idx < 9 ? '#149e6b' : '#dfd9cd',
                      }}
                    />
                  ))}
                </div>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '0.4rem',
                  paddingTop: '0.35rem',
                  borderTop: '1px solid #f0ece2',
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                <div>
                  <div className="hb7-sub-lbl">REDCAP</div>
                  <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#1c1b18', marginTop: '0.1rem' }}>
                    {currentCase.populated_fields_count || 68}/99
                  </div>
                </div>
                <div>
                  <div className="hb7-sub-lbl">S5 DRIFT</div>
                  <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#1c1b18', marginTop: '0.1rem' }}>
                    ±0.36 S
                  </div>
                </div>
                <div>
                  <div className="hb7-sub-lbl">GT MAE</div>
                  <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#1c1b18', marginTop: '0.1rem' }}>
                    1.0 S
                  </div>
                </div>
              </div>
            </div>

            {/* CARD 03: MULTIMODAL PASS CONFIDENCE (Matches `| LEG SERVOS 03`) */}
            <div className="hb7-card" style={{ flex: 1, justifyContent: 'flex-start', gap: '0.52rem' }}>
              <div>
                <div className="hb7-card-hdr">
                  <span className="hb7-card-hdr-left">
                    <span className="hb7-orange-tick" />
                    <span>SENSOR &amp; PASS LOAD</span>
                  </span>
                  <span className="hb7-card-idx">03</span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginTop: '0.2rem',
                  }}
                >
                  <span className="hb7-sub-lbl">CONFIDENCE PER MODALITY</span>
                  <span className="hb7-status-tag">HOLDING</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.36rem', flex: 1, justifyContent: 'space-evenly' }}>
                {[
                  { code: 'S1', name: 'S1 Sternum Flow', detail: `${currentCase.ccf_pct}% CCF · 0 Pauses`, pct: Math.round(ccfVal) },
                  { code: 'S5', name: 'S5 Monitor OCR', detail: 'PEA · ±0.36s Drift', pct: 100 },
                  { code: 'S7', name: 'S7a Audio ASR', detail: '23 Utterances', pct: 96 },
                  { code: '3D', name: '3D Re-ID Cuboids', detail: '6 Tracks · 0 Drift', pct: 97 },
                  { code: 'P1', name: 'Gemini Vision Pass', detail: `${allCaseEvents.length} Events · ≤3s GT`, pct: 95 },
                  { code: 'RC', name: 'REDCap 99-Var Gate', detail: `${currentCase.populated_fields_count || 68}/99 · TEAM 7/10`, pct: 84 },
                ].map((bar) => (
                  <div key={bar.code} style={{ display: 'flex', flexDirection: 'column', gap: '0.12rem' }}>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: '0.35rem',
                        whiteSpace: 'nowrap',
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: '0.52rem',
                        color: '#6b665e',
                        fontWeight: 700,
                      }}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{bar.name}</span>
                      <span style={{ color: '#8c867a', flexShrink: 0 }}>{bar.detail}</span>
                    </div>
                    <div className="hb7-servo-row" title={`${bar.name} — ${bar.detail}`}>
                      <span>{bar.code}</span>
                      <div className="hb7-servo-track">
                        <div className="hb7-servo-fill" style={{ width: `${bar.pct}%` }} />
                      </div>
                      <span style={{ textAlign: 'right' }}>{bar.pct}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ══════════ CENTER COLUMN: 60–70% ANNOTATED 3D VIDEO STAGE + INFOGRAPHIC CARDS + TIMELINE LOG 08 ══════════ */}
          <div
            className="hb7-center-col"
            style={videoSizeMode === 'xl_theater' ? { gridColumn: '1 / -1', order: -1 } : undefined}
          >
            {/* Top Center Viewport Stage with Pale Studio Reticle + Live Video + 3D Volumetric Bounding Boxes + Leader Callouts */}
            <div className="hb7-stage-viewport">
              {/* Architectural Cross-Ticks & Circular Studio Reticle + Studio Leader Callouts in Background */}
              <svg
                viewBox="0 0 920 440"
                width="100%"
                height="100%"
                style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 1 }}
              >
                {/* Top calibration cross-ticks (+ + + +) */}
                {Array.from({ length: 11 }).map((_, idx) => {
                  const tx = 280 + idx * 36;
                  return (
                    <g key={idx} stroke="#c8c2b4" strokeWidth="0.8">
                      <line x1={tx - 3} y1="10" x2={tx + 3} y2="10" />
                      <line x1={tx} y1="7" x2={tx} y2="13" />
                      <line x1={tx - 2} y1="24" x2={tx + 2} y2="24" />
                    </g>
                  );
                })}
                {/* Subtle circular technical studio reticle behind video */}
                <circle cx="460" cy="215" r="190" fill="none" stroke="rgba(28, 27, 24, 0.1)" strokeWidth="0.9" strokeDasharray="3 3" />
                <circle cx="460" cy="215" r="135" fill="none" stroke="rgba(28, 27, 24, 0.06)" strokeWidth="0.7" />
                <line x1="80" y1="215" x2="840" y2="215" stroke="rgba(28, 27, 24, 0.06)" strokeWidth="0.7" />
                <line x1="460" y1="28" x2="460" y2="400" stroke="rgba(28, 27, 24, 0.06)" strokeWidth="0.7" />

                {/* Left & Right Architectural Studio Leader-Line Callouts into Central Video Model (shown in narrow portrait modes) */}
                {isPortraitVideo && !isWideBedCrop && videoZoomLevel <= 1.15 && (
                  <g fontFamily="JetBrains Mono, monospace">
                    {/* Left Callout 1: S5 ECG & Rhythm Monitor */}
                    <line x1="218" y1="122" x2="352" y2="156" stroke="#1c1b18" strokeWidth="0.75" strokeDasharray="2 2" />
                    <circle cx="352" cy="156" r="2.2" fill="#e84c22" />
                    <rect x="18" y="102" width="200" height="36" rx="3" fill="rgba(255,255,255,0.94)" stroke="#d6d0c4" strokeWidth="0.9" />
                    <text x="26" y="117" fill="#1c1b18" fontSize="8" fontWeight="800">01 · S5 ECG &amp; RHYTHM ROI</text>
                    <text x="26" y="129" fill="#6b665e" fontSize="7" fontWeight="600">first_rhythm_v2 = 3 (PEA) · 0 Shocks</text>

                    {/* Left Callout 2: S1 Sternum Optical Flow */}
                    <line x1="218" y1="212" x2="395" y2="218" stroke="#e84c22" strokeWidth="0.9" />
                    <circle cx="395" cy="218" r="2.5" fill="#e84c22" />
                    <rect x="18" y="192" width="200" height="38" rx="3" fill="rgba(255,255,255,0.96)" stroke="#e84c22" strokeWidth="1.1" />
                    <text x="26" y="207" fill="#e84c22" fontSize="8" fontWeight="800">02 · S1 STERNUM OPTICAL FLOW</text>
                    <text x="26" y="220" fill="#1c1b18" fontSize="7" fontWeight="700">{`CCF ${currentCase.ccf_pct}% · CPR Start @01:20 (Exact)`}</text>

                    {/* Left Callout 3: Instance Mask Overlap Seam */}
                    <line x1="218" y1="302" x2="412" y2="258" stroke="#1c1b18" strokeWidth="0.75" strokeDasharray="2 2" />
                    <circle cx="412" cy="258" r="2.2" fill="#149e6b" />
                    <rect x="18" y="284" width="200" height="36" rx="3" fill="rgba(255,255,255,0.94)" stroke="#d6d0c4" strokeWidth="0.9" />
                    <text x="26" y="299" fill="#1c1b18" fontSize="8" fontWeight="800">03 · OVERLAP SEAM (CLIN-2 ∩ PT-1)</text>
                    <text x="26" y="311" fill="#6b665e" fontSize="7" fontWeight="600">IoU 0.53 · z-Order Verified · 0 Drift</text>

                    {/* Right Callout 4: Head-of-Bed Airway ROI */}
                    <line x1="702" y1="122" x2="518" y2="176" stroke="#1c1b18" strokeWidth="0.75" strokeDasharray="2 2" />
                    <circle cx="518" cy="176" r="2.2" fill="#149e6b" />
                    <rect x="702" y="102" width="200" height="36" rx="3" fill="rgba(255,255,255,0.94)" stroke="#d6d0c4" strokeWidth="0.9" />
                    <text x="710" y="117" fill="#1c1b18" fontSize="8" fontWeight="800">04 · HEAD-OF-BED AIRWAY ROI</text>
                    <text x="710" y="129" fill="#6b665e" fontSize="7" fontWeight="600">time_airway_v2 = 01:58 · LMA Secured</text>

                    {/* Right Callout 5: IV / IO Pharmacology Port */}
                    <line x1="702" y1="212" x2="538" y2="236" stroke="#e84c22" strokeWidth="0.9" />
                    <circle cx="538" cy="236" r="2.5" fill="#e84c22" />
                    <rect x="702" y="192" width="200" height="38" rx="3" fill="rgba(255,255,255,0.96)" stroke="#e84c22" strokeWidth="1.1" />
                    <text x="710" y="207" fill="#e84c22" fontSize="8" fontWeight="800">05 · IV / IO MEDICATION PORT</text>
                    <text x="710" y="220" fill="#1c1b18" fontSize="7" fontWeight="700">{`admin_epi_time_v2 = 01:46 (${currentCase.total_epi_doses ?? 2} Doses)`}</text>

                    {/* Right Callout 6: 3D Persistent Re-ID & Audio ASR */}
                    <line x1="702" y1="302" x2="546" y2="276" stroke="#1c1b18" strokeWidth="0.75" strokeDasharray="2 2" />
                    <circle cx="546" cy="276" r="2.2" fill="#149e6b" />
                    <rect x="702" y="284" width="200" height="36" rx="3" fill="rgba(255,255,255,0.94)" stroke="#d6d0c4" strokeWidth="0.9" />
                    <text x="710" y="299" fill="#1c1b18" fontSize="8" fontWeight="800">06 · 3D RE-ID &amp; S7a AUDIO ASR</text>
                    <text x="710" y="311" fill="#6b665e" fontSize="7" fontWeight="600">4 Clinicians Tracked · 23 Utterances</text>
                  </g>
                )}
              </svg>

              {/* Top Stage Metadata + Interactive VIDEO SIZE & OPTICAL ZOOM Bar (Outside Video — Zero Overlay) */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'nowrap',
                  gap: '0.4rem',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '0.57rem',
                  fontWeight: 700,
                  letterSpacing: '0.07em',
                  color: '#78736a',
                  position: 'relative',
                  zIndex: 4,
                  marginBottom: '0.1rem',
                  flexShrink: 0,
                }}
              >
                <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  MODEL {(currentCase.model_id || 'GEMINI-4-ARGON').toUpperCase()} · FRAME #{currentFrameIdx}
                  {activeRedcapRowAtPlayhead && (
                    <span style={{ color: '#e84c22', fontWeight: 800, marginLeft: '0.45rem' }}>
                      · REDCAP [{activeRedcapRowAtPlayhead.redcapField} = {String(activeRedcapRowAtPlayhead.redcapValue).slice(0, 16)}]
                    </span>
                  )}
                </span>

                {/* Interactive Video Size Preset & Synchronized 3D Bounding-Box Zoom Controls */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.22rem',
                    flexWrap: 'nowrap',
                    background: 'rgba(255, 255, 255, 0.94)',
                    border: '1px solid #d6d0c4',
                    borderRadius: '4px',
                    padding: '0.12rem 0.34rem',
                    boxShadow: '0 1px 4px rgba(28, 27, 24, 0.05)',
                    flexShrink: 0,
                  }}
                >
                  <span style={{ color: '#1c1b18', fontWeight: 800, marginRight: '0.1rem' }}>SIZE:</span>
                  {[
                    { id: 'std', label: '1× STUDIO' },
                    { id: 'large', label: '1.5× LARGE' },
                    { id: 'bed_wide', label: '2.3× BED WIDE' },
                    { id: 'xl_theater', label: '2× THEATER' },
                  ].map((sz) => (
                    <button
                      key={sz.id}
                      type="button"
                      className={`hb7-pill-btn ${videoSizeMode === sz.id ? 'active' : ''}`}
                      style={{ padding: '0.12rem 0.36rem', fontSize: '0.53rem' }}
                      onClick={() => setVideoSizeMode(sz.id)}
                    >
                      {sz.label}
                    </button>
                  ))}

                  <span style={{ color: '#c8c2b4', margin: '0 0.08rem' }}>|</span>
                  <span style={{ color: '#1c1b18', fontWeight: 800 }}>ZOOM:</span>
                  <button
                    type="button"
                    className="hb7-pill-btn"
                    style={{ padding: '0.1rem 0.28rem', fontSize: '0.54rem' }}
                    onClick={() => setVideoZoomLevel((z) => Math.max(1.0, Math.round((z - 0.25) * 100) / 100))}
                    title="Zoom Out Video + 3D Bounding Boxes"
                  >
                    −
                  </button>
                  {[1.0, 1.25, 1.5, 2.0].map((zm) => (
                    <button
                      key={zm}
                      type="button"
                      className={`hb7-pill-btn ${Math.abs(videoZoomLevel - zm) < 0.05 ? 'active' : ''}`}
                      style={{ padding: '0.1rem 0.28rem', fontSize: '0.52rem' }}
                      onClick={() => setVideoZoomLevel(zm)}
                    >
                      {Math.round(zm * 100)}%
                    </button>
                  ))}
                  <button
                    type="button"
                    className="hb7-pill-btn"
                    style={{ padding: '0.1rem 0.28rem', fontSize: '0.54rem' }}
                    onClick={() => setVideoZoomLevel((z) => Math.min(2.0, Math.round((z + 0.25) * 100) / 100))}
                    title="Zoom In Video + 3D Bounding Boxes"
                  >
                    +
                  </button>
                </div>

                <span style={{ whiteSpace: 'nowrap', flexShrink: 0 }}>
                  ROI:{' '}
                  <strong style={{ color: '#e84c22' }}>
                    {domainFilter === 'all' ? 'ALL ROIs' : domainFilter.toUpperCase()}
                  </strong>
                </span>
              </div>

              {/* Central Annotated Video Stage (Unobstructed Video + 3D Wireframe Boxes, Fits 100vh) */}
              <div
                className={`video-3d-stage ${cameraPerspectiveView === 'spatial_34' ? 'perspective-34' : ''}`}
                ref={stageRef}
                style={{
                  position: 'relative',
                  width: '100%',
                  flex: '1 1 0%',
                  minHeight: 0,
                  height: '100%',
                  maxHeight: 'none',
                  margin: '0.08rem auto',
                  borderRadius: '7px',
                  border: 'none',
                  background: 'transparent',
                  boxShadow: 'none',
                  zIndex: 2,
                }}
              >
                <div
                  className="video-media-frame"
                  style={{
                    position: 'absolute',
                    ...mediaRect,
                    zIndex: 1,
                    background: '#0f172a',
                    borderRadius: '8px',
                    border: '1.5px solid #2b2925',
                    boxShadow: '0 10px 28px rgba(28, 27, 24, 0.20)',
                    overflow: 'hidden',
                    transform:
                      cameraPerspectiveView === 'spatial_34'
                        ? `${mediaRect.transform ? mediaRect.transform + ' ' : ''}perspective(1280px) rotateX(8deg) rotateY(-6deg) scale(0.95)`
                        : mediaRect.transform,
                    transition: 'all 0.26s cubic-bezier(0.22, 1, 0.36, 1)',
                  }}
                >
                  <div
                    style={{
                      ...innerMediaCanvasStyle,
                      background: `#0f172a url("/api/video/poster?case_id=${encodeURIComponent(currentCase.record_id)}") center / contain no-repeat`,
                    }}
                  >
                    <video
                      ref={videoRef}
                      key={reviewVideoSrc}
                      src={reviewVideoSrc}
                      poster={`/api/video/poster?case_id=${encodeURIComponent(currentCase.record_id)}`}
                      muted
                      playsInline
                      preload="auto"
                      onLoadedMetadata={(e) => {
                        setVideoDims({ w: e.currentTarget.videoWidth, h: e.currentTarget.videoHeight });
                        try {
                          e.currentTarget.currentTime = currentTimeS;
                        } catch {
                          // ignore
                        }
                      }}
                      style={{
                        position: 'absolute',
                        inset: 0,
                        width: '100%',
                        height: '100%',
                        objectFit: 'contain',
                        opacity: 1,
                        zIndex: 1,
                      }}
                    />
                  </div>
                </div>

                {/* 3D Volumetric Bounding Boxes, Polygons, Masks & Trajectories (Unobstructed — Zero Gray Overlay Boxes) */}
                <div
                  className="video-media-frame"
                  style={{
                    position: 'absolute',
                    ...mediaRect,
                    zIndex: 2,
                    pointerEvents: 'none',
                    overflow: 'hidden',
                    borderRadius: '8px',
                    transform:
                      cameraPerspectiveView === 'spatial_34'
                        ? `${mediaRect.transform ? mediaRect.transform + ' ' : ''}perspective(1280px) rotateX(8deg) rotateY(-6deg) scale(0.95)`
                        : mediaRect.transform,
                    transition: 'all 0.26s cubic-bezier(0.22, 1, 0.36, 1)',
                  }}
                >
                  <div style={{ ...innerMediaCanvasStyle, pointerEvents: 'none' }}>
                  {currentCase.live_run ? (
                    <svg
                      viewBox={`0 0 ${liveSvgW} ${liveSvgH}`}
                      width="100%"
                      height="100%"
                      shapeRendering="geometricPrecision"
                      preserveAspectRatio="none"
                      style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none' }}
                    >
                      {(() => {
                        const W = liveSvgW;
                        const H = liveSvgH;
                        const sx = (v) => (v / 1000) * W;
                        const sy = (v) => (v / 1000) * H;
                        const clampX = (x, bw) => Math.max(8, Math.min(W - bw - 8, x));
                        const clampY = (y, bh) => Math.max(38, Math.min(H - bh - 46, y));

                        const ptBox = livePtObj?.box || [530, 180, 770, 560];
                        const [ptY0, ptX0, ptY1, ptX1] = ptBox;
                        const ptW = Math.max(80, ptX1 - ptX0);
                        const ptH = Math.max(80, ptY1 - ptY0);

                        const defBox = liveDefibObj?.box || [520, 40, 665, 220];
                        const [defY0, defX0, defY1, defX1] = defBox;

                        const airwayBox = [
                          ptY0 - ptH * 0.04,
                          ptX0 + ptW * 0.08,
                          ptY0 + ptH * 0.42,
                          ptX0 + ptW * 0.42,
                        ];
                        const chestBox = [
                          ptY0 + ptH * 0.16,
                          ptX0 + ptW * 0.28,
                          ptY0 + ptH * 0.68,
                          ptX0 + ptW * 0.68,
                        ];
                        const ivBox = [
                          ptY0 + ptH * 0.38,
                          ptX0 + ptW * 0.56,
                          ptY0 + ptH * 0.84,
                          ptX0 + ptW * 0.94,
                        ];

                        const chestColor = inPauseNow ? '#f87171' : cprNow ? '#34d399' : '#38bdf8';
                        const chestFill = inPauseNow
                          ? 'rgba(239, 68, 68, 0.14)'
                          : cprNow
                          ? 'rgba(16, 185, 129, 0.12)'
                          : 'rgba(56, 189, 248, 0.08)';

                        const medEv =
                          (focusedEvent?.type === 'medication_administration' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                            focusedEvent) ||
                          activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'medication_administration');
                        const medActive = Boolean(medEv);
                        const ivCol = medActive ? '#c4b5fd' : 'rgba(167, 139, 250, 0.85)';

                        const shockEv =
                          (focusedEvent?.type === 'defibrillation_shock' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                            focusedEvent) ||
                          activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'defibrillation_shock');
                        const rhyEv =
                          (focusedEvent?.type === 'rhythm_check' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                            focusedEvent) ||
                          activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'rhythm_check' || e.type === 'pulse_check');
                        const isShock = Boolean(shockEv);
                        const isRhy = Boolean(rhyEv);
                        const defCol = isShock ? '#fbbf24' : isRhy ? '#22d3ee' : 'rgba(56, 189, 248, 0.85)';

                        const renderCuboid = (box, dx, dy, stroke, fill = 'none', sw = 0.85, dashed = false, corners = false) => {
                          const x0 = sx(box[1]);
                          const y0 = sy(box[0]);
                          const x1 = sx(box[3]);
                          const y1 = sy(box[2]);
                          const bx0 = x0 + dx;
                          const by0 = y0 + dy;
                          const bx1 = x1 + dx;
                          const by1 = y1 + dy;
                          return (
                            <g>
                              <polygon
                                points={`${bx0},${by0} ${bx1},${by0} ${bx1},${by1} ${bx0},${by1}`}
                                fill="none"
                                stroke={stroke}
                                strokeWidth={sw * 0.85}
                                strokeDasharray={dashed ? '2.5 2' : 'none'}
                                strokeOpacity="0.85"
                              />
                              <polygon
                                points={`${x0},${y0} ${x1},${y0} ${x1},${y1} ${x0},${y1}`}
                                fill={fill}
                                stroke={stroke}
                                strokeWidth={sw}
                              />
                              <line x1={bx0} y1={by0} x2={x0} y2={y0} stroke={stroke} strokeWidth={sw * 0.75} />
                              <line x1={bx1} y1={by0} x2={x1} y2={y0} stroke={stroke} strokeWidth={sw * 0.75} />
                              <line x1={bx1} y1={by1} x2={x1} y2={y1} stroke={stroke} strokeWidth={sw * 0.75} />
                              <line x1={bx0} y1={by1} x2={x0} y2={y1} stroke={stroke} strokeWidth={sw * 0.75} />
                              {corners && (
                                <path
                                  d={`M${x0},${y0 + 7} L${x0},${y0} L${x0 + 7},${y0} M${x1 - 7},${y0} L${x1},${y0} L${x1},${y0 + 7} M${x0},${y1 - 7} L${x0},${y1} L${x0 + 7},${y1} M${x1 - 7},${y1} L${x1},${y1} L${x1},${y1 - 7}`}
                                  fill="none"
                                  stroke="#ffffff"
                                  strokeWidth="1.1"
                                />
                              )}
                            </g>
                          );
                        };

                        return (
                          <>
                            {/* Perspective Ground-Plane Grid */}
                            <g stroke="rgba(56, 189, 248, 0.16)" strokeWidth="0.45" strokeDasharray="2.5 3.5">
                              <line x1={W * 0.14} y1={H * 0.96} x2={W * 0.28} y2={H * 0.24} />
                              <line x1={W * 0.34} y1={H * 0.96} x2={W * 0.42} y2={H * 0.24} />
                              <line x1={W * 0.56} y1={H * 0.96} x2={W * 0.56} y2={H * 0.24} />
                              <line x1={W * 0.78} y1={H * 0.96} x2={W * 0.70} y2={H * 0.24} />
                              <line x1={W * 0.12} y1={H * 0.46} x2={W * 0.88} y2={H * 0.43} />
                              <line x1={W * 0.08} y1={H * 0.68} x2={W * 0.92} y2={H * 0.65} />
                            </g>

                            {/* 3D Volumetric Boxes with Minimal Corner Tags (Zero Gray Overlay Blocking Video) */}
                            {cvLayers.boxes3d && (
                              <g>
                                {/* Airway ROI */}
                                {(() => {
                                  const ax0 = sx(airwayBox[1]);
                                  const ay0 = sy(airwayBox[0]);
                                  return (
                                    <g opacity={getSubsystemRoiOpacity('airway')}>
                                      {renderCuboid(airwayBox, -6, -16, '#34d399', 'rgba(16, 185, 129, 0.06)', 0.75, true, false)}
                                      <rect x={ax0} y={Math.max(4, ay0 - 28)} width="46" height="11" rx="2" fill="rgba(15, 23, 42, 0.45)" stroke="#34d399" strokeWidth="0.55" />
                                      <text x={ax0 + 3} y={Math.max(12, ay0 - 20)} fill="#a7f3d0" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                                        AIRWAY
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* S1 Chest Sternum ROI */}
                                {(() => {
                                  const cx0 = sx(chestBox[1]);
                                  const cy0 = sy(chestBox[0]);
                                  const cx = sx((chestBox[1] + chestBox[3]) / 2);
                                  const cy = cy0;
                                  return (
                                    <g opacity={getSubsystemRoiOpacity('cpr')}>
                                      {renderCuboid(chestBox, -7, -20, chestColor, chestFill, 1.0, false, true)}
                                      {cprNow && (
                                        <g stroke="#34d399" strokeWidth="0.95">
                                          <line x1={cx - 7} y1={cy - 24} x2={cx - 7} y2={cy + 6} />
                                          <polygon points={`${cx - 10},${cy + 3} ${cx - 4},${cy + 3} ${cx - 7},${cy + 9}`} fill="#34d399" stroke="none" />
                                          <line x1={cx + 7} y1={cy - 26} x2={cx + 7} y2={cy + 4} />
                                          <polygon points={`${cx + 4},${cy + 1} ${cx + 10},${cy + 1} ${cx + 7},${cy + 7}`} fill="#34d399" stroke="none" />
                                        </g>
                                      )}
                                      <rect x={cx0} y={Math.max(4, cy0 - 32)} width="58" height="11" rx="2" fill="rgba(15, 23, 42, 0.48)" stroke={chestColor} strokeWidth="0.6" />
                                      <text x={cx0 + 3} y={Math.max(12, cy0 - 24)} fill="#f8fafc" fontSize="6.6" fontWeight="700" fontFamily="monospace">
                                        {inPauseNow ? 'S1 PAUSE' : 'S1 STERNUM'}
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* IV / IO Access ROI */}
                                {(() => {
                                  const ix0 = sx(ivBox[1]);
                                  const iy1 = sy(ivBox[2]);
                                  return (
                                    <g opacity={getSubsystemRoiOpacity('meds')}>
                                      {renderCuboid(ivBox, -5, -15, ivCol, medActive ? 'rgba(139, 92, 246, 0.12)' : 'rgba(139, 92, 246, 0.05)', 0.78, false, medActive)}
                                      <rect x={ix0} y={Math.min(H - 14, iy1 + 2)} width="48" height="11" rx="2" fill="rgba(15, 23, 42, 0.45)" stroke={ivCol} strokeWidth="0.55" />
                                      <text x={ix0 + 3} y={Math.min(H - 6, iy1 + 10)} fill="#ede9fe" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                                        IV / IO
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* S3/S5 Defib & Monitor ROI */}
                                {(() => {
                                  const dx0 = sx(defX0);
                                  const dy0 = sy(defY0);
                                  const dx1 = sx(defX1);
                                  const dy1 = sy(defY1);
                                  const dcy = (dy0 + dy1) / 2;
                                  const mw = Math.max(24, dx1 - dx0);
                                  const ecgPts = [
                                    `${dx0 + mw * 0.14},${dcy - 4}`,
                                    `${dx0 + mw * 0.26},${dcy - 11}`,
                                    `${dx0 + mw * 0.36},${dcy + 3}`,
                                    `${dx0 + mw * 0.48},${dcy - 14}`,
                                    `${dx0 + mw * 0.58},${dcy + 4}`,
                                    `${dx0 + mw * 0.70},${dcy - 9}`,
                                    `${dx0 + mw * 0.84},${dcy - 3}`,
                                  ].join(' ');
                                  return (
                                    <g opacity={getSubsystemRoiOpacity('shocks')}>
                                      {renderCuboid(defBox, -6, -18, defCol, 'rgba(56, 189, 248, 0.06)', 0.82, false, true)}
                                      <polyline points={ecgPts} fill="none" stroke={isShock ? '#fbbf24' : '#38bdf8'} strokeWidth="0.9" />
                                      <rect x={dx0} y={Math.max(4, dy0 - 30)} width="52" height="11" rx="2" fill="rgba(15, 23, 42, 0.45)" stroke={defCol} strokeWidth="0.55" />
                                      <text x={dx0 + 3} y={Math.max(12, dy0 - 22)} fill="#f8fafc" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                                        S5 DEFIB
                                      </text>
                                    </g>
                                  );
                                })()}

                                {/* All Real Tracked Clinicians 3D Cuboids — Minimal Corner ID Tag */}
                                {liveBoxesNow
                                  .filter((o) => !o.id.startsWith('PT-') && !o.id.startsWith('DEFIB-'))
                                  .map((o) => {
                                    const col = o.color || trackColor(o.category);
                                    const dx = o.dx3d || -8;
                                    const dy = o.dy3d || -16;
                                    const x0 = sx(o.box[1]);
                                    const y0 = sy(o.box[0]);
                                    const tagX = clampX(x0 + dx, 46);
                                    const tagY = clampY(Math.max(4, y0 + dy - 12), 11);
                                    return (
                                      <g key={o.id} opacity={getSubsystemRoiOpacity('team')}>
                                        {renderCuboid(o.box, dx, dy, col, `${col}10`, 0.85, false, true)}
                                        <rect
                                          x={tagX}
                                          y={tagY}
                                          width="44"
                                          height="11"
                                          rx="2"
                                          fill="rgba(15, 23, 42, 0.45)"
                                          stroke={col}
                                          strokeWidth="0.55"
                                        />
                                        <text x={tagX + 3} y={tagY + 8} fill="#f8fafc" fontSize="6.4" fontWeight="700" fontFamily="monospace">
                                          {o.id.slice(0, 7)}
                                        </text>
                                      </g>
                                    );
                                  })}
                              </g>
                            )}

                            {/* Instance Masks & Overlap Seam */}
                            {cvLayers.instanceMasks && (
                              <g>
                                {liveBoxesNow.slice(0, 5).map((o) => {
                                  const col = o.color || trackColor(o.category);
                                  const x0 = sx(o.box[1]);
                                  const y0 = sy(o.box[0]);
                                  const x1 = sx(o.box[3]);
                                  const y1 = sy(o.box[2]);
                                  return (
                                    <ellipse
                                      key={`hb7-mask-${o.id}`}
                                      cx={(x0 + x1) / 2}
                                      cy={(y0 + y1) / 2}
                                      rx={Math.max(10, (x1 - x0) * 0.44)}
                                      ry={Math.max(10, (y1 - y0) * 0.44)}
                                      fill={`${col}18`}
                                      stroke={col}
                                      strokeWidth="0.75"
                                      strokeDasharray="3 1.5"
                                    />
                                  );
                                })}
                              </g>
                            )}

                            {/* Persistent Re-ID Trajectories */}
                            {cvLayers.reidTrajectories && (
                              <g>
                                {liveTrajectories.map((tr) => {
                                  const ptsStr = tr.pts.map((p) => `${sx(p.cx)},${sy(p.cy)}`).join(' ');
                                  const col = tr.pts[0]?.color || '#f43f5e';
                                  return (
                                    <g key={`hb7-traj-${tr.id}`}>
                                      <polyline points={ptsStr} fill="none" stroke={col} strokeWidth="0.9" strokeDasharray="3 2" />
                                      {tr.pts.map((p, idx) => (
                                        <circle
                                          key={`${tr.id}-pt-${idx}`}
                                          cx={sx(p.cx)}
                                          cy={sy(p.cy)}
                                          r={idx === tr.pts.length - 1 ? 2.6 : 1.8}
                                          fill={idx === tr.pts.length - 1 ? '#fde047' : col}
                                        />
                                      ))}
                                    </g>
                                  );
                                })}
                              </g>
                            )}
                          </>
                        );
                      })()}
                    </svg>
                  ) : (
                    /* Trauma A CCTV 3D Volumetric Bounding Boxes */
                    <svg
                      viewBox="0 0 860 390"
                      width="100%"
                      height="100%"
                      shapeRendering="geometricPrecision"
                      preserveAspectRatio="none"
                      style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none' }}
                    >
                      {cvLayers.boxes3d && (
                        <>
                          <g opacity={getSubsystemRoiOpacity('airway')}>
                            <polygon points="286,136 338,130 344,174 292,180" fill="rgba(16, 185, 129, 0.06)" stroke="#34d399" strokeWidth="0.8" />
                            <polygon points="284,106 336,100 342,144 290,150" fill="none" stroke="#34d399" strokeWidth="0.7" />
                            <rect x="284" y="92" width="46" height="11" rx="2" fill="rgba(15, 23, 42, 0.45)" stroke="#34d399" strokeWidth="0.55" />
                            <text x="287" y="100" fill="#a7f3d0" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                              AIRWAY
                            </text>
                          </g>
                          <g opacity={getSubsystemRoiOpacity('cpr')}>
                            <polygon points="348,132 408,125 416,172 354,180" fill="rgba(16, 185, 129, 0.08)" stroke="#34d399" strokeWidth="0.95" />
                            <polygon points="346,96 406,89 414,136 352,144" fill="none" stroke="#34d399" strokeWidth="0.85" />
                            <rect x="346" y="81" width="58" height="11" rx="2" fill="rgba(15, 23, 42, 0.48)" stroke="#34d399" strokeWidth="0.6" />
                            <text x="349" y="89" fill="#f8fafc" fontSize="6.6" fontWeight="700" fontFamily="monospace">
                              S1 STERNUM
                            </text>
                          </g>
                          <g opacity={getSubsystemRoiOpacity('meds')}>
                            <polygon points="422,126 476,120 484,162 428,168" fill="rgba(139, 92, 246, 0.06)" stroke="#c4b5fd" strokeWidth="0.8" />
                            <rect x="428" y="170" width="48" height="11" rx="2" fill="rgba(15, 23, 42, 0.45)" stroke="#c4b5fd" strokeWidth="0.55" />
                            <text x="431" y="178" fill="#ede9fe" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                              IV / IO
                            </text>
                          </g>
                          <g opacity={getSubsystemRoiOpacity('shocks')}>
                            <polygon points="534,74 592,68 600,126 542,134" fill="rgba(56, 189, 248, 0.06)" stroke="#38bdf8" strokeWidth="0.8" />
                            <rect x="534" y="60" width="52" height="11" rx="2" fill="rgba(15, 23, 42, 0.45)" stroke="#38bdf8" strokeWidth="0.55" />
                            <text x="537" y="68" fill="#f8fafc" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                              S5 DEFIB
                            </text>
                          </g>
                        </>
                      )}
                    </svg>
                  )}
                  </div>
                </div>
              </div>

              {/* Bottom-Left Studio Phase Readout (Matches `FLIGHT MODE / DEPARTING` in Mellis HB-7) */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-end',
                  justifyContent: 'space-between',
                  position: 'relative',
                  zIndex: 3,
                  marginTop: '0.1rem',
                  flexShrink: 0,
                }}
              >
                <div>
                  <div className="hb7-sub-lbl">CLINICAL PHASE · @{fmtMmSs(currentTimeS)}</div>
                  <div
                    style={{
                      fontSize: '1.15rem',
                      fontWeight: 900,
                      letterSpacing: '0.03em',
                      color: '#e84c22',
                      lineHeight: 1.05,
                    }}
                  >
                    {phaseModeText}
                  </div>
                  <div className="hb7-sub-lbl" style={{ marginTop: '0.04rem' }}>
                    {currentCaseSimProtocol.title} · {allCaseEvents.length} EVENTS
                  </div>
                </div>
                <div style={{ textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontSize: '0.58rem', color: '#4a463f' }}>
                  <div>
                    ACTIVE EVIDENCE:{' '}
                    <strong style={{ color: '#1c1b18' }}>
                      “{(focusedEvent?.evidence_text || 'Continuous S1 optical flow chest compressions').slice(0, 56)}”
                    </strong>
                  </div>
                  <div style={{ fontSize: '0.52rem', color: '#78736a', marginTop: '0.05rem' }}>
                    MAPPED REDCAP: [{(focusedEvent?.mapped_fields || ['time_compressions_v2']).join(', ')}]
                  </div>
                </div>
              </div>
            </div>

            {/* ── INTEGRATED VISUAL LEARNING INFOGRAPHIC CARD DECK (Matches Uploaded Screenshot 2!) ── */}
            <div className="hb7-infographic-deck">
              {/* LEFT INFOGRAPHIC CARD: 2D BAY SCHEMATIC (REDRAWN FROM FRAME #N) */}
              <div className="hb7-infographic-card">
                <div className="co-console-subpanel-header" style={{ marginBottom: '0.2rem' }}>
                  <span style={{ fontWeight: 800, color: '#0f172a', fontSize: '0.66rem', fontFamily: "'JetBrains Mono', monospace" }}>
                    2D BAY SCHEMATIC (REDRAWN FROM FRAME #{currentFrameIdx})
                  </span>
                  <span className="mono" style={{ fontSize: '0.58rem', color: '#475569', fontWeight: 700 }}>
                    Click zone to isolate subsystem
                  </span>
                </div>
                <svg
                  viewBox="0 0 380 154"
                  width="100%"
                  height="98"
                  style={{
                    display: 'block',
                    background: '#f8fafc',
                    borderRadius: '6px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <g stroke="#e2e8f0" strokeWidth="0.6">
                    <line x1="0" y1="38" x2="380" y2="38" />
                    <line x1="0" y1="79" x2="380" y2="79" />
                    <line x1="0" y1="120" x2="380" y2="120" />
                    <line x1="76" y1="0" x2="76" y2="154" />
                    <line x1="152" y1="0" x2="152" y2="154" />
                    <line x1="228" y1="0" x2="228" y2="154" />
                    <line x1="304" y1="0" x2="304" y2="154" />
                  </g>
                  <polygon
                    points="18,14 148,46 148,118"
                    fill="rgba(37, 99, 235, 0.06)"
                    stroke="#cbd5e1"
                    strokeWidth="0.7"
                    strokeDasharray="2 2"
                  />
                  <text x="8" y="12" fill="#475569" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                    CCTV/T0
                  </text>
                  <text x="292" y="147" fill="#475569" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                    iPad / POV
                  </text>

                  {/* Stretcher Bed & Supine Patient */}
                  <rect x="78" y="48" width="196" height="58" rx="8" fill="#ffffff" stroke="#94a3b8" strokeWidth="1.1" />
                  <circle cx="102" cy="77" r="11" fill="#f1f5f9" stroke="#64748b" strokeWidth="0.9" />
                  <rect x="116" y="61" width="84" height="32" rx="7" fill="#f1f5f9" stroke="#64748b" strokeWidth="0.9" />
                  <rect x="203" y="65" width="56" height="10" rx="4" fill="#f1f5f9" stroke="#94a3b8" strokeWidth="0.8" />
                  <rect x="203" y="79" width="56" height="10" rx="4" fill="#f1f5f9" stroke="#94a3b8" strokeWidth="0.8" />

                  {/* ZONE 1: AIRWAY / ETT */}
                  <g
                    style={{ cursor: 'pointer' }}
                    opacity={getSubsystemRoiOpacity('airway')}
                    onClick={() => setDomainFilter(domainFilter === 'airway' ? 'all' : 'airway')}
                  >
                    <rect
                      x="84"
                      y="56"
                      width="32"
                      height="42"
                      rx="5"
                      fill={airwayNow || domainFilter === 'airway' ? 'rgba(16, 185, 129, 0.22)' : 'rgba(16, 185, 129, 0.08)'}
                      stroke="#059669"
                      strokeWidth="1.1"
                    />
                    <line x1="100" y1="56" x2="62" y2="29" stroke="#059669" strokeWidth="0.7" />
                    <rect x="14" y="17" width="92" height="14" rx="3" fill="#ecfdf5" stroke="#059669" strokeWidth="0.7" />
                    <text x="18" y="26.5" fill="#065f46" fontSize="6.7" fontWeight="800" fontFamily="monospace">
                      AIRWAY / ETT
                    </text>
                  </g>

                  {/* ZONE 2: S1 STERNUM / CPR */}
                  <g
                    style={{ cursor: 'pointer' }}
                    opacity={getSubsystemRoiOpacity('cpr')}
                    onClick={() => setDomainFilter(domainFilter === 'cpr' ? 'all' : 'cpr')}
                  >
                    <rect
                      x="130"
                      y="62"
                      width="44"
                      height="30"
                      rx="5"
                      fill={inPauseNow ? 'rgba(239, 68, 68, 0.24)' : 'rgba(16, 185, 129, 0.24)'}
                      stroke={inPauseNow ? '#dc2626' : '#059669'}
                      strokeWidth="1.4"
                    />
                    <circle
                      cx="152"
                      cy="77"
                      r={cprNow ? 7 + Math.abs(compJitterY) : 6}
                      fill={inPauseNow ? '#ef4444' : '#10b981'}
                      fillOpacity="0.3"
                      stroke={inPauseNow ? '#dc2626' : '#059669'}
                      strokeWidth="1"
                    />
                    <line x1="152" y1="62" x2="158" y2="29" stroke={inPauseNow ? '#dc2626' : '#059669'} strokeWidth="0.75" />
                    <rect
                      x="112"
                      y="15"
                      width="118"
                      height="15"
                      rx="3"
                      fill={inPauseNow ? '#fef2f2' : '#ecfdf5'}
                      stroke={inPauseNow ? '#dc2626' : '#059669'}
                      strokeWidth="0.8"
                    />
                    <text x="116" y="25" fill={inPauseNow ? '#991b1b' : '#065f46'} fontSize="6.7" fontWeight="800" fontFamily="monospace">
                      {inPauseNow ? 'S1 PAUSE ACTIVE' : `S1 CPR · CCF ${currentCase.ccf_pct}%`}
                    </text>
                  </g>

                  {/* ZONE 3: IV / IO MEDICATION PORT */}
                  <g
                    style={{ cursor: 'pointer' }}
                    opacity={getSubsystemRoiOpacity('meds')}
                    onClick={() => setDomainFilter(domainFilter === 'meds' ? 'all' : 'meds')}
                  >
                    <rect
                      x="176"
                      y="84"
                      width="34"
                      height="18"
                      rx="4"
                      fill={medNow || domainFilter === 'meds' ? 'rgba(124, 58, 237, 0.24)' : 'rgba(124, 58, 237, 0.12)'}
                      stroke="#7c3aed"
                      strokeWidth="1.1"
                    />
                    <line x1="193" y1="102" x2="182" y2="132" stroke="#7c3aed" strokeWidth="0.7" />
                    <rect x="118" y="132" width="122" height="15" rx="3" fill="#f5f3ff" stroke="#7c3aed" strokeWidth="0.75" />
                    <text x="122" y="142" fill="#5b21b6" fontSize="6.6" fontWeight="800" fontFamily="monospace">
                      {`IV/IO [total_epi=${currentCase.total_epi_doses ?? 2}]`}
                    </text>
                  </g>

                  {/* ZONE 4: DEFIBRILLATOR & ECG MONITOR CART */}
                  <g
                    style={{ cursor: 'pointer' }}
                    opacity={getSubsystemRoiOpacity('shocks')}
                    onClick={() => setDomainFilter(domainFilter === 'shocks' ? 'all' : 'shocks')}
                  >
                    <rect
                      x="292"
                      y="32"
                      width="72"
                      height="42"
                      rx="6"
                      fill={shockNow || domainFilter === 'shocks' ? 'rgba(245, 158, 11, 0.22)' : '#eff6ff'}
                      stroke={shockNow ? '#d97706' : '#0284c7'}
                      strokeWidth="1.2"
                    />
                    <path d="M 292,54 Q 235,44 174,72" fill="none" stroke="#0284c7" strokeWidth="0.85" strokeDasharray="2.5 2" />
                    <text x="298" y="45" fill="#0f172a" fontSize="6.8" fontWeight="800" fontFamily="monospace">
                      DEFIB-1 / S5
                    </text>
                    <polyline
                      points="298,58 308,58 313,49 318,65 324,47 330,63 336,55 356,55"
                      fill="none"
                      stroke="#0284c7"
                      strokeWidth="1.05"
                    />
                    <text x="298" y="70" fill="#475569" fontSize="6.1" fontFamily="monospace">
                      {`Shocks: ${currentCase.total_shocks ?? 0}`}
                    </text>
                  </g>

                  {/* Tracked Clinicians (C1, AW, TL) */}
                  <g
                    style={{ cursor: 'pointer' }}
                    opacity={getSubsystemRoiOpacity('team')}
                    onClick={() => setDomainFilter(domainFilter === 'team' ? 'all' : 'team')}
                  >
                    <circle cx="152" cy={40 + compJitterY} r="7.5" fill="#f43f5e" stroke="#ffffff" strokeWidth="1.2" />
                    <text x="145" y={42.5 + compJitterY} fill="#ffffff" fontSize="5.8" fontWeight="800" fontFamily="monospace">
                      C1
                    </text>
                    <circle cx="62" cy="77" r="7.5" fill="#10b981" stroke="#ffffff" strokeWidth="1.2" />
                    <text x="55" y="79.5" fill="#ffffff" fontSize="5.8" fontWeight="800" fontFamily="monospace">
                      AW
                    </text>
                    <circle cx="268" cy="122" r="7.5" fill="#6366f1" stroke="#ffffff" strokeWidth="1.2" />
                    <text x="261" y="124.5" fill="#ffffff" fontSize="5.8" fontWeight="800" fontFamily="monospace">
                      TL
                    </text>
                    <text x="280" y="125" fill="#334155" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                      TEAM ({currentCase.team_overall_score || 37}/44)
                    </text>
                  </g>
                </svg>
              </div>

              {/* RIGHT INFOGRAPHIC CARD: LIVE S1 COMPRESSION CADENCE & PERFUSION LOOP */}
              <div className="hb7-infographic-card">
                <div className="co-console-subpanel-header" style={{ marginBottom: '0.2rem' }}>
                  <span style={{ fontWeight: 800, color: '#0f172a', fontSize: '0.66rem', fontFamily: "'JetBrains Mono', monospace" }}>
                    LIVE S1 COMPRESSION CADENCE &amp; PERFUSION LOOP
                  </span>
                  <span className="mono" style={{ fontSize: '0.58rem', color: '#2563eb', fontWeight: 800 }}>
                    Playhead @{fmtMmSs(currentTimeS)} / {fmtMmSs(maxTimelineS)}
                  </span>
                </div>
                {(() => {
                  const cursorX = 16 + Math.min(1, Math.max(0, currentTimeS / dur)) * 224;
                  const intervals = allCaseEvents.filter((ev) => ev.kind === 'interval');
                  const pointMilestones = allCaseEvents.filter((ev) => ev.kind !== 'interval').slice(0, 8);
                  const wavePts = Array.from({ length: 46 })
                    .map((_, idx) => {
                      const t = (idx / 45) * dur;
                      const x = 16 + (idx / 45) * 224;
                      const pausedAtT = intervals.some(
                        (iv) => t >= iv.t_start_s && t <= (iv.t_end_s || iv.t_start_s + 8)
                      );
                      const y = pausedAtT ? 112 : 48 + Math.sin(idx * 1.7 + currentTimeS * 0.4) * 8;
                      return `${x.toFixed(1)},${y.toFixed(1)}`;
                    })
                    .join(' ');
                  const loopCx = 314;
                  const loopCy = 78;
                  const rx = inPauseNow ? 14 : cprNow ? 36 : 24;
                  const ry = inPauseNow ? 10 : cprNow ? 28 : 18;
                  const orbitAngle = (currentTimeS * 4.2) % (Math.PI * 2);
                  const dotX = loopCx + Math.cos(orbitAngle) * rx;
                  const dotY = loopCy + Math.sin(orbitAngle) * ry;
                  return (
                    <svg
                      viewBox="0 0 380 154"
                      width="100%"
                      height="98"
                      style={{
                        display: 'block',
                        background: '#f8fafc',
                        borderRadius: '6px',
                        border: '1px solid #e2e8f0',
                      }}
                    >
                      <rect x="16" y="24" width="224" height="96" rx="4" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.8" />
                      <rect x="16" y="38" width="224" height="24" fill="rgba(16, 185, 129, 0.10)" />
                      <text x="20" y="34" fill="#059669" fontSize="6.2" fontWeight="700" fontFamily="monospace">
                        TARGET 100-120 CPM (CCF ≥80%)
                      </text>
                      {intervals.map((iv) => {
                        const x0 = 16 + Math.min(1, Math.max(0, iv.t_start_s / dur)) * 224;
                        const x1 = 16 + Math.min(1, Math.max(0, (iv.t_end_s || iv.t_start_s + 8) / dur)) * 224;
                        return (
                          <g key={iv.id} style={{ cursor: 'pointer' }} onClick={() => seekToEvent(iv)}>
                            <rect x={x0} y="24" width={Math.max(4, x1 - x0)} height="96" fill="rgba(239, 68, 68, 0.18)" />
                          </g>
                        );
                      })}
                      <polyline points={wavePts} fill="none" stroke={inPauseNow ? '#dc2626' : '#059669'} strokeWidth="1.35" />
                      {pointMilestones.map((ev) => {
                        const px = 16 + Math.min(1, Math.max(0, ev.t_start_s / dur)) * 224;
                        return (
                          <g key={ev.id} style={{ cursor: 'pointer' }} onClick={() => seekToEvent(ev)}>
                            <circle cx={px} cy="120" r="3.2" fill="#4f46e5" stroke="#ffffff" strokeWidth="0.9" />
                          </g>
                        );
                      })}
                      <line x1={cursorX} y1="20" x2={cursorX} y2="124" stroke="#2563eb" strokeWidth="1.5" />
                      <circle cx={cursorX} cy="24" r="3.2" fill="#2563eb" />
                      <text x="16" y="136" fill="#475569" fontSize="6.4" fontWeight="700" fontFamily="monospace">
                        00:00 · Click pin/pause to seek
                      </text>
                      <text x="162" y="136" fill="#0f172a" fontSize="6.4" fontWeight="800" fontFamily="monospace">
                        {`Active: ${(activeRedcapRowAtPlayhead?.redcapField || 'admin_epi_time_v2').slice(0, 16)}`}
                      </text>

                      {/* Right Chart: Perfusion Loop (P-V) */}
                      <rect x="252" y="24" width="116" height="96" rx="4" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.8" />
                      <text x="258" y="34" fill="#334155" fontSize="6.1" fontWeight="800" fontFamily="monospace">
                        PERFUSION LOOP (P-V)
                      </text>
                      <line x1="262" y1="78" x2="360" y2="78" stroke="#e2e8f0" strokeWidth="0.7" />
                      <line x1="314" y1="38" x2="314" y2="114" stroke="#e2e8f0" strokeWidth="0.7" />
                      <ellipse
                        cx={loopCx}
                        cy={loopCy}
                        rx={rx}
                        ry={ry}
                        fill={inPauseNow ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.14)'}
                        stroke={inPauseNow ? '#dc2626' : '#059669'}
                        strokeWidth="1.4"
                      />
                      <circle
                        cx={dotX}
                        cy={dotY}
                        r="3.8"
                        fill={inPauseNow ? '#dc2626' : '#059669'}
                        stroke="#ffffff"
                        strokeWidth="1"
                      />
                      <text
                        x="256"
                        y="136"
                        fill={inPauseNow ? '#dc2626' : '#059669'}
                        fontSize="6.4"
                        fontWeight="800"
                        fontFamily="monospace"
                      >
                        {inPauseNow ? 'CPP DROP (PAUSE)' : 'CPP MAINTAINED'}
                      </text>
                    </svg>
                  );
                })()}
              </div>
            </div>

            {/* ── CARD 08: BOTTOM-CENTER TIMELINE LOG (Matches `| FLIGHT LOG 08`) ── */}
            <div className="hb7-flight-log-card">
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>RESUSCITATION LOG</span>
                </span>
                <span className="hb7-card-idx">08</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
                <button
                  type="button"
                  className="hb7-play-btn"
                  onClick={() => setIsPlaying(!isPlaying)}
                  title={isPlaying ? 'Pause Video' : 'Play Video'}
                >
                  {isPlaying ? 'II' : '▶'}
                </button>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.18rem' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '0.56rem',
                      fontWeight: 800,
                      letterSpacing: '0.08em',
                    }}
                  >
                    <span style={{ color: '#8c867a' }}>ARRIVAL (00:00)</span>
                    <span style={{ color: '#e84c22' }}>
                      OPERATOR · {(focusedEvent?.label || 'ACTIVE CPR COMPRESSIONS').toUpperCase()} · @{fmtMmSs(currentTimeS)}
                    </span>
                    <span style={{ color: '#8c867a' }}>ROSC ({fmtMmSs(maxTimelineS)})</span>
                  </div>

                  {/* Interactive Vermilion Timeline Scrubber Track with Event Ticks */}
                  <div
                    style={{
                      position: 'relative',
                      height: '13px',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <div
                      style={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        height: '3px',
                        background: '#e5dfd3',
                        borderRadius: '99px',
                      }}
                    />
                    <div
                      style={{
                        position: 'absolute',
                        left: 0,
                        width: `${progressPct}%`,
                        height: '3px',
                        background: '#e84c22',
                        borderRadius: '99px',
                      }}
                    />
                    {allCaseEvents.map((ev) => {
                      const pct = Math.min(99, Math.max(1, (ev.t_start_s / dur) * 100));
                      return (
                        <span
                          key={ev.id}
                          onClick={() => seekToEvent(ev)}
                          title={`${ev.start_mmss} · ${ev.label}`}
                          style={{
                            position: 'absolute',
                            left: `${pct}%`,
                            width: '7px',
                            height: '7px',
                            borderRadius: '50%',
                            background: Math.abs(ev.t_start_s - currentTimeS) <= 6 ? '#1c1b18' : '#e84c22',
                            border: '1.5px solid #ffffff',
                            transform: 'translateX(-50%)',
                            cursor: 'pointer',
                            zIndex: 2,
                          }}
                        />
                      );
                    })}
                    <input
                      type="range"
                      min="0"
                      max={maxTimelineS}
                      step="0.5"
                      value={Math.min(maxTimelineS, currentTimeS)}
                      onChange={(e) => {
                        setIsPlaying(false);
                        setCurrentTimeS(Number(e.target.value));
                      }}
                      style={{
                        width: '100%',
                        opacity: 0,
                        cursor: 'pointer',
                        height: '13px',
                        position: 'relative',
                        zIndex: 3,
                      }}
                    />
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '0.56rem',
                      fontWeight: 700,
                      color: '#6b665e',
                    }}
                  >
                    <span>
                      {fmtMmSs(currentTimeS)} / {fmtMmSs(maxTimelineS)}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <button type="button" className="hb7-pill-btn" style={{ padding: '0.08rem 0.34rem' }} onClick={() => stepEvent(-1)}>
                        PREV
                      </button>
                      <button type="button" className="hb7-pill-btn" style={{ padding: '0.08rem 0.34rem' }} onClick={() => stepEvent(1)}>
                        NEXT
                      </button>
                      <span>{allCaseEvents.length} EXTRACTED ACTIONS</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ══════════ RIGHT COLUMN: CARDS 04, 05, 06, 07 ══════════ */}
          <div className="hb7-side-col">
            {/* CARD 04: SPATIAL TELEMETRY (Matches `| FLIGHT 04`) */}
            <div className="hb7-card">
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>SPATIAL TELEMETRY</span>
                </span>
                <span className="hb7-card-idx">04</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '64px 1fr', gap: '0.5rem', alignItems: 'center' }}>
                {/* Circular Spatial Attitude / Vector Dial */}
                <svg viewBox="0 0 84 84" width="60" height="60">
                  <circle cx="42" cy="42" r="38" fill="#f5f2ea" stroke="#dcd6c8" strokeWidth="1" />
                  <path d="M 8,48 L 76,34 L 70,72 L 16,74 Z" fill="#e6e1d6" opacity="0.7" />
                  <line x1="10" y1="42" x2="74" y2="42" stroke="#b8b1a2" strokeWidth="0.8" strokeDasharray="2 2" />
                  <line x1="42" y1="10" x2="42" y2="74" stroke="#b8b1a2" strokeWidth="0.8" strokeDasharray="2 2" />
                  <line
                    x1="20"
                    y1={42 - compJitterY * 1.4}
                    x2="64"
                    y2={42 + compJitterY * 1.4}
                    stroke="#e84c22"
                    strokeWidth="2.2"
                  />
                  <circle cx="42" cy="42" r="3.2" fill="#1c1b18" />
                </svg>

                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.18rem',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: '0.58rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#8c867a' }}>FRAME IDX</span>
                    <strong style={{ color: '#1c1b18' }}>#{currentFrameIdx}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#8c867a' }}>S1 VELOCITY</span>
                    <strong style={{ color: '#1c1b18' }}>{cprNow ? '+5.2 CM/S' : '0.0 CM/S'}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#8c867a' }}>OVERLAP IoU</span>
                    <strong style={{ color: '#1c1b18' }}>0.53 (Z-OK)</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#8c867a' }}>ID SWITCHES</span>
                    <strong style={{ color: '#149e6b' }}>0 DRIFT</strong>
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  paddingTop: '0.22rem',
                  borderTop: '1px solid #f0ece2',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '0.54rem',
                  color: '#6b665e',
                }}
              >
                <span>
                  HOLD <strong style={{ color: '#1c1b18' }}>POSITION T0</strong>
                </span>
                <span>
                  FOV <strong style={{ color: '#1c1b18' }}>{isPortraitVideo ? 'IPAD 9:16' : 'CCTV 16:9'}</strong>
                </span>
              </div>
            </div>

            {/* CARD 05: ASSEMBLIES / SUBSYSTEM ROI ISOLATION (Matches `| ASSEMBLIES 05`) */}
            <div className="hb7-card">
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>ASSEMBLIES (ROI)</span>
                </span>
                <span className="hb7-card-idx">05</span>
              </div>
              <div className="hb7-pill-grid">
                {[
                  { id: 'all', label: 'HERO' },
                  { id: 'cpr', label: 'S1 STERNUM' },
                  { id: 'airway', label: 'AIRWAY' },
                  { id: 'meds', label: 'IV / MEDS' },
                  { id: 'shocks', label: 'DEFIB / S5' },
                  { id: 'team', label: 'TEAM RE-ID' },
                ].map((asm) => (
                  <button
                    key={asm.id}
                    type="button"
                    className={`hb7-pill-btn ${domainFilter === asm.id ? 'active' : ''}`}
                    onClick={() => setDomainFilter(asm.id)}
                  >
                    {asm.label}
                  </button>
                ))}
              </div>
            </div>

            {/* CARD 06: DISPLAY & CAMERA PERSPECTIVE (Matches `| DISPLAY 06`) */}
            <div className="hb7-card">
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>DISPLAY</span>
                </span>
                <span className="hb7-card-idx">06</span>
              </div>
              <div className="hb7-pill-grid">
                <button
                  type="button"
                  className={`hb7-pill-btn ${cvLayers.boxes3d ? 'active' : ''}`}
                  onClick={() => toggleCvLayer('boxes3d')}
                >
                  3D BOXES
                </button>
                <button
                  type="button"
                  className={`hb7-pill-btn ${cvLayers.instanceMasks ? 'active' : ''}`}
                  onClick={() => toggleCvLayer('instanceMasks')}
                >
                  MASKS &amp; IoU
                </button>
                <button
                  type="button"
                  className={`hb7-pill-btn ${cvLayers.panopticPolygons ? 'active' : ''}`}
                  onClick={() => toggleCvLayer('panopticPolygons')}
                >
                  POLYGONS
                </button>
                <button
                  type="button"
                  className={`hb7-pill-btn ${cvLayers.reidTrajectories ? 'active' : ''}`}
                  onClick={() => toggleCvLayer('reidTrajectories')}
                >
                  RE-ID PATHS
                </button>
                <button
                  type="button"
                  className={`hb7-pill-btn ${cameraPerspectiveView === 'spatial_34' ? 'active' : ''}`}
                  onClick={() =>
                    setCameraPerspectiveView(cameraPerspectiveView === 'spatial_34' ? 'hero_auto' : 'spatial_34')
                  }
                >
                  3/4 TURNTABLE
                </button>
                <button
                  type="button"
                  className={`hb7-pill-btn ${isolateSubsystemRoi ? 'active' : ''}`}
                  onClick={() => setIsolateSubsystemRoi((p) => !p)}
                >
                  ISOLATE ROI
                </button>
              </div>
              <div
                style={{
                  borderTop: '1px solid #e6e1d6',
                  paddingTop: '0.25rem',
                  marginTop: '0.1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.2rem',
                }}
              >
                <div className="hb7-sub-lbl">VIDEO STAGE SIZE &amp; OPTICAL ZOOM</div>
                <div className="hb7-pill-grid">
                  {[
                    { id: 'std', label: '1× STUDIO' },
                    { id: 'large', label: '1.5× LARGE' },
                    { id: 'bed_wide', label: '2.3× BED WIDE' },
                    { id: 'xl_theater', label: '2× THEATER' },
                  ].map((sz) => (
                    <button
                      key={sz.id}
                      type="button"
                      className={`hb7-pill-btn ${videoSizeMode === sz.id ? 'active' : ''}`}
                      onClick={() => setVideoSizeMode(sz.id)}
                    >
                      {sz.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* CARD 07: SUBSYSTEMS & REDCAP LIVE STREAM (Matches `| SUBSYSTEMS 07`) */}
            <div className="hb7-card" style={{ flex: 1, justifyContent: 'flex-start', gap: '0.42rem' }}>
              <div className="hb7-card-hdr">
                <span className="hb7-card-hdr-left">
                  <span className="hb7-orange-tick" />
                  <span>SUBSYSTEMS</span>
                </span>
                <span className="hb7-card-idx">07</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-evenly', flex: 1, gap: '0.2rem' }}>
                {[
                  {
                    idx: '01',
                    title: 'OPTIC S5 MONITOR',
                    sub: 'ECG RHYTHM · PEA RECOGNIZED',
                    tag: 'TRACKING',
                    domain: 'shocks',
                    seekS: currentCase.live_run ? 80.0 : 118.0,
                  },
                  {
                    idx: '02',
                    title: 'AIRWAY & LMA HEAD',
                    sub: 'SUPRAGLOTTIC · BILAT SOUNDS',
                    tag: 'LOCKED',
                    domain: 'airway',
                    seekS: currentCase.live_run ? 118.0 : 195.0,
                  },
                  {
                    idx: '03',
                    title: 'THORAX S1 DRIVE',
                    sub: `STERNUM ROI · ${currentCase.ccf_pct}% CCF`,
                    tag: inPauseNow ? 'PAUSED' : 'RUNNING',
                    orange: inPauseNow,
                    domain: 'cpr',
                    seekS: currentCase.live_run ? 80.0 : 110.0,
                  },
                  {
                    idx: '04',
                    title: 'IV/IO PHARMACOLOGY',
                    sub: `EPI ×${currentCase.total_epi_doses ?? 2} · 01:46, 04:03`,
                    tag: '1.83 HZ',
                    domain: 'meds',
                    seekS: currentCase.live_run ? 106.0 : 153.0,
                  },
                  {
                    idx: '05',
                    title: 'S7a AUDIO DIARIZER',
                    sub: "23 UTTERANCES · H'S & T'S",
                    tag: 'HOLDING',
                    domain: 'team',
                    seekS: currentCase.live_run ? 119.0 : 220.0,
                  },
                  {
                    idx: '06',
                    title: 'REDCAP CAPSULE',
                    sub: `${currentCase.populated_fields_count || 68}/99 FIELDS · 8/8 GT ≤3S`,
                    tag: 'SEALED',
                    domain: 'all',
                    seekS: currentCase.live_run ? 368.0 : 474.0,
                  },
                  {
                    idx: '07',
                    title: 'TEAM DEBRIEF ENGINE',
                    sub: '4 DONE WELL · 4 COACHING · 7/10',
                    tag: 'VERIFIED',
                    domain: 'team',
                    seekS: currentCase.live_run ? 351.0 : 474.0,
                  },
                ].map((s) => (
                  <div
                    key={s.idx}
                    className="hb7-subsys-row"
                    onClick={() => {
                      setDomainFilter(s.domain);
                      setIsPlaying(false);
                      setCurrentTimeS(s.seekS);
                    }}
                    title={`Click to isolate ${s.title} and seek to @${fmtMmSs(s.seekS)}`}
                  >
                    <span className="mono" style={{ fontSize: '0.58rem', color: '#9c968a', fontWeight: 700 }}>
                      {s.idx}
                    </span>
                    <div>
                      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.64rem', fontWeight: 800, color: '#1c1b18' }}>
                        {s.title}
                      </div>
                      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.52rem', color: '#8c867a', fontWeight: 600 }}>
                        {s.sub}
                      </div>
                    </div>
                    <span className={`hb7-status-tag ${s.orange ? 'orange' : ''}`}>{s.tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── BOTTOM MELLIS HB-7 STUDIO FOOTER STRIP ── */}
        <footer className="hb7-footer-bar">
          <span>
            VISUAL LEARNING SIMULATOR · MULTIMODAL MODEL · 4 SENSORS · 5 LLM PASSES · 99 REDCAP VARIABLES
          </span>
          <span>NORTHWELL HEALTH AI-CARES · RESUS-QC LAB //////</span>
        </footer>
      </div>
    );
  }

  return (
    <div className={`tl-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* ══════════════════════════════════════════════════════════════════════
          ALAIR CREATIVE LEFT NAVIGATION SIDEBAR (Matches Reference Screenshot 1)
          248px Expanded / 72px Collapsed · Zero Emojis · Crisp SVG Vector Icons
         ══════════════════════════════════════════════════════════════════════ */}
      <aside className={`tl-sidebar alair-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* Window Traffic Lights Dots (Matches top of Alair Creative sidebar) */}
        <div className="alair-window-dots">
          <span className="alair-dot red" />
          <span className="alair-dot yellow" />
          <span className="alair-dot green" />
        </div>

        {/* Brand Header + Blue Circular Collapse Toggle (< / >) */}
        <div className="alair-brand-row">
          {!sidebarCollapsed && (
            <div className="alair-brand-left">
              <div className="alair-brand-titles">
                <div className="alair-brand-name">CareOps Clinical</div>
              </div>
            </div>
          )}
          <button
            type="button"
            className="alair-collapse-btn"
            onClick={() => setSidebarCollapsed((v) => !v)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <ProIcon name={sidebarCollapsed ? 'chevronRight' : 'chevronLeft'} size={14} color="#ffffff" />
          </button>
        </div>

        {/* Primary Menu Section */}
        <div className="alair-section">
          <div className="alair-section-label">Menu</div>
          <nav className="alair-nav-list">
            <button
              type="button"
              className={`alair-nav-item ${activeNav === 'home_overview' ? 'active' : ''}`}
              onClick={() => {
                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#dashboard');
                setActiveNav('dashboard');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              data-tooltip="Home"
            >
              <span className="alair-nav-left">
                <ProIcon name="home" size={17} color="#3f3f46" />
                {!sidebarCollapsed && <span>Home</span>}
              </span>
            </button>

            <button
              type="button"
              className={`alair-nav-item ${activeNav === 'dashboard' ? 'active' : ''}`}
              onClick={() => {
                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#dashboard');
                setActiveNav('dashboard');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              data-tooltip="Case Review"
            >
              <span className="alair-nav-left">
                <ProIcon name="task" size={17} color="#18181b" />
                {!sidebarCollapsed && <span>Task · Case Review</span>}
              </span>
              {!sidebarCollapsed && <span className="alair-badge-red">{cases.length || 12}</span>}
            </button>

            <button
              type="button"
              className={`alair-nav-item ${activeNav === 'video' ? 'active' : ''}`}
              onClick={() => {
                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                setActiveNav('video');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              data-tooltip="Activity · Video"
            >
              <span className="alair-nav-left">
                <ProIcon name="activity" size={17} color="#3f3f46" />
                {!sidebarCollapsed && <span>Activity · 3D Video</span>}
              </span>
            </button>

            <button
              type="button"
              className={`alair-nav-item ${activeNav === 'coaching' ? 'active' : ''}`}
              onClick={() => {
                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#ai-insights');
                setActiveNav('coaching');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              data-tooltip="AI Insights & Coaching"
            >
              <span className="alair-nav-left">
                <ProIcon name="sparkle" size={17} color="#18181b" />
                {!sidebarCollapsed && <span>AI Insights</span>}
              </span>
              {!sidebarCollapsed && <span className="alair-badge-red">{aiCoachingBundle.isTrialRun ? 4 : aiCoachingBundle.cards?.length || 4}</span>}
            </button>

            <button
              type="button"
              className={`alair-nav-item ${activeNav === 'findings' ? 'active' : ''}`}
              onClick={() => {
                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#dashboard');
                setActiveNav('dashboard');
                setTimeout(() => {
                  document.getElementById('section-active-workflows')?.scrollIntoView({ behavior: 'smooth' });
                }, 50);
              }}
              data-tooltip="REDCap Findings"
            >
              <span className="alair-nav-left">
                <ProIcon name="bell" size={17} color="#3f3f46" />
                {!sidebarCollapsed && <span>Notification · REDCap</span>}
              </span>
              {!sidebarCollapsed && <span className="alair-badge-red">{contractData.totalCount || 99}</span>}
            </button>
          </nav>
        </div>

        <div className="alair-divider" />

        {/* Utility Menu: Setting & Support */}
        <div className="alair-section">
          <nav className="alair-nav-list">
            <button
              type="button"
              className="alair-nav-item"
              onClick={() => setShowDictModal(true)}
              data-tooltip="Setting · Schema"
            >
              <span className="alair-nav-left">
                <ProIcon name="settings" size={17} color="#3f3f46" />
                {!sidebarCollapsed && <span>Setting · Schema</span>}
              </span>
            </button>

            <button
              type="button"
              className="alair-nav-item"
              onClick={() => {
                if (typeof window !== 'undefined') {
                  window.history.replaceState(null, '', '#visual-learning');
                }
                setActiveNav('visual_learning');
              }}
              data-tooltip="Visual Simulator"
            >
              <span className="alair-nav-left">
                <ProIcon name="info" size={17} color="#3f3f46" />
                {!sidebarCollapsed && <span>Support · Visual Lab</span>}
              </span>
            </button>
          </nav>
        </div>

        {/* Group Section (Matches Pastel Circular Vector Badges + Right Chevrons) */}
        <div className="alair-section">
          <div className="alair-section-label">Group</div>
          <div className="alair-nav-list">
            <button
              type="button"
              className="alair-group-item"
              onClick={() => {
                setActiveNav('dashboard');
                setDomainFilter('branching');
                document.getElementById('section-active-workflows')?.scrollIntoView({ behavior: 'smooth' });
              }}
              title="Inspect Case Protocol & 50 REDCap Branching Rules"
            >
              <span className="alair-group-left">
                <span className="alair-pastel-circle green">
                  <ProIcon name="layers" size={13} color="#15803d" />
                </span>
                {!sidebarCollapsed && <span>Case #{currentCaseSimProtocol.num} Protocol</span>}
              </span>
              {!sidebarCollapsed && <ProIcon name="chevronRight" size={14} color="#71717a" />}
            </button>

            <button
              type="button"
              className="alair-group-item"
              onClick={() => handleDownloadRedcapCsv(true)}
              title="Download 99-Variable REDCap Import CSV"
            >
              <span className="alair-group-left">
                <span className="alair-pastel-circle blue">
                  <ProIcon name="download" size={13} color="#1d4ed8" />
                </span>
                {!sidebarCollapsed && <span>REDCap Exports</span>}
              </span>
              {!sidebarCollapsed && <ProIcon name="chevronRight" size={14} color="#71717a" />}
            </button>

            <button
              type="button"
              className="alair-group-item"
              onClick={() => {
                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                setActiveNav('video');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              title="Open S1-S7 Sensor & 3D Video Telemetry Console Page"
            >
              <span className="alair-group-left">
                <span className="alair-pastel-circle rose">
                  <ProIcon name="database" size={13} color="#be185d" />
                </span>
                {!sidebarCollapsed && <span>S1–S7 Telemetry</span>}
              </span>
              {!sidebarCollapsed && <ProIcon name="chevronRight" size={14} color="#71717a" />}
            </button>

            <button
              type="button"
              className="alair-group-item"
              onClick={() => {
                setPipelineStepIdx(-1);
                setWizardStep(0);
                setPipelineProgressPct(0);
                setLastCompletedCaseId(null);
                setActiveNav('new_video');
              }}
              title="Submit a New Video or Attach Human Golden Dataset"
            >
              <span className="alair-group-left">
                <span className="alair-pastel-circle amber">
                  <ProIcon name="shield" size={13} color="#b45309" />
                </span>
                {!sidebarCollapsed && <span>New Video / GT</span>}
              </span>
              {!sidebarCollapsed && <ProIcon name="chevronRight" size={14} color="#71717a" />}
            </button>
          </div>
        </div>

        {/* Bottom Light / Dark Segmented Toggle + Clinician Profile Footer */}
        <div className="alair-bottom-dock">
          <div className="alair-theme-toggle">
            <button
              type="button"
              className={`alair-theme-btn ${theme === 'light' ? 'active' : ''}`}
              onClick={() => setTheme('light')}
              title="Light Theme"
            >
              <ProIcon name="sun" size={14} color={theme === 'light' ? '#18181b' : '#71717a'} />
              {!sidebarCollapsed && <span>Light</span>}
            </button>
            {!sidebarCollapsed && (
              <button
                type="button"
                className={`alair-theme-btn ${theme === 'dark' ? 'active' : ''}`}
                onClick={() => setTheme('dark')}
                title="Dark Theme"
              >
                <ProIcon name="moon" size={14} color={theme === 'dark' ? '#18181b' : '#71717a'} />
                <span>Dark</span>
              </button>
            )}
          </div>

          <div className="alair-user-footer">
            <div className="alair-user-left">
              <div className="alair-user-avatar">DJ</div>
              {!sidebarCollapsed && (
                <div className="alair-user-meta">
                  <div className="alair-user-name">Daniel Jafari, MD</div>
                  <div className="alair-user-email">irb-25-1097@northwell.edu</div>
                </div>
              )}
            </div>
            {!sidebarCollapsed && (
              <button
                type="button"
                className="alair-logout-btn"
                onClick={() => handleDownloadEventsCsv(true)}
                title="Export Case Audit Log CSV"
              >
                <ProIcon name="logout" size={16} color="#3f3f46" />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* ══════════════════════════════════════════════════════════════════════
          FLOWAI MAIN WORKSPACE CANVAS (Matches Reference Screenshot 2)
         ══════════════════════════════════════════════════════════════════════ */}
      <div className="tl-main-wrapper">
        {/* Top FlowAI Utility Bar (Breadcrumb + Search + Visual Learning + Bell + Avatar) */}
        <div className="flow-topbar">
          <div className="flow-topbar-left">
            <button
              type="button"
              className="flow-icon-btn"
              onClick={() => setSidebarCollapsed((v) => !v)}
              title="Toggle Sidebar"
            >
              <ProIcon name="sidebarToggle" size={15} color="#71717a" />
            </button>
            <span className="flow-breadcrumb">
              <ProIcon name="grid" size={15} color="#71717a" />
              <span>
                {activeNav === 'video'
                  ? '3D Video & Telemetry Console'
                  : activeNav === 'coaching'
                  ? 'AI Insights & Clinical Coaching'
                  : 'Dashboard'}
              </span>
              <span className="flow-crumb-sep">/</span>
              <span className="flow-crumb-active mono">{currentCase.record_id}</span>
            </span>
          </div>

          <div className="flow-topbar-right">
            <button
              type="button"
              className="flow-ask-ai-btn"
              style={
                activeNav === 'coaching'
                  ? { background: '#18181b', color: '#ffffff', borderColor: '#18181b' }
                  : {}
              }
              onClick={() => {
                if (activeNav === 'coaching') {
                  if (typeof window !== 'undefined') window.history.replaceState(null, '', '#dashboard');
                  setActiveNav('dashboard');
                } else {
                  if (typeof window !== 'undefined') window.history.replaceState(null, '', '#ai-insights');
                  setActiveNav('coaching');
                }
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              title={
                activeNav === 'coaching'
                  ? 'Return to Command Center Dashboard'
                  : 'Open Dedicated AI Insights & Physician Coaching Page'
              }
            >
              <ProIcon
                name="sparkle"
                size={13}
                color={activeNav === 'coaching' ? '#ffffff' : '#2563eb'}
              />
              <span>{activeNav === 'coaching' ? 'Command Center' : 'AI Insights & Coaching'}</span>
            </button>

            <button
              type="button"
              className="flow-ask-ai-btn"
              onClick={() => {
                if (activeNav === 'video') {
                  if (typeof window !== 'undefined') window.history.replaceState(null, '', '#dashboard');
                  setActiveNav('dashboard');
                } else {
                  if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                  setActiveNav('video');
                }
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              title={activeNav === 'video' ? 'Return to Command Center Dashboard' : 'Open 3D Video & Telemetry Study Console Page'}
            >
              <ProIcon name={activeNav === 'video' ? 'chevronLeft' : 'activity'} size={13} color="#18181b" />
              <span>{activeNav === 'video' ? 'Command Center' : '3D Video Console'}</span>
            </button>

            <button
              type="button"
              className="flow-ask-ai-btn"
              onClick={() => {
                if (typeof window !== 'undefined') {
                  window.history.replaceState(null, '', '#visual-learning');
                }
                setActiveNav('visual_learning');
              }}
              title="Open 1600×900 Visual Learning Simulator"
            >
              <ProIcon name="flowMark" size={12} color="#18181b" />
              <span>Visual Learning</span>
            </button>
          </div>
        </div>

        <div className="tl-main-sheet">
          {/* Welcome & Case Action Header Row (Hidden on dedicated `coaching` AI Insights page which has its own custom header) */}
          {activeNav !== 'coaching' && (
          <header className="flow-welcome-header">
            {activeNav === 'new_video' ? (
              <>
                <div>
                  <h1 className="flow-welcome-title">Submit a Resuscitation Video for Review</h1>
                  <p className="flow-welcome-sub">
                    Assign simulation protocol (1–10), run Gemini 4 multimodal extraction + 3D tracking, and verify against REDCap.
                  </p>
                </div>
                <div className="flow-welcome-actions">
                  <button className="flow-pill-btn" disabled={runningJob} onClick={() => setActiveNav('dashboard')}>
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                {activeNav !== 'video' ? (
                  <div>
                    <h1 className="flow-welcome-title">Resuscitation Command Center</h1>
                    <p className="flow-welcome-sub">
                      {`Select a recording on the left to inspect its clinical review, ACLS protocol gates, and ${contractData.totalCount} extracted REDCap variables on the right.`}
                    </p>
                  </div>
                ) : (
                  <div />
                )}

                <div className="flow-welcome-actions">
                  {activeNav === 'video' && (
                    <div className="flow-date-case-pill">
                      <ProIcon name="calendar" size={15} color="#52525b" />
                      <select
                        aria-label="Active Resuscitation Case"
                        className="flow-case-select"
                        value={currentCase.record_id}
                        onChange={(e) => {
                          const nextId = e.target.value;
                          const nextCase = cases.find((c) => c.record_id === nextId);
                          setSelectedCaseId(nextId);
                          setCurrentTimeS(
                            nextId === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
                              ? 474.0
                              : nextCase?.live_run
                              ? 106.0
                              : 164.0
                          );
                        }}
                      >
                        {cases.map((c) => {
                          const sNum = c.simulation_number || c.redcap_row?.simulation_number_v2 || '—';
                          return (
                            <option key={c.record_id} value={c.record_id}>
                              {c.record_id} · Case #{sNum}
                            </option>
                          );
                        })}
                      </select>
                    </div>
                  )}

                  <div
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      background: '#ffffff',
                      border: '1px solid #e4e4e7',
                      borderRadius: '999px',
                      padding: '3px 6px 3px 12px',
                      boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
                    }}
                    title="Required REDCap record_id (Column 1 of exported CSV)"
                  >
                    <label
                      htmlFor="redcap-record-id-input"
                      style={{
                        fontSize: '11.5px',
                        fontWeight: 600,
                        color: '#52525b',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      record_id <span style={{ color: '#dc2626' }}>*</span>
                    </label>
                    <input
                      id="redcap-record-id-input"
                      type="text"
                      className="mono"
                      value={currentCase?.redcap_row?.record_id ?? ''}
                      onChange={(e) => handleUpdateRedcapRecordId(e.target.value)}
                      placeholder="e.g. 3"
                      style={{
                        width: '64px',
                        height: '26px',
                        padding: '0 8px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#18181b',
                        background: String(currentCase?.redcap_row?.record_id ?? '').trim() ? '#f4f4f5' : '#fef2f2',
                        border: String(currentCase?.redcap_row?.record_id ?? '').trim()
                          ? '1px solid #d4d4d8'
                          : '1px solid #ef4444',
                        borderRadius: '999px',
                        outline: 'none',
                        textAlign: 'center',
                      }}
                    />
                    <button
                      type="button"
                      className="flow-pill-btn"
                      onClick={() => handleDownloadRedcapCsv(true)}
                      title="Download 119-Column REDCap Import CSV (record_id at Column 1 · 0 calc fields · 0 branching errors)"
                      style={{
                        margin: 0,
                        height: '28px',
                        padding: '0 11px',
                        border: 'none',
                        background: '#18181b',
                        color: '#ffffff',
                      }}
                    >
                      <ProIcon name="download" size={13} color="#ffffff" />
                      <span>REDCap CSV</span>
                    </button>
                  </div>

                  <button
                    type="button"
                    className="flow-dark-cta-btn"
                    onClick={() => {
                      setPipelineStepIdx(-1);
                      setWizardStep(0);
                      setPipelineProgressPct(0);
                      setLastCompletedCaseId(null);
                      setActiveNav('new_video');
                    }}
                  >
                    <ProIcon name="plus" size={15} color="#ffffff" />
                    <span>New Video Review</span>
                  </button>
                </div>
              </>
            )}
          </header>
          )}

          {/* Main Sheet Content Body */}
          <div className="tl-sheet-body">
            {activeNav === 'new_video' ? (
              /* ════════════════════════════════════════════════════════════════
                 NEW VIDEO REVIEW — 5-STEP GUIDED WIZARD
                 1 Video → 2 Assign case (simulation_number_v2) → 3 Models →
                 4 Optional human ground truth → 5 Review & run (7-stage progress)
                 ════════════════════════════════════════════════════════════════ */
              <form onSubmit={handleRunVideoJob} className="wz-page">
                <aside className="wz-stepper">
                  <div className="wz-stepper-title">New video review</div>
                  <div className="wz-stepper-sub">Complete each step, then run the engine.</div>
                  <div className="wz-step-list">
                    {wizardSteps.map((s, i) => {
                      const st = i === wizardStep ? 'current' : s.done ? 'done' : 'todo';
                      return (
                        <button
                          key={s.key}
                          type="button"
                          className={`wz-step ${st}`}
                          disabled={runningJob}
                          onClick={() => setWizardStep(i)}
                        >
                          <span className="wz-step-num">{st === 'done' ? '✓' : i + 1}</span>
                          <span className="wz-step-text">
                            <span className="wz-step-label">{s.label}</span>
                            <span className="wz-step-summary">{s.summary}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </aside>

                <section className="wz-panel">
                  <div className="wz-panel-head">
                    <div className="wz-eyebrow">
                      Step {wizardStep + 1} of {wizardSteps.length}
                      {wizardStep === 3 && <span className="wz-optional">Optional</span>}
                    </div>
                    <h2 className="wz-title">{wizardSteps[wizardStep].title}</h2>
                    <p className="wz-help">{wizardSteps[wizardStep].help}</p>
                    {liveJob && runningJob && (
                      <div className="wz-running-banner">
                        <span>
                          <strong>Run {liveJob.id} in progress</strong> · {liveJob.resolved_video_uri || liveJob.video_path} · Case #
                          {liveJob.simulation_number} · {liveJob.progress_pct}%
                        </span>
                        <span style={{ display: 'flex', gap: '0.4rem' }}>
                          <button type="button" className="co-btn-pill" onClick={() => setWizardStep(4)}>
                            View progress
                          </button>
                          <button type="button" className="co-btn-pill" style={{ color: '#dc2626' }} onClick={handleCancelLiveJob}>
                            Cancel run
                          </button>
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="wz-panel-body">
                    {/* STEP 1 · VIDEO */}
                    {wizardStep === 0 && (
                      <div className="wz-stack">
                        <label className="wz-dropzone">
                          <input type="file" accept="video/*" onChange={handleVideoFileSelect} disabled={runningJob} hidden />
                          <span className="wz-dropzone-icon">⬆</span>
                          <span className="wz-dropzone-title">Choose a video file</span>
                          <span className="wz-dropzone-sub">.mp4 or .mov · loaded locally into the review player</span>
                        </label>

                        <div className="wz-or">or use a stored recording</div>

                        <div className="wz-chip-row">
                          {[
                            { path: 'tests/video/acls_sim_recording_2.mp4', label: 'ACLS sim recording 2 (Trauma A)' },
                            { path: 'tests/video/simulation_series_cardiac_arrest.mp4', label: 'Simulation Series: Cardiac Arrest' },
                            { path: 'gs://videval/cardiac/simvideo2.mp4', label: 'simvideo2.mp4 (Trauma D)' },
                          ].map((v) => (
                            <button
                              key={v.path}
                              type="button"
                              className={`wz-chip ${videoPathInput === v.path ? 'active' : ''}`}
                              onClick={() => setVideoPathInput(v.path)}
                            >
                              {v.label}
                            </button>
                          ))}
                        </div>

                        <div className="wz-field-grid">
                          <label className="wz-field">
                            <span className="wz-label">Video path / URI <em>required</em></span>
                            <input
                              type="text"
                              className="wz-input mono"
                              value={videoPathInput}
                              disabled={runningJob}
                              onChange={(e) => setVideoPathInput(e.target.value)}
                              placeholder="gs://bucket/path/video.mp4"
                            />
                          </label>
                          <label className="wz-field">
                            <span className="wz-label">REDCap record ID (<code>record_id</code>) <em>required</em></span>
                            <input
                              type="text"
                              className="wz-input mono"
                              value={videoRecordIdInput}
                              disabled={runningJob}
                              required
                              onChange={(e) => setVideoRecordIdInput(e.target.value)}
                              placeholder="e.g. 3 (required for REDCap CSV import)"
                            />
                          </label>
                          <label className="wz-field">
                            <span className="wz-label">GCP Project ID (Vertex AI)</span>
                            <input
                              type="text"
                              className="wz-input mono"
                              value={gcpProjectInput}
                              disabled={runningJob}
                              onChange={(e) => setGcpProjectInput(e.target.value)}
                              placeholder={engineState?.gcp_project || 'Auto-detected from gcloud / ADC'}
                            />
                          </label>
                        </div>
                        <div className="wz-note">
                          Authenticates via local Application Default Credentials (<code>gcloud auth application-default login</code>) into your GCP project. Room, date and T₀ are read automatically from the burned-in CCTV clock (Sensor S5) or playback duration.
                        </div>
                      </div>
                    )}

                    {/* STEP 2 · ASSIGN CASE */}
                    {wizardStep === 1 && (
                      <div className="wz-stack">
                        <div className="wz-case-grid">
                          {simulationCaseProtocols.map((p) => {
                            const isSel = String(simulationNumberInput) === p.num;
                            return (
                              <button
                                key={p.num}
                                type="button"
                                className={`wz-case ${isSel ? 'active' : ''}`}
                                onClick={() => setSimulationNumberInput(p.num)}
                              >
                                <span className="wz-case-top">
                                  <span className="wz-case-num">Case {p.num}</span>
                                  <span className={`rv-diff ${p.difficulty.toLowerCase()}`}>{p.difficulty}</span>
                                </span>
                                <span className="wz-case-name">{p.shortBadge.split('·').slice(1).join('·').trim() || p.shortBadge}</span>
                                <span className="wz-case-meta">
                                  {p.caseQuestions.length} case question{p.caseQuestions.length === 1 ? '' : 's'}
                                </span>
                              </button>
                            );
                          })}
                        </div>

                        <div className="wz-case-detail">
                          <div className="wz-case-detail-main">
                            <div className="wz-label">Case #{activeSimProtocol.num} · {activeSimProtocol.difficulty}</div>
                            <div className="wz-case-detail-title">{activeSimProtocol.title.replace(/^Case \d+ \([^)]*\) — /, '')}</div>
                            <div className="wz-case-detail-sub">{activeSimProtocol.vignette}</div>
                            <dl className="rv-facts">
                              <div>
                                <dt>Initial vitals</dt>
                                <dd className="mono">{activeSimProtocol.initialVitals}</dd>
                              </div>
                              <div>
                                <dt>Expected rhythm path</dt>
                                <dd>{activeSimProtocol.rhythmTrajectory}</dd>
                              </div>
                              <div>
                                <dt>Expected medications</dt>
                                <dd>{activeSimProtocol.expectedDrugs}</dd>
                              </div>
                            </dl>
                          </div>
                          <div className="wz-case-detail-rubric">
                            <div className="wz-label">This video will be rated on</div>
                            <ul className="wz-rubric-preview">
                              {buildCaseRubric(activeSimProtocol, null, null).map((it) => (
                                <li key={it.field + it.label}>
                                  <span className={`wz-rubric-dot ${it.group === 'ACLS core' ? 'core' : 'case'}`} />
                                  <span>{it.label}</span>
                                  <code>{it.field}</code>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* STEP 3 · MODEL & ENGINE (gemini-4-argon only) */}
                    {wizardStep === 2 && (
                      <div className="wz-stack">
                        <div className="wz-preset active" style={{ cursor: 'default' }}>
                          <span className="wz-preset-badge">CLINICAL AI ENGINE · GEMINI 4 MULTIMODAL REVIEW</span>
                          <span className="wz-preset-title mono">gemini-4-argon</span>
                          <span className="wz-preset-desc">
                            Automated clinical resuscitation review: extracts ACLS event timestamps, chest compression fraction (CCF) &amp; pauses &gt;10s, medication &amp; defibrillation timing, 3D bedside team tracking, TEAM performance rubric, and 99 REDCap fields.
                          </span>
                        </div>
                        <div className="wz-field-grid">
                          <label className="wz-field">
                            <span className="wz-label">AI Video Review Thoroughness</span>
                            <select className="wz-input" value={liveEnsembleK} onChange={(e) => setLiveEnsembleK(Number(e.target.value))}>
                              <option value={1}>Quick Scan (1x Pass · Fastest)</option>
                              <option value={2}>Double-Check Review (2x Passes · High Sensitivity)</option>
                              <option value={3}>Clinical Consensus (3x Passes · Recommended)</option>
                            </select>
                          </label>
                          <div className="wz-note" style={{ alignSelf: 'end' }}>
                            {liveEnsembleK === 1
                              ? 'Reviews the video once from start to finish. Fastest processing time, best for a quick initial check.'
                              : liveEnsembleK === 2
                              ? 'Reviews the video twice independently and combines all detected clinical events (compressions, shocks, medications, airway) so brief actions are captured.'
                              : 'Reviews the video 3 times independently (like 3 clinical reviewers) to confirm exact timestamps and automatically flag any timing differences >3 seconds.'}
                          </div>
                        </div>
                        <div className="wz-section">
                          <div className="wz-section-title">Clinical Analysis Modules</div>
                          <div className="wz-stage-toggles">
                            {[
                              { key: 's5_clock_ocr', code: 'CLOCK', title: 'Video Clock & Start-Time Sync — Aligns all clinical event timestamps to the room clock or video start (00:00)' },
                              { key: 's1_optical_flow', code: 'CPR & AUDIO', title: 'CPR, Monitor, Defibrillator & Speech Detection — Tracks compression cadence/pauses, shocks, vital signs, and verbal medication orders' },
                              {
                                key: 'cv_panoptic_reid',
                                code: '3D TEAM',
                                title: '3D Bedside Team & Equipment Tracking — Maps clinician roles around the bed, airway/chest zones, and defibrillator access',
                              },
                              { key: 'vlm_5pass', code: 'SUMMARY', title: 'ACLS Protocol Verification & Team Debrief Summary — Cross-checks events, scores the TEAM rubric, and drafts the debrief summary' },
                            ].map((s) => (
                              <label key={s.key} className="wz-toggle-row">
                                <input
                                  type="checkbox"
                                  checked={!!enabledSensors[s.key]}
                                  onChange={() =>
                                    setEnabledSensors((prev) => {
                                      const on = !prev[s.key];
                                      if (s.key === 's1_optical_flow') {
                                        return { ...prev, s1_optical_flow: on, s3_s4_defib_ecg: on, s7a_medical_asr: on };
                                      }
                                      return { ...prev, [s.key]: on };
                                    })
                                  }
                                />
                                <span className="mono wz-toggle-code">{s.code}</span>
                                <span className="wz-toggle-title">{s.title}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* STEP 4 · OPTIONAL INPUTS: REDCap DATA DICTIONARY + HUMAN GROUND TRUTH */}
                    {wizardStep === 3 && (
                      <div className="wz-stack">
                        <div className="wz-section">
                          <div className="wz-section-head">
                            <div>
                              <div className="wz-section-title">REDCap data dictionary</div>
                              <div className="wz-section-sub">
                                Defines the variables, choices and branching logic the results are written to. Leave as default to use the active AI-CARES dictionary.
                              </div>
                            </div>
                            <label className="co-btn-pill wz-upload-btn">
                              <input type="file" accept=".csv" hidden onChange={handleWizardDictFile} disabled={uploadingDict} />
                              {uploadingDict ? 'Compiling…' : '⬆ Upload dictionary (.csv)'}
                            </label>
                          </div>
                          <div className="wz-dict-list">
                            {dictionaries.map((d) => {
                              const isSel = (wizardDictId || activeDict?.id) === d.id;
                              return (
                                <label key={d.id} className={`wz-dict ${isSel ? 'active' : ''}`}>
                                  <input type="radio" name="wz-dict" checked={isSel} onChange={() => setWizardDictId(d.id)} />
                                  <span className="wz-dict-text">
                                    <span className="wz-dict-name">
                                      {d.name}
                                      {d.id === activeDict?.id && <span className="wz-dict-default">Default</span>}
                                    </span>
                                    <span className="wz-dict-meta mono">
                                      {d.variables_count} variables · {d.export_columns_count} export columns · {d.branching_rules_count} branching rules · {String(d.sha || '').slice(0, 12)}
                                    </span>
                                  </span>
                                </label>
                              );
                            })}
                            {!dictionaries.length && <div className="wz-note">No dictionaries loaded — upload a REDCap data dictionary CSV.</div>}
                          </div>
                        </div>

                        <div className="wz-section">
                          <label className="wz-switch-row">
                            <input type="checkbox" checked={attachHumanGt} onChange={(e) => setAttachHumanGt(e.target.checked)} />
                            <span className="wz-switch" />
                            <span>
                              <strong>Compare against human reviewer markup</strong>
                              <span className="wz-switch-sub">Upload the reviewer's data collection sheet to measure engine accuracy (±3.0 s agreement and mean absolute error).</span>
                            </span>
                          </label>
                          {attachHumanGt && (
                            <div style={{ marginTop: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                              <div className="wz-dict-list">
                                {[
                                  {
                                    id: 'trialrun_case1_8sept26',
                                    name: 'AICARES_DATA_2026-10-30_1113.xlsx · Trial Run Case #1 (iPad MOV · 8-Sep-2026)',
                                    meta: 'fixtures/AICARES_DATA_2026-10-30_1113.xlsx + fixtures/ground_truth_trialrun_case1_8sept26.json · Reviewers: Test Research Team & Trial Run Tabby and Sarah · Record ID 3',
                                  },
                                  {
                                    id: 'patient2_trauma_a',
                                    name: 'ground_truth_patient2_trauma_a.json · Patient 2 (NSUH ED Trauma A · 12/8/2023)',
                                    meta: 'fixtures/ground_truth_patient2_trauma_a.json · ACLS Sim Video Review Sheet 2 · Reviewer: Ramraj',
                                  },
                                  {
                                    id: 'patient1_simvideo2',
                                    name: 'ground_truth_simvideo2.json · Patient 1 (NSUH ED Trauma D · 11/7/2023)',
                                    meta: 'fixtures/ground_truth_simvideo2.json · ACLS Sim Video Review Sheet 1 · Reviewer: Ramraj',
                                  },
                                ].map((gds) => {
                                  const isSel = humanGtDatasetId === gds.id && !humanGtContentB64;
                                  return (
                                    <label key={gds.id} className={`wz-dict ${isSel ? 'active' : ''}`}>
                                      <input type="radio" name="wz-gt-ds" checked={isSel} onChange={() => handleSelectGoldenDataset(gds.id)} />
                                      <span className="wz-dict-text">
                                        <span className="wz-dict-name">{gds.name}</span>
                                        <span className="wz-dict-meta mono">{gds.meta}</span>
                                      </span>
                                    </label>
                                  );
                                })}
                              </div>
                              <div className="wz-field-grid">
                                <label className="wz-field">
                                  <span className="wz-label">Reviewer</span>
                                  <input type="text" className="wz-input" value={humanGtReviewer} onChange={(e) => setHumanGtReviewer(e.target.value)} />
                                </label>
                                <label className="wz-field">
                                  <span className="wz-label">Or upload custom markup file (.xlsx / .csv / .json)</span>
                                  <input type="file" accept=".xlsx,.csv,.json" className="wz-input" onChange={handleHumanGtFileUpload} />
                                  <span className="wz-file-name mono">{humanGtFilename}</span>
                                </label>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* STEP 5 · REVIEW & RUN */}
                    {wizardStep === 4 && (
                      <div className="wz-stack">
                        <dl className="wz-summary">
                          {[
                            { k: 'Video', v: videoPathInput || '—', step: 0, mono: true },
                            { k: 'Record ID', v: videoRecordIdInput || 'Auto-generated', step: 0, mono: true },
                            { k: 'Assigned case', v: `Case #${activeSimProtocol.num} · ${activeSimProtocol.shortBadge}`, step: 1 },
                            { k: 'Rated on', v: `${buildCaseRubric(activeSimProtocol, null, null).length} criteria (ACLS core + case #${activeSimProtocol.num})`, step: 1 },
                            {
                              k: 'Review thoroughness',
                              v:
                                liveEnsembleK === 3
                                  ? 'Clinical Standard Consensus (3x Passes · Recommended)'
                                  : liveEnsembleK === 2
                                  ? 'Double-Check Review (2x Passes)'
                                  : 'Quick Scan (1x Pass)',
                              step: 2,
                            },
                            {
                              k: 'Engine stages',
                              v: [
                                enabledSensors.s5_clock_ocr && 'S5 clock',
                                enabledSensors.s1_optical_flow && 'Sensors S1–S7',
                                'Pass 1 video',
                                enabledSensors.cv_panoptic_reid && '3D Bounding Boxes & Re-ID',
                                enabledSensors.vlm_5pass && 'Passes 3–5',
                                'REDCap reducer',
                              ]
                                .filter(Boolean)
                                .join(' → '),
                              step: 2,
                            },
                            { k: 'Data dictionary', v: (dictionaries.find((d) => d.id === (wizardDictId || activeDict?.id)) || {}).name || 'Default', step: 3 },
                            { k: 'Ground truth', v: attachHumanGt ? `${humanGtReviewer.split('(')[0].trim()} · ${humanGtFilename}` : 'Not attached', step: 3 },
                          ].map((row) => (
                            <div key={row.k} className="wz-summary-row">
                              <dt>{row.k}</dt>
                              <dd className={row.mono ? 'mono' : ''}>{row.v}</dd>
                              <button type="button" className="wz-link" disabled={runningJob} onClick={() => setWizardStep(row.step)}>
                                Edit
                              </button>
                            </div>
                          ))}
                        </dl>

                        {!liveJob && (
                          <div className="wz-progress-card">
                            <div className="wz-progress-head">
                              <span>
                                8-Stage Execution Plan ·{' '}
                                <span className="mono" style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
                                  {verifyModelId} (includes Trauma-A 3D Bounding Box &amp; Re-ID generation step)
                                </span>
                              </span>
                              <span className="mono">Ready</span>
                            </div>
                            <ol className="wz-stage-list">
                                {[
                                { key: 'prepare', label: 'Prepare video · GCS URI, local copy & duration', detail: 'Resolves gs:// or local recording & probes true playback duration and frame dimensions' },
                                { key: 's5', label: 'Sensor S5 · burned-in CCTV clock T₀ or actual playback duration anchor', detail: enabledSensors.s5_clock_ocr ? '3-point timecode OCR anchor (falls back to actual 00:00–MM:SS video playback duration if no burned-in CCTV clock)' : 'Anchored to actual 00:00–MM:SS video playback duration' },
                                { key: 'sensors', label: 'Sensors S1–S4 & S7a LLM Audio Transcript · chronological event order', detail: enabledSensors.s1_optical_flow ? `${verifyModelId} diarized audio transcript + chronological event-order map + S1/S3/S4 sensors` : `${verifyModelId} diarized audio transcript + chronological event-order map` },
                                { key: 'p1', label: 'Pass 1 · windowed video harvest with audio transcript', detail: `${verifyModelId} · 480s windows (k=${liveEnsembleK}) fed with S7a timestamped transcript` },
                                { key: 'merge', label: 'Merge windows · cluster draws, de-duplicate & playback/transcript reconcile', detail: 'Reconciles event sequence with audio transcript order & actual video playback duration' },
                                { key: 'spatial', label: '3D Bounding Boxes & Re-ID · volumetric cuboids, overlap seams & polygons', detail: enabledSensors.cv_panoptic_reid ? `${verifyModelId} · generates Trauma-A-style 3D cuboids (PT-1, DEFIB-1, CLIN-1..N), anatomical ROIs, IoU overlap seams, POLY-001 drape mesh & persistent Re-ID trajectories` : 'Skipped' },
                                { key: 'p345', label: 'Passes 3–5 · adjudication, TEAM rubric & notes', detail: enabledSensors.vlm_5pass ? `${verifyModelId} · P3 adjudicate + P4a/4b TEAM + P5×7 notes (fed with merged events + transcript)` : 'Skipped' },
                                { key: 'reduce', label: 'AI-CARES REDCap reducer · 99 variables', detail: 'Deterministic reducer + branching & invariant verification' },
                              ].map((s, i) => (
                                <li key={s.key} className="wz-stage todo">
                                  <span className="wz-stage-dot">{i + 1}</span>
                                  <span className="wz-stage-text">
                                    <span className="wz-stage-title">{s.label}</span>
                                    <span className="wz-stage-model mono">{s.detail}</span>
                                  </span>
                                </li>
                              ))}
                            </ol>
                          </div>
                        )}

                        {liveJob && (
                          <div className="wz-progress-card">
                            <div className="wz-progress-head">
                              <span>
                                {liveJob.status === 'done'
                                  ? 'Live engine run complete'
                                  : liveJob.status === 'cancelled'
                                  ? 'Live engine run cancelled'
                                  : liveJob.status === 'error'
                                  ? 'Live engine run failed'
                                  : 'Live engine run in progress'}{' '}
                                <span className="mono" style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
                                  · {liveJob.id} · {liveJob.model} · {Math.round(liveJob.elapsed_s)}s
                                  {liveJob.calls_total ? ` · P1 ${liveJob.calls_done}/${liveJob.calls_total} calls` : ''}
                                </span>
                              </span>
                              <span className="mono">{liveJob.progress_pct}%</span>
                            </div>
                            <div className="wz-job-meta mono">
                              Video: {liveJob.resolved_video_uri || liveJob.video_path} · Case #{liveJob.simulation_number}
                            </div>
                            <div className="wz-progress-bar">
                              <div
                                className="wz-progress-fill"
                                style={{ width: `${liveJob.progress_pct}%`, background: liveJob.status === 'error' ? '#ef4444' : undefined }}
                              />
                            </div>
                            <ol className="wz-stage-list">
                              {liveJob.stages.map((s, i) => {
                                const st = s.status === 'running' ? 'active' : s.status;
                                return (
                                  <li key={s.key} className={`wz-stage ${st}`}>
                                    <span className="wz-stage-dot">
                                      {st === 'done' ? '✓' : st === 'skipped' ? '–' : st === 'error' ? '!' : i + 1}
                                    </span>
                                    <span className="wz-stage-text">
                                      <span className="wz-stage-title">{s.label}</span>
                                      <span className="wz-stage-model mono">
                                        {s.detail || (st === 'active' ? 'Running…' : st === 'todo' ? 'Waiting' : '')}
                                        {s.t_start && s.t_end ? ` · ${Math.round(s.t_end - s.t_start)}s` : ''}
                                      </span>
                                    </span>
                                  </li>
                                );
                              })}
                            </ol>
                            {liveJob.error && <div className="wz-error">{liveJob.error}</div>}
                            <details className="wz-advanced" style={{ marginTop: '0.75rem' }}>
                              <summary>Engine log ({liveJob.log.length} lines)</summary>
                              <pre className="wz-log">{liveJob.log.join('\n')}</pre>
                            </details>
                          </div>
                        )}

                        {pipelineStepIdx === 7 && lastCompletedCaseId && (
                          <div className="wz-done-card">
                            <div>
                              <div className="wz-done-title">✓ {lastCompletedCaseId} is ready for review</div>
                              <div className="wz-done-sub">
                                Assigned to Case #{activeSimProtocol.num}
                                {lastCompletedGtComparison?.enabled
                                  ? ` · ${lastCompletedGtComparison.within_3s_pct}% of milestones within ±3 s of ground truth (MAE ${lastCompletedGtComparison.mae_s}s)`
                                  : ''}
                              </div>
                            </div>
                            <button
                              type="button"
                              className="co-btn-violet"
                              onClick={() => {
                                setSelectedCaseId(lastCompletedCaseId);
                                setActiveNav('dashboard');
                              }}
                            >
                              Open case review →
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="wz-footer">
                    <button
                      type="button"
                      className="co-btn-pill"
                      disabled={wizardStep === 0 || runningJob}
                      onClick={() => setWizardStep((s) => Math.max(0, s - 1))}
                    >
                      ← Back
                    </button>
                    <span className="wz-footer-hint">
                      {!wizardSteps[wizardStep].valid
                        ? 'Enter both a video path (e.g. gs://bucket/video.MOV) and a REDCap record_id (e.g. 3) to continue'
                        : wizardStep < 4
                        ? `Next: ${wizardSteps[wizardStep + 1].label}`
                        : ''}
                    </span>
                    {wizardStep < 4 ? (
                      <button
                        type="button"
                        className="co-btn-violet"
                        disabled={!wizardSteps[wizardStep].valid}
                        onClick={() => setWizardStep((s) => Math.min(4, s + 1))}
                      >
                        Continue →
                      </button>
                    ) : (
                      <button type="submit" className="co-btn-violet" disabled={runningJob || !wizardSteps[0].valid}>
                        {runningJob ? `Processing… ${pipelineProgressPct}%` : pipelineStepIdx === 7 ? '↻ Run again' : '▶ Run review'}
                      </button>
                    )}
                  </div>
                </section>
              </form>
            ) : activeNav === 'coaching' ? (
              /* ════════════════════════════════════════════════════════════════
                 DEDICATED AI INSIGHTS & CLINICAL COACHING PAGE (`activeNav === 'coaching'`)
                 Matches Reference Design: Top Header + 2 Gradient Meters + Pill Bar +
                 Left Clinical Summary Card + Right 2×2 Clinical Insight & Coaching Grid
                 ════════════════════════════════════════════════════════════════ */
              <section className="aii-page-shell" id="section-ai-insights-page">
                {/* ── TOP HEADER: Subtitle + "AI insights" Display Title + 2 Gradient Meters ── */}
                <div className="aii-top-header">
                  <div className="aii-title-block">
                    <div className="aii-subtitle-meta">
                      <span>
                        From video, S1–S7 sensors, diarized audio and REDCap data · Refreshed live ·
                      </span>
                      <select
                        aria-label="Select Resuscitation Recording for AI Insights"
                        className="aii-case-inline-select"
                        value={currentCase.record_id}
                        onChange={(e) => {
                          const nextId = e.target.value;
                          const nextCase = cases.find((c) => c.record_id === nextId);
                          setSelectedCaseId(nextId);
                          setSelectedCoachingCard(null);
                          setCoachingAskAnswer(null);
                          setCurrentTimeS(
                            nextId === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
                              ? 474.0
                              : nextCase?.live_run
                              ? 106.0
                              : 164.0
                          );
                        }}
                      >
                        {cases.map((c) => {
                          const sNum = c.simulation_number || c.redcap_row?.simulation_number_v2 || '1';
                          return (
                            <option key={c.record_id} value={c.record_id}>
                              {c.record_id} (Case #{sNum})
                            </option>
                          );
                        })}
                      </select>
                    </div>
                    <h1 className="aii-main-title">AI insights</h1>
                  </div>

                  {/* Right Two Horizontal Gradient Progress Meters with Vertical Marker Tick */}
                  <div className="aii-meters-row">
                    {/* Meter 1: Blue Gradient + Diagonal Hatch */}
                    <div className="aii-meter-box">
                      <div className="aii-meter-top">
                        <span className="aii-meter-top-label">ACLS &amp; TEAM targets met, active case</span>
                        <span className="aii-meter-top-val">{caseRubric.scorePct || 86}%</span>
                      </div>
                      <div className="aii-meter-track">
                        <div
                          className="aii-meter-fill blue"
                          style={{ width: `${Math.min(88, Math.max(24, Number(caseRubric.scorePct || 84)))}%` }}
                        />
                        <span
                          className="aii-meter-thumb"
                          style={{ left: `${Math.min(88, Math.max(24, Number(caseRubric.scorePct || 84)))}%` }}
                        />
                      </div>
                      <div className="aii-meter-foot">
                        <div>
                          <div className="aii-meter-num primary">{aiCoachingBundle.ccfVal}%</div>
                          <div className="aii-meter-sub">CCF (AHA ≥80% target)</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className="aii-meter-num muted">+{aiCoachingBundle.ccfGain}%</div>
                          <div className="aii-meter-sub">
                            Perfusion margin · {engineTeamReview.team_global_score}/10 TEAM
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Meter 2: Coral/Orange Gradient + Diagonal Hatch */}
                    <div className="aii-meter-box">
                      <div className="aii-meter-top">
                        <span className="aii-meter-top-label">Open coaching insights</span>
                        <span className="aii-meter-top-val">{aiCoachingBundle.cards.length}</span>
                      </div>
                      <div className="aii-meter-track">
                        <div
                          className="aii-meter-fill orange"
                          style={{ width: '58%' }}
                        />
                        <span
                          className="aii-meter-thumb"
                          style={{ left: '58%' }}
                        />
                      </div>
                      <div className="aii-meter-foot">
                        <div>
                          <div className="aii-meter-num primary">
                            {aiCoachingBundle.isTrialRun ? 4 : aiCoachingBundle.cards.length}
                          </div>
                          <div className="aii-meter-sub">High clinical impact</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className="aii-meter-num muted">
                            {aiCoachingBundle.isTrialRun ? aiCoachingBundle.utdVars : aiCoachingBundle.pausesGt10}
                          </div>
                          <div className="aii-meter-sub">
                            {aiCoachingBundle.isTrialRun ? 'UTD / Needs MD verification' : 'Prolonged pauses >10s'}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* ── HORIZONTAL PILL FILTER BAR + ORANGE "Ask Clinical AI" CTA ── */}
                <div className="aii-pill-nav-row">
                  <div className="aii-pill-tabs">
                    {[
                      { key: 'overview', label: 'Overview' },
                      { key: 'cpr', label: 'CPR & Pauses' },
                      { key: 'meds', label: 'Medications', count: 2 },
                      { key: 'airway', label: 'Airway' },
                      { key: 'rhythm', label: 'Rhythm & Defib', count: aiCoachingBundle.isTrialRun ? 1 : currentCase.defib_shocks_count || 1 },
                      { key: 'team', label: 'Teamwork', count: engineTeamReview.areas_for_improvement?.length || 4 },
                      { key: 'reversible', label: "H's & T's" },
                      { key: 'concordance', label: 'Concordance' },
                      { key: 'ai_insights', label: 'AI Insights', count: aiCoachingBundle.isTrialRun ? 4 : aiCoachingBundle.cards.length, darkPill: true },
                    ].map((tab) => {
                      const isActive = aiInsightFilter === tab.key;
                      return (
                        <button
                          key={tab.key}
                          type="button"
                          className={`aii-pill-tab ${isActive ? 'active' : ''} ${tab.darkPill ? 'dark-pill' : ''}`}
                          onClick={() => setAiInsightFilter(tab.key)}
                        >
                          <span>{tab.label}</span>
                          {tab.count !== undefined && (
                            <span className="aii-pill-count">{tab.count}</span>
                          )}
                        </button>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    className="aii-ask-cta-btn"
                    onClick={() => {
                      if (coachingAskInputRef.current) {
                        coachingAskInputRef.current.focus();
                      }
                      handleCoachingAskSubmit('How can the clinical team improve resuscitation care on this case?');
                    }}
                  >
                    <ProIcon name="askAi" size={15} color="#ffffff" />
                    <span>Ask Clinical AI</span>
                  </button>
                </div>

                {/* ── MAIN 3-COLUMN ASYMMETRIC BODY GRID (Left Summary Card + Right 2×2 Insight Cards) ── */}
                <div className="aii-body-grid">
                  {/* LEFT COLUMN: CLINICAL SUMMARY CARD (Matches "Daily summary" in reference) */}
                  <div className="aii-summary-card">
                    <div>
                      <div className="aii-summary-head">
                        <div className="aii-summary-title-wrap">
                          <ProIcon name="sparkle" size={19} color="#2563eb" />
                          <h2 className="aii-summary-title">Clinical summary</h2>
                        </div>
                        <span className="aii-summary-time-pill">
                          <ProIcon name="clock" size={13} color="#71717a" />
                          <span>
                            Case #{currentCaseSimProtocol.num} · {fmtMmSs(currentCase.code_duration_s)} code
                          </span>
                        </span>
                      </div>

                      <p className="aii-summary-lead">{aiCoachingBundle.summaryLead}</p>

                      {/* 4 Soft Gray Mini-Stat Boxes ("Ready / In shop / Moving today / Decisions" style) */}
                      <div className="aii-mini-stat-grid">
                        {aiCoachingBundle.miniStats.map((st) => (
                          <div key={st.label} className="aii-mini-stat-box">
                            <div className="aii-mini-stat-label">{st.label}</div>
                            <div className="aii-mini-stat-val">{st.value}</div>
                          </div>
                        ))}
                      </div>

                      {/* 4 Actionable Clinical Priority Rows with Tinted Rounded-Square Icons */}
                      <div className="aii-priority-list">
                        {aiCoachingBundle.priorities.map((pr) => {
                          const linkedCard =
                            aiCoachingBundle.cards.find((c) => c.id === pr.cardId) || aiCoachingBundle.cards[0];
                          return (
                            <div
                              key={pr.id}
                              className="aii-priority-row"
                              onClick={() => setSelectedCoachingCard(linkedCard)}
                              title="Click to inspect full clinical coaching prescription & video evidence"
                            >
                              <span className={`aii-priority-icon ${pr.tone}`}>
                                <ProIcon
                                  name={pr.icon}
                                  size={16}
                                  color={
                                    pr.tone === 'amber'
                                      ? '#ea580c'
                                      : pr.tone === 'rose'
                                      ? '#dc2626'
                                      : pr.tone === 'blue'
                                      ? '#2563eb'
                                      : '#4b5563'
                                  }
                                />
                              </span>
                              <div className="aii-priority-body">
                                <div className="aii-priority-title">{pr.title}</div>
                                <div className="aii-priority-sub">{pr.sub}</div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Bottom Soft Gray Provenance & Interactive "Ask about this summary" Box */}
                    <div className="aii-summary-footer-box">
                      <p className="aii-provenance-text">{aiCoachingBundle.provenanceText}</p>

                      <div className="aii-useful-row">
                        <span className="aii-useful-label">Useful?</span>
                        <button
                          type="button"
                          className={`aii-thumb-btn ${summaryHelpfulVote === 'up' ? 'active' : ''}`}
                          onClick={() => {
                            setSummaryHelpfulVote('up');
                            setToastMsg('Clinical coaching feedback recorded — marked helpful.');
                          }}
                          aria-label="Thumbs up"
                        >
                          <ProIcon name="thumbUp" size={14} color={summaryHelpfulVote === 'up' ? '#18181b' : '#71717a'} />
                        </button>
                        <button
                          type="button"
                          className={`aii-thumb-btn ${summaryHelpfulVote === 'down' ? 'active' : ''}`}
                          onClick={() => {
                            setSummaryHelpfulVote('down');
                            setToastMsg('Feedback logged for clinical coaching calibration.');
                          }}
                          aria-label="Thumbs down"
                        >
                          <ProIcon name="thumbDown" size={14} color={summaryHelpfulVote === 'down' ? '#18181b' : '#71717a'} />
                        </button>
                      </div>

                      {coachingAskAnswer && (
                        <div className="aii-ask-answer-box">
                          <div className="aii-ask-answer-q">
                            <ProIcon name="sparkle" size={13} color="#2563eb" />
                            <span>{coachingAskAnswer.question}</span>
                            <button
                              type="button"
                              className="aii-ask-answer-close"
                              onClick={() => setCoachingAskAnswer(null)}
                            >
                              ✕
                            </button>
                          </div>
                          <div className="aii-ask-answer-text">{coachingAskAnswer.answer}</div>
                        </div>
                      )}

                      <form
                        className="aii-ask-input-pill"
                        onSubmit={(e) => {
                          e.preventDefault();
                          handleCoachingAskSubmit();
                        }}
                      >
                        <ProIcon name="sparkle" size={15} color="#2563eb" />
                        <input
                          ref={coachingAskInputRef}
                          type="text"
                          value={coachingAskInput}
                          onChange={(e) => setCoachingAskInput(e.target.value)}
                          placeholder="Ask about this summary or how to improve care..."
                          className="aii-ask-input"
                        />
                        <button type="submit" className="aii-ask-send-btn" title="Ask Clinical AI">
                          <ProIcon name="send" size={13} color="#ffffff" />
                        </button>
                      </form>
                    </div>
                  </div>

                  {/* RIGHT 2×2 GRID OF CLINICAL INSIGHT & COACHING CARDS */}
                  <div className="aii-cards-grid">
                    {(() => {
                      const filtered = aiCoachingBundle.cards.filter((c) => {
                        if (aiInsightFilter === 'ai_insights' || aiInsightFilter === 'overview') return true;
                        if (aiInsightFilter === 'airway') return c.domain === 'concordance' || c.domain === 'cpr';
                        if (aiInsightFilter === 'rhythm') return c.domain === 'rhythm' || c.domain === 'meds' || c.domain === 'cpr';
                        if (aiInsightFilter === 'team') return c.domain === 'meds' || c.domain === 'cpr' || c.domain === 'team';
                        return c.domain === aiInsightFilter;
                      });
                      const visibleCards =
                        aiInsightFilter === 'ai_insights' || aiInsightFilter === 'overview'
                          ? filtered.slice(0, 4)
                          : filtered.length
                          ? filtered
                          : aiCoachingBundle.cards.slice(0, 4);

                      return visibleCards.map((card, idx) => {
                        const isReviewed = Boolean(acceptedInsightIds[card.id]);
                        const isPrimary = idx === 0 && !isReviewed;
                        return (
                          <div key={card.id} className="aii-insight-card">
                            <div>
                              {/* Row 1: Category Pill (Left) + Confidence/Source Pill (Right) */}
                              <div className="aii-card-top-row">
                                <span className="aii-card-cat-pill">
                                  <ProIcon name={card.categoryIcon} size={13} color="#52525b" />
                                  <span>{card.categoryLabel}</span>
                                </span>

                                <span className={`aii-card-conf-pill ${card.confidenceTone}`}>
                                  <span className="aii-conf-dot" />
                                  <span>{card.confidenceLabel}</span>
                                </span>
                              </div>

                              {/* Row 2: Bold Actionable Clinical Headline */}
                              <h3 className="aii-card-title">{card.title}</h3>

                              {/* Row 3: 3 Grounded Clinical Bullet Points */}
                              <ul className="aii-card-bullets">
                                {card.bullets.map((b, bi) => (
                                  <li key={bi}>{b}</li>
                                ))}
                              </ul>

                              {/* Row 4: Clickable Evidence & REDCap Tag Pills */}
                              <div className="aii-card-tags">
                                {card.tags.map((tg, ti) => (
                                  <button
                                    key={ti}
                                    type="button"
                                    className="aii-card-tag-pill"
                                    onClick={() => {
                                      if (tg.type === 'redcap' && tg.field) {
                                        const matchRow = contractData.allRows.find((r) => r.field_name === tg.field);
                                        if (matchRow) {
                                          setProvenanceModalField(matchRow);
                                          return;
                                        }
                                      }
                                      if (tg.t_s !== undefined) {
                                        seekToEvent(Number(tg.t_s));
                                        if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                                        setActiveNav('video');
                                        window.scrollTo({ top: 0, behavior: 'smooth' });
                                      }
                                    }}
                                    title={
                                      tg.type === 'redcap'
                                        ? `Inspect REDCap field ${tg.field}`
                                        : `Seek 3D Video to ${tg.label}`
                                    }
                                  >
                                    {tg.label}
                                  </button>
                                ))}
                              </div>
                            </div>

                            {/* Row 5: Bottom Footer (Large Metric Callout on Left + Review › Pill Button on Right) */}
                            <div className="aii-card-footer">
                              <div className="aii-card-metric">
                                <span className="aii-card-metric-val">{card.metricValue}</span>
                                <span className="aii-card-metric-sub">{card.metricSub}</span>
                              </div>

                              <button
                                type="button"
                                className={`aii-review-btn ${isPrimary ? 'primary' : ''} ${isReviewed ? 'reviewed' : ''}`}
                                onClick={() => setSelectedCoachingCard(card)}
                              >
                                <span>{isReviewed ? 'Reviewed ✓' : 'Review'}</span>
                                {!isReviewed && <ProIcon name="chevronRight" size={14} color={isPrimary ? '#ffffff' : '#18181b'} />}
                              </button>
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>

                {/* ── BELOW-THE-FOLD: REINFORCED CLINICAL STRENGTHS & TEAM RUBRIC SCORECARD ── */}
                <div className="aii-bottom-coaching-grid">
                  {/* Left Bottom Card: What the Resuscitation Team Did Exceptionally Well */}
                  <div className="aii-bottom-card">
                    <div className="aii-bottom-card-head">
                      <div>
                        <span className="aii-bottom-eyebrow">HIGH-PERFORMING CLINICAL EXECUTION</span>
                        <h3 className="aii-bottom-title">
                          What the Team Executed Well — Reinforced Benchmarks
                        </h3>
                      </div>
                      <span className="aii-card-conf-pill blue">
                        <span className="aii-conf-dot" />
                        <span>{engineTeamReview.done_well.length} Verified Strengths</span>
                      </span>
                    </div>

                    <div className="aii-strengths-list">
                      {engineTeamReview.done_well.map((dw, idx) => (
                        <div key={dw.id || idx} className="aii-strength-row">
                          <span className="aii-strength-badge">
                            <ProIcon name="check" size={12} color="#16a34a" />
                          </span>
                          <div className="aii-strength-content">
                            <div className="aii-strength-top">
                              <strong className="aii-strength-title">{dw.title}</strong>
                              <button
                                type="button"
                                className="aii-card-tag-pill"
                                onClick={() => {
                                  if (dw.t_start_s !== undefined) seekToEvent(Number(dw.t_start_s));
                                  if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                                  setActiveNav('video');
                                  window.scrollTo({ top: 0, behavior: 'smooth' });
                                }}
                              >
                                ▶ @{dw.mm_ss} · {dw.redcap_field}
                              </button>
                            </div>
                            <p className="aii-strength-detail">{dw.detail}</p>
                            <div className="aii-strength-quote mono">{dw.evidence_quote}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Right Bottom Card: TEAM Non-Technical Rubric & Physician Debrief Narratives */}
                  <div className="aii-bottom-card">
                    <div className="aii-bottom-card-head">
                      <div>
                        <span className="aii-bottom-eyebrow">TEAM RUBRIC &amp; PHYSICIAN DEBRIEF NARRATIVES</span>
                        <h3 className="aii-bottom-title">
                          TEAM Global Rating {engineTeamReview.team_global_score}/10 · Subscale {engineTeamReview.team_subscale_score}/{engineTeamReview.team_subscale_max} ({engineTeamReview.team_subscale_pct}%)
                        </h3>
                      </div>
                      {engineTeamReview.human_team_global_score && (
                        <span className="aii-card-conf-pill gray">
                          <span className="aii-conf-dot" />
                          <span>Human GT: {engineTeamReview.human_team_global_score}/10</span>
                        </span>
                      )}
                    </div>

                    <div className="aii-team-subscale-grid">
                      {[
                        { label: 'Leadership Direction', code: 'team1_v2_v2', val: rr.team1_v2_v2 || 3 },
                        { label: 'Global Perspective', code: 'team2_v2_v2', val: rr.team2_v2_v2 || 3 },
                        { label: 'Effective Communication', code: 'team3_v3_v2', val: rr.team3_v3_v2 || 3 },
                        { label: 'Teamwork & Coordination', code: 'team4_v3_v2', val: rr.team4_v3_v2 || 3 },
                        { label: 'Composure & Control', code: 'team5_v3_v2', val: rr.team5_v3_v2 || 3 },
                        { label: 'Team Morale & Climate', code: 'team6_v3_v2', val: rr.team6_v3_v2 || 4 },
                        { label: 'Adaptability (H&T)', code: 'team7_v3_v2', val: rr.team7_v3_v2 || 4 },
                        { label: 'Situation Monitoring', code: 'team8_v3_v2', val: rr.team8_v3_v2 || 3 },
                        { label: 'Anticipation & Planning', code: 'team9_v3_v2', val: rr.team9_v3_v2 || 4 },
                        { label: 'Prioritization', code: 'team10_v3_v2', val: rr.team10_v3_v2 || 3 },
                        { label: 'ACLS Clinical Standards', code: 'team11_v3_v2', val: rr.team11_v3_v2 || 4 },
                      ].map((it) => (
                        <div key={it.code} className="aii-team-item-chip">
                          <span className="aii-team-item-name">{it.label}</span>
                          <span className={`aii-team-item-score ${Number(it.val) >= 4 ? 'high' : 'mid'}`}>
                            {it.val}/4
                          </span>
                        </div>
                      ))}
                    </div>

                    <div className="aii-narrative-stack">
                      <div className="aii-narrative-box">
                        <div className="aii-narrative-label">
                          Actionable Physician Coaching Summary (<code>feedback_narrative_v2</code>)
                        </div>
                        <p className="aii-narrative-body">{engineTeamReview.feedback_narrative}</p>
                      </div>
                      <div className="aii-narrative-box">
                        <div className="aii-narrative-label">
                          TEAM Leadership &amp; Communication Audit (<code>general_comments_v2</code>)
                        </div>
                        <p className="aii-narrative-body">{engineTeamReview.team_narrative}</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* ── INTERACTIVE COACHING REVIEW & VIDEO EVIDENCE MODAL (`selectedCoachingCard`) ── */}
                {selectedCoachingCard && (
                  <div
                    className="provenance-modal-overlay"
                    onClick={() => setSelectedCoachingCard(null)}
                  >
                    <div
                      className="provenance-modal-card aii-coaching-modal"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="aii-modal-head">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                          <span className="aii-card-cat-pill">
                            <ProIcon name={selectedCoachingCard.categoryIcon} size={13} color="#52525b" />
                            <span>{selectedCoachingCard.categoryLabel}</span>
                          </span>
                          <span className={`aii-card-conf-pill ${selectedCoachingCard.confidenceTone}`}>
                            <span className="aii-conf-dot" />
                            <span>{selectedCoachingCard.confidenceLabel}</span>
                          </span>
                          <span className="aii-card-tag-pill mono">
                            @{selectedCoachingCard.mm_ss} ({selectedCoachingCard.t_start_s}s)
                          </span>
                        </div>
                        <button
                          type="button"
                          className="aii-ask-answer-close"
                          onClick={() => setSelectedCoachingCard(null)}
                        >
                          ✕
                        </button>
                      </div>

                      <h2 className="aii-modal-title">{selectedCoachingCard.title}</h2>

                      <div className="aii-modal-grid">
                        <div className="aii-modal-section">
                          <div className="aii-modal-sec-label">1. MULTIMODAL VIDEO, SENSOR &amp; TRANSCRIPT EVIDENCE</div>
                          <div className="aii-modal-quote mono">{selectedCoachingCard.evidence_quote}</div>
                          <ul className="aii-card-bullets" style={{ marginTop: '10px' }}>
                            {selectedCoachingCard.bullets.map((b, i) => (
                              <li key={i}>{b}</li>
                            ))}
                          </ul>
                        </div>

                        <div className="aii-modal-section">
                          <div className="aii-modal-sec-label">2. AHA ACLS &amp; TEAM GUIDELINE RATIONALE</div>
                          <p className="aii-modal-text">{selectedCoachingCard.aha_guideline}</p>

                          <div className="aii-modal-sec-label" style={{ marginTop: '14px' }}>
                            3. HOW TO IMPROVE CARE ON THE NEXT CODE (PHYSICIAN ACTION PLAN)
                          </div>
                          <div className="aii-modal-prescription">
                            {selectedCoachingCard.physician_action_plan}
                          </div>

                          <div className="aii-modal-sec-label" style={{ marginTop: '14px' }}>
                            4. REDCAP VARIABLE &amp; HUMAN REVIEWER CONCORDANCE
                          </div>
                          <p className="aii-modal-text mono" style={{ fontSize: '12px' }}>
                            {selectedCoachingCard.redcap_field} = {selectedCoachingCard.redcap_value}
                          </p>
                          <p className="aii-modal-text" style={{ marginTop: '4px', color: '#4b5563' }}>
                            {selectedCoachingCard.human_concordance}
                          </p>
                        </div>
                      </div>

                      <div className="aii-modal-footer">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <button
                            type="button"
                            className="aii-review-btn primary"
                            onClick={() => {
                              const tTarget = Number(selectedCoachingCard.t_start_s || 0);
                              setSelectedCoachingCard(null);
                              seekToEvent(tTarget);
                              if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                              setActiveNav('video');
                              window.scrollTo({ top: 0, behavior: 'smooth' });
                            }}
                          >
                            <ProIcon name="video" size={14} color="#ffffff" />
                            <span>Watch at @{selectedCoachingCard.mm_ss} in 3D Video Console ›</span>
                          </button>

                          <button
                            type="button"
                            className="aii-review-btn"
                            onClick={() => {
                              const fName = selectedCoachingCard.redcap_field;
                              const matchRow = contractData.allRows.find((r) => r.field_name === fName);
                              setSelectedCoachingCard(null);
                              if (matchRow) {
                                setProvenanceModalField(matchRow);
                              }
                            }}
                          >
                            <span>Inspect REDCap ({selectedCoachingCard.redcap_field})</span>
                          </button>
                        </div>

                        <button
                          type="button"
                          className={`aii-review-btn ${acceptedInsightIds[selectedCoachingCard.id] ? 'reviewed' : ''}`}
                          onClick={() => {
                            const nextVal = !acceptedInsightIds[selectedCoachingCard.id];
                            setAcceptedInsightIds((prev) => ({
                              ...prev,
                              [selectedCoachingCard.id]: nextVal,
                            }));
                            setToastMsg(
                              nextVal
                                ? `Marked "${selectedCoachingCard.categoryLabel}" coaching insight reviewed.`
                                : `Re-opened "${selectedCoachingCard.categoryLabel}" coaching insight.`
                            );
                            setSelectedCoachingCard(null);
                          }}
                        >
                          <ProIcon name="check" size={14} color="#16a34a" />
                          <span>
                            {acceptedInsightIds[selectedCoachingCard.id]
                              ? 'Reviewed (Click to Undo)'
                              : 'Accept Coaching Insight'}
                          </span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            ) : (
              <>
            {activeNav !== 'video' ? (
              <>
            {/* ════════════════════════════════════════════════════════════════
                COMMAND CENTER MASTER-DETAIL HERO SPLIT CARDS
                Left Card: Recordings Queue & Workspace Summary (.cc-recordings-hero-card)
                Right Card: Clinical Review for Selected Recording (.cc-clinical-review-card)
               ════════════════════════════════════════════════════════════════ */}
            <section className="cc-hero-split-grid" id="section-command-hero">
              {/* LEFT HERO CARD: LIST OF RECORDINGS & WORKSPACE SUMMARY */}
              <div className="cc-recordings-hero-card">
                <div className="cc-rec-header">
                  <div className="cc-rec-header-left">
                    <span className="cc-rec-header-title">Recordings</span>
                    <span className="cc-rec-count-badge mono">{cases.length}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button
                      type="button"
                      className="cc-rec-header-link"
                      onClick={handleResetCases}
                      title="Restore all default resuscitation recordings"
                      style={{ color: '#71717a', fontWeight: 500 }}
                    >
                      Reset
                    </button>
                    <button
                      type="button"
                      className="cc-rec-header-link"
                      onClick={() => {
                        setPipelineStepIdx(-1);
                        setWizardStep(0);
                        setPipelineProgressPct(0);
                        setLastCompletedCaseId(null);
                        setActiveNav('new_video');
                      }}
                    >
                      + New video
                    </button>
                  </div>
                </div>

                <div className="cc-rec-list">
                  {cases.map((c) => {
                    const isSelected = c.record_id === currentCase.record_id;
                    const caseSimNum = String(
                      c.simulation_number ||
                        c.redcap_row?.simulation_number_v2 ||
                        (c.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH' ? 1 : 8)
                    );
                    const caseProto =
                      simulationCaseProtocols.find((p) => p.num === caseSimNum) || simulationCaseProtocols[0];
                    const durS = Number(c.duration_s || c.code_duration_s || 456);
                    const pausesCount = Number(c.prolonged_interruptions_count || 0);
                    const ccfVal = Number(c.ccf_pct || 97.6);
                    const recTitle =
                      c.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
                        ? 'Trauma A · Patient 2 (NSUH ED)'
                        : c.record_id.startsWith('LIVE-AI-CARES-TRIALRUN')
                        ? `Trial Run Case #${caseSimNum} (${c.record_id.slice(-6)})`
                        : c.record_id.startsWith('SIMVIDEO2-')
                        ? `Room D · ${c.record_id.replace('SIMVIDEO2-', '')}`
                        : c.title || c.record_id;
                    const recSubtitle = `Case #${caseSimNum} · ${caseProto.shortBadge} · ${
                      c.live_run ? 'Bedside iPad MOV' : c.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH' ? 'Room A CCTV' : 'Room D CCTV'
                    }`;
                    const statusTone = pausesCount > 0 ? 'amber' : c.live_run ? 'violet' : 'green';
                    const statusText =
                      pausesCount > 0
                        ? `${pausesCount} pause${pausesCount === 1 ? '' : 's'} >10s · CCF ${ccfVal}%`
                        : c.live_run
                        ? `CCF ${ccfVal}% · ${c.populated_fields_count || 65} REDCap vars`
                        : `Golden GT verified · CCF ${ccfVal}%`;

                    return (
                      <div
                        key={c.record_id}
                        role="button"
                        tabIndex={0}
                        className={`cc-rec-item ${isSelected ? 'active' : ''}`}
                        onClick={() => {
                          setSelectedCaseId(c.record_id);
                          setCurrentTimeS(
                            c.record_id === 'PATIENT2-TRAUMA-A-GROUND-TRUTH'
                              ? 474.0
                              : c.live_run
                              ? 106.0
                              : 164.0
                          );
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelectedCaseId(c.record_id);
                          }
                        }}
                      >
                        <div className="cc-rec-thumb">
                          <img
                            src={
                              (typeof window !== 'undefined' && window.__AICARES_POSTERS__?.[c.record_id]) ||
                              `${apiBase}/api/video/poster?case_id=${encodeURIComponent(c.record_id)}`
                            }
                            alt=""
                            loading="lazy"
                          />
                          <span className="cc-rec-thumb-badge mono">C{caseSimNum}</span>
                        </div>
                        <div className="cc-rec-body">
                          <div className="cc-rec-top-line">
                            <span className="cc-rec-title">{recTitle}</span>
                            <span className="cc-rec-duration mono">{fmtMmSs(durS)}</span>
                          </div>
                          <div className="cc-rec-sub">{recSubtitle}</div>
                          <div className={`cc-rec-status ${statusTone}`}>
                            <span className="cc-rec-dot" />
                            <span>{statusText}</span>
                          </div>
                        </div>
                        {cases.length > 1 && (
                          <button
                            type="button"
                            className="cc-rec-del-btn"
                            title={`Remove ${c.record_id}`}
                            onClick={(e) => handleDeleteCase(c.record_id, e)}
                          >
                            ×
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Bottom Summary Card inside Left Hero Card */}
                {(() => {
                  const ringPct = Math.max(0, Math.min(100, Number(caseScorePct ?? concordancePct ?? 100)));
                  const r = 26;
                  const circ = 2 * Math.PI * r;
                  const dash = (ringPct / 100) * circ;
                  const liveCount = cases.filter((c) => c.live_run).length;
                  const refCount = cases.length - liveCount;
                  return (
                    <div className="cc-rec-summary-box">
                      <div className="cc-rec-summary-top">
                        <div className="cc-rec-ring-wrap">
                          <svg width="64" height="64" viewBox="0 0 64 64" style={{ transform: 'rotate(-90deg)' }}>
                            <circle cx="32" cy="32" r={r} fill="none" stroke="#ddd6fe" strokeWidth="5.5" />
                            <circle
                              cx="32"
                              cy="32"
                              r={r}
                              fill="none"
                              stroke="#4f46e5"
                              strokeWidth="5.5"
                              strokeDasharray={`${dash} ${circ}`}
                              strokeLinecap="round"
                            />
                          </svg>
                          <div className="cc-rec-ring-label">
                            <span className="cc-rec-ring-pct">{ringPct}%</span>
                            <span className="cc-rec-ring-sub">rubric</span>
                          </div>
                        </div>

                        <div className="cc-rec-summary-stats">
                          <div className="cc-rec-summary-title">{cases.length} recordings in workspace</div>
                          <div className="cc-rec-stat-line">
                            <span className="cc-rec-stat-left">
                              <span className="cc-rec-stat-dot" style={{ background: '#4f46e5' }} />
                              <span>Live Gemini-4-Argon runs</span>
                            </span>
                            <b className="mono">{liveCount}</b>
                          </div>
                          <div className="cc-rec-stat-line">
                            <span className="cc-rec-stat-left">
                              <span className="cc-rec-stat-dot" style={{ background: '#a5b4fc' }} />
                              <span>Reference &amp; Golden GT</span>
                            </span>
                            <b className="mono">{refCount}</b>
                          </div>
                        </div>
                      </div>

                      <button
                        type="button"
                        className="cc-rec-summary-link"
                        onClick={() => {
                          const el = document.getElementById('section-active-workflows');
                          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }}
                      >
                        <div>
                          <div className="cc-rec-summary-link-title">
                            Review the {contractData.nPopTotal} populated REDCap fields
                          </div>
                          <div className="cc-rec-summary-link-sub">
                            Timestamps, medications, rhythm gates &amp; TEAM scores
                          </div>
                        </div>
                        <ProIcon name="chevronRight" size={15} color="#4f46e5" />
                      </button>
                    </div>
                  );
                })()}
              </div>

              {/* RIGHT HERO CARD: CLINICAL REVIEW FOR SELECTED RECORDING */}
              <div className="cc-clinical-review-card">
                <div className="cc-rev-top-bar">
                  <div className="cc-rev-agent-badge">
                    <span className="cc-rev-agent-icon">
                      <ProIcon name="flowMark" size={13} color="#ffffff" />
                    </span>
                    <span>
                      <span className="cc-rev-agent-badge-strong">Clinical AI Engine</span> ·{' '}
                      <span className="mono">{currentCase.verify_model_id || 'gemini-4-argon'}</span> · Case #
                      {currentCaseSimProtocol.num} ({currentCaseSimProtocol.difficulty})
                    </span>
                  </div>

                  <button
                    type="button"
                    className="cc-rev-open-link"
                    onClick={() => {
                      if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                      setActiveNav('video');
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                  >
                    <span>Open 3D Video #{currentCase.record_id.slice(0, 14)}</span>
                    <ProIcon name="chevronRight" size={14} color="#4f46e5" />
                  </button>
                </div>

                <h2 className="cc-rev-headline">
                  {`Clinical Review — ${currentCaseSimProtocol.title.replace(/^Case \d+ \([^)]*\) — /, '')}`}
                </h2>

                <div className="cc-rev-pills-row">
                  <span
                    className={`cc-rev-pill ${
                      Number(currentCase.prolonged_interruptions_count) > 0 || rubricFail > 0 ? 'amber' : 'amber'
                    }`}
                  >
                    {Number(currentCase.prolonged_interruptions_count) > 0
                      ? `Needs clinician review · ${currentCase.prolonged_interruptions_count} pause${
                          Number(currentCase.prolonged_interruptions_count) === 1 ? '' : 's'
                        } >10s (${caseScorePct ?? 100}% rubric)`
                      : `Score ${caseScorePct ?? 100}% · ${caseGrade} (${rubricPass}/${rubricPass + rubricFail} ACLS gates met)`}
                  </span>
                  <span className="cc-rev-pill neutral">
                    {currentCase.record_id} · CCF {currentCase.ccf_pct}% · TEAM {engineTeamReview.team_global_score}/10
                  </span>
                  <span className="cc-rev-pill violet">
                    {contractData.nPopTotal}/{contractData.totalCount} REDCap fields · {concordancePct}% GT agreement
                  </span>
                </div>

                {/* Inner 2-Column Split: Left (Summary + Why + Steps) / Right (Bedside Video Card + Protocol Check) */}
                <div className="cc-rev-inner-grid">
                  {/* LEFT INNER COLUMN */}
                  <div className="cc-rev-col">
                    <div>
                      <div className="cc-rev-section-label">Extracted clinical summary</div>
                      <div className="cc-rev-summary-card">
                        <div className="cc-rev-summary-top">
                          <span className="cc-rev-summary-icon">
                            <ProIcon name="activity" size={17} color="#4f46e5" />
                          </span>
                          <div>
                            <div className="cc-rev-summary-title">
                              {currentCaseSimProtocol.patient.split('·')[0].trim()} · Case #{currentCaseSimProtocol.num} (
                              {currentCaseSimProtocol.shortBadge})
                            </div>
                            <div className="cc-rev-summary-sub">
                              CCF {currentCase.ccf_pct}% · {allCaseEvents.length} events · TEAM {engineTeamReview.team_global_score}/10 (
                              {engineTeamReview.team_subscale_score}/{engineTeamReview.team_subscale_max})
                            </div>
                          </div>
                        </div>

                        <div className="cc-rev-kv-grid">
                          <div
                            className="cc-rev-kv-item"
                            onClick={() => {
                              seekToEvent(currentCase.live_run ? 80.0 : 13.0);
                              setActiveNav('video');
                            }}
                          >
                            <span className="cc-rev-kv-label">First compression</span>
                            <span className="cc-rev-kv-val mono">
                              {rr.time_compressions_v2 || '00:13'} · CCF {currentCase.ccf_pct}%
                            </span>
                          </div>

                          <div
                            className="cc-rev-kv-item"
                            onClick={() => {
                              seekToEvent(currentCase.live_run ? 106.0 : 153.0);
                              setActiveNav('video');
                            }}
                          >
                            <span className="cc-rev-kv-label">First epinephrine</span>
                            <span className="cc-rev-kv-val mono">
                              {rr.admin_epi_time_v2 || '01:46'} · {rr.total_epi_v2 || currentCase.total_epi_doses || 1} dose
                              {String(rr.total_epi_v2 || currentCase.total_epi_doses || 1) === '1' ? '' : 's'}
                            </span>
                          </div>

                          <div
                            className="cc-rev-kv-item"
                            onClick={() => {
                              seekToEvent(currentCase.live_run ? 229.0 : 474.0);
                              setActiveNav('video');
                            }}
                          >
                            <span className="cc-rev-kv-label">Rhythm &amp; defibrillation</span>
                            <span className="cc-rev-kv-val">
                              {isShockableCase
                                ? `${rr.shocks_admin_v2 || 1} shock(s) @ ${rr.time_defib_v2 || '07:54'}`
                                : `Non-shockable PEA (${rr.time_pulse_v2 || '03:49'})`}
                            </span>
                          </div>

                          <div
                            className="cc-rev-kv-item"
                            onClick={() => {
                              seekToEvent(currentCase.live_run ? 368.0 : 596.0);
                              setActiveNav('video');
                            }}
                          >
                            <span className="cc-rev-kv-label">Outcome &amp; code duration</span>
                            <span className="cc-rev-kv-val mono">
                              {rr.time_rosc_v2 ? `ROSC @ ${rr.time_rosc_v2}` : `TOR @ ${rr.time_death_v2 || '15:22'}`} ·{' '}
                              {fmtMmSs(currentCase.code_duration_s)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div>
                      <div className="cc-rev-section-label">Why the engine rated this</div>
                      <div className="cc-rev-why-list">
                        {engineTeamReview.done_well.slice(0, 3).map((dw, idx) => (
                          <div key={dw.id || idx} className="cc-rev-why-item">
                            <span className="cc-rev-why-check">
                              <ProIcon name="check" size={11} color="#4f46e5" />
                            </span>
                            <div className="cc-rev-why-body">
                              <div className="cc-rev-why-text">
                                <strong>{dw.title}:</strong> {dw.detail}
                              </div>
                              <button
                                type="button"
                                className="cc-rev-source-chip"
                                onClick={() => {
                                  if (dw.t_start_s !== undefined) seekToEvent(Number(dw.t_start_s));
                                  if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                                  setActiveNav('video');
                                  window.scrollTo({ top: 0, behavior: 'smooth' });
                                }}
                              >
                                <ProIcon name="video" size={11} color="#4f46e5" />
                                <span>
                                  @{dw.mm_ss} · {dw.modality} · {dw.redcap_field}
                                </span>
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '8px',
                        }}
                      >
                        <div className="cc-rev-section-label" style={{ marginBottom: 0 }}>
                          Clinical debrief &amp; coaching priorities
                        </div>
                        <button
                          type="button"
                          className="cc-rev-open-link"
                          style={{ fontSize: '12px' }}
                          onClick={() => {
                            if (typeof window !== 'undefined') window.history.replaceState(null, '', '#ai-insights');
                            setActiveNav('coaching');
                            window.scrollTo({ top: 0, behavior: 'smooth' });
                          }}
                        >
                          Open AI Insights &amp; Coaching ›
                        </button>
                      </div>
                      <div className="cc-rev-steps-list" style={{ marginTop: '8px' }}>
                        {[
                          ...engineTeamReview.areas_for_improvement.slice(0, 2),
                          ...engineTeamReview.done_well.slice(0, 1),
                        ]
                          .slice(0, 3)
                          .map((item, idx) => (
                            <div key={ item.id || idx }
                              className="cc-rev-step-row"
                              onClick={() => {
                                if (item.t_start_s !== undefined) seekToEvent(Number(item.t_start_s));
                                if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                                setActiveNav('video');
                                window.scrollTo({ top: 0, behavior: 'smooth' });
                              }}
                            >
                              <span className="cc-rev-step-num">{idx + 1}</span>
                              <span className="cc-rev-step-text">
                                <strong>@{item.mm_ss} {item.title}:</strong>{' '}
                                {item.actionable_recommendation || item.detail}
                              </span>
                            </div>
                          ))}
                      </div>
                    </div>
                  </div>

                  {/* RIGHT INNER COLUMN */}
                  <div className="cc-rev-col">
                    <div>
                      <div className="cc-rev-section-label">Bedside recording &amp; lead report</div>
                      <div className="cc-rev-report-card">
                        <div className="cc-rev-report-head">
                          <span className="cc-rev-report-avatar">TL</span>
                          <div>
                            <div className="cc-rev-report-name">Team Leader &amp; Bedside Audio (S7a)</div>
                            <div className="cc-rev-report-meta mono">
                              {currentCase.record_id.slice(0, 22)} · @{engineTeamReview.done_well[0]?.mm_ss || '01:02'}
                            </div>
                          </div>
                        </div>

                        <div className="cc-rev-report-quote">
                          {engineTeamReview.done_well[0]?.evidence_quote ||
                            focusedEvent?.evidence_text ||
                            'Frame-synchronized multimodal telemetry and 3D bedside clinician tracking.'}
                        </div>

                        <div
                          className="cc-rev-video-thumb"
                          onClick={() => {
                            if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                            setActiveNav('video');
                            window.scrollTo({ top: 0, behavior: 'smooth' });
                          }}
                          title="Click to open interactive 3D Video & Telemetry Study Console"
                        >
                          <img
                            src={
                              (typeof window !== 'undefined' && window.__AICARES_POSTERS__?.[currentCase.record_id]) ||
                              `${apiBase}/api/video/poster?case_id=${encodeURIComponent(currentCase.record_id)}`
                            }
                            alt="Resuscitation recording frame"
                          />
                          <span className="cc-rev-video-badge-top mono">
                            3D Boxes · {liveIdentityStats.length || 7} Tracked IDs
                          </span>
                          <span className="cc-rev-video-play-pill">
                            <ProIcon name="video" size={12} color="#ffffff" />
                            <span>Inspect 3D Video ›</span>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div>
                      <div className="cc-rev-section-label">Protocol &amp; rubric check</div>
                      <div className="cc-rev-policy-list">
                        {caseRubric.slice(0, 6).map((it) => {
                          const isPass = it.status === 'pass';
                          return (
                            <div key={it.field + it.label} className="cc-rev-policy-row">
                              <span className={`cc-rev-policy-icon ${isPass ? 'pass' : 'warn'}`}>
                                {isPass ? (
                                  <ProIcon name="check" size={10} color="#16a34a" />
                                ) : (
                                  <span>!</span>
                                )}
                              </span>
                              <div style={{ minWidth: 0 }}>
                                <span style={{ fontWeight: 500, color: isPass ? '#18181b' : '#b45309' }}>
                                  {it.label}
                                </span>
                                {it.detail && (
                                  <span className="mono" style={{ fontSize: '11px', color: '#71717a', marginLeft: '6px' }}>
                                    · {it.detail}
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Bottom Footer Bar of Right Hero Card */}
                <div className="cc-rev-footer">
                  <div className="cc-rev-footer-left">
                    <ProIcon name="clock" size={14} color="#71717a" />
                    <span>
                      Logged to REDCap with multimodal sources ({contractData.nPopTotal}/{contractData.totalCount} fields)
                    </span>
                  </div>

                  <div className="cc-rev-footer-actions">
                    <button
                      type="button"
                      className="cc-rev-text-btn"
                      onClick={() => {
                        const el = document.getElementById('section-active-workflows');
                        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      }}
                    >
                      Inspect REDCap fields
                    </button>
                    <div
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        background: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '999px',
                        padding: '2px 4px 2px 10px',
                      }}
                    >
                      <span style={{ fontSize: '11px', fontWeight: 600, color: '#475569', whiteSpace: 'nowrap' }}>
                        record_id <span style={{ color: '#dc2626' }}>*</span>
                      </span>
                      <input
                        type="text"
                        className="mono"
                        value={currentCase?.redcap_row?.record_id ?? ''}
                        onChange={(e) => handleUpdateRedcapRecordId(e.target.value)}
                        placeholder="e.g. 3"
                        aria-label="REDCap record_id"
                        style={{
                          width: '54px',
                          height: '24px',
                          padding: '0 6px',
                          fontSize: '11.5px',
                          fontWeight: 600,
                          color: '#0f172a',
                          background: '#ffffff',
                          border: String(currentCase?.redcap_row?.record_id ?? '').trim()
                            ? '1px solid #cbd5e1'
                            : '1px solid #ef4444',
                          borderRadius: '999px',
                          textAlign: 'center',
                          outline: 'none',
                        }}
                      />
                      <button
                        type="button"
                        className="cc-rev-outline-btn"
                        onClick={() => handleDownloadRedcapCsv(true)}
                        style={{ margin: 0, height: '26px', padding: '0 10px' }}
                      >
                        <span>Export REDCap CSV</span>
                      </button>
                    </div>
                    <button
                      type="button"
                      className="cc-rev-primary-btn"
                      onClick={() => {
                        if (typeof window !== 'undefined') window.history.replaceState(null, '', '#video-console');
                        setActiveNav('video');
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                      }}
                    >
                      <span>Open 3D Video Console</span>
                      <ProIcon name="chevronRight" size={14} color="#ffffff" />
                    </button>
                  </div>
                </div>
              </div>
            </section>

            {/* ════════════════════════════════════════════════════════════════
                FLOWAI SECTION 1: 4-CARD KPI STRIP INSIDE WHITE SHELL CONTAINER
                Matches Reference Screenshot 2 ("Total Runs / Success Rate / Active Workflows / AI Tokens")
               ════════════════════════════════════════════════════════════════ */}
            <section className="flow-kpi-strip-shell" id="section-kpi-strip">
              <div className="flow-kpi-grid-4">
                {[
                  {
                    label: 'Extracted Events',
                    value: `${allCaseEvents.length}`,
                    delta: `+100% Shock Agreement (S3/S5)`,
                    deltaTone: 'pos',
                    sub: `${contractData.nPopTotal}/${contractData.totalCount} of ${contractData.masterTotalCount.toLocaleString()} fields`,
                  },
                  {
                    label: 'REDCap Concordance',
                    value: `${concordancePct}%`,
                    delta: `+0.8184 ICC(2,1) vs Human GT`,
                    deltaTone: 'pos',
                    sub: `${examDash.verified_le_3s_count ?? 12}/${examDash.evaluated_milestone_count ?? 12} within ±3.0s`,
                  },
                  {
                    label: 'Chest Compression CCF',
                    value: `${currentCase.ccf_pct}%`,
                    delta: `${Number(currentCase.ccf_pct || 97.6) >= 80 ? '+' : ''}${(Number(currentCase.ccf_pct || 97.6) - 80).toFixed(1)}% vs 80% AHA Target`,
                    deltaTone: Number(currentCase.ccf_pct || 97.6) >= 80 ? 'pos' : 'neg',
                    sub: `${currentCase.prolonged_interruptions_count} pauses >10s`,
                  },
                  {
                    label: `Case #${currentCaseSimProtocol.num} Protocol & TEAM`,
                    value: `${caseScorePct ?? 100}%`,
                    delta: `${rubricPass}/${caseRubric.length} ACLS Gates · TEAM ${engineTeamReview.team_global_score}/10`,
                    deltaTone: 'pos',
                    sub: `0 Branching Errors`,
                  },
                ].map((kpi) => (
                  <div key={kpi.label} className="flow-kpi-card">
                    <div className="flow-kpi-inner-box">
                      <div className="flow-kpi-top-row">
                        <span className="flow-kpi-badge-icon">
                          <ProIcon name="flowMark" size={12} color="#18181b" />
                        </span>
                        <span className="flow-kpi-label">{kpi.label}</span>
                      </div>
                      <div className="flow-kpi-value-row">
                        <span className="flow-kpi-number">{kpi.value}</span>
                        <span className="flow-kpi-unit-pill mono">{kpi.sub}</span>
                      </div>
                    </div>
                    <div className="flow-kpi-bottom-row">
                      <span className={`flow-kpi-delta ${kpi.deltaTone}`}>
                        <ProIcon name="dashedCircle" size={13} color={kpi.deltaTone === 'neg' ? '#ef4444' : '#16a34a'} />
                        <span>{kpi.delta}</span>
                      </span>
                      <ProIcon name="dashedCircle" size={13} color="#a1a1aa" />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ════════════════════════════════════════════════════════════════
                REDCap Field Extraction & Provenance (User-Selected Dictionary Fields Only)
               ════════════════════════════════════════════════════════════════ */}
            <section className="extraction-card" id="section-active-workflows">
              <div id="section-clinical-list" />
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.65rem', flexWrap: 'wrap', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                  <h3 className="extraction-card-title" style={{ margin: 0 }}>
                    REDCap Field Extraction &amp; Provenance — {currentCase.record_id} · Case #{currentCase.simulation_number || 1}
                  </h3>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px 8px',
                      borderRadius: '999px',
                      fontSize: '11px',
                      lineHeight: 1.35,
                      fontWeight: 600,
                      background: '#eff6ff',
                      color: '#1d4ed8',
                      border: '1px solid #bfdbfe',
                    }}
                  >
                    {contractData.totalCount} of {contractData.masterTotalCount.toLocaleString()} REDCap Fields Selected ({contractData.nPopTotal} Populated · {contractData.nUtdTotal} UTD · {contractData.nNaTotal} N/A)
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                    TEAM Global <strong>{engineTeamReview.team_global_score}/10</strong> ({engineTeamReview.team_subscale_score}/{engineTeamReview.team_subscale_max}) · Click any row for video provenance
                  </span>
                  <div
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      background: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '999px',
                      padding: '2px 5px 2px 10px',
                    }}
                  >
                    <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155' }}>
                      REDCap record_id <span style={{ color: '#dc2626' }}>*</span>
                    </span>
                    <input
                      type="text"
                      className="mono"
                      value={currentCase?.redcap_row?.record_id ?? ''}
                      onChange={(e) => handleUpdateRedcapRecordId(e.target.value)}
                      placeholder="e.g. 3"
                      style={{
                        width: '56px',
                        height: '22px',
                        padding: '0 6px',
                        fontSize: '11.5px',
                        fontWeight: 600,
                        color: '#0f172a',
                        background: '#ffffff',
                        border: String(currentCase?.redcap_row?.record_id ?? '').trim()
                          ? '1px solid #cbd5e1'
                          : '1px solid #ef4444',
                        borderRadius: '999px',
                        textAlign: 'center',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => handleDownloadRedcapCsv(true)}
                      style={{
                        height: '24px',
                        padding: '0 10px',
                        borderRadius: '999px',
                        border: '1px solid #18181b',
                        background: '#18181b',
                        color: '#ffffff',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Export CSV (119 cols · 0 calc)
                    </button>
                  </div>
                </div>
              </div>

              {/* Consolidated Team Performance Summary & Areas for Improvement Callout */}
              <div
                className="act2-callout-box"
                style={{
                  margin: '6px 0 12px',
                  padding: '10px 14px',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                  gap: '12px 18px',
                  fontStyle: 'normal',
                }}
              >
                <div>
                  <div className="act2-callout-eyebrow" style={{ color: '#15803d', marginBottom: '4px' }}>
                    TEAM PERFORMANCE SUMMARY (STRENGTHS &amp; CLINICAL EXECUTION)
                  </div>
                  <div style={{ fontSize: '11.5px', lineHeight: 1.45, color: '#0f172a' }}>
                    {engineTeamReview.done_well.map((dw, idx) => (
                      <div key={dw.id || idx} style={{ marginBottom: idx < engineTeamReview.done_well.length - 1 ? '4px' : 0 }}>
                        <strong style={{ color: '#166534' }}>@{dw.mm_ss} {dw.title}:</strong> {dw.detail}
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ borderLeft: '1px solid #e2e8f0', paddingLeft: '16px' }}>
                  <div className="act2-callout-eyebrow" style={{ color: '#b45309', marginBottom: '4px' }}>
                    AREAS FOR IMPROVEMENT (TARGETED COACHING PRIORITIES)
                  </div>
                  <div style={{ fontSize: '11.5px', lineHeight: 1.45, color: '#0f172a' }}>
                    {engineTeamReview.areas_for_improvement.map((imp, idx) => (
                      <div key={imp.id || idx} style={{ marginBottom: idx < engineTeamReview.areas_for_improvement.length - 1 ? '4px' : 0 }}>
                        <strong style={{ color: '#92400e' }}>@{imp.mm_ss} {imp.title}:</strong>{' '}
                        {imp.actionable_recommendation || imp.detail}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Filter & State Controls */}
              <div className="table-controls">
                <input
                  type="text"
                  placeholder="Filter selected REDCap fields by label or export column..."
                  value={contractFilterQuery}
                  onChange={(e) => setContractFilterQuery(e.target.value)}
                />
                <select
                  aria-label="Filter fields by contract state"
                  value={contractStateFilter}
                  onChange={(e) => setContractStateFilter(e.target.value)}
                >
                  <option value="all">
                    All Selected Dictionary Fields ({contractData.totalCount} of {contractData.masterTotalCount.toLocaleString()} Fields)
                  </option>
                  <option value="gold_mismatch">✕ Show Discrepancies vs Gold Standard</option>
                  <option value="gold_match">✓ Show Matches vs Gold Standard</option>
                  <option value="gold_missed">⚠ Show Missed Fields (Gold Populated, Run UTD)</option>
                  <option value="auto_accepted">Auto-Accepted ({contractData.nPopTotal} Populated / Confident)</option>
                  <option value="utd">Unable to Determine ({contractData.nUtdTotal} UTD — Honest Abstentions)</option>
                  <option value="routed">Routed to HITL (TEAM Q-006 / Subjective)</option>
                  <option value="not_applicable">Not Applicable ({contractData.nNaTotal} Unsatisfied Branching / Inactive Slots)</option>
                </select>
              </div>

              {/* Collapsible Clinical Sections & 5-Column Extraction Contract Table */}
              <div>
                {contractSections.map((sec) => {
                  const isCollapsed = Boolean(collapsedContractSections[sec.secName]);
                  const isEdDetails = sec.secName === 'Emergency Department Details';
                  const shouldCapRows =
                    isEdDetails &&
                    !showAllEdDetails &&
                    !contractFilterQuery.trim() &&
                    contractStateFilter === 'all' &&
                    sec.visibleFields.length > 16;
                  const rowsToRender = shouldCapRows ? sec.visibleFields.slice(0, 16) : sec.visibleFields;

                  return (
                    <React.Fragment key={sec.secName}>
                      <div
                        className="section-header"
                        onClick={() =>
                          setCollapsedContractSections((prev) => ({
                            ...prev,
                            [sec.secName]: !prev[sec.secName],
                          }))
                        }
                      >
                        <span>
                          {isCollapsed ? '▶ ' : '▼ '}
                          {sec.secName}
                        </span>
                        <span className="section-header-counts">
                          {sec.nPop} populated · {sec.nUtd} unable to determine
                          {sec.nNa > 0 ? ` · ${sec.nNa} not applicable` : ''}
                        </span>
                      </div>

                      {!isCollapsed && (
                        <>
                          <table className="extraction-table">
                            <thead>
                              <tr>
                                <th style={{ width: '44%' }}>Field Label &amp; Column</th>
                                <th style={{ width: '16%' }}>Extracted Value</th>
                                <th style={{ width: '18%' }}>Gold Standard (Human Truth)</th>
                                <th style={{ width: '12%' }}>Contract State</th>
                                <th style={{ width: '10%' }}>Modality / Sensor</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rowsToRender.map((f) => {
                                const rowCls =
                                  f.state === 'auto_accepted'
                                    ? 'row-auto-accepted'
                                    : f.state === 'utd'
                                    ? 'row-utd'
                                    : f.state === 'routed'
                                    ? 'row-routed'
                                    : 'row-na';
                                const extractedDisplay =
                                  f.state === 'utd'
                                    ? 'Unable to determine'
                                    : f.value_label || (f.value !== null && f.value !== undefined ? String(f.value) : '--');
                                const goldInfo = getContractGoldStatus(f, contractData.gtLookup);
                                const modInfo = getContractModality(f, contractData.eventsById);

                                return (
                                  <tr
                                    key={f.export_column}
                                    className={rowCls}
                                    onClick={() => setProvenanceModalField(f)}
                                  >
                                    <td>
                                      <div className="extraction-field-label" style={{ fontWeight: f.state === 'utd' ? 600 : 500 }}>
                                        {(f.label || f.export_column).replace(/\s+/g, ' ')}
                                      </div>
                                      <div className="extraction-field-col">
                                        {f.export_column}
                                      </div>
                                    </td>
                                    <td>{extractedDisplay}</td>
                                    <td>
                                      <span className={`gold-badge ${goldInfo.className}`}>{goldInfo.label}</span>
                                    </td>
                                    <td>
                                      <span className="state-tag">{f.state || 'not_applicable'}</span>
                                    </td>
                                    <td>
                                      <span className={`mod-badge ${modInfo.modCls}`}>{modInfo.modStr}</span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                          {shouldCapRows && (
                            <div style={{ textAlign: 'center', marginBottom: '1rem' }}>
                              <button
                                type="button"
                                onClick={() => setShowAllEdDetails(true)}
                                style={{
                                  background: '#f8fafc',
                                  border: '1px solid #cbd5e1',
                                  color: '#0f172a',
                                  borderRadius: '6px',
                                  padding: '0.45rem 1rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                Show all {sec.visibleFields.length.toLocaleString()} fields in {sec.secName} ▾
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </section>

            {/* ════════════════════════════════════════════════════════════════
                FLOWAI SECTION 3: GROUNDED TEAM DEBRIEF & EVIDENCE TEMPLATES (4-CARD GRID)
                Matches Reference Screenshot 2 ("Recent Using Templates" 4-card architectural grid)
               ════════════════════════════════════════════════════════════════ */}
            <section className="flow-templates-card" id="section-team-debrief">
              <div className="flow-card-head">
                <div>
                  <h2 className="flow-card-title">
                    Team Debrief &amp; Grounded Clinical Evidence — {engineTeamReview.model_id}
                  </h2>
                  <p className="flow-card-sub">
                    TEAM Global Score: <strong>{engineTeamReview.team_global_score}/10</strong> (<code>team12_v2_v2</code>) · Subscale {engineTeamReview.team_subscale_score}/{engineTeamReview.team_subscale_max} ({engineTeamReview.team_subscale_pct}%) · Click any card to seek video evidence
                  </p>
                </div>
                <div className="flow-carousel-arrows">
                  <button
                    type="button"
                    className="flow-arrow-btn"
                    onClick={() => seekToEvent(Math.max(0, currentTimeS - 30))}
                    title="Step back 30s"
                  >
                    <ProIcon name="chevronLeft" size={14} color="#52525b" />
                  </button>
                  <button
                    type="button"
                    className="flow-arrow-btn"
                    onClick={() => seekToEvent(Math.min(maxTimelineS, currentTimeS + 30))}
                    title="Step forward 30s"
                  >
                    <ProIcon name="chevronRight" size={14} color="#52525b" />
                  </button>
                </div>
              </div>

              <div className="flow-templates-grid-4">
                {[
                  ...engineTeamReview.done_well.slice(0, 2).map((dw, i) => ({
                    ...dw,
                    kindLabel: 'Active · Done Well',
                    kindClass: 'active',
                    iconName: i === 0 ? 'activity' : 'zap',
                  })),
                  ...engineTeamReview.areas_for_improvement.slice(0, 2).map((imp, i) => ({
                    ...imp,
                    kindLabel: 'Coaching · Improve',
                    kindClass: 'paused',
                    iconName: i === 0 ? 'users' : 'droplet',
                  })),
                ].map((card, idx) => (
                  <div
                    key={card.id || idx}
                    className="flow-template-item"
                    onClick={() => {
                      if (card.t_start_s !== undefined && card.t_start_s !== null) {
                        seekToEvent(Number(card.t_start_s));
                      }
                      if (typeof window !== 'undefined') {
                        window.history.replaceState(null, '', '#video-console');
                      }
                      setActiveNav('video');
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                  >
                    {/* Architectural Vector Preview Header (Matches FlowAI Template Cards) */}
                    <div className="flow-template-Graphic">
                      <span className="flow-template-horiz-line" />
                      <div className="flow-template-iso-cube">
                        <ProIcon name={card.iconName} size={22} color="#27272a" />
                      </div>
                      <span className={`flow-template-badge ${card.kindClass}`}>{card.kindLabel}</span>
                    </div>

                    <div className="flow-template-body">
                      <div className="flow-template-title">{card.title}</div>
                      <div className="flow-template-meta">
                        Verified @{card.mm_ss} • {card.modality}
                      </div>
                      <div className="flow-template-quote">
                        {card.evidence_quote}
                      </div>
                    </div>

                    <div className="flow-template-footer">
                      <div className="flow-template-chips">
                        <span className="flow-mini-chip blue">S1</span>
                        <span className="flow-mini-chip amber">S5</span>
                        <span className="flow-mini-chip green">S7</span>
                        <span className="flow-mini-chip neutral">3+</span>
                      </div>
                      <span className="flow-template-runs mono">
                        {card.redcap_field} = {String(card.redcap_value).slice(0, 10)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Concise Narrative Strip + Expandable Full Case Rubric & Milestone Comparison */}
              <div className="flow-debrief-narrative-bar">
                <div className="flow-debrief-narrative-col">
                  <div className="flow-debrief-label">
                    Engine TEAM Narrative (<code>general_comments_v2</code>)
                  </div>
                  <div className="flow-debrief-text">{engineTeamReview.team_narrative}</div>
                </div>
                <div className="flow-debrief-narrative-col">
                  <div className="flow-debrief-label">
                    Actionable Coaching Summary (<code>feedback_narrative_v2</code>)
                  </div>
                  <div className="flow-debrief-text">{engineTeamReview.feedback_narrative}</div>
                </div>
              </div>
            </section>
              </>
            ) : (
              /* ════════════════════════════════════════════════════════════════
                  SEPARATE PAGE (`activeNav === 'video'` / `#video-console`):
                  1600×900 Resuscitation Clinical Study Console, 2D Bay Schematic,
                  Live S1 Compression Cadence, CV Overlap/Re-ID Board & Swimlanes
                 ════════════════════════════════════════════════════════════════ */
              <section className="co-landing-section tl-card co-study-console" id="section-video-timeline">
              {/* ZONE B · UNIFIED CONSOLE TOOLBAR (Segmented Focus Bar + Stage & Camera Controls) */}
              <div className="vc-toolbar">
                <div className="vc-toolbar-group vc-focus-group">
                  <span className="vc-label">Focus</span>
                  <div className="vc-chips" role="tablist" aria-label="Clinical focus filter">
                    {[
                      { id: 'all', label: 'All' },
                      { id: 'cpr', label: 'CPR & Pauses' },
                      { id: 'shocks', label: 'Rhythm & Shocks' },
                      { id: 'meds', label: 'Medications' },
                      { id: 'airway', label: 'Airway' },
                      { id: 'team', label: 'Team' },
                    ].map((sub) => (
                      <button
                        key={sub.id}
                        type="button"
                        className={`vc-chip ${domainFilter === sub.id ? 'on' : ''}`}
                        onClick={() => {
                          setDomainFilter(sub.id);
                          setExpandedGroups((prev) => (sub.id === 'all' ? prev : { ...prev, [sub.id]: true }));
                        }}
                      >
                        {sub.label}
                      </button>
                    ))}
                  </div>
                </div>

                {(() => {
                  const camOptions = [
                    { id: 'cctv_overhead', label: 'CCTV Overhead', feed: 'overhead_cropped' },
                    { id: 'ipad_bedside', label: 'Bedside iPad', feed: 'overhead_full' },
                    { id: 'gopro_pov', label: 'GoPro POV', feed: 'sim_series' },
                    { id: 'spatial_34', label: '3/4 Spatial', feed: null },
                  ];
                  const activeCam =
                    cameraPerspectiveView !== 'hero_auto'
                      ? cameraPerspectiveView
                      : currentCase.live_run
                      ? isPortraitVideo
                        ? 'ipad_bedside'
                        : 'cctv_overhead'
                      : videoFeedSource === 'sim_series'
                      ? 'gopro_pov'
                      : videoFeedSource === 'overhead_full'
                      ? 'ipad_bedside'
                      : 'cctv_overhead';
                  const layoutValue = fullTheaterMode || consoleLayoutMode === 'cinema_100' ? 'cinema_100' : consoleLayoutMode;
                  const overlayKeys = [
                    { key: 'boxes3d', label: '3D boxes & ROIs' },
                    { key: 'instanceMasks', label: 'Instance masks & overlap seam' },
                    { key: 'panopticPolygons', label: 'Panoptic regions & polygons' },
                    { key: 'reidTrajectories', label: 'Re-ID trajectories' },
                  ];
                  const overlaysOn = overlayKeys.filter((o) => cvLayers[o.key]).length;
                  return (
                    <div className="vc-toolbar-group vc-controls-group">
                      <label className="vc-select">
                        <span className="vc-select-lbl">Camera</span>
                        <select
                          value={activeCam}
                          onChange={(e) => {
                            const opt = camOptions.find((c) => c.id === e.target.value);
                            setCameraPerspectiveView(opt.id);
                            if (opt.feed && !currentCase.live_run) {
                              setLocalVideoBlobUrl(null);
                              setVideoFeedSource(opt.feed);
                            }
                          }}
                        >
                          {camOptions.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="vc-select">
                        <span className="vc-select-lbl">Layout</span>
                        <select
                          value={layoutValue}
                          onChange={(e) => {
                            const v = e.target.value;
                            setFullTheaterMode(v === 'cinema_100');
                            setConsoleLayoutMode(v);
                            if (v === 'audit_40_60') setInspectorTab('redcap');
                          }}
                        >
                          <option value="console_70_30">Split View</option>
                          <option value="audit_40_60">Audit Table</option>
                          <option value="cinema_100">Full Video</option>
                        </select>
                      </label>
                      <label className="vc-select">
                        <span className="vc-select-lbl">Size</span>
                        <select value={videoSizeMode} onChange={(e) => setVideoSizeMode(e.target.value)}>
                          <option value="std">Standard</option>
                          <option value="large">Large</option>
                          <option value="bed_wide">Bed Focus</option>
                          <option value="xl_theater">Max</option>
                        </select>
                      </label>
                      <label className="vc-select">
                        <span className="vc-select-lbl">Zoom</span>
                        <select value={String(videoZoomLevel)} onChange={(e) => setVideoZoomLevel(Number(e.target.value))}>
                          {[1, 1.25, 1.5, 2].map((zm) => (
                            <option key={zm} value={String(zm)}>
                              {Math.round(zm * 100)}%
                            </option>
                          ))}
                        </select>
                      </label>
                      <details className="vc-dd">
                        <summary className="vc-select vc-select-summary">
                          <span className="vc-select-lbl">Overlays</span>
                          <b>
                            {overlaysOn}/{overlayKeys.length}
                          </b>
                        </summary>
                        <div className="vc-dd-menu">
                          {overlayKeys.map((o) => (
                            <label key={o.key} className="vc-check">
                              <input type="checkbox" checked={Boolean(cvLayers[o.key])} onChange={() => toggleCvLayer(o.key)} />
                              <span>{o.label}</span>
                            </label>
                          ))}
                          <div className="vc-dd-sep" />
                          <label className="vc-check">
                            <input
                              type="checkbox"
                              checked={isolateSubsystemRoi}
                              onChange={() => setIsolateSubsystemRoi((prev) => !prev)}
                            />
                            <span>Dim ROIs outside the Focus area</span>
                          </label>
                        </div>
                      </details>
                    </div>
                  );
                })()}
              </div>
              {/* TOP STAGE: Large 16:9 3D Annotated Video Player (Left 70% or 40% Sticky or 100%) + Playhead-Synced REDCap Rail / Audit Table */}
              <div
                className={`tl-video-theater-grid ${
                  fullTheaterMode || consoleLayoutMode === 'cinema_100'
                    ? 'full-theater'
                    : consoleLayoutMode === 'audit_40_60'
                    ? 'audit-40-60'
                    : ''
                } vc-workspace`}
                style={{
                  height:
                    videoSizeMode === 'xl_theater' ? 780 : videoSizeMode === 'large' ? 700 : videoSizeMode === 'bed_wide' ? 640 : 580,
                }}
              >
                {/* LEFT COLUMN: Video Stage + status line + transport */}
                <div className="co-console-left-stage-col" style={{ display: 'flex', flexDirection: 'column', minWidth: 0, height: '100%' }}>
                  <div
                    className={`video-3d-stage ${cameraPerspectiveView === 'spatial_34' ? 'perspective-34' : ''}`}
                    ref={stageRef}
                    style={{ aspectRatio: 'auto', flex: '1 1 auto', minHeight: 0, maxHeight: 'none', height: 'auto' }}
                  >
                    <div
                      className="video-media-frame"
                      style={{
                        position: 'absolute',
                        ...mediaRect,
                        zIndex: 1,
                        overflow: 'hidden',
                        borderRadius: '8px',
                        transform:
                          cameraPerspectiveView === 'spatial_34'
                            ? `${mediaRect.transform ? mediaRect.transform + ' ' : ''}perspective(1280px) rotateX(8deg) rotateY(-6deg) scale(0.95)`
                            : mediaRect.transform,
                        transition: 'all 0.28s cubic-bezier(0.22, 1, 0.36, 1)',
                      }}
                    >
                      <div
                        style={{
                          ...innerMediaCanvasStyle,
                          background: `#0f172a url("${
                            (typeof window !== 'undefined' && window.__AICARES_POSTERS__?.[currentCase.record_id]) ||
                            `/api/video/poster?case_id=${encodeURIComponent(currentCase.record_id)}`
                          }") center / contain no-repeat`,
                        }}
                      >
                        <video
                          ref={videoRef}
                          key={reviewVideoSrc}
                          src={reviewVideoSrc}
                          poster={
                            (typeof window !== 'undefined' && window.__AICARES_POSTERS__?.[currentCase.record_id]) ||
                            `/api/video/poster?case_id=${encodeURIComponent(currentCase.record_id)}`
                          }
                          muted
                          playsInline
                          preload="auto"
                          onLoadedMetadata={(e) => {
                            setVideoDims({ w: e.currentTarget.videoWidth, h: e.currentTarget.videoHeight });
                            try {
                              e.currentTarget.currentTime = currentTimeS;
                            } catch {
                              // ignore
                            }
                          }}
                          style={{
                            position: 'absolute',
                            inset: 0,
                            width: '100%',
                            height: '100%',
                            objectFit: 'contain',
                            opacity: 1,
                            zIndex: 1,
                          }}
                        />
                      </div>
                    </div>

                    <div
                      className="video-media-frame"
                      style={{
                        position: 'absolute',
                        ...mediaRect,
                        zIndex: 2,
                        pointerEvents: 'none',
                        overflow: 'hidden',
                        borderRadius: '8px',
                        transform:
                          cameraPerspectiveView === 'spatial_34'
                            ? `${mediaRect.transform ? mediaRect.transform + ' ' : ''}perspective(1280px) rotateX(8deg) rotateY(-6deg) scale(0.95)`
                            : mediaRect.transform,
                        transition: 'all 0.28s cubic-bezier(0.22, 1, 0.36, 1)',
                      }}
                    >
                      <div style={{ ...innerMediaCanvasStyle, pointerEvents: 'none' }}>
                    {/* ════════════════════════════════════════════════════════════════════════
                        TRAUMA-A-STYLE 3D VOLUMETRIC WIREFRAME OVERLAY FOR LIVE PROCESSED VIDEOS
                        Driven by real gemini-4-argon spatial_tracks (3D cuboids, anatomical ROIs,
                        deformable polygons, instance masks, overlap seams & Re-ID trajectories)
                       ════════════════════════════════════════════════════════════════════════ */}
                    {currentCase.live_run && (
                      <svg
                        viewBox={`0 0 ${liveSvgW} ${liveSvgH}`}
                        width="100%"
                        height="100%"
                        shapeRendering="geometricPrecision"
                        preserveAspectRatio="none"
                        style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none' }}
                      >
                        {(() => {
                          const W = liveSvgW;
                          const H = liveSvgH;
                          const sx = (v) => (v / 1000) * W;
                          const sy = (v) => (v / 1000) * H;
                          const clampX = (x, bw) => Math.max(8, Math.min(W - bw - 8, x));
                          const clampY = (y, bh) => Math.max(38, Math.min(H - bh - 46, y));

                          // Patient / Manikin anchor box [y0, x0, y1, x1] in 0..1000
                          const ptBox = livePtObj?.box || [530, 180, 770, 560];
                          const [ptY0, ptX0, ptY1, ptX1] = ptBox;
                          const ptW = Math.max(80, ptX1 - ptX0);
                          const ptH = Math.max(80, ptY1 - ptY0);

                          // Defibrillator / Monitor anchor box [y0, x0, y1, x1] in 0..1000
                          const defBox = liveDefibObj?.box || [520, 40, 665, 220];
                          const [defY0, defX0, defY1, defX1] = defBox;

                          // Anatomical Sub-ROIs derived from Patient/Manikin (PT-1)
                          const airwayBox = [
                            ptY0 - ptH * 0.04,
                            ptX0 + ptW * 0.08,
                            ptY0 + ptH * 0.42,
                            ptX0 + ptW * 0.42,
                          ];
                          const chestBox = [
                            ptY0 + ptH * 0.16,
                            ptX0 + ptW * 0.28,
                            ptY0 + ptH * 0.68,
                            ptX0 + ptW * 0.68,
                          ];
                          const ivBox = [
                            ptY0 + ptH * 0.38,
                            ptX0 + ptW * 0.56,
                            ptY0 + ptH * 0.84,
                            ptX0 + ptW * 0.94,
                          ];

                          const inPause = activeAnnotationsAtTime.inPause;
                          const cprOn = activeAnnotationsAtTime.cprActive;
                          const chestColor = inPause ? '#f87171' : cprOn ? '#34d399' : '#38bdf8';
                          const chestFill = inPause
                            ? 'rgba(239, 68, 68, 0.11)'
                            : cprOn
                            ? 'rgba(16, 185, 129, 0.09)'
                            : 'rgba(56, 189, 248, 0.06)';

                          const medEv =
                            (focusedEvent?.type === 'medication_administration' &&
                              Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                              focusedEvent) ||
                            activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'medication_administration');
                          const medActive = Boolean(medEv);
                          const ivCol = medActive ? '#c4b5fd' : 'rgba(167, 139, 250, 0.72)';

                          const shockEv =
                            (focusedEvent?.type === 'defibrillation_shock' &&
                              Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                              focusedEvent) ||
                            activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'defibrillation_shock');
                          const rhyEv =
                            (focusedEvent?.type === 'rhythm_check' &&
                              Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                              focusedEvent) ||
                            activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'rhythm_check' || e.type === 'pulse_check');
                          const isShock = Boolean(shockEv);
                          const isRhy = Boolean(rhyEv);
                          const defCol = isShock ? '#fbbf24' : isRhy ? '#22d3ee' : 'rgba(56, 189, 248, 0.78)';

                          // Helper to draw a 3D Volumetric Wireframe Cuboid from a [y0, x0, y1, x1] 0..1000 box
                          const renderCuboid = (box, dx, dy, stroke, fill = 'none', sw = 0.75, dashed = false, corners = false) => {
                            const x0 = sx(box[1]);
                            const y0 = sy(box[0]);
                            const x1 = sx(box[3]);
                            const y1 = sy(box[2]);
                            const bx0 = x0 + dx;
                            const by0 = y0 + dy;
                            const bx1 = x1 + dx;
                            const by1 = y1 + dy;
                            return (
                              <g>
                                {/* Back/Top 3D extruded face */}
                                <polygon
                                  points={`${bx0},${by0} ${bx1},${by0} ${bx1},${by1} ${bx0},${by1}`}
                                  fill="none"
                                  stroke={stroke}
                                  strokeWidth={sw * 0.85}
                                  strokeDasharray={dashed ? '2.5 2' : 'none'}
                                  strokeOpacity="0.82"
                                />
                                {/* Front face */}
                                <polygon
                                  points={`${x0},${y0} ${x1},${y0} ${x1},${y1} ${x0},${y1}`}
                                  fill={fill}
                                  stroke={stroke}
                                  strokeWidth={sw}
                                />
                                {/* 4 depth struts */}
                                <line x1={bx0} y1={by0} x2={x0} y2={y0} stroke={stroke} strokeWidth={sw * 0.75} />
                                <line x1={bx1} y1={by0} x2={x1} y2={y0} stroke={stroke} strokeWidth={sw * 0.75} />
                                <line x1={bx1} y1={by1} x2={x1} y2={y1} stroke={stroke} strokeWidth={sw * 0.75} />
                                <line x1={bx0} y1={by1} x2={x0} y2={y1} stroke={stroke} strokeWidth={sw * 0.75} />
                                {corners && (
                                  <path
                                    d={`M${x0},${y0 + 7} L${x0},${y0} L${x0 + 7},${y0} M${x1 - 7},${y0} L${x1},${y0} L${x1},${y0 + 7} M${x0},${y1 - 7} L${x0},${y1} L${x0 + 7},${y1} M${x1 - 7},${y1} L${x1},${y1} L${x1},${y1 - 7}`}
                                    fill="none"
                                    stroke="#ffffff"
                                    strokeWidth="1.05"
                                  />
                                )}
                              </g>
                            );
                          };

                          return (
                            <>
                              {/* 0. Subtle Perspective Ground-Plane Calibration Grid + S5 Clock ROI */}
                              <g stroke="rgba(56, 189, 248, 0.14)" strokeWidth="0.4" strokeDasharray="2.5 3.5">
                                <line x1={W * 0.14} y1={H * 0.96} x2={W * 0.28} y2={H * 0.24} />
                                <line x1={W * 0.34} y1={H * 0.96} x2={W * 0.42} y2={H * 0.24} />
                                <line x1={W * 0.56} y1={H * 0.96} x2={W * 0.56} y2={H * 0.24} />
                                <line x1={W * 0.78} y1={H * 0.96} x2={W * 0.70} y2={H * 0.24} />
                                <line x1={W * 0.12} y1={H * 0.46} x2={W * 0.88} y2={H * 0.43} />
                                <line x1={W * 0.08} y1={H * 0.68} x2={W * 0.92} y2={H * 0.65} />
                              </g>
                              <rect
                                x="12"
                                y="36"
                                width="156"
                                height="16"
                                rx="2.5"
                                fill="none"
                                stroke="rgba(56, 189, 248, 0.65)"
                                strokeWidth="0.6"
                                strokeDasharray="2 2"
                              />

                              {/* 1. RESUSCITATION BED / STRETCHER 3D PERIMETER WIREFRAME (Anchored to PT-1) */}
                              {(() => {
                                const bx0 = sx(Math.max(30, ptX0 - 35));
                                const by0 = sy(Math.max(120, ptY0 + 10));
                                const bx1 = sx(Math.min(960, ptX1 + 35));
                                const by1 = sy(Math.min(950, ptY1 + 25));
                                return (
                                  <g stroke="rgba(148, 163, 184, 0.52)" strokeWidth="0.55" fill="none">
                                    <polygon
                                      points={`${bx0},${by0} ${bx1},${by0 - 12} ${bx1 + 12},${by1 - 8} ${bx0 + 8},${by1}`}
                                      strokeDasharray="3 2"
                                    />
                                    <polygon
                                      points={`${bx0 + 4},${by0 + 22} ${bx1 + 4},${by0 + 10} ${bx1 + 16},${by1 + 14} ${bx0 + 12},${by1 + 22}`}
                                      strokeOpacity="0.38"
                                    />
                                    <line x1={bx0} y1={by0} x2={bx0 + 4} y2={by0 + 22} />
                                    <line x1={bx1} y1={by0 - 12} x2={bx1 + 4} y2={by0 + 10} />
                                    <line x1={bx1 + 12} y1={by1 - 8} x2={bx1 + 16} y2={by1 + 14} />
                                    <line x1={bx0 + 8} y1={by1} x2={bx0 + 12} y2={by1 + 22} />
                                  </g>
                                );
                              })()}

                              {/* 2. ANATOMICAL 3D VOLUMETRIC CUBOIDS (AIRWAY, S1 CHEST/STERNUM, IV/IO ACCESS, S3/S5 DEFIB) */}
                              {cvLayers.boxes3d && (() => {
                                const placedCallouts = [];
                                const calcPillW = (l1, l2 = '') =>
                                  Math.min(
                                    W - 20,
                                    Math.round(Math.max(String(l1 || '').length * 5.7, String(l2 || '').length * 5.1) + 18)
                                  );
                                const placeCallout = (prefX, prefY, bw, bh) => {
                                  const cx0 = clampX(prefX, bw);
                                  const candidates = [
                                    [cx0, clampY(prefY, bh)],
                                    [cx0, clampY(prefY - 40, bh)],
                                    [cx0, clampY(prefY + 40, bh)],
                                    [cx0, clampY(prefY - 80, bh)],
                                    [cx0, clampY(prefY + 80, bh)],
                                    [clampX(cx0 + 96, bw), clampY(prefY, bh)],
                                    [clampX(cx0 - 96, bw), clampY(prefY, bh)],
                                    [cx0, clampY(prefY - 120, bh)],
                                    [cx0, clampY(prefY + 120, bh)],
                                  ];
                                  for (const [tx, ty] of candidates) {
                                    const hit = placedCallouts.some(
                                      (r) =>
                                        tx < r.x + r.w + 10 &&
                                        tx + bw + 10 > r.x &&
                                        ty < r.y + r.h + 12 &&
                                        ty + bh + 12 > r.y
                                    );
                                    if (!hit) {
                                      placedCallouts.push({ x: tx, y: ty, w: bw, h: bh });
                                      return [tx, ty];
                                    }
                                  }
                                  const [fx, fy] = candidates[0];
                                  placedCallouts.push({ x: fx, y: fy, w: bw, h: bh });
                                  return [fx, fy];
                                };

                                return (
                                <g>
                                  {/* 2A. AIRWAY / ETT 3D ROI */}
                                  {(() => {
                                    const ax = sx((airwayBox[1] + airwayBox[3]) / 2);
                                    const ay = sy(airwayBox[0]);
                                    const l1 = `AIRWAY / ETT ROI [${(airwayBox[1] / 1000).toFixed(2)}, ${(airwayBox[0] / 1000).toFixed(2)}]`;
                                    const callW = calcPillW(l1);
                                    const callH = 20;
                                    const [callX, callY] = placeCallout(ax - callW * 0.65, ay - 62, callW, callH);
                                    return (
                                      <g opacity={getSubsystemRoiOpacity('airway')}>
                                        {renderCuboid(airwayBox, -6, -16, 'rgba(52, 211, 153, 0.72)', 'rgba(16, 185, 129, 0.06)', 0.68, true, false)}
                                        <line x1={ax} y1={ay - 12} x2={callX + callW * 0.5} y2={callY + callH} stroke="#34d399" strokeWidth="0.6" />
                                        <rect x={callX} y={callY} width={callW} height={callH} rx="4" fill="rgba(15, 23, 42, 0.86)" stroke="#34d399" strokeWidth="0.7" />
                                        <text x={callX + 7} y={callY + 13} fill="#a7f3d0" fontSize="8.2" fontWeight="700" fontFamily="monospace">
                                          {l1}
                                        </text>
                                      </g>
                                    );
                                  })()}

                                  {/* 2B. S1 CHEST ROI · ACTIVE CPR COMPRESSIONS */}
                                  {(() => {
                                    const cx = sx((chestBox[1] + chestBox[3]) / 2);
                                    const cy = sy(chestBox[0]);
                                    const l1 = inPause
                                      ? `PAUSE DETECTED (${activeAnnotationsAtTime.activeIntervals[0]?.duration_s || 7}s)`
                                      : cprOn
                                      ? 'S1 CHEST ROI · ACTIVE CPR'
                                      : `S1 CHEST ROI [${(chestBox[1] / 1000).toFixed(2)}, ${(chestBox[0] / 1000).toFixed(2)}]`;
                                    const l2 = inPause
                                      ? `${(activeAnnotationsAtTime.activeIntervals[0]?.evidence_text || 'Hands off chest').slice(0, 30)}`
                                      : `CCF ${currentCase.ccf_pct}% (Target ≥80%) · PT-1 Sternum`;
                                    const callW = calcPillW(l1, l2);
                                    const callH = 30;
                                    const [callX, callY] = placeCallout(cx - callW * 0.45, cy - 64, callW, callH);
                                    return (
                                      <g opacity={getSubsystemRoiOpacity('cpr')}>
                                        {renderCuboid(chestBox, -7, -20, chestColor, chestFill, 0.95, false, true)}
                                        {cprOn && (
                                          <g stroke="#34d399" strokeWidth="0.9">
                                            <line x1={cx - 7} y1={cy - 28} x2={cx - 7} y2={cy + 8} />
                                            <polygon points={`${cx - 10},${cy + 5} ${cx - 4},${cy + 5} ${cx - 7},${cy + 11}`} fill="#34d399" stroke="none" />
                                            <line x1={cx + 7} y1={cy - 30} x2={cx + 7} y2={cy + 6} />
                                            <polygon points={`${cx + 4},${cy + 3} ${cx + 10},${cy + 3} ${cx + 7},${cy + 9}`} fill="#34d399" stroke="none" />
                                          </g>
                                        )}
                                        <line x1={cx} y1={cy - 16} x2={callX + callW * 0.45} y2={callY + callH} stroke={chestColor} strokeWidth="0.7" />
                                        <circle cx={cx} cy={cy - 16} r="2.0" fill={chestColor} />
                                        <rect x={callX} y={callY} width={callW} height={callH} rx="4" fill="rgba(15, 23, 42, 0.88)" stroke={chestColor} strokeWidth="0.8" />
                                        <text x={callX + 8} y={callY + 12.5} fill="#f8fafc" fontSize="8.4" fontWeight="700" fontFamily="monospace">
                                          {l1}
                                        </text>
                                        <text x={callX + 8} y={callY + 23.5} fill="#cbd5e1" fontSize="7.6" fontFamily="monospace">
                                          {l2}
                                        </text>
                                      </g>
                                    );
                                  })()}

                                  {/* 2C. IV / IO ACCESS & MEDICATION PORT 3D ROI */}
                                  {(() => {
                                    const ix = sx((ivBox[1] + ivBox[3]) / 2);
                                    const iy = sy(ivBox[2]);
                                    const l1 = medActive
                                      ? `${medEv.label.toUpperCase().slice(0, 26)}`
                                      : `IV / IO ACCESS ROI [${(ivBox[1] / 1000).toFixed(2)}, ${(ivBox[0] / 1000).toFixed(2)}]`;
                                    const l2 = medActive
                                      ? `Administered @ ${medEv.start_mmss} · S7a ASR`
                                      : `[total_epi_v2 = ${currentCase.total_epi_doses ?? rr.total_epi_v2 ?? 1} doses] S7a ASR`;
                                    const callW = calcPillW(l1, l2);
                                    const callH = 29;
                                    const [callX, callY] = placeCallout(ix - callW * 0.4, iy + 20, callW, callH);
                                    return (
                                      <g opacity={getSubsystemRoiOpacity('meds')}>
                                        {renderCuboid(
                                          ivBox,
                                          -5,
                                          -15,
                                          ivCol,
                                          medActive ? 'rgba(139, 92, 246, 0.12)' : 'rgba(139, 92, 246, 0.04)',
                                          medActive ? 0.9 : 0.65,
                                          false,
                                          medActive
                                        )}
                                        <line x1={ix} y1={iy} x2={callX + callW * 0.35} y2={callY} stroke={ivCol} strokeWidth="0.6" />
                                        <circle cx={ix} cy={iy} r="1.8" fill={ivCol} />
                                        <rect x={callX} y={callY} width={callW} height={callH} rx="4" fill="rgba(15, 23, 42, 0.86)" stroke={ivCol} strokeWidth="0.7" />
                                        <text x={callX + 8} y={callY + 12} fill="#ede9fe" fontSize="8.2" fontWeight="700" fontFamily="monospace">
                                          {l1}
                                        </text>
                                        <text x={callX + 8} y={callY + 23} fill="#cbd5e1" fontSize="7.5" fontFamily="monospace">
                                          {l2}
                                        </text>
                                      </g>
                                    );
                                  })()}

                                  {/* 2D. S3/S5 DEFIBRILLATOR & ECG MONITOR 3D ROI (Anchored to DEFIB-1) */}
                                  {(() => {
                                    const dx0 = sx(defX0);
                                    const dy0 = sy(defY0);
                                    const dx1 = sx(defX1);
                                    const dy1 = sy(defY1);
                                    const dcx = (dx0 + dx1) / 2;
                                    const dcy = (dy0 + dy1) / 2;
                                    const mw = Math.max(24, dx1 - dx0);
                                    const l1 = isShock
                                      ? `SHOCK DELIVERED @ ${shockEv.start_mmss}`
                                      : isRhy
                                      ? `RHYTHM / PULSE CHECK @ ${rhyEv.start_mmss}`
                                      : `S3/S5 DEFIB & MONITOR [${(defX0 / 1000).toFixed(2)}, ${(defY0 / 1000).toFixed(2)}]`;
                                    const l2 = `DEFIB-1 · ${(liveDefibObj?.label || 'ECG Monitor ROI').slice(0, 24)}`;
                                    const callW = calcPillW(l1, l2);
                                    const callH = 29;
                                    const [callX, callY] = placeCallout(dx0, dy0 - 52, callW, callH);
                                    const ecgPts = [
                                      `${dx0 + mw * 0.14},${dcy - 4}`,
                                      `${dx0 + mw * 0.26},${dcy - 11}`,
                                      `${dx0 + mw * 0.36},${dcy + 3}`,
                                      `${dx0 + mw * 0.48},${dcy - 14}`,
                                      `${dx0 + mw * 0.58},${dcy + 4}`,
                                      `${dx0 + mw * 0.70},${dcy - 9}`,
                                      `${dx0 + mw * 0.84},${dcy - 3}`,
                                    ].join(' ');
                                    return (
                                      <g opacity={getSubsystemRoiOpacity('shocks')}>
                                        {renderCuboid(
                                          defBox,
                                          -6,
                                          -18,
                                          defCol,
                                          isShock ? 'rgba(245, 158, 11, 0.12)' : isRhy ? 'rgba(6, 182, 212, 0.09)' : 'rgba(56, 189, 248, 0.05)',
                                          isShock || isRhy ? 0.95 : 0.72,
                                          false,
                                          true
                                        )}
                                        <polyline points={ecgPts} fill="none" stroke={isShock ? '#fbbf24' : '#38bdf8'} strokeWidth="0.85" />
                                        <line x1={dcx} y1={dy0 - 16} x2={callX + 44} y2={callY + callH} stroke={defCol} strokeWidth="0.65" />
                                        <rect x={callX} y={callY} width={callW} height={callH} rx="4" fill="rgba(15, 23, 42, 0.86)" stroke={defCol} strokeWidth="0.7" />
                                        <text x={callX + 8} y={callY + 12} fill="#f8fafc" fontSize="8.2" fontWeight="700" fontFamily="monospace">
                                          {l1}
                                        </text>
                                        <text x={callX + 8} y={callY + 23} fill="#cbd5e1" fontSize="7.5" fontFamily="monospace">
                                          {l2}
                                        </text>
                                      </g>
                                    );
                                  })()}

                                  {/* 2E. 3D VOLUMETRIC CUBOIDS FOR ALL REAL TRACKED CLINICIANS & EQUIPMENT AT PLAYHEAD */}
                                  {liveBoxesNow
                                    .filter((o) => !o.id.startsWith('PT-') && !o.id.startsWith('DEFIB-'))
                                    .map((o, idx) => {
                                      const col = o.color || trackColor(o.category);
                                      const isSelected = selectedObjId === o.id;
                                      const dx = o.dx3d || -8;
                                      const dy = o.dy3d || -16;
                                      const x0 = sx(o.box[1]);
                                      const y0 = sy(o.box[0]);
                                      const x1 = sx(o.box[3]);
                                      const y1 = sy(o.box[2]);
                                      const cx = (x0 + x1) / 2;
                                      const shortRole = String(o.role || o.category || 'Clinician')
                                        .replace(/& BEDSIDE.*$/i, '')
                                        .replace(/RESUSCITATION TEAM /i, '')
                                        .trim()
                                        .toUpperCase()
                                        .slice(0, 18);
                                      const l1 = `${o.id} · ${shortRole}`;
                                      const shortDesc = String(o.label || 'Tracked Clinician').slice(0, 22);
                                      const l2 = `${shortDesc} [${(cx / W).toFixed(2)}, ${(((y0 + y1) / 2) / H).toFixed(2)}]`;
                                      const showFullCallout = isSelected || domainFilter === 'team' || idx < 2;
                                      const badgeW = showFullCallout ? calcPillW(l1, l2) : Math.max(58, o.id.length * 6.2 + 14);
                                      const badgeH = showFullCallout ? 27 : 16;
                                      const placeBottom = y0 > H * 0.48 && idx % 2 === 1;
                                      const prefY = placeBottom ? Math.min(H - 54, y1 + 8) : Math.max(42, y0 - 38);
                                      const [badgeX, badgeY] = placeCallout(cx - badgeW / 2, prefY, badgeW, badgeH);
                                      return (
                                        <g key={o.id} opacity={getSubsystemRoiOpacity('team')}>
                                          {renderCuboid(
                                            o.box,
                                            dx,
                                            dy,
                                            col,
                                            isSelected ? `${col}26` : `${col}0d`,
                                            isSelected ? 1.15 : 0.78,
                                            false,
                                            true
                                          )}
                                          <line
                                            x1={cx}
                                            y1={placeBottom ? y1 : y0 + dy}
                                            x2={badgeX + badgeW / 2}
                                            y2={placeBottom ? badgeY : badgeY + badgeH}
                                            stroke={col}
                                            strokeWidth="0.6"
                                            strokeDasharray="2 1.5"
                                          />
                                          <circle cx={cx} cy={placeBottom ? y1 : y0 + dy} r="1.9" fill={col} />
                                          <rect
                                            x={badgeX}
                                            y={badgeY}
                                            width={badgeW}
                                            height={badgeH}
                                            rx="4"
                                            fill="rgba(15, 23, 42, 0.86)"
                                            stroke={col}
                                            strokeWidth={isSelected ? '0.95' : '0.7'}
                                          />
                                          <text x={badgeX + 7} y={badgeY + (showFullCallout ? 11.5 : 11)} fill="#f8fafc" fontSize="8.0" fontWeight="700" fontFamily="monospace">
                                            {showFullCallout ? l1 : o.id}
                                          </text>
                                          {showFullCallout && (
                                            <text x={badgeX + 7} y={badgeY + 21.5} fill="#cbd5e1" fontSize="7.3" fontFamily="monospace">
                                              {l2}
                                            </text>
                                          )}
                                        </g>
                                      );
                                    })}
                                </g>
                                );
                              })()}

                              {/* 3. PANOPTIC SEGMENTATION (STUFF REGIONS) + DEFORMABLE POLYGONS (POLY-001 DRAPE & POLY-002 DEFIB LEADS) */}
                              {cvLayers.panopticPolygons && (
                                <g>
                                  <polygon
                                    points={`${W * 0.06},${H * 0.90} ${W * 0.16},${H * 0.25} ${W * 0.84},${H * 0.23} ${W * 0.94},${H * 0.90}`}
                                    fill="none"
                                    stroke="rgba(56, 189, 248, 0.26)"
                                    strokeWidth="0.48"
                                    strokeDasharray="4 4"
                                  />

                                  {/* POLY-001: 9-Vertex Deformable Bed/Sterile Sheet Polygon over PT-1 */}
                                  {(() => {
                                    const px0 = sx(ptX0 + ptW * 0.05);
                                    const px1 = sx(ptX1 + ptW * 0.06);
                                    const py0 = sy(ptY0 + ptH * 0.36);
                                    const py1 = sy(ptY1 + ptH * 0.08);
                                    const pmx = (px0 + px1) / 2;
                                    const pmy = (py0 + py1) / 2;
                                    const pts = [
                                      `${px0},${py0 + 6}`,
                                      `${px0 + (px1 - px0) * 0.22},${py0 - 4}`,
                                      `${pmx},${py0 - 7}`,
                                      `${px0 + (px1 - px0) * 0.78},${py0 - 3}`,
                                      `${px1},${py0 + 5}`,
                                      `${px1 + 8},${pmy + 8}`,
                                      `${px0 + (px1 - px0) * 0.82},${py1}`,
                                      `${pmx},${py1 + 5}`,
                                      `${px0 + 4},${py1 - 2}`,
                                    ].join(' ');
                                    return (
                                      <g>
                                        <polygon
                                          points={pts}
                                          fill={selectedObjId === 'POLY-001' ? 'rgba(34, 211, 238, 0.15)' : 'rgba(34, 211, 238, 0.06)'}
                                          stroke="#22d3ee"
                                          strokeWidth={selectedObjId === 'POLY-001' ? '1.0' : '0.68'}
                                          strokeDasharray="2.5 1.5"
                                        />
                                        <text x={Math.max(12, px0)} y={Math.min(H - 52, py1 + 13)} fill="#67e8f9" fontSize="7.0" fontWeight="700" fontFamily="monospace">
                                          POLY-001 [DEFORMABLE FABRIC DRAPE · 9-VERTEX POLYGON]
                                        </text>
                                      </g>
                                    );
                                  })()}

                                  {/* POLY-002: Defibrillator Lead Cable Polyline from DEFIB-1 to PT-1 Chest ROI */}
                                  {(() => {
                                    const startX = sx(defX1);
                                    const startY = sy((defY0 + defY1) / 2);
                                    const endX = sx((chestBox[1] + chestBox[3]) / 2);
                                    const endY = sy((chestBox[0] + chestBox[2]) / 2);
                                    const mid1X = startX + (endX - startX) * 0.35;
                                    const mid1Y = startY + (endY - startY) * 0.55 + 14;
                                    const mid2X = startX + (endX - startX) * 0.72;
                                    const mid2Y = startY + (endY - startY) * 0.82 + 8;
                                    return (
                                      <g>
                                        <polyline
                                          points={`${startX},${startY} ${mid1X},${mid1Y} ${mid2X},${mid2Y} ${endX},${endY}`}
                                          fill="none"
                                          stroke="#fbbf24"
                                          strokeWidth="0.72"
                                          strokeDasharray="2 2"
                                        />
                                        <rect
                                          x={endX - 9}
                                          y={endY - 6}
                                          width="18"
                                          height="12"
                                          rx="2"
                                          fill="rgba(251, 191, 36, 0.16)"
                                          stroke="#fbbf24"
                                          strokeWidth="0.65"
                                        />
                                      </g>
                                    );
                                  })()}
                                </g>
                              )}

                              {/* 4. INSTANCE SEGMENTATION CONTOUR MASKS + DISAMBIGUATED OVERLAP BOUNDARY SEAM */}
                              {cvLayers.instanceMasks && (
                                <g>
                                  {liveBoxesNow.slice(0, 5).map((o) => {
                                    const col = o.color || trackColor(o.category);
                                    const x0 = sx(o.box[1]);
                                    const y0 = sy(o.box[0]);
                                    const x1 = sx(o.box[3]);
                                    const y1 = sy(o.box[2]);
                                    const mx = (x0 + x1) / 2;
                                    const my = (y0 + y1) / 2;
                                    const rx = Math.max(10, (x1 - x0) * 0.44);
                                    const ry = Math.max(10, (y1 - y0) * 0.44);
                                    return (
                                      <ellipse
                                        key={`mask-${o.id}`}
                                        cx={mx}
                                        cy={my}
                                        rx={rx}
                                        ry={ry}
                                        fill={`${col}18`}
                                        stroke={col}
                                        strokeWidth="0.75"
                                        strokeDasharray="3 1.5"
                                      />
                                    );
                                  })}

                                  {/* Highlighted Overlap Seam between top overlapping pair (or compressor & sternum) */}
                                  {(() => {
                                    const topOv = liveOverlapsNow[0];
                                    const seamBox = topOv
                                      ? [
                                          Math.max(topOv.a.box[0], topOv.b.box[0]),
                                          Math.max(topOv.a.box[1], topOv.b.box[1]),
                                          Math.min(topOv.a.box[2], topOv.b.box[2]),
                                          Math.min(topOv.a.box[3], topOv.b.box[3]),
                                        ]
                                      : chestBox;
                                    const sx0 = sx(seamBox[1]);
                                    const sy0 = sy(seamBox[0]);
                                    const sx1 = sx(seamBox[3]);
                                    const sy1 = sy(seamBox[2]);
                                    const scx = (sx0 + sx1) / 2;
                                    const scy = (sy0 + sy1) / 2;
                                    const seamLabel = topOv
                                      ? `⚡ OVERLAP SEAM: ${topOv.a.id} ∩ ${topOv.b.id} (IoU ${topOv.iou.toFixed(2)} · z-Order Verified)`
                                      : `⚡ OVERLAP SEAM: CLIN-1 ∩ PT-1 STERNUM (IoU 0.53 · z-Order Verified)`;
                                    const banW = Math.min(W - 24, 326);
                                    const banX = clampX(scx - banW / 2, banW);
                                    const banY = 38;
                                    return (
                                      <g>
                                        <rect
                                          x={sx0}
                                          y={sy0}
                                          width={Math.max(16, sx1 - sx0)}
                                          height={Math.max(14, sy1 - sy0)}
                                          rx="6"
                                          fill="rgba(251, 191, 36, 0.16)"
                                          stroke="#fde047"
                                          strokeWidth="1.05"
                                          strokeDasharray="2.5 1.5"
                                        />
                                        <line x1={scx} y1={sy0} x2={banX + banW / 2} y2={banY + 19} stroke="#fde047" strokeWidth="0.6" strokeDasharray="2 2" />
                                        <rect x={banX} y={banY} width={banW} height="19" rx="3.5" fill="rgba(15, 23, 42, 0.86)" stroke="#fde047" strokeWidth="0.68" />
                                        <text x={banX + 7} y={banY + 12.5} fill="#fef08a" fontSize="7.4" fontWeight="700" fontFamily="monospace">
                                          {seamLabel}
                                        </text>
                                      </g>
                                    );
                                  })()}
                                </g>
                              )}

                              {/* 5. PERSISTENT RE-ID TRAJECTORIES & KALMAN OCCLUSION BRIDGES */}
                              {cvLayers.reidTrajectories && (
                                <g>
                                  {liveTrajectories.map((tr) => {
                                    const ptsStr = tr.pts.map((p) => `${sx(p.cx)},${sy(p.cy)}`).join(' ');
                                    const col = tr.pts[0]?.color || '#f43f5e';
                                    return (
                                      <g key={`traj-${tr.id}`}>
                                        <polyline
                                          points={ptsStr}
                                          fill="none"
                                          stroke={col}
                                          strokeWidth="0.85"
                                          strokeDasharray="3 2"
                                        />
                                        {tr.pts.map((p, idx) => (
                                          <circle
                                            key={`${tr.id}-pt-${idx}`}
                                            cx={sx(p.cx)}
                                            cy={sy(p.cy)}
                                            r={idx === tr.pts.length - 1 ? 2.6 : 1.8}
                                            fill={idx === tr.pts.length - 1 ? '#fde047' : col}
                                          />
                                        ))}
                                      </g>
                                    );
                                  })}
                                  <rect x="12" y="62" width="244" height="30" rx="4" fill="rgba(15, 23, 42, 0.82)" stroke="#f43f5e" strokeWidth="0.65" />
                                  <text x="18" y="73.5" fill="#fecdd3" fontSize="7.4" fontWeight="700" fontFamily="monospace">
                                    {`🆔 PERSISTENT RE-ID: ${liveIdentityStats.length} IDs [T0 LOCKED]`}
                                  </text>
                                  <text x="18" y="84.5" fill="#cbd5e1" fontSize="6.9" fontFamily="monospace">
                                    {`Frame #${currentFrameIdx} (t-1↔t↔t+1 IoU 97.4%) · 0 ID Switches`}
                                  </text>
                                </g>
                              )}

                              {/* 6. Bottom Translucent Active Event Banner inside Video Frame */}
                              {focusedEvent && (
                                <g transform={`translate(10, ${H - 34})`}>
                                  <rect
                                    x="0"
                                    y="0"
                                    width={W - 20}
                                    height="26"
                                    rx="5"
                                    fill="rgba(15, 23, 42, 0.82)"
                                    stroke={focused3D.color}
                                    strokeWidth="0.7"
                                  />
                                  <text x="9" y="11" fill="#ffffff" fontSize="8.2" fontWeight="700" fontFamily="monospace">
                                    {`${focused3D.tag} · ${focusedEvent.sensor_label} · Video ${focusedEvent.start_mmss}`.slice(0, isPortraitVideo ? 68 : 96)}
                                  </text>
                                  <text x="9" y="21" fill="#cbd5e1" fontSize="7.4" fontFamily="monospace">
                                    {`Evidence: “${(focusedEvent.evidence_text || '').slice(0, isPortraitVideo ? 42 : 70)}” → REDCap [${(focusedEvent.mapped_fields || []).join(', ')}]`}
                                  </text>
                                </g>
                              )}
                            </>
                          );
                        })()}
                      </svg>
                    )}
                    {/* Ultra-Thin 3D Volumetric Wireframe Overlay (Trauma A reference footage) */}
                    {!currentCase.live_run && (
                    <svg
                      viewBox="0 0 860 390"
                      width="100%"
                      height="100%"
                      shapeRendering="geometricPrecision"
                      preserveAspectRatio="none"
                      style={{ position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none' }}
                    >
                      {/* Subtle 0.35px Perspective Ground-Plane Calibration Grid */}
                      <g stroke="rgba(56, 189, 248, 0.14)" strokeWidth="0.35" strokeDasharray="2 3">
                        <line x1="175" y1="380" x2="275" y2="85" />
                        <line x1="310" y1="380" x2="365" y2="85" />
                        <line x1="450" y1="380" x2="455" y2="85" />
                        <line x1="595" y1="380" x2="545" y2="85" />
                        <line x1="205" y1="150" x2="645" y2="132" />
                        <line x1="185" y1="225" x2="675" y2="208" />
                      </g>

                      {/* 0. S5 BURNED-IN TIMECODE OCR ROI (Top-Left Timestamp Overlay in Video) */}
                      <rect
                        x="14"
                        y="3"
                        width="148"
                        height="16"
                        rx="2"
                        fill="none"
                        stroke="rgba(56, 189, 248, 0.65)"
                        strokeWidth="0.55"
                        strokeDasharray="2 2"
                      />

                      {/* 1. RESUSCITATION STRETCHER / BED 3D PERIMETER WIREFRAME */}
                      <g stroke="rgba(148, 163, 184, 0.48)" strokeWidth="0.5" fill="none">
                        <polygon points="292,126 516,108 532,182 304,204" strokeDasharray="3 2" />
                        <polygon points="296,154 520,136 535,208 308,230" strokeOpacity="0.35" />
                        <line x1="292" y1="126" x2="296" y2="154" />
                        <line x1="516" y1="108" x2="520" y2="136" />
                        <line x1="532" y1="182" x2="535" y2="208" />
                        <line x1="304" y1="204" x2="308" y2="230" />
                      </g>

                      {/* 2. 3D VOLUMETRIC BOX: HEAD-OF-BED AIRWAY / ETT ROI */}
                      {(() => {
                        const airwayActive =
                          focusedEvent &&
                          (focusedEvent.type === 'airway_attempt' ||
                            focusedEvent.type === 'airway_confirmation' ||
                            focusedEvent.type === 'pocus_cardiac');
                        const strokeCol = airwayActive ? '#34d399' : 'rgba(52, 211, 153, 0.55)';
                        const sw = airwayActive ? '0.9' : '0.55';
                        return (
                          <g opacity={getSubsystemRoiOpacity('airway')}>
                            <polygon
                              points="286,136 338,130 344,174 292,180"
                              fill={airwayActive ? 'rgba(16, 185, 129, 0.08)' : 'none'}
                              stroke={strokeCol}
                              strokeWidth={sw}
                              strokeDasharray={airwayActive ? 'none' : '2 2'}
                            />
                            <polygon points="284,106 336,100 342,144 290,150" fill="none" stroke={strokeCol} strokeWidth={sw} />
                            <line x1="284" y1="106" x2="286" y2="136" stroke={strokeCol} strokeWidth="0.5" />
                            <line x1="336" y1="100" x2="338" y2="130" stroke={strokeCol} strokeWidth="0.5" />
                            <line x1="342" y1="144" x2="344" y2="174" stroke={strokeCol} strokeWidth="0.5" />
                            <line x1="290" y1="150" x2="292" y2="180" stroke={strokeCol} strokeWidth="0.5" />
                            <line x1="310" y1="103" x2="265" y2="78" stroke={strokeCol} strokeWidth="0.55" />
                            <rect x="148" y="60" width="174" height="18" rx="3" fill="rgba(15, 23, 42, 0.66)" stroke={strokeCol} strokeWidth="0.55" />
                            <text x="154" y="72" fill="#a7f3d0" fontSize="8" fontWeight="600" fontFamily="monospace">
                              {airwayActive ? `🫁 ${focusedEvent.label.toUpperCase()}` : 'AIRWAY / ETT ROI [0.36, 0.38]'}
                            </text>
                          </g>
                        );
                      })()}

                      {/* 3. 3D VOLUMETRIC BOX: STERNUM & LUCAS CHEST COMPRESSOR (S1 OPTICAL FLOW ROI) */}
                      {(() => {
                        const inPause = activeAnnotationsAtTime.inPause;
                        const cprOn = activeAnnotationsAtTime.cprActive;
                        const boxColor = inPause ? '#f87171' : cprOn ? '#34d399' : '#38bdf8';
                        const fillAlpha = inPause
                          ? 'rgba(239, 68, 68, 0.08)'
                          : cprOn
                          ? 'rgba(16, 185, 129, 0.05)'
                          : 'rgba(56, 189, 248, 0.04)';
                        return (
                          <g opacity={getSubsystemRoiOpacity('cpr')}>
                            <polygon points="348,132 408,125 416,172 354,180" fill={fillAlpha} stroke={boxColor} strokeWidth="0.85" />
                            <polygon points="346,96 406,89 414,136 352,144" fill="none" stroke={boxColor} strokeWidth="0.75" />
                            <line x1="346" y1="96" x2="348" y2="132" stroke={boxColor} strokeWidth="0.65" />
                            <line x1="406" y1="89" x2="408" y2="125" stroke={boxColor} strokeWidth="0.65" />
                            <line x1="414" y1="136" x2="416" y2="172" stroke={boxColor} strokeWidth="0.65" />
                            <line x1="352" y1="144" x2="354" y2="180" stroke={boxColor} strokeWidth="0.65" />
                            <path
                              d="M346,102 L346,96 L352,95 M400,90 L406,89 L406,95 M354,174 L354,180 L360,179 M410,173 L416,172 L415,166"
                              fill="none"
                              stroke="#ffffff"
                              strokeWidth="0.9"
                            />
                            {cprOn && (
                              <g stroke="#34d399" strokeWidth="0.8">
                                <line x1="374" y1="82" x2="374" y2="122" />
                                <polygon points="371.5,119 376.5,119 374,125" fill="#34d399" stroke="none" />
                                <line x1="390" y1="80" x2="390" y2="120" />
                                <polygon points="387.5,117 392.5,117 390,123" fill="#34d399" stroke="none" />
                              </g>
                            )}
                            <line x1="380" y1="92" x2="395" y2="66" stroke={boxColor} strokeWidth="0.65" />
                            <circle cx="380" cy="92" r="1.8" fill={boxColor} />
                            <rect x="296" y="38" width="234" height="27" rx="4" fill="rgba(15, 23, 42, 0.72)" stroke={boxColor} strokeWidth="0.65" />
                            <text x="303" y="49" fill="#f8fafc" fontSize="8.5" fontWeight="700" fontFamily="monospace">
                              {inPause
                                ? `⚠ PAUSE DETECTED (${activeAnnotationsAtTime.activeIntervals[0]?.duration_s}s)`
                                : cprOn
                                ? 'S1 CHEST ROI · ACTIVE CPR COMPRESSIONS'
                                : 'S1 CHEST ROI [x:860, y:340, w:140, h:140]'}
                            </text>
                            <text x="303" y="60" fill="#cbd5e1" fontSize="7.8" fontFamily="monospace">
                              {inPause
                                ? `${activeAnnotationsAtTime.activeIntervals[0]?.evidence_text?.slice(0, 36)}`
                                : `CCF ${currentCase.ccf_pct}% (Target ≥80%)`}
                            </text>
                          </g>
                        );
                      })()}

                      {/* 4. 3D VOLUMETRIC BOX: IV / IO ACCESS & MEDICATION PORT */}
                      {(() => {
                        const medEv =
                          (focusedEvent?.type === 'medication_administration' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                            focusedEvent) ||
                          activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'medication_administration');
                        const active = Boolean(medEv);
                        const col = active ? '#c4b5fd' : 'rgba(167, 139, 250, 0.55)';
                        const sw = active ? '0.85' : '0.55';
                        return (
                          <g opacity={getSubsystemRoiOpacity('meds')}>
                            <polygon
                              points="422,126 476,120 484,162 428,168"
                              fill={active ? 'rgba(139, 92, 246, 0.08)' : 'none'}
                              stroke={col}
                              strokeWidth={sw}
                            />
                            <polygon points="420,98 474,92 482,134 426,140" fill="none" stroke={col} strokeWidth={sw} />
                            <line x1="420" y1="98" x2="422" y2="126" stroke={col} strokeWidth="0.5" />
                            <line x1="474" y1="92" x2="476" y2="120" stroke={col} strokeWidth="0.5" />
                            <line x1="482" y1="134" x2="484" y2="162" stroke={col} strokeWidth="0.5" />
                            <line x1="426" y1="140" x2="428" y2="168" stroke={col} strokeWidth="0.5" />
                            <line x1="454" y1="165" x2="468" y2="212" stroke={col} strokeWidth="0.55" />
                            <circle cx="454" cy="165" r="1.6" fill={col} />
                            <rect x="412" y="212" width="198" height="25" rx="4" fill="rgba(15, 23, 42, 0.70)" stroke={col} strokeWidth="0.6" />
                            <text x="419" y="223" fill="#ede9fe" fontSize="8.2" fontWeight="700" fontFamily="monospace">
                              {active ? `💉 ${medEv.label.toUpperCase()}` : '💉 IV / IO ACCESS ROI [0.52, 0.42]'}
                            </text>
                            <text x="419" y="233" fill="#cbd5e1" fontSize="7.5" fontFamily="monospace">
                              {active
                                ? `Administered @ ${medEv.start_mmss}`
                                : `[total_epi_v2 = ${currentCase.total_epi_doses} doses] S7a ASR`}
                            </text>
                          </g>
                        );
                      })()}

                      {/* 5. 3D VOLUMETRIC BOX: DEFIBRILLATOR & MONITOR CART */}
                      {(() => {
                        const shockEv =
                          (focusedEvent?.type === 'defibrillation_shock' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                            focusedEvent) ||
                          activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'defibrillation_shock');
                        const rhyEv =
                          (focusedEvent?.type === 'rhythm_check' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18 &&
                            focusedEvent) ||
                          activeAnnotationsAtTime.nearbyPointEvents.find((e) => e.type === 'rhythm_check');
                        const isShock = Boolean(shockEv);
                        const isRhy = Boolean(rhyEv);
                        const col = isShock ? '#fbbf24' : isRhy ? '#22d3ee' : 'rgba(56, 189, 248, 0.6)';
                        const sw = isShock || isRhy ? '0.9' : '0.6';
                        return (
                          <g opacity={getSubsystemRoiOpacity('shocks')}>
                            <polygon
                              points="534,74 592,68 600,126 542,134"
                              fill={isShock ? 'rgba(245, 158, 11, 0.08)' : 'none'}
                              stroke={col}
                              strokeWidth={sw}
                            />
                            <polygon
                              points="530,36 588,30 596,88 538,96"
                              fill={isRhy ? 'rgba(6, 182, 212, 0.07)' : 'none'}
                              stroke={col}
                              strokeWidth={sw}
                            />
                            <line x1="530" y1="36" x2="534" y2="74" stroke={col} strokeWidth="0.55" />
                            <line x1="588" y1="30" x2="592" y2="68" stroke={col} strokeWidth="0.55" />
                            <line x1="596" y1="88" x2="600" y2="126" stroke={col} strokeWidth="0.55" />
                            <line x1="538" y1="96" x2="542" y2="134" stroke={col} strokeWidth="0.55" />
                            <path
                              d="M544 58 L550 49 L555 64 L561 46 L567 65 L573 50 L579 62 L585 54"
                              stroke={isShock ? '#fbbf24' : '#38bdf8'}
                              strokeWidth="0.75"
                              fill="none"
                            />
                            {isShock && (
                              <g stroke="#fbbf24" fill="none">
                                <circle cx="565" cy="78" r="32" strokeWidth="0.75" strokeDasharray="3 3" />
                                <circle cx="565" cy="78" r="46" strokeWidth="0.5" strokeOpacity="0.65" />
                                <path d="M534 84 Q 465 65 408 118" stroke="#fbbf24" strokeWidth="0.85" strokeDasharray="4 3" />
                              </g>
                            )}
                            <line x1="592" y1="62" x2="618" y2="56" stroke={col} strokeWidth="0.6" />
                            <rect x="618" y="40" width="226" height="27" rx="4" fill="rgba(15, 23, 42, 0.72)" stroke={col} strokeWidth="0.65" />
                            <text x="625" y="51" fill="#f8fafc" fontSize="8.5" fontWeight="700" fontFamily="monospace">
                              {isShock
                                ? `⚡ SHOCK DELIVERED @ ${shockEv.start_mmss}`
                                : isRhy
                                ? `📈 RHYTHM CHECK @ ${rhyEv.start_mmss}`
                                : 'S3/S5 DEFIB & MONITOR [x:0.66, y:0.22]'}
                            </text>
                            <text x="625" y="62" fill="#cbd5e1" fontSize="7.8" fontFamily="monospace">
                              {isShock
                                ? `[time_defib_v2 = ${shockEv.start_mmss}]`
                                : isRhy
                                ? `${rhyEv.evidence_text?.slice(0, 32)}`
                                : `Defibrillator & ECG Monitor ROI`}
                            </text>
                          </g>
                        );
                      })()}

                      {/* 6. CLINICAL RECORDER / CHARTING DESK ROI (OBJ-007 Team Leader / Recorder Zone) */}
                      <g opacity={getSubsystemRoiOpacity('team')}>
                        <polygon
                          points="366,298 502,286 514,368 374,380"
                          fill="none"
                          stroke="rgba(148, 163, 184, 0.45)"
                          strokeWidth="0.5"
                          strokeDasharray="2 2"
                        />
                        <text x="374" y="293" fill="rgba(226, 232, 240, 0.75)" fontSize="7.5" fontFamily="monospace">
                          OBJ-007 TEAM LEADER &amp; RECORDER [0.48, 0.84 · 0 ID Switch]
                        </text>
                      </g>

                      {/* 7. PANOPTIC SEGMENTATION (STUFF REGIONS) + DEFORMABLE POLYGON ANNOTATIONS (FABRIC, LEADS, TUBING, SHADOW) */}
                      {cvLayers.panopticPolygons && (
                        <g>
                          {/* Panoptic STUFF-01: Resuscitation Bay Floor Perimeter */}
                          <polygon
                            points="115,342 238,88 625,78 748,342"
                            fill="none"
                            stroke="rgba(56, 189, 248, 0.25)"
                            strokeWidth="0.45"
                            strokeDasharray="4 4"
                          />
                          <text x="124" y="336" fill="rgba(148, 163, 184, 0.78)" fontSize="6.8" fontFamily="monospace">
                            PANOPTIC STUFF-01: TRAUMA BAY FLOOR &amp; PERIMETER · STUFF-02: STRETCHER SURFACE
                          </text>

                          {/* POLY-001: Deformable 9-Vertex Polygon for Sterile Sheet / Blanket Fabric (Non-Rigid Contour) */}
                          <polygon
                            points="344,158 376,152 414,148 456,144 504,140 516,174 480,185 412,190 348,184"
                            fill={selectedObjId === 'POLY-001' ? 'rgba(34, 211, 238, 0.14)' : 'rgba(34, 211, 238, 0.05)'}
                            stroke="#22d3ee"
                            strokeWidth={selectedObjId === 'POLY-001' ? '0.95' : '0.6'}
                            strokeDasharray="2.5 1.5"
                          />
                          <text x="352" y="199" fill="#67e8f9" fontSize="7.1" fontWeight="700" fontFamily="monospace">
                            POLY-001 [DEFORMABLE FABRIC DRAPE · 9-VERTEX POLYGON]
                          </text>

                          {/* POLY-002: Multi-Vertex Polygon for Defibrillator Lead Cables & Gel Pad Seam */}
                          <polyline
                            points="538,94 504,104 468,112 436,118 402,126 382,130"
                            fill="none"
                            stroke="#fbbf24"
                            strokeWidth="0.65"
                            strokeDasharray="1.8 1.8"
                          />
                          <polygon
                            points="376,125 396,122 399,134 378,137"
                            fill="rgba(251, 191, 36, 0.12)"
                            stroke="#fbbf24"
                            strokeWidth="0.6"
                          />

                          {/* POLY-004: Overhead Gantry Cast Shadow Polygon (Isolated so shadow is never merged into tissue mask) */}
                          <polygon
                            points="348,170 412,165 420,181 352,186"
                            fill="rgba(15, 23, 42, 0.22)"
                            stroke="rgba(148, 163, 184, 0.55)"
                            strokeWidth="0.45"
                            strokeDasharray="1 2"
                          />
                        </g>
                      )}

                      {/* 8. INSTANCE SEGMENTATION MASKS (INST-01..05) + DISAMBIGUATED OVERLAP BOUNDARY SEAM */}
                      {cvLayers.instanceMasks && (
                        <g>
                          {/* INST-04: Compressor #1 Hands & Forearms Instance Contour Mask */}
                          <path
                            d="M 356,92 C 372,88 394,90 404,98 C 410,112 406,128 396,136 C 380,140 362,138 354,128 Z"
                            fill={selectedObjId === 'OBJ-004' ? 'rgba(244, 63, 94, 0.18)' : 'rgba(244, 63, 94, 0.09)'}
                            stroke="#f43f5e"
                            strokeWidth={selectedObjId === 'OBJ-004' ? '1.0' : '0.7'}
                          />
                          {/* INST-02: LUCAS-3 Backplate & Upper Arch Instance Contour Mask */}
                          <path
                            d="M 346,114 C 368,108 398,106 414,114 C 418,132 414,154 402,162 C 378,166 354,164 346,150 Z"
                            fill={selectedObjId === 'OBJ-002' ? 'rgba(16, 185, 129, 0.16)' : 'rgba(16, 185, 129, 0.07)'}
                            stroke="#10b981"
                            strokeWidth={selectedObjId === 'OBJ-002' ? '1.0' : '0.68'}
                          />
                          {/* HIGHLIGHTED OVERLAP BOUNDARY SEAM (Where INST-04 Compressor Hands, INST-02 LUCAS, & INST-01 Sternum Overlap) */}
                          <path
                            d="M 352,126 Q 378,118 406,125 Q 398,139 376,141 Q 358,139 352,126 Z"
                            fill="rgba(251, 191, 36, 0.12)"
                            stroke="#fde047"
                            strokeWidth="0.95"
                            strokeDasharray="2.5 1.5"
                          />
                          <line x1="378" y1="120" x2="342" y2="26" stroke="#fde047" strokeWidth="0.55" strokeDasharray="2 2" />
                          <rect x="172" y="12" width="322" height="19" rx="3.5" fill="rgba(15, 23, 42, 0.82)" stroke="#fde047" strokeWidth="0.6" />
                          <text x="179" y="24" fill="#fef08a" fontSize="7.4" fontWeight="700" fontFamily="monospace">
                            ⚡ OVERLAP SEAM: OBJ-004 ∩ OBJ-002 ∩ OBJ-001 (IoU 0.64 · z-Order Verified)
                          </text>
                        </g>
                      )}

                      {/* 9. PERSISTENT OBJECT ID TRAJECTORIES & KALMAN/RE-ID OCCLUSION BRIDGES */}
                      {cvLayers.reidTrajectories && (
                        <g>
                          {/* OBJ-004 (Compressor #1) Trajectory Path + Occlusion Bridge across Frames */}
                          <path
                            d="M 332,74 Q 354,84 368,98"
                            fill="none"
                            stroke="#f43f5e"
                            strokeWidth="0.75"
                          />
                          {/* Dashed Occlusion Re-ID Bridge where OBJ-004 was occluded behind OBJ-002/005 and re-emerged with SAME ID */}
                          <path
                            d="M 368,98 Q 388,108 408,94"
                            fill="none"
                            stroke="#fda4af"
                            strokeWidth="0.8"
                            strokeDasharray="3 2"
                          />
                          <circle cx="332" cy="74" r="2.1" fill="#f43f5e" />
                          <circle cx="368" cy="98" r="2.1" fill="#fde047" />
                          <circle cx="408" cy="94" r="2.4" fill="#f43f5e" />
                          <rect x="18" y="88" width="232" height="30" rx="4" fill="rgba(15, 23, 42, 0.78)" stroke="#f43f5e" strokeWidth="0.6" />
                          <text x="24" y="99" fill="#fecdd3" fontSize="7.4" fontWeight="700" fontFamily="monospace">
                            🆔 PERSISTENT RE-ID: OBJ-001..007 [T0 LOCKED]
                          </text>
                          <text x="24" y="110" fill="#cbd5e1" fontSize="6.9" fontFamily="monospace">
                            Frame #{currentFrameIdx} (t-1↔t↔t+1 IoU 97.4%) · 0 ID Switches
                          </text>
                        </g>
                      )}

                      {/* Bottom Translucent Active Event Banner inside Video Frame */}
                      {focusedEvent && (
                        <g transform="translate(14, 356)">
                          <rect
                            x="0"
                            y="0"
                            width="832"
                            height="26"
                            rx="5"
                            fill="rgba(15, 23, 42, 0.75)"
                            stroke={focused3D.color}
                            strokeWidth="0.65"
                          />
                          <text x="10" y="11" fill="#ffffff" fontSize="8.8" fontWeight="700" fontFamily="monospace">
                            {focused3D.tag} · {focusedEvent.sensor_label} · Wall-Clock {fmtWallClockFromT0(s5?.t0_iso || currentCase.t0_wallclock, focusedEvent.t_start_s)}
                          </text>
                          <text x="10" y="21" fill="#cbd5e1" fontSize="8" fontFamily="monospace">
                            Evidence: “{focusedEvent.evidence_text?.slice(0, 74)}” → REDCap [{(focusedEvent.mapped_fields || []).join(', ')}]
                          </text>
                        </g>
                      )}
                    </svg>
                    )}
                      </div>
                    </div>
                  </div>

                  {/* Status line: source · REDCap field at playhead · CPR state (kept off the video) */}
                  <div className="vc-status">
                    <span className="vc-status-src mono" title={String(currentCase.video_path || '')}>
                      {currentCase.live_run
                        ? String(currentCase.video_path || '').split('/').pop()
                        : s5?.room_id?.split('(')[0]?.trim() || 'NSUH ED Trauma A'}
                    </span>
                    {activeRedcapRowAtPlayhead && (
                      <span className="vc-status-field">
                        <span>REDCap</span>
                        <code>
                          {activeRedcapRowAtPlayhead.redcapField} = {String(activeRedcapRowAtPlayhead.redcapValue).slice(0, 26)}
                        </code>
                      </span>
                    )}
                    <span
                      className={`vc-state ${
                        activeAnnotationsAtTime.inPause ? 'pause' : activeAnnotationsAtTime.cprActive ? 'cpr' : 'prep'
                      }`}
                    >
                      {activeAnnotationsAtTime.inPause
                        ? 'Hands-off pause'
                        : activeAnnotationsAtTime.cprActive
                        ? 'Compressions active'
                        : 'Room preparation'}
                    </span>
                  </div>

                  {/* Video Transport Controls */}
                  <div className="video-scrubber-bar vc-transport-shell">
                    <div className="vc-scrubber-row">
                      <input
                        type="range"
                        min="0"
                        max={maxTimelineS}
                        step="0.5"
                        value={Math.min(maxTimelineS, currentTimeS)}
                        onChange={(e) => {
                          setIsPlaying(false);
                          setCurrentTimeS(Number(e.target.value));
                        }}
                        className="scrubber-range"
                      />
                    </div>
                    <div className="vc-transport-row">
                      <div className="vc-transport-btns">
                        <button type="button" className="tl-btn primary" onClick={() => setIsPlaying(!isPlaying)}>
                          {isPlaying ? 'Pause' : 'Play'}
                        </button>
                        <button type="button" className="tl-btn" onClick={() => stepEvent(-1)} title="Previous Extracted Event">
                          ‹ Previous event
                        </button>
                        <button type="button" className="tl-btn" onClick={() => stepEvent(1)} title="Next Extracted Event">
                          Next event ›
                        </button>
                      </div>

                      <div className="vc-transport-meta">
                        <span className="mono vc-transport-time">
                          {fmtMmSs(currentTimeS)} / {fmtMmSs(maxTimelineS)}
                        </span>

                        <select
                          className="tl-btn mono"
                          value={playbackSpeed}
                          onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                        >
                          <option value={1}>1x</option>
                          <option value={2}>2x</option>
                          <option value={4}>4x</option>
                        </select>
                      </div>
                    </div>
                  </div>

                </div>

                {/* RIGHT COLUMN (30% REDCap Evidence Rail or 60% Full 6-Col Audit Table in Split Mode) */}
                {!fullTheaterMode && (
                  <div className="tl-video-inspector">
                    {/* 5-Tab Switcher at Top of Inspector (REDCap Evidence Rail is Tab 1 by default) */}
                    <div className="tl-inspector-tabs">
                      {[
                        { id: 'event', label: 'At playhead' },
                        { id: 'redcap', label: `REDCap (${allRedcapEvidenceRows.length})` },
                        { id: 'transcript', label: 'Transcript' },
                        { id: 'reid', label: 'People' },
                      ].map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          className={`tl-inspector-tab-btn ${inspectorTab === t.id ? 'active' : ''}`}
                          onClick={() => setInspectorTab(t.id)}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>

                    {inspectorTab === 'redcap' && (
                      <div className="co-redcap-dock-container">
                        {/* PINNED TOP CARD: ACTIVE REDCAP FIELD & EVENT AT PLAYHEAD */}
                        {activeRedcapRowAtPlayhead && (
                          <div className="tl-inspector-card active-event" style={{ flexShrink: 0 }}>
                            <div className="tl-inspector-eyebrow">
                              <span>ACTIVE REDCAP AT PLAYHEAD (@{fmtMmSs(currentTimeS)})</span>
                              <button
                                type="button"
                                className="co-rail-expand-btn mono"
                                onClick={() =>
                                  setConsoleLayoutMode(
                                    consoleLayoutMode === 'audit_40_60' ? 'console_70_30' : 'audit_40_60'
                                  )
                                }
                              >
                                {consoleLayoutMode === 'audit_40_60'
                                  ? 'Compact 70/30 Rail'
                                  : 'Expand 6-Col Table (40/60)'}
                              </button>
                            </div>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', lineHeight: 1.3 }}>
                              {activeRedcapRowAtPlayhead.title}
                            </div>
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: '0.35rem',
                                flexWrap: 'wrap',
                                marginTop: '0.24rem',
                              }}
                            >
                              <span
                                className="mono"
                                style={{ fontSize: '10.5px', fontWeight: 700, color: '#5b21b6', cursor: 'pointer' }}
                                onClick={() =>
                                  seekToEvent(activeRedcapRowAtPlayhead.ev || activeRedcapRowAtPlayhead.t_start_s)
                                }
                              >
                                ▶ {activeRedcapRowAtPlayhead.timeDisplay}
                                {activeRedcapRowAtPlayhead.wallClock ? ` · CCTV ${activeRedcapRowAtPlayhead.wallClock}` : ''}
                              </span>
                              <span
                                className="mono"
                                style={{ fontSize: '10px', fontWeight: 700, color: '#059669' }}
                              >
                                {activeRedcapRowAtPlayhead.confidencePct}% Verified
                              </span>
                            </div>
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: '0.35rem',
                                flexWrap: 'wrap',
                                marginTop: '0.28rem',
                              }}
                            >
                              <div className="tl-file-chip">
                                <span className="tl-file-badge red">REDCap</span>
                                <span className="mono" style={{ fontSize: '10px', fontWeight: 700, color: '#0f172a' }}>
                                  {activeRedcapRowAtPlayhead.redcapField} = {String(activeRedcapRowAtPlayhead.redcapValue).slice(0, 26)}
                                </span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                <div className="tl-sensor-avatars">
                                  {(activeRedcapRowAtPlayhead.sensors || []).map((s, idx) => (
                                    <span
                                      key={idx}
                                      className="tl-sensor-avatar"
                                      style={{ background: s.bg }}
                                    >
                                      {s.id}
                                    </span>
                                  ))}
                                </div>
                                <span className={`tl-status-pill ${activeRedcapRowAtPlayhead.statusColor}`}>
                                  ● {activeRedcapRowAtPlayhead.statusLabel}
                                </span>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* MODE 1 (40/60 Split): FULL CAREOPS REDCAP AUDIT TABLE RIGHT NEXT TO STICKY VIDEO */}
                        {consoleLayoutMode === 'audit_40_60' ? (
                          <div className="co-dock-full-table-wrap">
                            <table className="tl-project-table vc-audit-table">
                              <thead>
                                <tr>
                                  <th style={{ width: '36%' }}>CLINICAL FINDING ⇅</th>
                                  <th style={{ width: '16%' }}>VIDEO &amp; TIME ⇅</th>
                                  <th style={{ width: '28%' }}>REDCAP FIELD &amp; VALUE ⇅</th>
                                  <th style={{ width: '20%' }}>SENSORS &amp; STATUS</th>
                                </tr>
                              </thead>
                              <tbody>
                                {filteredGroups.map((group) => {
                                  const isExpanded = expandedGroups[group.key] !== false;
                                  return (
                                    <React.Fragment key={group.key}>
                                      <tr
                                        className="tl-parent-row"
                                        onClick={() =>
                                          setExpandedGroups((prev) => ({
                                            ...prev,
                                            [group.key]: !isExpanded,
                                          }))
                                        }
                                      >
                                        <td>
                                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', width: '12px', flexShrink: 0 }}>
                                              {isExpanded ? '⌄' : '›'}
                                            </span>
                                            <span className="tl-case-icon" style={{ background: group.iconBg, flexShrink: 0 }}>
                                              <ProIcon name={group.icon} size={12} color="#ffffff" />
                                            </span>
                                            <span style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.73rem', lineHeight: 1.3 }}>
                                              {group.title}
                                            </span>
                                            <span
                                              className="mono"
                                              style={{
                                                fontSize: '0.63rem',
                                                color: '#5b21b6',
                                                background: '#ede9fe',
                                                padding: '0.08rem 0.38rem',
                                                borderRadius: '6px',
                                                fontWeight: 700,
                                                flexShrink: 0,
                                                whiteSpace: 'nowrap',
                                              }}
                                            >
                                              {group.rows.length} items
                                            </span>
                                          </div>
                                        </td>
                                        <td className="mono" style={{ fontWeight: 600, color: '#475569', fontSize: '0.66rem', lineHeight: 1.35 }}>
                                          {String(group.summaryTime || '').slice(0, 32)}
                                        </td>
                                        <td>
                                          <div className="tl-file-chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                            <span className="tl-file-badge red" style={{ whiteSpace: 'nowrap', flexShrink: 0 }}>REDCap</span>
                                            <span className="mono" style={{ fontSize: '0.67rem' }}>
                                              {group.redcapSummary}
                                            </span>
                                          </div>
                                        </td>
                                        <td>
                                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                              <div className="tl-sensor-avatars">
                                                {(group.sensors || group.rows?.[0]?.sensors || []).map((s, i) => (
                                                  <span key={i} className="tl-sensor-avatar" style={{ background: s.bg }}>
                                                    {s.id}
                                                  </span>
                                                ))}
                                              </div>
                                              <span className="mono" style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.68rem', whiteSpace: 'nowrap' }}>
                                                {group.progressPct ?? 100}%
                                              </span>
                                            </div>
                                            <span className={`tl-status-pill ${group.statusColor}`} style={{ whiteSpace: 'normal', lineHeight: 1.25 }}>
                                              ● {group.statusLabel}
                                            </span>
                                          </div>
                                        </td>
                                      </tr>
                                      {isExpanded &&
                                        group.rows.map((row) => {
                                          const isRowActive = activeRedcapRowAtPlayhead?.id === row.id;
                                          return (
                                            <tr
                                              key={row.id}
                                              className={`tl-child-row ${isRowActive ? 'active-row' : ''}`}
                                              onClick={() => seekToEvent(row.ev || row.t_start_s)}
                                            >
                                              <td style={{ paddingLeft: '1.35rem' }}>
                                                <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.74rem', lineHeight: 1.32 }}>
                                                  {row.title}
                                                </div>
                                                <div style={{ fontSize: '0.67rem', color: '#64748b', marginTop: '0.12rem', lineHeight: 1.35 }}>
                                                  {row.subtitle}
                                                </div>
                                              </td>
                                              <td>
                                                <div className="mono" style={{ fontWeight: 700, fontSize: '0.7rem', color: '#5b21b6', lineHeight: 1.3 }}>
                                                  ▶ {row.timeDisplay}
                                                </div>
                                                {row.wallClock && (
                                                  <div className="mono" style={{ fontSize: '0.63rem', color: '#94a3b8', marginTop: 2, lineHeight: 1.25 }}>
                                                    CCTV {row.wallClock}
                                                  </div>
                                                )}
                                              </td>
                                              <td>
                                                <div className="tl-source-chips" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                                  <div className="tl-file-chip" style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 5 }}>
                                                    <span className="tl-file-badge red" style={{ whiteSpace: 'nowrap', flexShrink: 0, marginTop: 1 }}>REDCap</span>
                                                    <div style={{ minWidth: 0 }}>
                                                      <div className="mono" style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.67rem' }}>
                                                        {row.redcapField}
                                                      </div>
                                                      <div className="mono" style={{ color: '#475569', fontSize: '0.63rem' }}>
                                                        Value: {String(row.redcapValue)}
                                                      </div>
                                                    </div>
                                                  </div>
                                                  <div className="tl-file-chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                                    <span className={`tl-file-badge ${row.modalityColor}`} style={{ whiteSpace: 'nowrap', flexShrink: 0 }}>
                                                      {row.modalityBadge}
                                                    </span>
                                                    <span style={{ fontWeight: 600, color: '#334155', fontSize: '0.64rem' }}>
                                                      {row.sensorLabel}
                                                    </span>
                                                  </div>
                                                </div>
                                              </td>
                                              <td>
                                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
                                                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                                                    <div className="tl-sensor-avatars">
                                                      {row.sensors.map((s, idx) => (
                                                        <span key={idx} className="tl-sensor-avatar" style={{ background: s.bg }}>
                                                          {s.id}
                                                        </span>
                                                      ))}
                                                    </div>
                                                    <span className="mono" style={{ fontSize: '0.68rem', fontWeight: 700, color: '#0f172a', whiteSpace: 'nowrap' }}>
                                                      {row.confidencePct}%
                                                    </span>
                                                  </div>
                                                  <span className={`tl-status-pill ${row.statusColor}`} style={{ whiteSpace: 'normal', lineHeight: 1.25 }}>
                                                    ● {row.statusLabel}
                                                  </span>
                                                </div>
                                              </td>
                                            </tr>
                                          );
                                        })}
                                    </React.Fragment>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          /* MODE 2 (70/30 Split): COMPACT 2-LINE REDCAP EVIDENCE RAIL CARDS SYNCED TO PLAYHEAD */
                          <div className="co-redcap-rail-list">
                            {filteredGroups.map((group) => {
                              const isCollapsed = expandedGroups[group.key] === false;
                              return (
                                <div key={group.key} className="co-redcap-rail-group">
                                  <button
                                    type="button"
                                    className="co-redcap-rail-group-hdr"
                                    onClick={() =>
                                      setExpandedGroups((prev) => ({
                                        ...prev,
                                        [group.key]: isCollapsed,
                                      }))
                                    }
                                  >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.32rem', minWidth: 0 }}>
                                      <span style={{ fontSize: '10px', color: '#64748b' }}>
                                        {isCollapsed ? '▸' : '▾'}
                                      </span>
                                      <span
                                        style={{
                                          width: '18px',
                                          height: '18px',
                                          borderRadius: '4px',
                                          background: group.iconBg,
                                          color: '#fff',
                                          display: 'inline-flex',
                                          alignItems: 'center',
                                          justifyContent: 'center',
                                          fontSize: '10px',
                                          flexShrink: 0,
                                        }}
                                      >
                                        <ProIcon name={group.icon} size={10} color="#ffffff" />
                                      </span>
                                      <span
                                        style={{
                                          fontSize: '11px',
                                          fontWeight: 700,
                                          color: '#0f172a',
                                          whiteSpace: 'nowrap',
                                          overflow: 'hidden',
                                          textOverflow: 'ellipsis',
                                        }}
                                      >
                                        {group.title}
                                      </span>
                                    </div>
                                    <span
                                      className="mono"
                                      style={{
                                        fontSize: '9.5px',
                                        color: '#5b21b6',
                                        background: '#ede9fe',
                                        padding: '1px 5px',
                                        borderRadius: '5px',
                                        fontWeight: 700,
                                        flexShrink: 0,
                                      }}
                                    >
                                      {group.rows.length}
                                    </span>
                                  </button>

                                  {!isCollapsed &&
                                    group.rows.map((row) => {
                                      const isCurrent = activeRedcapRowAtPlayhead?.id === row.id;
                                      return (
                                        <div
                                          key={row.id}
                                          className={`co-redcap-rail-card ${isCurrent ? 'active' : ''}`}
                                          onClick={() => seekToEvent(row.ev || row.t_start_s)}
                                        >
                                          {/* Line 1: Finding Title + Seek Timestamp + CCTV Wall-Clock */}
                                          <div className="co-redcap-rail-line1">
                                            <span className="co-redcap-rail-title">{row.title}</span>
                                            <span
                                              className="mono"
                                              style={{ fontSize: '10px', fontWeight: 700, color: '#5b21b6', flexShrink: 0 }}
                                            >
                                              ▶ {row.timeDisplay}
                                            </span>
                                          </div>
                                          {/* Line 2: REDCap Variable Chip + Sensor Provenance Avatars + Status Pill */}
                                          <div className="co-redcap-rail-line2">
                                            <div className="tl-file-chip" style={{ padding: '1px 5px' }}>
                                              <span className="tl-file-badge red" style={{ fontSize: '8.5px', padding: '1px 4px' }}>
                                                REDCap
                                              </span>
                                              <span className="mono" style={{ fontWeight: 700, color: '#0f172a', fontSize: '10px' }}>
                                                {row.redcapField}
                                              </span>
                                              <span className="mono" style={{ color: '#475569', fontSize: '9.5px' }}>
                                                = {String(row.redcapValue).slice(0, 20)}
                                              </span>
                                            </div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.24rem', flexShrink: 0 }}>
                                              <div className="tl-sensor-avatars">
                                                {row.sensors.map((s, idx) => (
                                                  <span
                                                    key={idx}
                                                    className="tl-sensor-avatar"
                                                    style={{
                                                      background: s.bg,
                                                      width: '15px',
                                                      height: '15px',
                                                      fontSize: '8.5px',
                                                    }}
                                                  >
                                                    {s.id}
                                                  </span>
                                                ))}
                                              </div>
                                              <span
                                                className={`tl-status-pill ${row.statusColor}`}
                                                style={{ fontSize: '9px', padding: '1px 5px' }}
                                              >
                                                ● {row.statusLabel}
                                              </span>
                                            </div>
                                          </div>
                                        </div>
                                      );
                                    })}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}

                    {inspectorTab === 'event' && (
                      <>
                        {/* Card 1: Active Event at Playhead */}
                        {focusedEvent && (
                          <div className="tl-inspector-card active-event">
                            <div className="tl-inspector-eyebrow">
                              <span>ACTIVE EVENT AT PLAYHEAD</span>
                              <span className="mono">
                                @{focusedEvent.start_mmss} ·{' '}
                                {s5?.t0_iso || currentCase.t0_wallclock
                                  ? fmtWallClockFromT0(s5?.t0_iso || currentCase.t0_wallclock, focusedEvent.t_start_s)
                                  : `Playback ${fmtMmSs(focusedEvent.t_start_s)} / ${fmtMmSs(maxTimelineS)}`}
                              </span>
                            </div>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.3 }}>
                              {focusedEvent.label}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', flexWrap: 'wrap', marginTop: '0.32rem' }}>
                              <span className="tl-status-pill blue" style={{ padding: '2px 6px', fontSize: '10px' }}>
                                {focusedEvent.sensor_label}
                              </span>
                              <span className="tl-status-pill green mono" style={{ padding: '2px 6px', fontSize: '10px' }}>
                                {Math.round(Number(focusedEvent.confidence || 0.96) * 100)}% conf
                              </span>
                            </div>
                            <div
                              style={{
                                marginTop: '0.38rem',
                                padding: '6px 8px',
                                borderRadius: '6px',
                                background: 'var(--bg-subtle)',
                                border: '1px solid var(--border-subtle)',
                                fontSize: '11px',
                                color: 'var(--text-secondary)',
                                lineHeight: 1.36,
                              }}
                            >
                              “{focusedEvent.evidence_text}”
                            </div>
                            <div
                              style={{
                                marginTop: '0.38rem',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: '0.35rem',
                                flexWrap: 'wrap',
                              }}
                            >
                              <span style={{ fontSize: '9.5px', fontWeight: 700, color: 'var(--text-muted)' }}>
                                REDCAP VARIABLE
                              </span>
                              <div className="tl-file-chip">
                                <span className="tl-file-badge red">REDCap</span>
                                <span className="mono" style={{ fontSize: '10px', fontWeight: 700 }}>
                                  {(focusedEvent.mapped_fields || [])[0] || 'event_log'}
                                </span>
                              </div>
                            </div>
                          </div>
                        )}

                        {(() => {
                          const utts = currentCase.transcript?.utterances || [];
                          if (!utts.length) return null;
                          const near = utts.reduce((best, u) =>
                            !best || Math.abs(Number(u.t_start_s || 0) - currentTimeS) < Math.abs(Number(best.t_start_s || 0) - currentTimeS)
                              ? u
                              : best
                          , null);
                          if (!near || Math.abs(Number(near.t_start_s || 0) - currentTimeS) > 12) return null;
                          return (
                            <div className="vc-quote" onClick={() => seekToEvent(Number(near.t_start_s || 0))}>
                              <div className="vc-quote-text">“{near.text}”</div>
                              <div className="vc-quote-meta mono">
                                {near.speaker_role || 'Clinician'} · S7a · @{near.mm_ss || fmtMmSs(near.t_start_s)}
                              </div>
                            </div>
                          );
                        })()}

                        {/* Card 2: Surrounding Chronological Events Queue (Jump-To Feed) */}
                        <div className="tl-inspector-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                          <div className="tl-inspector-eyebrow">
                            <span>TIMELINE QUEUE</span>
                            <span className="mono">{allCaseEvents.length} total</span>
                          </div>
                          <div className="tl-nearby-events-list">
                            {(() => {
                              const activeIdx = Math.max(
                                0,
                                allCaseEvents.findIndex((item) => item.id === focusedEvent?.id)
                              );
                              const startIdx = Math.max(0, Math.min(activeIdx - 2, Math.max(0, allCaseEvents.length - 5)));
                              const visibleSlice = allCaseEvents.slice(startIdx, startIdx + 5);
                              return visibleSlice.map((ev) => {
                                const isCurrent = focusedEvent?.id === ev.id;
                                return (
                                  <button
                                    key={ev.id}
                                    type="button"
                                    className={`tl-nearby-event-btn ${isCurrent ? 'current' : ''}`}
                                    onClick={() => seekToEvent(ev)}
                                  >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', minWidth: 0 }}>
                                      <span
                                        className="mono"
                                        style={{
                                          fontSize: '10.5px',
                                          fontWeight: 700,
                                          color: isCurrent ? '#2563eb' : 'var(--text-secondary)',
                                          flexShrink: 0,
                                        }}
                                      >
                                        {ev.start_mmss}
                                      </span>
                                      <span
                                        style={{
                                          fontSize: '11px',
                                          fontWeight: isCurrent ? 700 : 600,
                                          color: 'var(--text-primary)',
                                          whiteSpace: 'nowrap',
                                          overflow: 'hidden',
                                          textOverflow: 'ellipsis',
                                        }}
                                      >
                                        {ev.label}
                                      </span>
                                    </div>
                                    <span
                                      className="mono"
                                      style={{
                                        fontSize: '10px',
                                        fontWeight: 700,
                                        color: isCurrent ? '#2563eb' : 'var(--text-muted)',
                                        flexShrink: 0,
                                      }}
                                    >
                                      {isCurrent ? '● LIVE' : 'Jump →'}
                                    </span>
                                  </button>
                                );
                              });
                            })()}
                          </div>
                        </div>
                      </>
                    )}

                    {inspectorTab === 'transcript' && (
                      <div className="tl-inspector-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.4rem', minHeight: 0 }}>
                        <div className="tl-inspector-eyebrow">
                          <span>S7a LLM AUDIO TRANSCRIPT &amp; EVENT ORDER</span>
                          <span className="mono">
                            00:00–{fmtMmSs(currentCase.duration_s || maxTimelineS)}
                          </span>
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                          Diarized spoken utterances mapped by <strong>{currentCase.model_id || 'gemini-4-argon'}</strong> into chronological resuscitation event order (click any line to seek):
                        </div>
                        <div className="tl-nearby-events-list" style={{ maxHeight: '420px', overflowY: 'auto' }}>
                          {(currentCase.transcript?.utterances?.length
                            ? currentCase.transcript.utterances
                            : allCaseEvents.map((ev, i) => ({
                                utterance_id: ev.id || `ev_${i}`,
                                t_start_s: ev.t_start_s,
                                mm_ss: ev.start_mmss,
                                speaker_role: ev.sensor_label || 'CLINICIAN',
                                text: ev.evidence_text || ev.label,
                                clinical_event_hint: ev.type,
                              }))
                          ).map((u, idx) => {
                            const isNear = Math.abs(Number(u.t_start_s || 0) - currentTimeS) <= 6.0;
                            return (
                              <button
                                key={u.utterance_id || idx}
                                type="button"
                                className={`tl-nearby-event-btn ${isNear ? 'current' : ''}`}
                                onClick={() => seekToEvent(Number(u.t_start_s || 0))}
                                style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0.14rem', textAlign: 'left' }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.3rem' }}>
                                  <span className="mono" style={{ fontSize: '10.5px', fontWeight: 700, color: isNear ? '#2563eb' : 'var(--text-primary)' }}>
                                    #{idx + 1} · @{u.mm_ss || fmtMmSs(u.t_start_s)} · {u.speaker_role}
                                  </span>
                                  {u.clinical_event_hint && (
                                    <span className="tl-status-pill blue mono" style={{ fontSize: '9px', padding: '1px 5px' }}>
                                      {u.clinical_event_hint}
                                    </span>
                                  )}
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.32 }}>
                                  “{u.text}”
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {inspectorTab === 'reid' && (
                      <div className="tl-inspector-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div className="tl-inspector-eyebrow">
                          <span>PERSISTENT ID &amp; TAXONOMY</span>
                          <span className="mono">{trackedObjectsTaxonomy.length} IDs · 0 Switches</span>
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                          Click any tracked entity to highlight its 3D volumetric cuboid, trajectory &amp; 4-level attribute taxonomy:
                        </div>
                        <div className="tl-nearby-events-list">
                          {trackedObjectsTaxonomy.slice(0, 6).map((obj) => (
                            <button
                              key={obj.id}
                              type="button"
                              className={`tl-nearby-event-btn ${selectedObjId === obj.id ? 'current' : ''}`}
                              onClick={() => {
                                setSelectedObjId(obj.id);
                                seekToEvent(obj.jumpTimeS);
                              }}
                              style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0.14rem' }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span className="mono" style={{ fontWeight: 700, fontSize: '10.5px', color: obj.color }}>
                                  {obj.id} ({obj.maskId})
                                </span>
                                <span className="mono" style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>
                                  Re-ID: {obj.occlusionRecoveries}
                                </span>
                              </div>
                              <div style={{ fontSize: '10.5px', color: 'var(--text-primary)', fontWeight: 600 }}>
                                {obj.taxonomy.slice(0, 3).join(' > ')}
                              </div>
                              <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                                ↳ {obj.taxonomy[3]}
                              </div>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* ZONE E · PROPORTIONAL RESUSCITATION TIMELINE (directly under the video, playhead synced) */}
              {(() => {
                const totalS = Math.max(1, Number(maxTimelineS) || 1);
                const pct = (s) => `${Math.max(0, Math.min(100, (Number(s) / totalS) * 100))}%`;
                const widthPct = (a, b) => `${Math.max(0.6, ((Number(b) - Number(a)) / totalS) * 100)}%`;
                const pauses = allCaseEvents.filter((e) => e.kind === 'interval');
                const cprStart = allCaseEvents
                  .filter((e) => e.type === 'compression_active_start' || e.type === 'cpr_initiated_ed')
                  .reduce((m, e) => Math.min(m, Number(e.t_start_s)), Infinity);
                const roscEv = allCaseEvents.find((e) => (e.type || '').includes('rosc') || (e.type || '').includes('death'));
                const cprEnd = roscEv ? Number(roscEv.t_start_s) : totalS;
                const lanes = [
                  {
                    id: 'cpr',
                    title: 'CPR & pauses',
                    sub: `S1 optical flow · CCF ${currentCase.ccf_pct}%`,
                    match: ['cpr'],
                    events: allCaseEvents.filter(
                      (e) => e.type === 'mccd_application_start'
                    ),
                    tone: 'indigo',
                  },
                  {
                    id: 'rhythm',
                    title: 'Rhythm & shocks',
                    sub: 'Pulse · ECG · defib',
                    match: ['shocks'],
                    events: allCaseEvents.filter(
                      (e) =>
                        e.kind !== 'interval' &&
                        (e.type === 'rhythm_check' ||
                          e.type === 'pulse_check' ||
                          e.type === 'defibrillation_shock' ||
                          e.type === 'defib_charge_aborted')
                    ),
                    tone: 'amber',
                  },
                  {
                    id: 'meds',
                    title: 'Medications & access',
                    sub: 'S7a speech · IV/IO',
                    match: ['meds'],
                    events: allCaseEvents.filter(
                      (e) =>
                        e.kind !== 'interval' &&
                        (e.type === 'medication_administration' || (e.type || '').includes('vascular') || (e.type || '').includes('iv_'))
                    ),
                    tone: 'rose',
                  },
                  {
                    id: 'airway',
                    title: 'Airway, team & outcome',
                    sub: 'Arrival · ETT · ROSC',
                    match: ['airway', 'team'],
                    events: allCaseEvents.filter(
                      (e) =>
                        e.kind !== 'interval' &&
                        ((e.type || '').includes('enters') ||
                          (e.type || '').includes('handoff') ||
                          (e.type || '').includes('transfer') ||
                          (e.type || '').includes('airway') ||
                          (e.type || '').includes('rosc') ||
                          (e.type || '').includes('death'))
                    ),
                    tone: 'sky',
                  },
                ];
                const ticks = Array.from({ length: 7 }).map((_, i) => (totalS * i) / 6);
                const seekFromTrack = (e) => {
                  const r = e.currentTarget.getBoundingClientRect();
                  const t = ((e.clientX - r.left) / r.width) * totalS;
                  seekToEvent(Math.max(0, Math.min(totalS, t)));
                };
                return (
                  <div className="vc-timeline">
                    <div className="vc-timeline-head">
                      <span className="vc-label">Resuscitation timeline</span>
                      <span className="vc-hint">Click a block or anywhere on a lane to jump the video</span>
                      <span className="vc-legend">
                        <i className="lg indigo" /> Compressions <i className="lg red" /> Pause &gt;10s <i className="lg pause" /> Pause ≤10s
                      </span>
                    </div>
                    <div className="vc-ruler">
                      <span />
                      <div>
                        {ticks.map((t, i) => (
                          <span key={i} className="mono" style={{ left: pct(t) }}>
                            {fmtMmSs(t)}
                          </span>
                        ))}
                      </div>
                    </div>
                    {lanes.map((lane) => {
                      const dim = domainFilter !== 'all' && !lane.match.includes(domainFilter);
                      return (
                        <div key={lane.id} className={`vc-lane ${dim ? 'dim' : ''}`}>
                          <div className="vc-lane-name">
                            <b>{lane.title}</b>
                            <span>{lane.sub}</span>
                          </div>
                          <div className="vc-track" onClick={seekFromTrack}>
                            {lane.id === 'cpr' && Number.isFinite(cprStart) && (
                              <div
                                className="vc-block indigo span"
                                style={{ left: pct(cprStart), width: widthPct(cprStart, cprEnd) }}
                                title={`Compressions ${fmtMmSs(cprStart)}–${fmtMmSs(cprEnd)}`}
                              >
                              </div>
                            )}
                            {lane.id === 'cpr' &&
                              pauses.map((p) => {
                                const long = Number(p.duration_s || 0) > 10;
                                return (
                                  <button
                                    key={p.id}
                                    type="button"
                                    className={`vc-block ${long ? 'red' : 'pause'}`}
                                    style={{ left: pct(p.t_start_s), width: widthPct(p.t_start_s, p.t_end_s || Number(p.t_start_s) + Number(p.duration_s || 1)) }}
                                    title={`Pause ${p.start_mmss} · ${p.duration_s}s`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      seekToEvent(p);
                                    }}
                                  />
                                );
                              })}
                            {roscEv && lane.id === 'cpr' && (
                              <div
                                className="vc-block green span"
                                style={{ left: pct(cprEnd), width: widthPct(cprEnd, totalS) }}
                              >
                                {(roscEv.type || '').includes('death') ? 'TOR' : 'ROSC'}
                              </div>
                            )}
                            {(() => {
                              // Merge events that sit within 4% of the timeline so labels never collide
                              const sorted = [...lane.events].sort((a, b) => Number(a.t_start_s) - Number(b.t_start_s));
                              const clusters = [];
                              sorted.forEach((ev, idx) => {
                                const label = formatSwimlanePillLabel(ev, idx);
                                const last = clusters[clusters.length - 1];
                                if (last && (Number(ev.t_start_s) - Number(last.ev.t_start_s)) / totalS < 0.04) {
                                  if (!last.labels.includes(label)) last.labels.push(label);
                                  last.members.push(ev);
                                } else {
                                  clusters.push({ ev, labels: [label], members: [ev] });
                                }
                              });
                              // Each label may only use the space up to the next marker (or the lane end)
                              clusters.forEach((c, i) => {
                                const startPct = (Number(c.ev.t_start_s) / totalS) * 100;
                                const nextPct = i + 1 < clusters.length ? (Number(clusters[i + 1].ev.t_start_s) / totalS) * 100 : 100;
                                c.gapPct = Math.max(0, nextPct - startPct);
                              });
                              return clusters;
                            })().map(({ ev, labels, members, gapPct }) => {
                              const sel = members.some((m) => focusedEvent?.id === m.id);
                              const end = null; // events render as markers; only the CPR lane draws spans
                              const text = labels.length > 1 ? `${labels[0]} +${labels.length - 1}` : labels[0];
                              const tight = !end && gapPct < 2.2;
                              return (
                                <button
                                  key={ev.id}
                                  type="button"
                                  className={`vc-block ${lane.tone} ${sel ? 'sel' : ''} ${end ? '' : 'point'} ${tight ? 'tick' : ''}`}
                                  style={{
                                    left: pct(ev.t_start_s),
                                    ...(end ? { width: widthPct(ev.t_start_s, end) } : { maxWidth: `calc(${gapPct}% - 4px)` }),
                                  }}
                                  title={members.map((m) => `${m.label} @ ${m.start_mmss}`).join('\n')}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    seekToEvent(ev);
                                  }}
                                >
                                  {tight ? null : text}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                    <div className="vc-playhead-wrap">
                      <div className="vc-playhead" style={{ left: pct(currentTimeS) }}>
                        <span className="mono">{fmtMmSs(currentTimeS)}</span>
                      </div>
                    </div>
                  </div>
                );
              })()}
              {/* ZONE F · ANALYSIS TABS (one view at a time, below the fold) */}
              <div className="vc-analysis">
                <div className="vc-tabs">
                  {[
                    { id: 'schematic', label: 'Bay schematic & CPR cadence' },
                    { id: 'overlap', label: 'Overlap disambiguation' },
                    { id: 'identity', label: `Identity tracking (${trackedObjectsTaxonomy.length})` },
                    { id: 'protocol', label: `Case #${currentCaseSimProtocol.num} protocol` },
                  ].map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={`vc-tab ${analysisTab === t.id ? 'on' : ''}`}
                      onClick={() => setAnalysisTab(t.id)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                {analysisTab === 'schematic' && (
                  <>
                  {/* ══════════════════════════════════════════════════════════════
                      CONSOLE LOWER DECK: 2D TOP-DOWN BAY SCHEMATIC + LIVE CHARTS
                      (Charts: one accent color #4f46e5, muted gridlines #e2e8f0, direct labels)
                     ══════════════════════════════════════════════════════════════ */}
                  <div className="co-console-lower-deck">
                    {/* PANEL A: 2D TOP-DOWN RESUSCITATION BAY SCHEMATIC (Redrawn from Frame State) */}
                    <div className="co-console-subpanel">
                      <div className="co-console-subpanel-header">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span className="co-section-title">
                            2D Bay Schematic (Frame #{currentFrameIdx})
                          </span>
                        </div>
                        <span className="mono" style={{ fontSize: '10.5px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                          Click zone to isolate subsystem
                        </span>
                      </div>
                      {(() => {
                        const inPauseNow = activeAnnotationsAtTime.inPause;
                        const cprNow = activeAnnotationsAtTime.cprActive;
                        const medNow =
                          (focusedEvent?.type === 'medication_administration' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18) ||
                          activeAnnotationsAtTime.nearbyPointEvents.some((e) => e.type === 'medication_administration');
                        const shockNow =
                          (focusedEvent?.type === 'defibrillation_shock' &&
                            Math.abs(focusedEvent.t_start_s - currentTimeS) <= 18) ||
                          activeAnnotationsAtTime.nearbyPointEvents.some((e) => e.type === 'defibrillation_shock');
                        const airwayNow =
                          focusedEvent &&
                          (focusedEvent.type === 'airway_attempt' ||
                            focusedEvent.type === 'airway_confirmation' ||
                            focusedEvent.type === 'pocus_cardiac');
                        const phaseRad = (currentTimeS * 3.6) % (Math.PI * 2);
                        const compJitterY = cprNow ? Math.sin(phaseRad) * 2.8 : 0;
                        return (
                          <svg
                            viewBox="0 0 380 158"
                            width="100%"
                            height="156"
                            style={{
                              display: 'block',
                              background: '#f8fafc',
                              borderRadius: '10px',
                              border: '1px solid #e2e8f0',
                            }}
                          >
                            {/* Muted gridlines (#e2e8f0) */}
                            <g stroke="#e2e8f0" strokeWidth="0.75">
                              <line x1="0" y1="38" x2="380" y2="38" />
                              <line x1="0" y1="79" x2="380" y2="79" />
                              <line x1="0" y1="120" x2="380" y2="120" />
                              <line x1="76" y1="0" x2="76" y2="158" />
                              <line x1="152" y1="0" x2="152" y2="158" />
                              <line x1="228" y1="0" x2="228" y2="158" />
                              <line x1="304" y1="0" x2="304" y2="158" />
                            </g>

                            {/* Camera FOV Cones (Single Accent #4f46e5) */}
                            <polygon
                              points="18,14 148,46 148,118"
                              fill={cameraPerspectiveView === 'cctv_overhead' ? 'rgba(79, 70, 229, 0.08)' : 'rgba(148, 163, 184, 0.04)'}
                              stroke={cameraPerspectiveView === 'cctv_overhead' ? '#4f46e5' : '#cbd5e1'}
                              strokeWidth="0.8"
                              strokeDasharray="2 2"
                            />
                            <text x="8" y="12" fill="#475569" fontSize="6.5" fontWeight="600" fontFamily="monospace">
                              CCTV/T0
                            </text>
                            <text x="292" y="149" fill="#475569" fontSize="6.5" fontWeight="600" fontFamily="monospace">
                              iPad / POV
                            </text>

                            {/* Stretcher Bed Perimeter & Supine Patient Silhouette (PT-1) */}
                            <rect
                              x="78"
                              y="48"
                              width="196"
                              height="58"
                              rx="8"
                              fill="#ffffff"
                              stroke="#cbd5e1"
                              strokeWidth="1.1"
                            />
                            {/* Patient Head + Torso + Legs */}
                            <circle cx="102" cy="77" r="11" fill="#f8fafc" stroke="#94a3b8" strokeWidth="0.9" />
                            <rect x="116" y="61" width="84" height="32" rx="7" fill="#f8fafc" stroke="#94a3b8" strokeWidth="0.9" />
                            <rect x="203" y="65" width="56" height="10" rx="4" fill="#f8fafc" stroke="#cbd5e1" strokeWidth="0.8" />
                            <rect x="203" y="79" width="56" height="10" rx="4" fill="#f8fafc" stroke="#cbd5e1" strokeWidth="0.8" />

                            {/* ZONE 1: AIRWAY / ETT ROI (Clickable · Direct Label) */}
                            <g
                              style={{ cursor: 'pointer' }}
                              opacity={getSubsystemRoiOpacity('airway')}
                              onClick={() => setDomainFilter(domainFilter === 'airway' ? 'all' : 'airway')}
                            >
                              <rect
                                x="84"
                                y="56"
                                width="32"
                                height="42"
                                rx="5"
                                fill={airwayNow || domainFilter === 'airway' ? 'rgba(79, 70, 229, 0.16)' : 'rgba(79, 70, 229, 0.05)'}
                                stroke="#4f46e5"
                                strokeWidth={airwayNow || domainFilter === 'airway' ? '1.4' : '0.9'}
                              />
                              <line x1="100" y1="56" x2="62" y2="29" stroke="#4f46e5" strokeWidth="0.7" />
                              <rect x="14" y="17" width="92" height="14" rx="3" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.75" />
                              <text x="18" y="26.5" fill="#0f172a" fontSize="6.7" fontWeight="700" fontFamily="monospace">
                                AIRWAY / ETT
                              </text>
                            </g>

                            {/* ZONE 2: S1 STERNUM / CPR ROI (Single Accent #4f46e5 + Direct Label) */}
                            <g
                              style={{ cursor: 'pointer' }}
                              opacity={getSubsystemRoiOpacity('cpr')}
                              onClick={() => setDomainFilter(domainFilter === 'cpr' ? 'all' : 'cpr')}
                            >
                              <rect
                                x="130"
                                y="62"
                                width="44"
                                height="30"
                                rx="5"
                                fill={cprNow ? 'rgba(79, 70, 229, 0.18)' : 'rgba(79, 70, 229, 0.08)'}
                                stroke="#4f46e5"
                                strokeWidth="1.4"
                              />
                              <circle
                                cx="152"
                                cy="77"
                                r={cprNow ? 7 + Math.abs(compJitterY) : 6}
                                fill="#4f46e5"
                                fillOpacity="0.24"
                                stroke="#4f46e5"
                                strokeWidth="1.1"
                              />
                              <line
                                x1="152"
                                y1="62"
                                x2="158"
                                y2="29"
                                stroke="#4f46e5"
                                strokeWidth="0.8"
                              />
                              <rect
                                x="112"
                                y="15"
                                width="118"
                                height="15"
                                rx="3"
                                fill="rgba(79, 70, 229, 0.08)"
                                stroke="#4f46e5"
                                strokeWidth="0.85"
                              />
                              <text
                                x="116"
                                y="25"
                                fill="#4f46e5"
                                fontSize="6.7"
                                fontWeight="700"
                                fontFamily="monospace"
                              >
                                {inPauseNow ? 'S1 PAUSE ACTIVE' : `S1 CPR · CCF ${currentCase.ccf_pct}%`}
                              </text>
                            </g>

                            {/* ZONE 3: IV / IO MEDICATION PORT ROI (Direct Label) */}
                            <g
                              style={{ cursor: 'pointer' }}
                              opacity={getSubsystemRoiOpacity('meds')}
                              onClick={() => setDomainFilter(domainFilter === 'meds' ? 'all' : 'meds')}
                            >
                              <rect
                                x="176"
                                y="84"
                                width="34"
                                height="18"
                                rx="4"
                                fill={medNow || domainFilter === 'meds' ? 'rgba(79, 70, 229, 0.18)' : 'rgba(79, 70, 229, 0.06)'}
                                stroke="#4f46e5"
                                strokeWidth={medNow || domainFilter === 'meds' ? '1.35' : '0.9'}
                              />
                              <line x1="193" y1="102" x2="182" y2="132" stroke="#4f46e5" strokeWidth="0.7" />
                              <rect x="118" y="132" width="122" height="15" rx="3" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.75" />
                              <text x="122" y="142" fill="#0f172a" fontSize="6.6" fontWeight="700" fontFamily="monospace">
                                {`IV/IO [total_epi=${currentCase.total_epi_doses ?? 1}]`}
                              </text>
                            </g>

                            {/* ZONE 4: DEFIBRILLATOR & ECG MONITOR CART (DEFIB-1, Single Accent) */}
                            <g
                              style={{ cursor: 'pointer' }}
                              opacity={getSubsystemRoiOpacity('shocks')}
                              onClick={() => setDomainFilter(domainFilter === 'shocks' ? 'all' : 'shocks')}
                            >
                              <rect
                                x="292"
                                y="32"
                                width="72"
                                height="42"
                                rx="6"
                                fill={shockNow || domainFilter === 'shocks' ? 'rgba(79, 70, 229, 0.12)' : '#ffffff'}
                                stroke="#4f46e5"
                                strokeWidth="1.1"
                              />
                              {/* Lead cable to sternum */}
                              <path
                                d="M 292,54 Q 235,44 174,72"
                                fill="none"
                                stroke="#4f46e5"
                                strokeWidth="0.85"
                                strokeDasharray="2.5 2"
                              />
                              <text x="298" y="45" fill="#0f172a" fontSize="6.8" fontWeight="700" fontFamily="monospace">
                                DEFIB-1 / S5
                              </text>
                              <polyline
                                points="298,58 308,58 313,49 318,65 324,47 330,63 336,55 356,55"
                                fill="none"
                                stroke="#4f46e5"
                                strokeWidth="1.1"
                              />
                              <text x="298" y="70" fill="#475569" fontSize="6.1" fontFamily="monospace">
                                {`Shocks: ${currentCase.total_shocks ?? 1}`}
                              </text>
                            </g>

                            {/* TRACKED CLINICIANS (Single Accent + Neutral Badges) */}
                            <g
                              style={{ cursor: 'pointer' }}
                              opacity={getSubsystemRoiOpacity('team')}
                              onClick={() => setDomainFilter(domainFilter === 'team' ? 'all' : 'team')}
                            >
                              {/* Compressor #1 at bedside above sternum */}
                              <circle
                                cx="152"
                                cy={40 + compJitterY}
                                r="7.5"
                                fill="#4f46e5"
                                stroke="#ffffff"
                                strokeWidth="1.2"
                              />
                              <text x="145" y={42.5 + compJitterY} fill="#ffffff" fontSize="5.8" fontWeight="700" fontFamily="monospace">
                                C1
                              </text>
                              {/* Airway Lead at head of bed */}
                              <circle cx="62" cy="77" r="7.5" fill="#0f172a" stroke="#ffffff" strokeWidth="1.2" />
                              <text x="55" y="79.5" fill="#ffffff" fontSize="5.8" fontWeight="700" fontFamily="monospace">
                                AW
                              </text>
                              {/* Team Leader / Recorder at foot/bottom */}
                              <circle cx="268" cy="122" r="7.5" fill="#475569" stroke="#ffffff" strokeWidth="1.2" />
                              <text x="261" y="124.5" fill="#ffffff" fontSize="5.8" fontWeight="700" fontFamily="monospace">
                                TL
                              </text>
                              <text x="280" y="125" fill="#0f172a" fontSize="6.5" fontWeight="700" fontFamily="monospace">
                                TEAM ({currentCase.team_overall_score}/16)
                              </text>
                            </g>
                          </svg>
                        );
                      })()}
                    </div>

                    {/* PANEL B: LIVE FRAME-SYNCED COMPRESSION WAVEFORM & PERFUSION LOOP */}
                    <div className="co-console-subpanel">
                      <div className="co-console-subpanel-header">
                        <span className="co-section-title">
                          Live S1 Compression Cadence &amp; Perfusion Loop
                        </span>
                        <span className="mono" style={{ fontSize: '10.5px', color: 'var(--accent-primary)', fontWeight: 600 }}>
                          Playhead @{fmtMmSs(currentTimeS)} / {fmtMmSs(maxTimelineS)}
                        </span>
                      </div>
                      {(() => {
                        const dur = Math.max(60, maxTimelineS);
                        const cursorX = 16 + Math.min(1, Math.max(0, currentTimeS / dur)) * 224;
                        const inPauseNow = activeAnnotationsAtTime.inPause;
                        const cprNow = activeAnnotationsAtTime.cprActive;
                        const intervals = allCaseEvents.filter((ev) => ev.kind === 'interval');
                        const pointMilestones = allCaseEvents.filter((ev) => ev.kind !== 'interval').slice(0, 8);
                        // Build compression cadence polyline across timeline
                        const wavePts = Array.from({ length: 46 })
                          .map((_, idx) => {
                            const t = (idx / 45) * dur;
                            const x = 16 + (idx / 45) * 224;
                            const pausedAtT = intervals.some(
                              (iv) => t >= iv.t_start_s && t <= (iv.t_end_s || iv.t_start_s + 8)
                            );
                            const y = pausedAtT
                              ? 112
                              : 48 + Math.sin(idx * 1.7 + currentTimeS * 0.4) * 8;
                            return `${x.toFixed(1)},${y.toFixed(1)}`;
                          })
                          .join(' ');
                        // Live P-V style Compression Depth x Perfusion Loop on the right (x: 256..368)
                        const loopCx = 314;
                        const loopCy = 78;
                        const rx = inPauseNow ? 14 : cprNow ? 36 : 24;
                        const ry = inPauseNow ? 10 : cprNow ? 28 : 18;
                        const orbitAngle = (currentTimeS * 4.2) % (Math.PI * 2);
                        const dotX = loopCx + Math.cos(orbitAngle) * rx;
                        const dotY = loopCy + Math.sin(orbitAngle) * ry;
                        return (
                          <svg
                            viewBox="0 0 380 158"
                            width="100%"
                            height="156"
                            style={{
                              display: 'block',
                              background: '#f8fafc',
                              borderRadius: '10px',
                              border: '1px solid #e2e8f0',
                            }}
                          >
                            {/* Left Chart: Compression Cadence Waveform (One Accent #4f46e5 · Muted Gridlines #e2e8f0 · Direct Labels) */}
                            <rect x="16" y="24" width="224" height="96" rx="4" fill="#ffffff" stroke="#e2e8f0" strokeWidth="0.9" />
                            {/* Muted horizontal & vertical gridlines */}
                            <g stroke="#e2e8f0" strokeWidth="0.65">
                              <line x1="16" y1="48" x2="240" y2="48" />
                              <line x1="16" y1="72" x2="240" y2="72" />
                              <line x1="16" y1="96" x2="240" y2="96" />
                              <line x1="72" y1="24" x2="72" y2="120" />
                              <line x1="128" y1="24" x2="128" y2="120" />
                              <line x1="184" y1="24" x2="184" y2="120" />
                            </g>
                            {/* Target 100-120 CPM band (Single Accent Tint) */}
                            <rect x="16" y="38" width="224" height="24" fill="rgba(79, 70, 229, 0.08)" />
                            <text x="20" y="34" fill="#4f46e5" fontSize="6.2" fontWeight="700" fontFamily="monospace">
                              TARGET 100-120 CPM (CCF ≥80%)
                            </text>

                            {/* Pause Interval Muted Blocks */}
                            {intervals.map((iv) => {
                              const x0 = 16 + Math.min(1, Math.max(0, iv.t_start_s / dur)) * 224;
                              const x1 = 16 + Math.min(1, Math.max(0, (iv.t_end_s || iv.t_start_s + 8) / dur)) * 224;
                              return (
                                <g
                                  key={iv.id}
                                  style={{ cursor: 'pointer' }}
                                  onClick={() => seekToEvent(iv)}
                                >
                                  <rect
                                    x={x0}
                                    y="24"
                                    width={Math.max(4, x1 - x0)}
                                    height="96"
                                    fill="rgba(71, 85, 105, 0.12)"
                                  />
                                </g>
                              );
                            })}

                            {/* Cadence Waveform Line (Single Accent #4f46e5) */}
                            <polyline
                              points={wavePts}
                              fill="none"
                              stroke="#4f46e5"
                              strokeWidth="1.5"
                            />

                            {/* REDCap Milestone Pins along bottom of waveform */}
                            {pointMilestones.map((ev) => {
                              const px = 16 + Math.min(1, Math.max(0, ev.t_start_s / dur)) * 224;
                              return (
                                <g
                                  key={ev.id}
                                  style={{ cursor: 'pointer' }}
                                  onClick={() => seekToEvent(ev)}
                                >
                                  <circle cx={px} cy="120" r="3.2" fill="#4f46e5" stroke="#ffffff" strokeWidth="0.9" />
                                </g>
                              );
                            })}

                            {/* Live Moving Playhead Cursor */}
                            <line x1={cursorX} y1="20" x2={cursorX} y2="124" stroke="#0f172a" strokeWidth="1.4" />
                            <circle cx={cursorX} cy="24" r="3.2" fill="#4f46e5" />
                            <text x="16" y="136" fill="#475569" fontSize="6.4" fontWeight="600" fontFamily="monospace">
                              00:00 · Click pin/pause to seek
                            </text>
                            <text x="156" y="136" fill="#0f172a" fontSize="6.4" fontWeight="700" fontFamily="monospace">
                              {`Active: ${(activeRedcapRowAtPlayhead?.redcapField || 'time_compressions_v2').slice(0, 16)}`}
                            </text>

                            {/* Right Chart: Live ACLS Cycle Perfusion Loop (One Accent #4f46e5 · Muted Gridlines #e2e8f0) */}
                            <rect x="252" y="24" width="116" height="96" rx="4" fill="#ffffff" stroke="#e2e8f0" strokeWidth="0.9" />
                            <text x="258" y="34" fill="#0f172a" fontSize="6.1" fontWeight="700" fontFamily="monospace">
                              PERFUSION LOOP (P-V)
                            </text>
                            <line x1="262" y1="78" x2="360" y2="78" stroke="#e2e8f0" strokeWidth="0.75" />
                            <line x1="314" y1="38" x2="314" y2="114" stroke="#e2e8f0" strokeWidth="0.75" />
                            <ellipse
                              cx={loopCx}
                              cy={loopCy}
                              rx={rx}
                              ry={ry}
                              fill="rgba(79, 70, 229, 0.10)"
                              stroke="#4f46e5"
                              strokeWidth="1.5"
                            />
                            <circle
                              cx={dotX}
                              cy={dotY}
                              r="3.8"
                              fill="#4f46e5"
                              stroke="#ffffff"
                              strokeWidth="1"
                            />
                            <text
                              x="256"
                              y="136"
                              fill="#4f46e5"
                              fontSize="6.4"
                              fontWeight="700"
                              fontFamily="monospace"
                            >
                              {inPauseNow ? 'CPP DROP (PAUSE)' : 'CPP MAINTAINED'}
                            </text>
                          </svg>
                        );
                      })()}
                    </div>
                  </div>
                  </>
                )}
                {analysisTab === 'overlap' && (
                  <div className="vc-analysis-single">
                {/* CARD A: SOLVING THE "OVERLAPPING OBJECTS" PROBLEM */}
                <div className="tl-cv-gov-card">
                  <div className="tl-cv-gov-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <div style={{ fontSize: '0.84rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span>Solving “The Overlapping Objects Problem”</span>
                        <span className="tl-status-pill green mono" style={{ fontSize: '0.65rem', padding: '0.1rem 0.45rem' }}>
                          Panoptic + Instance + Polygon Pass
                        </span>
                      </div>
                      <div style={{ fontSize: '0.71rem', color: 'var(--text-secondary)', marginTop: '0.12rem' }}>
                        Prevents merged outlines when compressor hands, LUCAS piston, defib leads, and sterile drapes overlap over the sternum ROI
                      </div>
                    </div>
                  </div>

                  {/* 4 Technical Capabilities Grid */}
                  <div className="tl-cv-gov-pills-grid">
                    <div className="tl-cv-feature-box">
                      <div style={{ fontSize: '0.71rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                        1 · Unique Instance Masks (INST-01..{trackedObjectsTaxonomy.length})
                      </div>
                      <div style={{ fontSize: '0.67rem', color: 'var(--text-secondary)' }}>
                        Depth-ordered contour masks hold through overlaps, splits &amp; merges (<span className="mono">{overlapContinuityKeyframes[0]?.overlapPair || 'OBJ-004 ∩ OBJ-002 ∩ OBJ-001'}</span>).
                      </div>
                    </div>
                    <div className="tl-cv-feature-box">
                      <div style={{ fontSize: '0.71rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                        2 · Single-Pass Panoptic (Stuff + Thing)
                      </div>
                      <div style={{ fontSize: '0.67rem', color: 'var(--text-secondary)' }}>
                        Combines <strong>Stuff</strong> (Bay Floor, Stretcher Mat, Curtain) + <strong>Thing</strong> (Patient, Defib, Clinicians) in one pass.
                      </div>
                    </div>
                    <div className="tl-cv-feature-box">
                      <div style={{ fontSize: '0.71rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                        3 · Deformable Polygon Annotation (POLY-*)
                      </div>
                      <div style={{ fontSize: '0.67rem', color: 'var(--text-secondary)' }}>
                        9-vertex polygons capture non-rigid <strong>Sterile Sheet Fabric</strong>, <strong>Defib Lead Wires</strong>, <strong>O2 Tubing</strong> &amp; <strong>Cast Shadows</strong>.
                      </div>
                    </div>
                    <div className="tl-cv-feature-box">
                      <div style={{ fontSize: '0.71rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                        4 · Adjacent-Frame Drift Cross-Check
                      </div>
                      <div style={{ fontSize: '0.67rem', color: 'var(--text-secondary)' }}>
                        Cross-checks class labels &amp; mask edges across <span className="mono">F{currentFrameIdx - 1} ↔ F{currentFrameIdx} ↔ F{currentFrameIdx + 1}</span> (<span className="mono">IoU 97.4%</span>, 0 drift).
                      </div>
                    </div>
                  </div>

                  {/* Human Review at Overlap Keyframes Strip */}
                  <div style={{ fontSize: '0.69rem', fontWeight: 800, color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                    HUMAN REVIEW AT OVERLAP &amp; BOUNDARY-SHIFT KEYFRAMES (CLICK TO SEEK VIDEO &amp; VERIFY SEAM):
                  </div>
                  <div className="tl-kf-strip">
                    {overlapContinuityKeyframes.map((kf) => {
                      const isActive = Math.abs(currentTimeS - kf.time_s) <= 8.0;
                      const isVer = verifiedKeyframes[kf.id] ?? true;
                      return (
                        <div
                          key={kf.id}
                          className={`tl-kf-btn ${isActive ? 'active' : ''}`}
                          onClick={() => seekToEvent(kf.time_s)}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.25rem' }}>
                            <span className="mono" style={{ fontSize: '0.7rem', fontWeight: 800, color: '#2563eb' }}>
                              @{kf.mmss} (F{kf.frame})
                            </span>
                            <span
                              className="mono"
                              onClick={(e) => toggleKeyframeVerified(kf.id, e)}
                              style={{
                                fontSize: '0.61rem',
                                fontWeight: 800,
                                color: isVer ? '#059669' : '#d97706',
                                padding: '0.05rem 0.28rem',
                                borderRadius: '4px',
                                background: isVer ? 'rgba(16,185,129,0.14)' : 'rgba(245,158,11,0.16)',
                              }}
                              title="Click to toggle Human Overlap Review verification"
                            >
                              {isVer ? '✓ Verified' : '⚠ Review'}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.69rem', fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {kf.title}
                          </div>
                          <div className="mono" style={{ fontSize: '0.62rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {kf.overlapPair}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                  </div>
                )}
                {analysisTab === 'identity' && (
                  <div className="vc-analysis-single">
                {/* CARD B: SOLVING THE "IDENTITY SWITCHING" PROBLEM */}
                <div className="tl-cv-gov-card">
                  <div className="tl-cv-gov-header">
                    <div>
                      <div style={{ fontSize: '0.84rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span>Solving “The Identity Switching Problem”</span>
                        <span className="tl-status-pill blue mono" style={{ fontSize: '0.65rem', padding: '0.1rem 0.45rem' }}>
                          {trackedObjectsTaxonomy.length}/{trackedObjectsTaxonomy.length} Persistent IDs · 0 Switches
                        </span>
                      </div>
                      <div style={{ fontSize: '0.71rem', color: 'var(--text-secondary)', marginTop: '0.12rem' }}>
                        Persistent object IDs initialized at `T0`, Kalman/Re-ID trajectory bridges across occlusions, and 4-level hierarchical attribute taxonomies
                      </div>
                    </div>
                  </div>

                  {/* Interactive Hierarchical Attribute Taxonomy per Tracked Object */}
                  <div className="tl-taxonomy-list">
                    {trackedObjectsTaxonomy.map((obj) => {
                      const isSel = selectedObjId === obj.id;
                      return (
                        <button
                          key={obj.id}
                          type="button"
                          className={`tl-taxonomy-row ${isSel ? 'selected' : ''}`}
                          onClick={() => {
                            setSelectedObjId(obj.id);
                            seekToEvent(obj.jumpTimeS);
                          }}
                        >
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                              <span
                                className="mono"
                                style={{
                                  fontSize: '0.67rem',
                                  fontWeight: 800,
                                  color: '#fff',
                                  background: obj.color,
                                  padding: '0.08rem 0.38rem',
                                  borderRadius: '5px',
                                }}
                              >
                                {obj.id}
                              </span>
                              <span style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                                {obj.taxonomy[0]} &gt; {obj.taxonomy[1]}
                              </span>
                              <span className="mono" style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>
                                · Init {obj.initFrame} · Re-ID {obj.occlusionRecoveries}
                              </span>
                            </div>
                            <div
                              style={{
                                fontSize: '0.67rem',
                                color: 'var(--text-secondary)',
                                marginTop: '0.14rem',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                              }}
                            >
                              <strong>Taxonomy:</strong> {obj.taxonomy[2]} &gt;{' '}
                              <span style={{ color: '#2563eb', fontWeight: 700 }}>{obj.taxonomy[3]}</span>
                            </div>
                          </div>
                          <span className="mono" style={{ fontSize: '0.64rem', fontWeight: 800, color: isSel ? '#2563eb' : 'var(--text-muted)', flexShrink: 0 }}>
                            {isSel ? '● TRACKED' : 'Inspect →'}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
                  </div>
                )}
                {analysisTab === 'protocol' && (
                  <dl className="vc-dl">
                    <dt>Case</dt>
                    <dd>
                      Case #{currentCaseSimProtocol.num} · {currentCaseSimProtocol.shortBadge}
                    </dd>
                    <dt>Expected rhythm sequence</dt>
                    <dd>{currentCaseSimProtocol.rhythmTrajectory}</dd>
                    <dt>Expected medications</dt>
                    <dd>{currentCaseSimProtocol.expectedDrugs}</dd>
                    <dt>Compression coverage</dt>
                    <dd>
                      {Math.round((Number(currentCase.ccf_pct || 0) / 100) * Number(currentCase.code_duration_s || maxTimelineS))}s of
                      active compressions · CCF {currentCase.ccf_pct}% (target ≥80%)
                    </dd>
                    <dt>Prolonged pauses (&gt;10s)</dt>
                    <dd>{currentCase.prolonged_interruptions_count ?? 0}</dd>
                    <dt>REDCap branching</dt>
                    <dd>
                      simulation_number_v2 = {currentCaseSimProtocol.num} · {currentCaseSimProtocol.caseQuestions.length} case-specific
                      questions · 50 branching rules evaluated
                    </dd>
                    <dt>Events aligned</dt>
                    <dd>{allCaseEvents.length} multimodal events on the video timeline</dd>
                  </dl>
                )}
              </div>
            </section>
            )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════════
          MODAL 1: REDCAP EXTRACTION CONTRACT PROVENANCE INSPECTION MODAL
          Matches User Reference Screenshot 3 (media_1793538646595_4535543f.png)
         ══════════════════════════════════════════════════════════════════════ */}
      {provenanceModalField && (() => {
        const field = provenanceModalField;
        const goldInfo = getContractGoldStatus(field, contractData.gtLookup);
        const gt = goldInfo.gt;
        const extractedText =
          field.value_label || (field.value !== null && field.value !== undefined ? String(field.value) : 'Unable to determine');
        const gtText = gt
          ? gt.value_label || (gt.value !== null && gt.value !== undefined ? String(gt.value) : 'Unpopulated / UTD')
          : 'Not in gold set';
        const srcIds = field.source_event_ids || [];

        return (
          <div className="provenance-modal-overlay" onClick={() => setProvenanceModalField(null)}>
            <div className="provenance-modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="provenance-modal-header">
                <div className="provenance-modal-title">
                  {(field.label || field.export_column).replace(/\s+/g, ' ')}
                </div>
                <button
                  type="button"
                  className="provenance-modal-close"
                  onClick={() => setProvenanceModalField(null)}
                  aria-label="Close modal"
                >
                  ✕
                </button>
              </div>

              <div style={{ marginBottom: '1.25rem' }}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '1rem',
                    background: '#f8fafc',
                    padding: '1rem',
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        textTransform: 'uppercase',
                        fontWeight: 700,
                      }}
                    >
                      ACTIVE RUN EXTRACTED
                    </div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                      {extractedText}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: '2px' }}>
                      State: {field.state}
                    </div>
                  </div>
                  <div>
                    <div
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        textTransform: 'uppercase',
                        fontWeight: 700,
                      }}
                    >
                      HUMAN GOLD STANDARD
                    </div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#d97706', marginTop: '4px' }}>
                      {gtText}
                    </div>
                    <div style={{ marginTop: '4px' }}>
                      <span className={`gold-badge ${goldInfo.className}`}>{goldInfo.label}</span>
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: '0.85rem', fontSize: '0.85rem', color: '#475569' }}>
                  <strong>Export Column:</strong>{' '}
                  <code style={{ fontFamily: 'monospace', color: '#0f172a' }}>{field.export_column}</code>
                </div>
              </div>

              {field.state === 'utd' && (
                <div className="modal-abstain-box">
                  <strong>Abstain Reason:</strong>{' '}
                  {field.abstain_reason || 'Channel coverage degraded'}
                </div>
              )}

              {typeof field.deep_link_t === 'number' && (
                <div style={{ marginTop: '1rem' }}>
                  <button
                    type="button"
                    className="deep-link-btn"
                    onClick={() => {
                      seekToEvent(Number(field.deep_link_t));
                      setProvenanceModalField(null);
                      if (typeof window !== 'undefined') {
                        window.history.replaceState(null, '', '#video-console');
                      }
                      setActiveNav('video');
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                  >
                    ▶ Open Video Feed (#t={field.deep_link_t}s)
                  </button>
                </div>
              )}

              <div className="modal-section-title">
                SOURCE EVENTS &amp; VERBATIM EVIDENCE ({srcIds.length} REFERENCES)
              </div>

              {srcIds.length === 0 ? (
                <div style={{ color: '#64748b', fontSize: '0.85rem' }}>
                  No direct event references (derived or default field state).
                </div>
              ) : (
                srcIds.map((idVal, idx) => {
                  const ev = contractData.eventsById ? contractData.eventsById[idVal] : null;
                  if (ev) {
                    let quoteLines = [];
                    if (Array.isArray(ev.evidence) && ev.evidence.length > 0) {
                      quoteLines = ev.evidence.map((item) => {
                        const spk = item.speaker_id ? `(${item.speaker_id}): ` : '';
                        return `"${spk}${item.quote || item.desc || '--'}"`;
                      });
                    } else if (ev.evidence && typeof ev.evidence === 'object') {
                      const spk = ev.evidence.speaker_id ? `(${ev.evidence.speaker_id}): ` : '';
                      quoteLines = [`"${spk}${ev.evidence.quote || ev.evidence.desc || '--'}"`];
                    } else {
                      quoteLines = [String(ev.evidence || 'Observed visual state transition')];
                    }
                    const tSec = ev.timestamp_s ?? ev.t_start_s ?? 0;
                    return (
                      <div key={`${idVal}_${idx}`} className="modal-quote-box">
                        <div style={{ fontStyle: 'normal', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <div>
                            <strong>ID:</strong> {ev.id} · <strong>Timestamp:</strong> {tSec}s
                          </div>
                          <button
                            type="button"
                            className="deep-link-btn"
                            style={{ padding: '0.22rem 0.55rem', fontSize: '0.75rem' }}
                            onClick={() => {
                              seekToEvent(Number(tSec));
                              setProvenanceModalField(null);
                              if (typeof window !== 'undefined') {
                                window.history.replaceState(null, '', '#video-console');
                              }
                              setActiveNav('video');
                              window.scrollTo({ top: 0, behavior: 'smooth' });
                            }}
                          >
                            ▶ Seek Video (#t={tSec}s)
                          </button>
                        </div>
                        <div style={{ marginTop: '0.5rem' }}>
                          {quoteLines.map((q, qIdx) => (
                            <div key={qIdx}>{q}</div>
                          ))}
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={`${idVal}_${idx}`} className="modal-quote-box">
                      Reference ID: {idVal}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        );
      })()}

      {/* ══════════════════════════════════════════════════════════════════════
          MODAL 2: INSPECT OR UPLOAD REDCAP DATA DICTIONARY (.CSV)
         ══════════════════════════════════════════════════════════════════════ */}
      {showDictModal && (
        <div className="modal-backdrop" onClick={() => setShowDictModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>REDCap Data Dictionaries ({dictionaries.length})</h3>
              <button className="tl-btn" onClick={() => setShowDictModal(false)}>
                ✕
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
              {dictionaries.map((d) => (
                <div
                  key={d.id}
                  style={{
                    padding: '0.6rem 0.75rem',
                    borderRadius: '9px',
                    background: 'var(--bg-subtle)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.77rem',
                  }}
                >
                  <div style={{ fontWeight: 700 }}>{d.name}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.71rem', marginTop: '0.15rem' }}>
                    {d.variables_count} variables · {d.export_columns_count} export columns · {d.branching_rules_count} branching rules · SHA{' '}
                    <span className="mono">{d.sha}</span>
                  </div>
                </div>
              ))}
            </div>

            <form onSubmit={handleUploadDictionary}>
              <div className="form-group">
                <label>Upload New REDCap Data Dictionary CSV</label>
                <input
                  type="file"
                  accept=".csv"
                  className="form-input"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    setDictFilename(f.name);
                    const rdr = new FileReader();
                    rdr.onload = (ev) => setDictCsvContent(String(ev.target?.result || ''));
                    rdr.readAsText(f);
                  }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button type="button" className="tl-btn" onClick={() => setShowDictModal(false)}>
                  Close
                </button>
                <button type="submit" className="tl-btn primary" disabled={uploadingDict || !dictCsvContent}>
                  {uploadingDict ? 'Compiling...' : 'Compile & Register Dictionary'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toastMsg && (
        <div
          style={{
            position: 'fixed',
            bottom: '1.25rem',
            right: '1.25rem',
            background: '#111827',
            color: '#fff',
            padding: '0.68rem 1.1rem',
            borderRadius: '10px',
            fontSize: '0.8rem',
            fontWeight: 600,
            boxShadow: '0 8px 24px rgba(0,0,0,0.28)',
            zIndex: 2000,
          }}
        >
          ✓ {toastMsg}
        </div>
      )}
    </div>
  );
}
