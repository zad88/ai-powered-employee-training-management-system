"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Skill = {
  skill_id: number;
  skill_name: string;
  description: string | null;
  category: string | null;
  esco_concept_uri: string | null;
  alternative_labels: string | null;
};

type SkillForm = {
  skill_name: string;
  description: string;
  category: string;
  esco_concept_uri: string;
  alternative_labels: string;
};

const emptyForm: SkillForm = {
  skill_name: "",
  description: "",
  category: "",
  esco_concept_uri: "",
  alternative_labels: "",
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<SkillForm>(emptyForm);

  async function loadSkills() {
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/skills", { cache: "no-store" });
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
    loadSkills();
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

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyForm);
    setError("");
    setSuccess("");
    setShowForm(true);
  }

  function openEditForm(skill: Skill) {
    setEditingId(skill.skill_id);
    setForm({
      skill_name: skill.skill_name,
      description: skill.description ?? "",
      category: skill.category ?? "",
      esco_concept_uri: skill.esco_concept_uri ?? "",
      alternative_labels: skill.alternative_labels ?? "",
    });
    setError("");
    setSuccess("");
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(emptyForm);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (form.skill_name.trim().length < 2) {
      setError("Skill name must contain at least two characters.");
      return;
    }

    if (form.esco_concept_uri.trim()) {
      try {
        new URL(form.esco_concept_uri.trim());
      } catch {
        setError("Enter a valid ESCO reference URL.");
        return;
      }
    }

    const payload = {
      skill_name: form.skill_name.trim(),
      description: form.description.trim() || null,
      category: form.category.trim() || null,
      esco_concept_uri: form.esco_concept_uri.trim() || null,
      alternative_labels: form.alternative_labels.trim() || null,
    };

    setSaving(true);

    try {
      const isEditing = editingId !== null;
      const response = await fetch(
        isEditing ? `/api/skills/${editingId}` : "/api/skills/",
        {
          method: isEditing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        let message = "Unable to save the skill.";
        try {
          const data = await response.json();
          message = typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? data);
        } catch {
          // Keep the default error message.
        }
        throw new Error(message);
      }

      setSuccess(isEditing
        ? "Skill updated successfully."
        : "Skill created successfully.");

      closeForm();
      await loadSkills();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save the skill.");
    } finally {
      setSaving(false);
    }
  }

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
            <button className="job-skills-submit" onClick={openCreateForm}>
              + Add skill
            </button>
          </div>

          {error && <div className="job-skills-alert error">{error}</div>}
          {success && <div className="job-skills-alert success">{success}</div>}

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

          {showForm && (
            <section className="skills-panel">
              <div className="skills-panel-heading">
                <div>
                  <h2>{editingId ? "Edit skill" : "Create a new skill"}</h2>
                  <p>{editingId ? "Update the selected catalogue entry." : "Add a skill to the shared reference catalogue."}</p>
                </div>
              </div>

              <form className="job-skills-form" onSubmit={handleSubmit}>
                <label>
                  Skill name *
                  <input required minLength={2} maxLength={150}
                    value={form.skill_name}
                    onChange={e => setForm({ ...form, skill_name: e.target.value })}
                    placeholder="e.g. Python" />
                </label>

                <label>
                  Category
                  <input maxLength={100} value={form.category}
                    onChange={e => setForm({ ...form, category: e.target.value })}
                    placeholder="e.g. Technical" />
                </label>

                <label className="skills-form-full">
                  Description
                  <textarea rows={3} value={form.description}
                    onChange={e => setForm({ ...form, description: e.target.value })}
                    placeholder="Describe the skill..." />
                </label>

                <label>
                  ESCO concept URI
                  <input type="url" maxLength={500} value={form.esco_concept_uri}
                    onChange={e => setForm({ ...form, esco_concept_uri: e.target.value })}
                    placeholder="https://..." />
                </label>

                <label>
                  Alternative labels
                  <input value={form.alternative_labels}
                    onChange={e => setForm({ ...form, alternative_labels: e.target.value })}
                    placeholder="Other names for this skill" />
                </label>

                <div className="job-skills-form-actions skills-form-full">
                  <button type="submit" className="job-skills-submit" disabled={saving}>
                    {saving ? "Saving..." : editingId ? "Save changes" : "Create skill"}
                  </button>
                  <button type="button" className="job-skills-cancel"
                    onClick={closeForm} disabled={saving}>
                    Cancel
                  </button>
                </div>
              </form>
            </section>
          )}

          <section className="skills-panel">
            <div className="skills-panel-heading">
              <div>
                <h2>Skills directory</h2>
                <p>Search, filter and manage existing catalogue entries.</p>
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

                    <div className="skills-card-actions">
                      <button className="job-skills-edit" onClick={() => openEditForm(skill)}>
                        Edit skill
                      </button>
                    </div>
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
