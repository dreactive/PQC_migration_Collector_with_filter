const dataNode = document.getElementById("viewer-data");
const dataset = dataNode ? JSON.parse(dataNode.textContent) : { sections: [], candidates: [] };
const firstSection = (dataset.sections || []).find((section) => section.count > 0) || (dataset.sections || [])[0];
let activeSectionId = firstSection ? firstSection.id : null;
let activeCandidateKey = null;
let query = "";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function link(url, label) {
  if (!url) return "";
  return `<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(label || url)}</a>`;
}

function activeSection() {
  return (dataset.sections || []).find((section) => section.id === activeSectionId) || { candidates: [] };
}

function filteredCandidates() {
  const text = query.trim().toLowerCase();
  const candidates = activeSection().candidates || [];
  if (!text) return candidates;
  return candidates.filter((candidate) => JSON.stringify(candidate).toLowerCase().includes(text));
}

function renderSummary() {
  const counts = dataset.label_counts || {};
  document.getElementById("summary").innerHTML = `
    <span>${esc(dataset.status || "ready")}</span>
    <span>${esc(dataset.candidate_count || 0)} candidates</span>
    <span>${esc(dataset.source_path || "")}</span>
  `;
  return counts;
}

function renderSections() {
  const nav = document.getElementById("sectionNav");
  nav.innerHTML = (dataset.sections || []).map((section) => `
    <button class="section-button ${section.id === activeSectionId ? "active" : ""}" data-section="${esc(section.id)}">
      <span>${esc(section.title)}</span>
      <strong>${esc(section.count || 0)}</strong>
    </button>
  `).join("");
  nav.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeSectionId = button.dataset.section;
      activeCandidateKey = null;
      render();
    });
  });
}

function candidateTitle(candidate) {
  const repo = candidate.repository && candidate.repository.full_name ? candidate.repository.full_name : "unknown/repo";
  const path = candidate.source && candidate.source.primary_path ? candidate.source.primary_path : "unknown path";
  return `${repo} :: ${path}`;
}

function renderCandidateList() {
  const list = document.getElementById("candidateList");
  const candidates = filteredCandidates();
  if (!activeCandidateKey && candidates.length) activeCandidateKey = candidates[0].candidate_key;
  list.innerHTML = candidates.map((candidate) => `
    <button class="candidate-row ${candidate.candidate_key === activeCandidateKey ? "active" : ""}" data-key="${esc(candidate.candidate_key)}">
      <span>${esc(candidateTitle(candidate))}</span>
      <small>${esc(candidate.final_label)}</small>
    </button>
  `).join("") || `<p class="empty">No candidates</p>`;
  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeCandidateKey = button.dataset.key;
      renderDetail();
      renderCandidateList();
    });
  });
}

function activeCandidate() {
  const candidates = filteredCandidates();
  return candidates.find((candidate) => candidate.candidate_key === activeCandidateKey) || candidates[0] || null;
}

function chips(values) {
  const items = Array.isArray(values) ? values : Object.entries(values || {}).map(([key, value]) => `${key}: ${value}`);
  return `<div class="chips">${items.map((item) => `<span>${esc(item)}</span>`).join("")}</div>`;
}

function renderChecklist(items) {
  return `<div class="checklist">${(items || []).map((item) => `
    <div class="check ${item.passed ? "ok" : "missing"}">
      <b>${esc(item.passed ? "OK" : "Missing")}</b>
      <span>${esc(item.label)}</span>
      <small>${esc(item.details || "")}</small>
    </div>
  `).join("")}</div>`;
}

function evidenceValue(row, key) {
  const value = row[key];
  if (Array.isArray(value)) return value.join(", ");
  return value ?? "";
}

function renderEvidenceTable(title, rows) {
  const fields = [
    "signal", "signal_type", "near", "source_field", "file_path",
    "patch_hunk_header", "patch_line_no", "new_file_line", "old_file_line",
    "line_number", "context", "raw_path"
  ];
  if (!rows || !rows.length) {
    return `<section class="evidence-section"><h3>${esc(title)}</h3><p class="empty">No evidence</p></section>`;
  }
  return `<section class="evidence-section">
    <h3>${esc(title)}</h3>
    <div class="table-wrap"><table>
      <thead><tr>${fields.map((field) => `<th>${esc(field)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${fields.map((field) => `<td>${esc(evidenceValue(row, field))}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>
  </section>`;
}

function renderRawPaths(paths) {
  if (!paths || !paths.length) return `<p class="empty">No raw paths</p>`;
  return `<ul class="raw-paths">${paths.map((path) => `<li>${esc(path)}</li>`).join("")}</ul>`;
}

function renderDetail() {
  const detail = document.getElementById("detail");
  const candidate = activeCandidate();
  if (!candidate) {
    detail.innerHTML = `<p class="empty">No candidate selected</p>`;
    return;
  }
  activeCandidateKey = candidate.candidate_key;
  const source = candidate.source || {};
  const repo = candidate.repository || {};
  const groups = candidate.evidence_groups || {};
  detail.innerHTML = `
    <div class="detail-header">
      <div>
        <p class="eyebrow">${esc(candidate.section_title)}</p>
        <h2>${esc(candidateTitle(candidate))}</h2>
      </div>
      <span class="label">${esc(candidate.final_label)}</span>
    </div>
    <section class="facts">
      <div><b>Repository</b><span>${link(repo.html_url, repo.full_name) || esc(repo.full_name || "")}</span></div>
      <div><b>Commit</b><span>${link(source.commit_url, source.commit_sha) || esc(source.commit_sha || "")}</span></div>
      <div><b>Pull request</b><span>${link(source.pr_url, source.pr_number ? `#${source.pr_number}` : "")}</span></div>
      <div><b>Changed path</b><span>${esc(source.primary_path || "")}</span></div>
    </section>
    <section class="block"><h3>Reason Codes</h3>${chips(candidate.reason_codes || [])}</section>
    <section class="block"><h3>Signals</h3>${chips(candidate.signals || {})}</section>
    <section class="block"><h3>Migration Checklist</h3>${renderChecklist(candidate.migration_checklist || [])}</section>
    ${renderEvidenceTable("PQC Added Evidence", groups.pqc_added)}
    ${renderEvidenceTable("Legacy Removed Evidence", groups.legacy_removed)}
    ${renderEvidenceTable("Intent Evidence", groups.intent)}
    ${renderEvidenceTable("Hybrid Evidence", groups.hybrid)}
    ${renderEvidenceTable("Partial Evidence", groups.partial)}
    ${renderEvidenceTable("Full Evidence", groups.full)}
    ${renderEvidenceTable("Exact Path Evidence", groups.exact_path)}
    ${renderEvidenceTable("Other Review Evidence", groups.other)}
    <section class="block"><h3>Raw Paths</h3>${renderRawPaths(candidate.raw_paths)}</section>
  `;
}

function render() {
  renderSummary();
  renderSections();
  renderCandidateList();
  renderDetail();
}

document.getElementById("searchInput").addEventListener("input", (event) => {
  query = event.target.value;
  activeCandidateKey = null;
  renderCandidateList();
  renderDetail();
});

render();
