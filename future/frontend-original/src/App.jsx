import { useEffect, useState } from "react";
import { api } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

export default function App() {
  const [user, setUser] = useState(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const { access } = api.getTokens();
    if (!access) {
      setChecked(true);
      return;
    }
    api.me()
      .then(setUser)
      .catch(() => api.clearTokens())
      .finally(() => setChecked(true));
  }, []);

  if (!checked) return null;

  return user ? (
    <Dashboard user={user} onLogout={() => { api.clearTokens(); setUser(null); }} />
  ) : (
    <Login onLogin={setUser} />
  );
}
