"use client";

import { FormEvent, useEffect, useState } from "react";
import { authenticatedFetch } from "../lib/api";

type Occupation = {
  id: number;
  preferred_label: string;
  alternative_labels: string | null;
  description: string | null;
};

type SuggestedSkill = {
  skill_id: number;
  skill_name: string;
  description: string | null;
  skill_type: string | null;
  relation_type: "essential" | "optional";
};

type OccupationDetails = Occupation & {
  definition: string | null;
  skills: SuggestedSkill[];
};

type SearchResults = {
  items: Occupation[];
  page: number;
  total_pages: number;
  total: number;
};

type Review = {
  included: boolean;
  required_proficiency: number;
  importance: string;
};

type ExistingRequirement = {
  job_title: string;
  skill_id: number;
  approval_status: string;
};

export function selectedSkills(review: Record<number, Review>) {
  return Object.entries(review)
    .filter(([, value]) => value.included)
    .map(([skillId, value]) => ({
      skill_id: Number(skillId),
      required_proficiency: value.required_proficiency,
      importance: value.importance,
    }));
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(url, init);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    const body: unknown = await response.json().catch(() => null);
    if (
      typeof body === "object" && body !== null &&
      "detail" in body && typeof body.detail === "string"
    ) {
      message = body.detail;
    }
    throw new Error(message);
  }
  return await response.json() as T;
}

