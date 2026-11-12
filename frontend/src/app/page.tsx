const modules = [
  {
    number: "01",
    title: "Employee Management",
    description: "Manage employee profiles, organizational information, roles and imported company data.",
    stage: "Definition",
    status: "Next to implement",
    icon: "♙",
  },
  {
    number: "02",
    title: "Skills Management",
    description: "Manage skill categories, competencies, proficiency levels, evidence and assessments.",
    stage: "Definition",
    status: "Next to implement",
    icon: "◇",
  },
  {
    number: "03",
    title: "Training Need Analysis",
    description: "Identify employee skill gaps using roles, required skills, assessments and performance evidence.",
    stage: "TNA",
    status: "Next to implement",
    icon: "⌕",
  },
  {
    number: "04",
    title: "Course Catalogue",
    description: "Manage company courses, prerequisites, delivery methods and course-to-skill mappings.",
    stage: "Planning",
    status: "Next to implement",
    icon: "▣",
  },
  {
    number: "05",
    title: "Training Planning",
    description: "Generate proposed training plans, review recommendations and manage manager approvals.",
    stage: "Planning",
    status: "Next to implement",
    icon: "▤",
  },
  {
    number: "06",
    title: "Training Execution",
    description: "Manage sessions, enrolments, attendance, completion and employee feedback.",
    stage: "Execution",
    status: "Next to implement",
    icon: "▷",
  },
  {
    number: "07",
    title: "Reporting & Insights",
    description: "Monitor training progress, skill development, completion and organizational insights.",
    stage: "Reporting",
    status: "Next to implement",
    icon: "▥",
  },
];

const stages = [
  { number: "01", name: "Definition", detail: "Employees, roles and skills" },
  { number: "02", name: "Training Need Analysis", detail: "Identify skill gaps" },
  { number: "03", name: "Training Planning", detail: "Recommend and approve courses" },
  { number: "04", name: "Training Execution", detail: "Deliver and track training" },
  { number: "05", name: "Reporting", detail: "Measure training outcomes" },
];

export default function Dashboard() {
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand">
          <div className="brand-icon">T</div>
          <div>
            <strong>TalentFlow</strong>
            <span>Training Management</span>
          </div>
        </a>

        <div className="nav-label">WORKSPACE</div>
        <a href="/" className="nav-item active">▦ <span>Overview</span></a>
        <a href="/imports" className="nav-item">▤ <span>Employee Imports</span></a>
        <div className="nav-label nav-spaced">MANAGEMENT</div>
        <div className="nav-item">♙ <span>Employees</span></div>
        <div className="nav-item">◇ <span>Skills</span></div>
        <div className="nav-item">▣ <span>Courses</span></div>
        <div className="nav-item">⌕ <span>Training Needs</span></div>
        <div className="nav-item">▤ <span>Training Plans</span></div>
        <div className="nav-item">▷ <span>Execution</span></div>
        <div className="nav-item">▥ <span>Reports</span></div>

        <div className="sidebar-bottom">
          <div className="user-avatar">TM</div>
          <div>
            <strong>Training Manager</strong>
            <span>Administrator</span>
          </div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace / Overview</div>
          <div className="topbar-right">
            <span className="system-status"><i /> Application workspace</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content dashboard-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">MAIN WORKSPACE</div>
              <h1>Training Management Dashboard</h1>
              <p>Manage your organization's employee development and training lifecycle.</p>
            </div>
            <span className="workspace-badge">Training Manager</span>
          </div>

          <section className="welcome-panel">
            <div>
              <div className="welcome-label">EMPLOYEE DEVELOPMENT PLATFORM</div>
              <h2>Welcome to TalentFlow</h2>
              <p>
                A centralized workspace for identifying skill gaps,
                planning employee development and tracking training outcomes.
              </p>
              <a href="/imports" className="button welcome-button">
                Open employee imports →
              </a>
            </div>
            <div className="welcome-art">
              <div className="art-circle">
                <span>✧</span>
              </div>
            </div>
          </section>

          <div className="section-heading dashboard-section-heading">
            <div>
              <h2>Training lifecycle</h2>
              <p>The five main stages of the system.</p>
            </div>
            <span className="count-pill">5 stages</span>
          </div>

          <section className="lifecycle-grid">
            {stages.map((stage, index) => (
              <div className="lifecycle-card" key={stage.number}>
                <div className="lifecycle-number">{stage.number}</div>
                <div className="lifecycle-title">{stage.name}</div>
                <div className="lifecycle-detail">{stage.detail}</div>
                {index !== stages.length - 1 && (
                  <span className="lifecycle-arrow">→</span>
                )}
              </div>
            ))}
          </section>

          <div className="section-heading dashboard-section-heading module-heading">
            <div>
              <h2>System modules</h2>
              <p>Access the available workspace and explore the planned modules.</p>
            </div>
          </div>

          <section className="module-grid">
            <a href="/imports" className="module-card available-module">
              <div className="module-card-top">
                <span className="module-icon">▤</span>
                <span className="module-status available-status">Available</span>
              </div>
              <div className="module-stage">DATA MANAGEMENT</div>
              <h3>Employee Imports</h3>
              <p>Import company employee data, review validation issues and manage corrections.</p>
              <div className="module-link">Open module →</div>
            </a>

            {modules.map((module) => (
              <article className="module-card" key={module.number}>
                <div className="module-card-top">
                  <span className="module-icon">{module.icon}</span>
                  <span className="module-status">{module.status}</span>
                </div>
                <div className="module-stage">{module.stage.toUpperCase()}</div>
                <h3>{module.title}</h3>
                <p>{module.description}</p>
                <div className="module-number">MODULE {module.number}</div>
              </article>
            ))}
          </section>

          <footer className="page-footer">
            TalentFlow <span>·</span> AI-Powered Employee Training Management System
          </footer>
        </div>
      </section>
    </main>
  );
}
