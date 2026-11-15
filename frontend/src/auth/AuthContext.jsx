import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import ReauthDialog from "../components/auth/ReauthDialog";
import { api, configureAuth } from "../services/api";

/**
 * Who is signed in, and what may they do.
 *
 * The SERVER is the source of truth: on every page load we ask GET /api/auth/me. The browser's HttpOnly session cookie
 * decides the answer; this context just remembers it so the UI can show the right navigation and buttons.
 * Hiding a button is NOT security: every API call is checked again by the backend.
 */
const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", user: null, config: null, error: null, notice: null });
  // One shared password prompt, even if several requests need it at the same moment.
  const [reauthPrompt, setReauthPrompt] = useState(null);
  const pendingReauth = useRef(null);
  const askForPassword = useCallback(() => {
    if (!pendingReauth.current) {
      pendingReauth.current = new Promise((resolve) => setReauthPrompt({ resolve }));
      pendingReauth.current.finally(() => { pendingReauth.current = null; });
    }
    return pendingReauth.current;
  }, []);

  const signedIn = useCallback((me) => {
    configureAuth({ token: me.csrf_token });
    setState((s) => ({ ...s, status: "authenticated", user: me, error: null, notice: null }));
  }, []);

  const signedOut = useCallback((notice = null) => {
    configureAuth({ token: null });
    setState((s) => ({ ...s, status: "anonymous", user: null, notice }));
  }, []);

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: "loading", error: null }));
    try {
      const config = await api.auth.config();
      setState((s) => ({ ...s, config }));
      signedIn(await api.auth.me());
    } catch (error) {
      if (error.status === 401) signedOut();
      else setState((s) => ({ ...s, status: "error", error })); // API unreachable, database down, ...
    }
  }, [signedIn, signedOut]);

  useEffect(() => {
    // Any API call that comes back 401 means the session ended (expired, signed out elsewhere, password changed).
    configureAuth({
      reauth: askForPassword,
      unauthorized: (error) =>
        signedOut(error.code === "session_expired" ? "Your session has expired. Please sign in again."
          : error.code === "account_disabled" ? "Your account has been disabled." : "Please sign in to continue."),
    });
    load();
  }, [load, signedOut, askForPassword]);

  const value = useMemo(() => {
    const permissions = new Set(state.user?.permissions ?? []);
    return {
      ...state,
      can: (permission) => permissions.has(permission),
      canAny: (...list) => list.some((p) => permissions.has(p)),
      retry: load,
      login: async (body) => signedIn(await api.auth.login(body)),
      register: async (body) => signedIn(await api.auth.register(body)),
      logout: async () => {
        try {
          await api.auth.logout();
        } finally {
          signedOut("You have been signed out.");
        }
      },
      refresh: async () => signedIn(await api.auth.me()), // after changing your own name, etc.
      updateUser: (me) => signedIn(me),
      clearNotice: () => setState((s) => ({ ...s, notice: null })),
    };
  }, [state, load, signedIn, signedOut]);

  return (
    <AuthContext.Provider value={value}>
      {children}
      {reauthPrompt && (
        <ReauthDialog minutes={state.config?.reauth_minutes}
          onDone={(ok) => { reauthPrompt.resolve(ok); setReauthPrompt(null); }} />
      )}
    </AuthContext.Provider>
  );
}
