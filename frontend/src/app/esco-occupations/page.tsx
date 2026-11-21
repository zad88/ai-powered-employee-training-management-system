"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { authenticatedFetch } from "../../lib/api";

type OccupationSummary = {
  id: number;
  esco_concept_uri: string;
  preferred_label: string;
  alternative_labels: string | null;
  description: string | null;
  isco_group: string | null;
  code: string | null;
};

type OccupationSkill = {
  skill_id: number;
  skill_name: string;
  esco_concept_uri: string | null;
  description: string | null;
  alternative_labels: string | null;
  skill_type: string | null;
  relation_type: "essential" | "optional";
};

type OccupationDetails = OccupationSummary & {
  definition: string | null;
  scope_note: string | null;
  regulated_profession_note: string | null;
  nace_code: string | null;
  status: string | null;
  modified_date: string | null;
  skills: OccupationSkill[];
  essential_skills_count: number;
  optional_skills_count: number;
};

type OccupationPage = {
  items: OccupationSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

type ListQuery = {
  search: string;
  page: number;
};

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

async function responseError(response: Response, fallback: string) {
  let detail: unknown;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      detail = body.detail;
    }
  } catch {
    // Use the status-based message when the response is not JSON.
  }

  return typeof detail === "string"
    ? detail
    : `${fallback} (${response.status}).`;
}

