/* app.js — GitHub EMU Migration Desktop App (pywebview bridge) */

"use strict";

// ── State ────────────────────────────────────────────────────────────
const state = {
  report: null,
  ssoPlan: null,
  emuPlan: null,
  markdown: null,
  geiScript: null,
};

// ── DOM helpers ──────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const show = (el) => { el.style.display = ""; };
const hide = (el) => { el.style.display = "none"; };

function esc(str) {
  if (str == null) return "";
  const el = document.createElement("span");
  el.textContent = String(str);
  return el.innerHTML;
}

// ── Wait for pywebview API bridge ────────────────────────────────────
// pywebview exposes window.pywebview.api once the native bridge is ready.
function apiReady() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) {
      resolve(window.pywebview.api);
    } else {
      window.addEventListener("pywebviewready", () => resolve(window.pywebview.api));
    }
  });
}

let api; // populated on load

// ── Tabs ─────────────────────────────────────────────────────────────
$$(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab-btn").forEach((b) => b.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
  });
});

// ── Config builder ───────────────────────────────────────────────────
function gatherConfig() {
  return {
    github: {
      enterprise: $("#gh-enterprise").value.trim(),
      organization: $("#gh-org").value.trim(),
      token: $("#gh-token").value.trim(),
    },
    entra_id: {
      tenant_id: $("#entra-tenant").value.trim(),
      client_id: $("#entra-client").value.trim(),
      client_secret: $("#entra-secret").value.trim(),
      app_display_name: $("#entra-app").value.trim(),
    },
    adfs: {
      entity_id: $("#adfs-entity").value.trim(),
      sso_url: $("#adfs-sso").value.trim(),
    },
    emu: {
      short_code: $("#emu-short").value.trim(),
      owners_group: $("#emu-owners").value.trim(),
      members_group: $("#emu-members").value.trim(),
    },
    migration: { dry_run: true },
  };
}

// ── Render: Metrics ──────────────────────────────────────────────────
function renderMetrics(report) {
  const samlLinked = report.members.filter((m) => m.saml_identity).length;
  const items = [
    { label: "Total Members", value: report.total_members },
    { label: "Repositories", value: report.total_repos },
    { label: "SAML Linked", value: `${samlLinked}/${report.total_members}` },
    { label: "Outside Collabs", value: report.outside_collaborators },
  ];
  $("#metrics-row").innerHTML = items
    .map((m) => `<div class="metric-card"><div class="label">${m.label}</div><div class="value">${m.value}</div></div>`)
    .join("");
}

// ── Render: Members ──────────────────────────────────────────────────
function renderMembers(members) {
  $("#members-table tbody").innerHTML = members
    .map((m) => `<tr>
      <td>${esc(m.login)}</td>
      <td>${esc(m.role)}</td>
      <td>${esc(m.email || "—")}</td>
      <td>${m.saml_identity ? "✓ " + esc(m.saml_identity) : '<span style="color:var(--gh-red)">✗ not linked</span>'}</td>
    </tr>`)
    .join("");
}

// ── Render: Repos ────────────────────────────────────────────────────
function renderRepos(repos) {
  $("#repos-table tbody").innerHTML = repos
    .map((r) => {
      const vis = r.private ? "Private" : "Public";
      const size = r.size_kb >= 1024 ? `${(r.size_kb / 1024).toFixed(1)} MB` : `${r.size_kb} KB`;
      return `<tr>
        <td>${esc(r.name)}${r.archived ? ' <span class="sev-badge sev-info">archived</span>' : ""}</td>
        <td>${vis}</td>
        <td>${size}</td>
        <td>${r.has_actions ? "✓" : "—"}</td>
      </tr>`;
    })
    .join("");
}

// ── Render: Risks ────────────────────────────────────────────────────
function renderRisks(risks) {
  $("#risks-container").innerHTML = risks
    .map((r) => `<div class="risk-card">
      <div class="risk-header">
        <span class="sev-badge sev-${(r.severity || "info").toLowerCase()}">${esc(r.severity)}</span>
        <span class="risk-title">${esc(r.title)}</span>
        <span style="margin-left:auto;color:var(--gh-muted)">${r.check_icon}</span>
      </div>
      <div class="risk-desc">${esc(r.description)}</div>
      <div class="mitigation-box">↳ ${esc(r.mitigation)}</div>
    </div>`)
    .join("");
}

