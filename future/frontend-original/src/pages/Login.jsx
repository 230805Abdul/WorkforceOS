import { useState } from "react";
import { api } from "../api";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      if (mode === "register") {
        await api.register({ email, password, full_name: fullName, role: "recruiter" });
      }
      const { access_token, refresh_token } = await api.login(email, password);
      api.setTokens(access_token, refresh_token);
      onLogin(await api.me());
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="container" style={{ maxWidth: 400, paddingTop: "4rem" }}>
      <h1>WorkforceOS</h1>
      <p style={{ color: "#94a3b8" }}>Cloud-native workforce & recruitment platform</p>
      <form className="card" onSubmit={submit}>
        {error && <div className="error">{error}</div>}
        {mode === "register" && (
          <input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        )}
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
        <button type="submit" style={{ width: "100%" }}>
          {mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
      <button
        onClick={() => setMode(mode === "login" ? "register" : "login")}
        style={{ background: "transparent", color: "#93c5fd" }}
      >
        {mode === "login" ? "Need an account? Register" : "Have an account? Log in"}
      </button>
    </div>
  );
}
