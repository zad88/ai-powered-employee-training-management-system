"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { authenticatedFetch } from "../../lib/api";

type Skill = {
  skill_id: number;
  skill_name: string;
  description: string | null;
  category: string | null;
  esco_concept_uri: string | null;
  alternative_labels: string | null;
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");

  async function loadSkills() {
    setLoading(true);
    setError("");

    try {
      const response = await authenticatedFetch("/api/skills", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Unable to load skills (${response.status}).`);
      }

      const data = await response.json();
      setSkills(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load skills.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSkills(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const categories = useMemo(
    () => [...new Set(skills.map((skill) => skill.category).filter(Boolean))].sort(),
    [skills]
  );

  const filteredSkills = useMemo(() => {
    const term = search.trim().toLowerCase();

    return skills.filter((skill) => {
      const matchesSearch =
        !term ||
        skill.skill_name.toLowerCase().includes(term) ||
        (skill.description ?? "").toLowerCase().includes(term) ||
        (skill.alternative_labels ?? "").toLowerCase().includes(term);

      return matchesSearch &&
        (category === "All" || skill.category === category);
    });
  }, [skills, search, category]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <div className="brand-icon">T</div>
          <div><strong>TalentFlow</strong><span>Training Management</span></div>
        </Link>

        <div className="nav-label">WORKSPACE</div>
        <Link href="/" className="nav-item">▦ <span>Overview</span></Link>
        <Link href="/imports" className="nav-item">▤ <span>Employee Imports</span></Link>

        <div className="nav-label nav-spaced">MANAGEMENT</div>
        <Link href="/employees" className="nav-item">♙ <span>Employees</span></Link>
        <Link href="/skills" className="nav-item active">◇ <span>Skills</span></Link>
        <Link href="/employee-skills" className="nav-item">▣ <span>Employee Skills</span></Link>
        <Link href="/assessments" className="nav-item">✓ <span>Assessments</span></Link>
        <Link href="/job-requirements" className="nav-item">⌕ <span>Job Requirements</span></Link>
        <Link href="/tna" className="nav-item">▥ <span>Training Needs</span></Link>

        <div className="sidebar-bottom">
          <div className="user-avatar">TM</div>
          <div><strong>Training Manager</strong><span>Administrator</span></div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace / Skills</div>
          <div className="topbar-right">
            <span className="system-status"><i /> Shared reference catalogue</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content skills-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">TALENT MANAGEMENT</div>
              <h1>Skills Catalogue</h1>
              <p>Manage the shared skill reference catalogue used across employee assessments and job requirements.</p>
            </div>
            <span className="skills-readonly">Shared reference catalogue</span>
          </div>

          {error && <div className="job-skills-alert error">{error}</div>}

          <section className="skills-stats">
            <div className="skills-stat">
              <span>Total skills</span>
              <strong>{loading ? "—" : skills.length.toLocaleString()}</strong>
              <small>Skills in the shared catalogue</small>
            </div>
            <div className="skills-stat">
              <span>Categories</span>
              <strong>{loading ? "—" : categories.length}</strong>
              <small>Distinct categories</small>
            </div>
            <div className="skills-stat">
              <span>ESCO references</span>
              <strong>{loading ? "—" : skills.filter(s => s.esco_concept_uri).length}</strong>
              <small>Skills with ESCO identifiers</small>
            </div>
            <div className="skills-stat">
              <span>Search results</span>
              <strong>{loading ? "—" : filteredSkills.length}</strong>
              <small>Skills matching your filters</small>
            </div>
          </section>

          <section className="skills-panel">
            <div className="skills-panel-heading">
              <div>
                <h2>Skills directory</h2>
                <p>Search and filter the globally shared ESCO skills catalogue.</p>
              </div>
              <span className="skills-readonly">SHARED CATALOGUE</span>
            </div>

            <div className="skills-filters">
              <div className="skills-search">
                <span>⌕</span>
                <input value={search} onChange={e => setSearch(e.target.value)}
                  placeholder="Search skill name, description or alternative label..." />
              </div>
              <select value={category} onChange={e => setCategory(e.target.value)}>
                <option value="All">All categories</option>
                {categories.map(item => <option key={item} value={item!}>{item}</option>)}
              </select>
              <button className="clear-filters"
                onClick={() => { setSearch(""); setCategory("All"); }}>
                Reset
              </button>
            </div>

            {loading && <div className="skills-message">Loading skills catalogue...</div>}

            {!loading && !error && (
              <div className="skills-grid">
                {filteredSkills.map(skill => (
                  <article className="skill-card" key={skill.skill_id}>
                    <div className="skills-card-top">
                      <div className="skill-icon">◇</div>
                      <span className="skill-id">SKILL #{skill.skill_id}</span>
                    </div>
                    <h3>{skill.skill_name}</h3>
                    <span className="skill-category">{skill.category || "Uncategorized"}</span>
                    <p className="skill-description">{skill.description || "No description available."}</p>

                    {skill.alternative_labels && (
                      <div className="skill-alternatives">
                        <strong>Alternative labels:</strong>
                        <span>{skill.alternative_labels}</span>
                      </div>
                    )}

                    <div className="skill-card-footer">
                      <span>ESCO reference</span>
                      <span className={skill.esco_concept_uri ? "esco-linked" : "esco-missing"}>
                        {skill.esco_concept_uri ? "Linked" : "Not linked"}
                      </span>
                    </div>

                    {skill.esco_concept_uri && (
                      <a className="skill-esco-link" href={skill.esco_concept_uri}
                        target="_blank" rel="noreferrer">
                        View ESCO reference ↗
                      </a>
                    )}

                  </article>
                ))}

                {filteredSkills.length === 0 && (
                  <div className="skills-empty">
                    <strong>No skills found</strong>
                    <p>Try changing your search or category filter, or add a new skill.</p>
                  </div>
                )}
              </div>
            )}
          </section>

          <section className="skills-related-links">
            <Link href="/employee-skills">
              <strong>Employee Skills</strong>
              <span>Review employee proficiency and skill gaps →</span>
            </Link>
            <Link href="/assessments">
              <strong>Skill Assessments</strong>
              <span>Create assessments and review evidence →</span>
            </Link>
            <Link href="/job-requirements">
              <strong>Job Requirements</strong>
              <span>Define and approve role skill requirements →</span>
            </Link>
          </section>
        </div>
      </section>
    </main>
  );
}
