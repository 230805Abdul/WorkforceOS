import { useEffect, useState } from "react";
import { api } from "../api";

export default function Dashboard({ user, onLogout }) {
  const [jobs, setJobs] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  const [error, setError] = useState("");

  function loadJobs() {
    api.listJobs().then(setJobs).catch((e) => setError(e.message));
  }

  useEffect(loadJobs, []);

  async function createJob(e) {
    e.preventDefault();
    try {
      await api.createJob({
        title: newTitle,
        description: "Add a description",
        department: "Engineering",
        location: "Remote",
      });
      setNewTitle("");
      loadJobs();
    } catch (err) {
      setError(err.message);
    }
  }

  const badgeClass = { open: "badge-open", draft: "badge-draft", closed: "badge-closed" };

  return (
    <div>
      <nav>
        <strong>WorkforceOS</strong>
        <span style={{ marginLeft: "auto", color: "#94a3b8" }}>
          {user.full_name} · {user.role}
        </span>
        <a href="#" onClick={onLogout}>Log out</a>
      </nav>
      <div className="container">
        <h2>Open Roles</h2>
        {error && <div className="error">{error}</div>}

        {["admin", "recruiter", "hiring_manager"].includes(user.role) && (
          <form className="card" onSubmit={createJob} style={{ display: "flex", gap: "0.5rem" }}>
            <input
              placeholder="New job title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              style={{ marginBottom: 0 }}
              required
            />
            <button type="submit">Post job</button>
          </form>
        )}

        {jobs.length === 0 && <p style={{ color: "#94a3b8" }}>No jobs posted yet.</p>}
        {jobs.map((job) => (
          <div className="card" key={job.id}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{job.title}</strong>
              <span className={`badge ${badgeClass[job.status] || ""}`}>{job.status}</span>
            </div>
            <p style={{ color: "#94a3b8", margin: "0.4rem 0 0" }}>
              {job.department} · {job.location}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
