import { NavLink, Outlet } from "react-router";

import { useAuth } from "../auth";
import { ModeBadge } from "./ModeBadge";

const NAV = [
  { to: "/", label: "Ask", end: true },
  { to: "/history", label: "History", end: false },
  { to: "/recorded", label: "Recorded runs", end: false },
  { to: "/dictionary", label: "Data dictionary", end: false },
  { to: "/about", label: "About", end: false },
];

export function Logo() {
  return (
    <span className="flex items-center gap-2.5 font-display text-[15px] font-semibold text-ink">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="#0b0f0d" stroke="rgba(148,168,156,.14)" />
        <path
          d="M8 22V10m0 12h16M12 19v-4m4 4v-8m4 8v-6"
          stroke="#34d399"
          strokeWidth="2.4"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      Arunika Analyst
    </span>
  );
}

export function FictionalNotice({ className = "" }: { className?: string }) {
  return (
    <p className={`text-xs text-ink-mute ${className}`}>
      PT Arunika Niaga is a fictional company and all of its data is synthetic. A portfolio project
      by Baron Purwa Hartono, built to production standards.
    </p>
  );
}

export function Layout() {
  const { user, signOut } = useAuth();
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-bg"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-line-faint bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <NavLink to="/" aria-label="Arunika Analyst, home">
            <Logo />
          </NavLink>
          <nav
            aria-label="Main"
            className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto"
          >
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition-colors ${
                    isActive ? "bg-panel-strong text-ink" : "text-ink-mute hover:text-ink"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <ModeBadge />
          </div>
          {user === null && (
            <NavLink to="/login" className="btn-primary px-3 py-1.5 text-sm">
              Sign in to ask
            </NavLink>
          )}
          {user && (
            <div className="flex items-center gap-3">
              <span className="hidden text-right text-xs leading-tight sm:block">
                <span className="block text-ink-soft">{user.user_id}</span>
                <span className="text-ink-mute">
                  {user.role === "manager" ? "Manager · Jabodetabek only" : "Analyst · all regions"}
                </span>
              </span>
              <button
                type="button"
                className="btn-ghost px-3 py-1.5"
                onClick={() => void signOut()}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-[1180px] flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
      <footer className="border-t border-line-faint">
        <div className="mx-auto max-w-[1180px] px-4 py-5 sm:px-6">
          <FictionalNotice />
        </div>
      </footer>
    </div>
  );
}
