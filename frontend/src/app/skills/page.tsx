"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

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

  useEffect(() => {
    async function loadSkills() {
      try {
        const response = await fetch("/api/skills", { cache: "no-store" });
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        setSkills(await response.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load skills.");
      } finally {
        setLoading(false);
      }
    }
    loadSkills();
  }, []);

  const categories = useMemo(
    () => [...new Set(skills.map((s) => s.category).filter(Boolean))].sort(),
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

      return matchesSearch && (category === "All" || skill.category === category);
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
        <Link href="/" className="nav-item">â–¦ <span>Overview</span></Link>
        <Link href="/imports" className="nav-item">â–¤ <span>Employee Imports</span></Link>

        <div className="nav-label nav-spaced">MANAGEMENT</div>
        <Link href="/employees" className="nav-item">â™™ <span>Employees</span></Link>
        <Link href="/employee-skills" className="nav-item">▣ <span>Employee Skills</span></Link>
        <Link href="/skills" className="nav-item active">â—‡ <span>Skills</span></Link>
        <div className="nav-item">â–£ <span>Courses</span></div>
        <div className="nav-item">âŒ• <span>Training Needs</span></div>
        <div className="nav-item">â–¤ <span>Training Plans</span></div>
        <div className="nav-item">â–· <span>Execution</span></div>
        <div className="nav-item">â–¥ <span>Reports</span></div>

        <div className="sidebar-bottom">
          <div className="user-avatar">TM</div>
          <div><strong>Training Manager</strong><span>Administrator</span></div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace / Skills</div>
          <div className="topbar-right">
            <span className="system-status"><i /> Read-only catalogue</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content skills-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">TALENT MANAGEMENT</div>
              <h1>Skills</h1>
              <p>Explore the organization's skill catalogue and reference information.</p>
            </div>
            <span className="workspace-badge">Company Skill Catalogue</span>
          </div>

          <section className="skills-stats">
            <div className="skills-stat">
              <span>Total skills</span>
              <strong>{loading ? "â€”" : skills.length.toLocaleString()}</strong>
              <small>Skills in the database</small>
            </div>
            <div className="skills-stat">
              <span>Categories</span>
              <strong>{loading ? "â€”" : categories.length}</strong>
              <small>Distinct skill categories</small>
            </div>
            <div className="skills-stat">
              <span>ESCO references</span>
              <strong>{loading ? "â€”" : skills.filter((s) => s.esco_concept_uri).length}</strong>
              <small>Skills with ESCO identifiers</small>
            </div>
            <div className="skills-stat">
              <span>Search results</span>
              <strong>{loading ? "â€”" : filteredSkills.length}</strong>
              <small>Based on current filters</small>
            </div>
          </section>

          <section className="skills-panel">
            <div className="skills-panel-heading">
              <div><h2>Skills directory</h2><p>Search and explore existing skills.</p></div>
              <span className="skills-readonly">READ ONLY</span>
            </div>

            <div className="skills-filters">
              <div className="skills-search">
                <span>âŒ•</span>
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search skill name, description or alternative label..."
                />
              </div>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="All">All categories</option>
                {categories.map((item) => <option key={item} value={item!}>{item}</option>)}
              </select>
              <button className="clear-filters" onClick={() => { setSearch(""); setCategory("All"); }}>
                Reset
              </button>
            </div>

            {loading && <div className="skills-message">Loading skills catalogue...</div>}

            {!loading && error && (
              <div className="skills-error">
                <strong>Unable to load skills</strong>
                <p>{error}</p>
                <p>Check that the backend and frontend are running.</p>
              </div>
            )}

            {!loading && !error && (
              <div className="skills-grid">
                {filteredSkills.map((skill) => (
                  <article className="skill-card" key={skill.skill_id}>
                    <div className="skills-card-top">
                      <div className="skill-icon">â—‡</div>
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
                      <a className="skill-esco-link" href={skill.esco_concept_uri} target="_blank" rel="noreferrer">
                        View ESCO reference â†—
                      </a>
                    )}
                  </article>
                ))}
                {filteredSkills.length === 0 && (
                  <div className="skills-empty">
                    <strong>No skills found</strong>
                    <p>Try changing your search or category filter.</p>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