export default function ESCOOccupationsPage() {
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState<ListQuery>({ search: "", page: 1 });
  const [occupations, setOccupations] = useState<OccupationPage | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [selectedOccupationId, setSelectedOccupationId] = useState<number | null>(
    null
  );
  const [occupation, setOccupation] = useState<OccupationDetails | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const backButtonRef = useRef<HTMLButtonElement>(null);
  const detailHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const search = searchInput.trim();
      setQuery((current) => (
        current.search === search && current.page === 1
          ? current
          : { search, page: 1 }
      ));
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(query.page),
      page_size: String(PAGE_SIZE),
    });
    if (query.search) {
      params.set("search", query.search);
    }

    async function loadOccupations() {
      setListLoading(true);
      setListError("");

      try {
        const response = await authenticatedFetch(
          `/api/esco-occupations?${params.toString()}`,
          { cache: "no-store", signal: controller.signal }
        );
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Unable to load ESCO occupations")
          );
        }

        const data = await response.json() as OccupationPage;
        if (!controller.signal.aborted) {
          setOccupations(data);
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setListError(
            reason instanceof Error
              ? reason.message
              : "Unable to load ESCO occupations."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setListLoading(false);
        }
      }
    }

    void loadOccupations();
    return () => controller.abort();
  }, [query]);

  useEffect(() => {
    if (selectedOccupationId === null) {
      return;
    }

    const controller = new AbortController();
    backButtonRef.current?.focus();

    async function loadOccupationDetails() {
      try {
        const response = await authenticatedFetch(
          `/api/esco-occupations/${selectedOccupationId}`,
          { cache: "no-store", signal: controller.signal }
        );
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Unable to load occupation details")
          );
        }

        const data = await response.json() as OccupationDetails;
        if (!controller.signal.aborted) {
          setOccupation(data);
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setDetailError(
            reason instanceof Error
              ? reason.message
              : "Unable to load occupation details."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      }
    }

    void loadOccupationDetails();
    return () => controller.abort();
  }, [selectedOccupationId]);

  useEffect(() => {
    if (occupation) {
      detailHeadingRef.current?.focus();
    }
  }, [occupation]);

  function openOccupation(occupationId: number) {
    setOccupation(null);
    setDetailError("");
    setDetailLoading(true);
    setSelectedOccupationId(occupationId);
  }

  function returnToResults() {
    setSelectedOccupationId(null);
    setOccupation(null);
    setDetailError("");
    setDetailLoading(false);
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const search = searchInput.trim();
    setQuery((current) => (
      current.search === search && current.page === 1
        ? current
        : { search, page: 1 }
    ));
  }

  function showPage(page: number) {
    setQuery((current) => ({ ...current, page }));
  }

  const essentialSkills = occupation?.skills.filter(
    (skill) => skill.relation_type === "essential"
  ) ?? [];
  const optionalSkills = occupation?.skills.filter(
    (skill) => skill.relation_type === "optional"
  ) ?? [];

  return (
    <main className="content skills-content esco-occupations-content">
      <header className="page-heading">
        <div>
          <div className="eyebrow">SHARED REFERENCE CATALOGUE</div>
          <h1>ESCO Occupation Explorer</h1>
          <p>Explore occupations and the skills associated with each role.</p>
        </div>
        <span className="skills-readonly">ESCO REFERENCE DATA</span>
      </header>

      {selectedOccupationId === null ? (
        <section className="skills-panel">
          <div className="skills-panel-heading">
            <div>
              <h2>Occupation directory</h2>
              <p>Search preferred and alternative occupation labels.</p>
            </div>
          </div>

          <form className="skills-filters esco-occupation-search" onSubmit={submitSearch}>
            <label className="skills-search">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                maxLength={200}
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search occupation names or alternative labels..."
                aria-label="Search occupation names or alternative labels"
              />
            </label>
            <button className="button primary" type="submit">Search</button>
          </form>

          {listError && (
            <div className="job-skills-alert error" role="alert">{listError}</div>
          )}
          {listLoading && (
            <div className="skills-message" role="status">
              Loading ESCO occupations...
            </div>
          )}
          {!listLoading && !listError && occupations && occupations.items.length === 0 && (
            <div className="skills-empty esco-empty">
              <strong>No occupations found</strong>
              <p>Try a different occupation name or alternative label.</p>
            </div>
          )}
          {!listLoading && !listError && occupations && occupations.items.length > 0 && (
            <>
              <div className="skills-grid esco-occupation-grid">
                {occupations.items.map((item) => (
                  <button
                    className="skill-card esco-occupation-card"
                    key={item.id}
                    type="button"
                    onClick={() => openOccupation(item.id)}
                    aria-label={`View ${item.preferred_label}`}
                  >
                    <div className="skills-card-top">
                      <div className="skill-icon" aria-hidden="true">◇</div>
                      <span className="skill-id">
                        {item.isco_group ? `ISCO ${item.isco_group}` : `#${item.id}`}
                      </span>
                    </div>
                    <h3>{item.preferred_label}</h3>
                    {(item.code || item.alternative_labels) && (
                      <div className="esco-occupation-meta">
                        {item.code && <span>Code: {item.code}</span>}
                        {item.alternative_labels && (
                          <span className="esco-alternative-labels">
                            Also known as: {item.alternative_labels}
                          </span>
                        )}
                      </div>
                    )}
                    <p className="skill-description">
                      {item.description || "No description available."}
                    </p>
                    <span className="skill-esco-link">View occupation details →</span>
                  </button>
                ))}
              </div>

              <nav className="esco-pagination" aria-label="Occupation pages">
                <span>
                  Showing {(occupations.page - 1) * occupations.page_size + 1}
                  {"–"}
                  {Math.min(
                    occupations.page * occupations.page_size,
                    occupations.total
                  )}
                  {" "}of {occupations.total}
                </span>
                <div>
                  <button
                    className="clear-filters"
                    type="button"
                    onClick={() => showPage(query.page - 1)}
                    disabled={query.page <= 1}
                  >
                    Previous
                  </button>
                  <span>Page {occupations.page} of {occupations.total_pages}</span>
                  <button
                    className="clear-filters"
                    type="button"
                    onClick={() => showPage(query.page + 1)}
                    disabled={query.page >= occupations.total_pages}
                  >
                    Next
                  </button>
                </div>
              </nav>
            </>
          )}
        </section>
      ) : (
        <section className="esco-occupation-detail">
          <button
            ref={backButtonRef}
            className="clear-filters esco-back-button"
            type="button"
            onClick={returnToResults}
          >
            ← Back to occupation results
          </button>

          {detailLoading && (
            <div className="skills-message" role="status" aria-live="polite" aria-atomic="true">
              Loading occupation details...
            </div>
          )}
          {detailError && (
            <div className="job-skills-alert error" role="alert">{detailError}</div>
          )}
          {occupation && (
            <>
              <section className="skills-panel esco-occupation-summary">
                <div className="skills-panel-heading">
                  <div>
                    <div className="eyebrow">ESCO OCCUPATION</div>
                    <h2 ref={detailHeadingRef} tabIndex={-1}>
                      {occupation.preferred_label}
                    </h2>
                  </div>
                  {occupation.isco_group && (
                    <span className="skills-readonly">ISCO {occupation.isco_group}</span>
                  )}
                </div>
                {occupation.alternative_labels && (
                  <div className="skill-alternatives">
                    <strong>Alternative labels</strong>
                    <span>{occupation.alternative_labels}</span>
                  </div>
                )}
                {occupation.description && (
                  <div className="esco-detail-copy">
                    <h3>Description</h3>
                    <p>{occupation.description}</p>
                  </div>
                )}
                {occupation.definition && (
                  <div className="esco-detail-copy">
                    <h3>Definition</h3>
                    <p>{occupation.definition}</p>
                  </div>
                )}
                {occupation.scope_note && (
                  <div className="esco-detail-copy">
                    <h3>Scope note</h3>
                    <p>{occupation.scope_note}</p>
                  </div>
                )}
                <div className="esco-detail-identifiers">
                  {occupation.code && <span>Code: {occupation.code}</span>}
                  <a
                    href={occupation.esco_concept_uri}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View ESCO reference ↗
                  </a>
                </div>
              </section>

              <div className="esco-skill-groups">
                <SkillSection title="Essential skills" skills={essentialSkills} />
                <SkillSection title="Optional skills" skills={optionalSkills} />
              </div>
            </>
          )}
        </section>
      )}
    </main>
  );
}

function SkillSection({
  title,
  skills,
}: {
  title: string;
  skills: OccupationSkill[];
}) {
  return (
    <section className="skills-panel esco-skill-section">
      <div className="skills-panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{skills.length} associated {skills.length === 1 ? "skill" : "skills"}</p>
        </div>
      </div>
      {skills.length === 0 ? (
        <div className="skills-message">No {title.toLowerCase()} are listed.</div>
      ) : (
        <div className="esco-associated-skills">
          {skills.map((skill) => (
            <article className="skill-card esco-associated-skill" key={skill.skill_id}>
              <h3>{skill.skill_name}</h3>
              {skill.description && <p className="skill-description">{skill.description}</p>}
              {skill.skill_type && (
                <span className="skill-category">{skill.skill_type}</span>
              )}
              {skill.alternative_labels && (
                <div className="skill-alternatives">
                  <strong>Alternative labels</strong>
                  <span>{skill.alternative_labels}</span>
                </div>
              )}
              {skill.esco_concept_uri && (
                <a
                  className="skill-esco-link esco-skill-uri"
                  href={skill.esco_concept_uri}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`View ESCO skill ${skill.esco_concept_uri}`}
                >
                  {skill.esco_concept_uri} ↗
                </a>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
