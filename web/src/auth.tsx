import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { SESSION_EXPIRED, api } from "./api/client";
import type { Me } from "./api/types";

interface AuthState {
  user: Me | null | undefined; // undefined while the first /api/me is in flight
  setUser: (user: Me | null) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((me) => alive && setUser(me))
      .catch(() => alive && setUser(null));
    const expired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED, expired);
    return () => {
      alive = false;
      window.removeEventListener(SESSION_EXPIRED, expired);
    };
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(() => ({ user, setUser, signOut }), [user, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth needs an AuthProvider");
  return ctx;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) {
    return (
      <p className="p-8 text-ink-mute" role="status">
        Loading…
      </p>
    );
  }
  if (user === null) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}