// ── Render: Steps ────────────────────────────────────────────────────
function renderSteps(steps, container) {
  container.innerHTML = steps
    .map((s) => `<div class="step-card">
      <div>
        <span class="step-badge ${s.manual ? "step-manual" : "step-auto"}">${s.manual ? "MANUAL" : "AUTO"}</span>
        <span style="color:var(--gh-muted);font-size:0.75rem">Phase ${esc(s.phase)} · Step ${s.order}</span>
      </div>
      <div class="step-title">${esc(s.title)}</div>
      <div class="step-desc">${esc(s.description)}</div>
    </div>`)
    .join("");
}

// ── Render: Migration results ────────────────────────────────────────
function renderExecResults(data) {
  const container = $("#exec-results");
  if (!data.ok) {
    container.innerHTML = `<div class="alert alert-danger">Migration failed: ${esc(data.error)}</div>`;
    return;
  }
  let html = `<div class="alert alert-${data.failed ? "warning" : "success"}">
    Completed: ${data.succeeded} succeeded, ${data.failed} failed out of ${data.total} repos
  </div>`;
  html += `<div class="table-wrap"><table class="data-table">
    <thead><tr><th>Repo</th><th>Status</th><th>Migration ID</th><th>Error</th></tr></thead><tbody>`;
  for (const r of data.results) {
    const cls = r.status === "succeeded" ? "color:var(--gh-green)" : r.status === "failed" ? "color:var(--gh-red)" : "";
    html += `<tr><td>${esc(r.repo)}</td><td style="${cls}">${esc(r.status)}</td><td>${esc(r.migration_id || "—")}</td><td>${esc(r.error || "—")}</td></tr>`;
  }
  html += `</tbody></table></div>`;
  container.innerHTML = html;
}

// ── Refresh all panels ───────────────────────────────────────────────
function refreshUI() {
  // Assessment
  if (state.report) {
    hide($("#assess-empty")); show($("#assess-content"));
    renderMetrics(state.report);
    renderMembers(state.report.members);
    renderRepos(state.report.repos);
    renderRisks(state.report.risks);
  } else {
    show($("#assess-empty")); hide($("#assess-content"));
  }
  // Plans
  if (state.ssoPlan) {
    hide($("#plans-empty")); show($("#plans-content"));
    renderSteps(state.ssoPlan.steps, $("#sso-steps"));
    renderSteps(state.emuPlan.steps, $("#emu-steps"));
  } else {
    show($("#plans-empty")); hide($("#plans-content"));
  }
  // Report
  if (state.markdown) {
    hide($("#report-empty")); show($("#report-content"));
    $("#report-md").textContent = state.markdown;
  } else {
    show($("#report-empty")); hide($("#report-content"));
  }
  // GEI Script
  if (state.geiScript) {
    hide($("#gei-empty")); show($("#gei-content"));
    $("#gei-script").textContent = state.geiScript;
  } else {
    show($("#gei-empty")); hide($("#gei-content"));
  }
  // Auto-fill execute tab from assessment
  if (state.report) {
    if (!$("#exec-source-org").value) {
      $("#exec-source-org").value = state.report.organization;
      $("#exec-target-org").value = state.report.organization + "-emu";
      $("#exec-repos").value = state.report.repos.map((r) => r.name).join(", ");
    }
  }
}

// ── Demo button ──────────────────────────────────────────────────────
$("#btn-demo").addEventListener("click", async () => {
  const btn = $("#btn-demo");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Loading…';
  try {
    const data = await api.demo();
    state.report = data.report;
    state.ssoPlan = data.sso_plan;
    state.emuPlan = data.emu_plan;
    state.markdown = data.markdown;
    state.geiScript = data.gei_script;
    refreshUI();
  } catch (err) {
    alert("Demo failed: " + (err.message || err));
  } finally {
    btn.disabled = false;
    btn.textContent = "Load Demo Data";
  }
});

// ── Live assess button ───────────────────────────────────────────────
$("#gh-token").addEventListener("input", () => {
  $("#btn-assess").disabled = !$("#gh-token").value.trim();
});

