import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface NavItem {
  key: string;
  label: string;
  to?: string;
  icon: ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  {
    key: "datasets",
    label: "Datasets",
    to: "/",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <ellipse cx="10" cy="5" rx="6.5" ry="2.4" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M3.5 5v10c0 1.3 2.9 2.4 6.5 2.4s6.5-1.1 6.5-2.4V5"
          stroke="currentColor"
          strokeWidth="1.6"
        />
        <path
          d="M3.5 10c0 1.3 2.9 2.4 6.5 2.4s6.5-1.1 6.5-2.4"
          stroke="currentColor"
          strokeWidth="1.6"
        />
      </svg>
    ),
  },
  {
    key: "new-analysis",
    label: "New Analysis",
    to: "/",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <path
          d="M3 5.5A2.5 2.5 0 0 1 5.5 3h9A2.5 2.5 0 0 1 17 5.5v5A2.5 2.5 0 0 1 14.5 13H9l-4 3.2V13H5.5A2.5 2.5 0 0 1 3 10.5v-5Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path
          d="M10 6.5l.7 1.6 1.6.7-1.6.7-.7 1.6-.7-1.6-1.6-.7 1.6-.7.7-1.6Z"
          fill="currentColor"
        />
      </svg>
    ),
  },
  {
    key: "models",
    label: "Models",
    to: "/models",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <path
          d="M10 2.5 17.5 7 10 11.5 2.5 7 10 2.5Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path d="M2.5 10.5 10 15l7.5-4.5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M2.5 14 10 18.5 17.5 14" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    key: "scheduled-runs",
    label: "Scheduled Runs",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10.5" r="7" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M10 6.5v4l2.8 1.6"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M7 2.2h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    key: "settings",
    label: "Settings",
    icon: (
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
        <path
          d="M3 6h8M14.5 6H17M3 14h4M9.5 14H17"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <circle cx="11" cy="6" r="2" style={{ fill: "var(--surface)" }} stroke="currentColor" strokeWidth="1.6" />
        <circle cx="7" cy="14" r="2" style={{ fill: "var(--surface)" }} stroke="currentColor" strokeWidth="1.6" />
      </svg>
    ),
  },
];

interface SidebarProps {
  activeItem?: string;
}

export function Sidebar({ activeItem = "datasets" }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <svg width="26" height="26" viewBox="0 0 26 26" fill="none" style={{ color: "var(--accent)" }}>
          <rect x="1.5" y="1.5" width="23" height="23" rx="6" stroke="currentColor" strokeWidth="1.8" />
          <line x1="5" y1="5" x2="21" y2="21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="21" y1="5" x2="5" y2="21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="13" cy="13" r="2.2" fill="currentColor" />
        </svg>
        <span className="brand-name">HermesBoost</span>
      </div>
      <span className="workspace-pill">Default Organization</span>
      <nav className="nav">
        {NAV_ITEMS.map((item) => {
          const isActive = item.key === activeItem;
          const className = `nav-item${isActive ? " active" : ""}`;
          if (item.to) {
            return (
              <Link key={item.key} to={item.to} className={className}>
                {item.icon}
                {item.label}
              </Link>
            );
          }
          return (
            <button
              key={item.key}
              type="button"
              className={className}
              disabled={!isActive}
              title={isActive ? undefined : "Coming soon"}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <div className="avatar">G</div>
        <div>
          <div className="user-name">Guest</div>
          <div className="user-role">Dev mode &middot; no login yet</div>
        </div>
      </div>
    </aside>
  );
}