export function EscoJobSkillReview({
  onCreated,
  requirements,
}: {
  onCreated: () => void;
  requirements: ExistingRequirement[];
}) {
  const [titles, setTitles] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [mappedId, setMappedId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [occupation, setOccupation] = useState<OccupationDetails | null>(null);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [review, setReview] = useState<Record<number, Review>>({});
  const [loadingTitles, setLoadingTitles] = useState(true);
  const [loadingMapping, setLoadingMapping] = useState(false);
  const [loadingOccupation, setLoadingOccupation] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    async function loadTitles() {
      try {
        const data = await request<string[]>("/api/company-esco-mappings/titles", {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) setTitles(data);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Unable to load job titles.");
        }
      } finally {
        if (!controller.signal.aborted) setLoadingTitles(false);
      }
    }
    void loadTitles();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!title) return;
    const controller = new AbortController();
    async function loadMapping() {
      try {
        const params = new URLSearchParams({ job_title: title });
        const data = await request<{ occupation_id: number | null }>(
          `/api/company-esco-mappings/mapping?${params}`,
          { signal: controller.signal }
        );
        if (!controller.signal.aborted) {
          setMappedId(data.occupation_id);
          setSelectedId(data.occupation_id);
          setLoadingOccupation(data.occupation_id !== null);
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Unable to load mapping.");
        }
      } finally {
        if (!controller.signal.aborted) setLoadingMapping(false);
      }
    }
    void loadMapping();
    return () => controller.abort();
  }, [title]);

  useEffect(() => {
    if (selectedId === null) return;
    const controller = new AbortController();
    async function loadOccupation() {
      try {
        const data = await request<OccupationDetails>(
          `/api/esco-occupations/${selectedId}`,
          { signal: controller.signal }
        );
        if (!controller.signal.aborted) {
          setOccupation(data);
          const next: Record<number, Review> = {};
          for (const skill of data.skills) {
            next[skill.skill_id] = {
              included: false,
              required_proficiency: 3,
              importance: "Medium",
            };
          }
          setReview(next);
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Unable to load occupation.");
        }
      } finally {
        if (!controller.signal.aborted) setLoadingOccupation(false);
      }
    }
    void loadOccupation();
    return () => controller.abort();
  }, [selectedId]);

  function selectTitle(value: string) {
    setTitle(value);
    setMappedId(null);
    setSelectedId(null);
    setOccupation(null);
    setReview({});
    setLoadingMapping(Boolean(value));
    setLoadingOccupation(false);
    setError("");
    setMessage("");
  }

  async function searchOccupations(page: number) {
    setSearching(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "10" });
      if (search.trim()) params.set("search", search.trim());
      const data = await request<SearchResults>(`/api/esco-occupations?${params}`);
      setResults(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to search occupations.");
    } finally {
      setSearching(false);
    }
  }

  function chooseOccupation(id: number) {
    if (id === selectedId) return;
    setOccupation(null);
    setReview({});
    setSelectedId(id);
    setLoadingOccupation(true);
    setError("");
    setMessage("");
  }

  async function saveMapping() {
    if (!title || selectedId === null) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await request("/api/company-esco-mappings/mapping", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_title: title, occupation_id: selectedId }),
      });
      setMappedId(selectedId);
      setMessage("Mapping saved. ESCO skills remain suggestions until confirmed.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save mapping.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmSkills() {
    if (!title || selectedId === null || selectedId !== mappedId) return;
    const skills = selectedSkills(review);
    if (!skills.length) {
      setError("Select at least one suggested skill.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await request<{ created: number; already_existing: number }>(
        "/api/company-esco-mappings/requirements",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_title: title, occupation_id: selectedId, skills }),
        }
      );
      setMessage(
        `${result.created} requirement(s) created as Pending; ` +
        `${result.already_existing} existing requirement(s) left unchanged.`
      );
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create requirements.");
    } finally {
      setSaving(false);
    }
  }

  function updateReview(skillId: number, patch: Partial<Review>) {
    setReview((current) => ({
      ...current,
      [skillId]: { ...current[skillId], ...patch },
    }));
  }

  return (
    <section className="job-skills-panel">
      <div className="job-skills-section-heading">
        <div>
          <h2>ESCO occupation mapping and skill review</h2>
          <p>ESCO skills are suggestions, not approved company requirements.</p>
        </div>
      </div>
      {error && <div className="job-skills-alert error" role="alert">{error}</div>}
      {message && <div className="job-skills-alert success" role="status">{message}</div>}
      <div className="job-skills-form">
        <label>
          Company employee job title
          <select
            value={title}
            onChange={(event) => selectTitle(event.target.value)}
            disabled={loadingTitles || saving}
          >
            <option value="">Select a job title</option>
            {titles.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      </div>
      {loadingTitles && <p className="job-skills-note" role="status">Loading job titles...</p>}
      {!loadingTitles && titles.length === 0 && (
        <p className="job-skills-note">No employee job titles are available.</p>
      )}
      {title && (
        <>
          {loadingMapping && <p className="job-skills-note" role="status">Loading mapping...</p>}
          <form
            className="skills-filters"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              void searchOccupations(1);
            }}
          >
            <label className="skills-search">
              <input
                type="search"
                maxLength={200}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search ESCO occupation or alternative label"
                aria-label="Search ESCO occupations"
              />
            </label>
            <button type="submit" className="job-skills-refresh" disabled={searching || saving}>
              Search
            </button>
          </form>
          {searching && <p className="job-skills-note" role="status">Searching...</p>}
          {results && !searching && (
            <div>
              <p className="job-skills-note">{results.total} occupations found.</p>
              {results.items.map((item) => (
                <p key={item.id}>
                  <button
                    type="button"
                    className="job-skills-refresh"
                    disabled={saving || loadingMapping}
                    onClick={() => chooseOccupation(item.id)}
                  >
                    {item.preferred_label}
                  </button>
                  {item.alternative_labels && ` — ${item.alternative_labels}`}
                </p>
              ))}
              {results.total_pages > 1 && (
                <div className="job-skills-form-actions">
                  <button type="button" className="job-skills-refresh"
                    disabled={results.page <= 1 || saving}
                    onClick={() => void searchOccupations(results.page - 1)}>Previous</button>
                  <span>Page {results.page} of {results.total_pages}</span>
                  <button type="button" className="job-skills-refresh"
                    disabled={results.page >= results.total_pages || saving}
                    onClick={() => void searchOccupations(results.page + 1)}>Next</button>
                </div>
              )}
            </div>
          )}
          {loadingOccupation && <p className="job-skills-note" role="status">Loading occupation...</p>}
          {occupation && (
            <>
              <h3>{occupation.preferred_label}</h3>
              {occupation.alternative_labels && <p>Alternative labels: {occupation.alternative_labels}</p>}
              {occupation.description && <p>{occupation.description}</p>}
              {occupation.definition && <p>{occupation.definition}</p>}
              <p className="job-skills-note">
                {mappedId === selectedId ? "Saved mapping" : "Not yet saved for this job title"}
              </p>
              <button type="button" className="job-skills-submit"
                disabled={saving || mappedId === selectedId}
                onClick={() => void saveMapping()}>Save mapping</button>
              {(["essential", "optional"] as const).map((relation) => (
                <section key={relation}>
                  <h3>{relation === "essential" ? "Essential" : "Optional"} ESCO suggestions</h3>
                  {occupation.skills.filter((skill) => skill.relation_type === relation).length === 0 && (
                    <p className="job-skills-note">No suggestions in this category.</p>
                  )}
                  {occupation.skills.filter((skill) => skill.relation_type === relation).map((skill) => (
                    <div className="skill-card" key={`${relation}-${skill.skill_id}`}>
                      <label>
                        <input type="checkbox"
                          checked={review[skill.skill_id]?.included ?? false}
                          onChange={(event) => updateReview(skill.skill_id, { included: event.target.checked })}
                          disabled={saving} />
                        {" "}{skill.skill_name}
                      </label>
                      {skill.skill_type && <span className="skill-category"> {skill.skill_type}</span>}
                      {requirements
                        .filter((item) =>
                          item.skill_id === skill.skill_id &&
                          item.job_title.trim().toLowerCase() === title.trim().toLowerCase()
                        )
                        .map((item, index) => (
                          <p key={index} className="job-skills-note">
                            Existing company requirement: {item.approval_status}. Confirmation will not change it.
                          </p>
                        ))}
                      {skill.description && <p>{skill.description}</p>}
                      <div className="job-skills-form">
                        <label>
                          Required proficiency for {skill.skill_name}
                          <select value={review[skill.skill_id]?.required_proficiency ?? 3}
                            disabled={saving || !review[skill.skill_id]?.included}
                            onChange={(event) => updateReview(skill.skill_id, { required_proficiency: Number(event.target.value) })}>
                            {[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level}</option>)}
                          </select>
                        </label>
                        <label>
                          Importance for {skill.skill_name}
                          <select value={review[skill.skill_id]?.importance ?? "Medium"}
                            disabled={saving || !review[skill.skill_id]?.included}
                            onChange={(event) => updateReview(skill.skill_id, { importance: event.target.value })}>
                            {["Low", "Medium", "High", "Critical"].map((item) => <option key={item}>{item}</option>)}
                          </select>
                        </label>
                      </div>
                    </div>
                  ))}
                </section>
              ))}
              <p className="job-skills-note">Confirmation creates Pending requirements only; existing requirements are not changed.</p>
              <button type="button" className="job-skills-submit"
                disabled={saving || mappedId !== selectedId}
                onClick={() => void confirmSkills()}>Confirm selected skills</button>
            </>
          )}
        </>
      )}
    </section>
  );
}