$("#btn-assess").addEventListener("click", async () => {
  const btn = $("#btn-assess");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Assessing…';
  try {
    const cfg = gatherConfig();
    const assessRes = await api.assess(cfg);
    if (!assessRes.ok) throw new Error(assessRes.error);
    state.report = assessRes.report;

    const plansRes = await api.plans(cfg);
    state.ssoPlan = plansRes.sso_plan;
    state.emuPlan = plansRes.emu_plan;

    const reportRes = await api.report(cfg);
    if (reportRes.ok) state.markdown = reportRes.markdown;

    // GEI script
    const repos = state.report.repos.map((r) => r.name);
    const gei = await api.gei_script(repos, cfg.github.organization, cfg.github.organization + "-emu");
    state.geiScript = gei.script;

    refreshUI();
  } catch (err) {
    alert("Assessment failed: " + (err.message || err));
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Live Assessment";
  }
});

// ── Copy / Download ──────────────────────────────────────────────────
function flashBtn(btn, msg) {
  const orig = btn.textContent;
  btn.textContent = msg;
  setTimeout(() => (btn.textContent = orig), 1500);
}

$("#btn-copy-md").addEventListener("click", () => {
  if (state.markdown) {
    navigator.clipboard.writeText(state.markdown);
    flashBtn($("#btn-copy-md"), "Copied ✓");
  }
});

$("#btn-download-md").addEventListener("click", () => {
  if (state.markdown) {
    const blob = new Blob([state.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "migration-report.md";
    a.click();
    URL.revokeObjectURL(url);
  }
});

$("#btn-copy-gei").addEventListener("click", () => {
  if (state.geiScript) {
    navigator.clipboard.writeText(state.geiScript);
    flashBtn($("#btn-copy-gei"), "Copied ✓");
  }
});

// ── Execute Migration tab ────────────────────────────────────────────
async function checkGei() {
  try {
    const res = await api.check_gei();
    const box = $("#gei-status-box");
    if (res.installed) {
      box.innerHTML = '<div class="gei-status gei-ok">✓ gh CLI and gh-gei extension detected</div>';
      $("#btn-dry-run").disabled = false;
    } else {
      box.innerHTML = '<div class="gei-status gei-miss">✗ gh CLI or gh-gei extension not found — install with: <code>gh extension install github/gh-gei</code></div>';
      $("#btn-dry-run").disabled = true;
    }
  } catch {
    $("#gei-status-box").innerHTML = '<div class="gei-status gei-miss">✗ Could not detect gh CLI</div>';
  }
}

function parseRepos() {
  return $("#exec-repos").value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

$("#btn-dry-run").addEventListener("click", async () => {
  const btn = $("#btn-dry-run");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Running dry-run…';
  try {
    const res = await api.run_gei_migration(
      $("#exec-source-org").value.trim(),
      $("#exec-target-org").value.trim(),
      parseRepos(),
      $("#exec-source-pat").value.trim(),
      $("#exec-target-pat").value.trim(),
      true,
    );
    renderExecResults(res);
    if (res.ok) $("#btn-migrate").disabled = false;
  } catch (err) {
    $("#exec-results").innerHTML = `<div class="alert alert-danger">${esc(err.message || err)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Dry Run";
  }
});

$("#btn-migrate").addEventListener("click", async () => {
  if (!confirm("This will migrate repositories for real. Continue?")) return;
  const btn = $("#btn-migrate");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Migrating…';
  try {
    const res = await api.run_gei_migration(
      $("#exec-source-org").value.trim(),
      $("#exec-target-org").value.trim(),
      parseRepos(),
      $("#exec-source-pat").value.trim(),
      $("#exec-target-pat").value.trim(),
      false,
    );
    renderExecResults(res);
  } catch (err) {
    $("#exec-results").innerHTML = `<div class="alert alert-danger">${esc(err.message || err)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Migrate (Live)";
  }
});

// ── Keyboard shortcut ────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    const btn = $("#btn-assess");
    if (!btn.disabled) btn.click();
  }
});

// ── Init ─────────────────────────────────────────────────────────────
(async () => {
  api = await apiReady();
  checkGei();
})();
