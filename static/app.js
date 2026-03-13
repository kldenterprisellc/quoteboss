/* QuoteBoss — app.js */

// ── Pricing data (injected from Flask) ──────────────
const PRICING = window.__PRICING__ || {};

// ── Trade metadata ───────────────────────────────────
const TRADES = [
  { id: "HVAC",        emoji: "❄️",  label: "HVAC" },
  { id: "Plumbing",    emoji: "🔧",  label: "Plumbing" },
  { id: "Electrical",  emoji: "⚡",  label: "Electrical" },
  { id: "Roofing",     emoji: "🏠",  label: "Roofing" },
  { id: "Landscaping", emoji: "🌿",  label: "Landscaping" },
  { id: "General",     emoji: "🛠️",  label: "General" },
];

const MATERIALS = {
  HVAC:        ["Refrigerant", "Filters", "Ductwork", "Thermostat", "Capacitors", "Copper Line"],
  Plumbing:    ["PVC Pipe", "Copper Pipe", "Fittings", "Sealant", "Fixtures", "Water Heater"],
  Electrical:  ["Wire", "Breakers", "Outlets", "Junction Box", "Conduit", "Panel"],
  Roofing:     ["Shingles", "Underlayment", "Flashing", "Gutters", "Ice Shield", "Nails/Fasteners"],
  Landscaping: ["Sod", "Mulch", "Plants/Shrubs", "Irrigation Parts", "Soil", "Edging"],
  General:     ["Lumber", "Drywall", "Paint", "Fasteners", "Flooring", "Adhesives"],
};

// ── State ────────────────────────────────────────────
let state = {
  step: 1,
  trade: null,
  jobType: null,
  quoteId: null,
  lineItems: [],
  totalMin: 0,
  totalMax: 0,
  customPricingOpen: false,
};

// ── localStorage helpers ─────────────────────────────
const STORAGE_KEY = "quoteboss_contractor";

function saveContractorInfo() {
  const info = {
    name: $("contractor-name")?.value || "",
    business: $("contractor-business")?.value || "",
    phone: $("contractor-phone")?.value || "",
    email: $("contractor-email")?.value || "",
  };
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(info)); } catch(e) {}
}

function loadContractorInfo() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const info = JSON.parse(raw);
    if (info.name)     { const el = $("contractor-name");     if (el) el.value = info.name; }
    if (info.business) { const el = $("contractor-business"); if (el) el.value = info.business; }
    if (info.phone)    { const el = $("contractor-phone");    if (el) el.value = info.phone; }
    if (info.email)    { const el = $("contractor-email");    if (el) el.value = info.email; }
  } catch(e) {}
}

// ── DOM refs ─────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Init ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  buildTradeGrid();
  setupStepIndicators();
  loadSharedQuote();
  loadContractorInfo();
  showStep(1);
});

// ── Shared quote load ────────────────────────────────
function loadSharedQuote() {
  if (!window.__SHARED_QUOTE__) return;
  try {
    const q = JSON.parse(window.__SHARED_QUOTE__);
    state.quoteId = q.quote_id;
    state.lineItems = q.line_items;
    state.totalMin = q.total_min;
    state.totalMax = q.total_max;
    renderResult();
    showStep(4);
  } catch(e) { console.error("Failed to load shared quote", e); }
}

// ── Build Trade Grid ─────────────────────────────────
function buildTradeGrid() {
  const grid = $("trade-grid");
  grid.innerHTML = "";
  TRADES.forEach(t => {
    const div = document.createElement("div");
    div.className = "trade-card";
    div.dataset.trade = t.id;
    div.innerHTML = `<span class="trade-emoji">${t.emoji}</span><span class="trade-name">${t.label}</span>`;
    div.addEventListener("click", () => selectTrade(t.id));
    grid.appendChild(div);
  });
}

// ── Trade Selection ──────────────────────────────────
function selectTrade(tradeId) {
  state.trade = tradeId;
  state.jobType = null;
  document.querySelectorAll(".trade-card").forEach(c => c.classList.remove("selected"));
  document.querySelector(`[data-trade="${tradeId}"]`).classList.add("selected");
  buildJobGrid(tradeId);
  buildMaterialsGrid(tradeId);
}

// ── Job Type Grid ────────────────────────────────────
function buildJobGrid(tradeId) {
  const jobs = Object.keys(PRICING[tradeId] || {});
  const grid = $("job-grid");
  grid.innerHTML = "";
  jobs.forEach(job => {
    const btn = document.createElement("button");
    btn.className = "job-btn";
    btn.textContent = job;
    btn.addEventListener("click", () => selectJob(job, btn));
    grid.appendChild(btn);
  });
  $("job-section").classList.remove("hidden");
}

function selectJob(job, btn) {
  state.jobType = job;
  document.querySelectorAll(".job-btn").forEach(b => b.classList.remove("selected"));
  btn.classList.add("selected");
  // Update custom pricing hint with national average for this job
  updateCustomPricingHint();
}

function updateCustomPricingHint() {
  const note = $("custom-pricing-note");
  if (!note || !state.trade || !state.jobType) return;
  const p = (PRICING[state.trade] || {})[state.jobType];
  if (!p) return;
  const unit = p.unit === "job" ? "flat job" : p.unit;
  note.textContent = `National avg for ${state.jobType}: $${p.min.toLocaleString()}–$${p.max.toLocaleString()} (${unit})`;
}

function toggleCustomPricing() {
  state.customPricingOpen = !state.customPricingOpen;
  const panel = $("custom-pricing-panel");
  const chevron = $("custom-pricing-chevron");
  if (state.customPricingOpen) {
    panel.classList.remove("hidden");
    chevron.textContent = "▲";
    updateCustomPricingHint();
  } else {
    panel.classList.add("hidden");
    chevron.textContent = "▼";
    $("custom-price-min").value = "";
    $("custom-price-max").value = "";
  }
}

// ── Materials Grid ───────────────────────────────────
function buildMaterialsGrid(tradeId) {
  const mats = MATERIALS[tradeId] || [];
  const grid = $("materials-grid");
  grid.innerHTML = "";
  mats.forEach(mat => {
    const label = document.createElement("label");
    label.className = "check-item";
    label.innerHTML = `<input type="checkbox" value="${mat}"> ${mat}`;
    grid.appendChild(label);
  });
}

function getCheckedMaterials() {
  return Array.from(document.querySelectorAll("#materials-grid input:checked")).map(i => i.value);
}

// ── Step Navigation ──────────────────────────────────
function setupStepIndicators() {
  document.querySelectorAll(".step-indicator").forEach(el => {
    el.addEventListener("click", () => {
      const s = parseInt(el.dataset.step);
      if (s < state.step) showStep(s);
    });
  });
}

function showStep(n) {
  state.step = n;
  document.querySelectorAll(".step-section").forEach(s => s.classList.add("hidden"));
  const target = $(`step-${n}`);
  if (target) {
    target.classList.remove("hidden");
  }
  updateProgress(n);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateProgress(n) {
  document.querySelectorAll(".step-indicator").forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.remove("active", "done");
    if (s === n) el.classList.add("active");
    else if (s < n) el.classList.add("done");
  });
  document.querySelectorAll(".step-line").forEach(el => {
    const s = parseInt(el.dataset.after);
    el.style.background = s < n ? "var(--navy)" : "var(--border)";
  });
}

// ── Step 1 → 2 ───────────────────────────────────────
function goToStep2() {
  if (!state.trade) { showToast("⚠️ Please select a trade first"); return; }
  if (!state.jobType) { showToast("⚠️ Please select a job type"); return; }
  showStep(2);
}

// ── Step 2 → 3 ───────────────────────────────────────
function goToStep3() {
  showStep(3);
}

// ── Step 3 → generate ────────────────────────────────
async function generateQuote() {
  // Collect contractor info
  const contractorName = $("contractor-name").value.trim();
  const contractorBusiness = $("contractor-business").value.trim();
  if (!contractorName || !contractorBusiness) {
    showToast("⚠️ Please enter your name and business name");
    return;
  }

  // Save contractor info for next time
  saveContractorInfo();

  // Custom pricing
  const customMin = $("custom-price-min")?.value;
  const customMax = $("custom-price-max")?.value;
  const hasCustom = state.customPricingOpen && customMin && customMax &&
                    parseFloat(customMin) > 0 && parseFloat(customMax) >= parseFloat(customMin);

  const payload = {
    trade: state.trade,
    job_type: state.jobType,
    property_size: parseFloat($("property-size").value) || 1500,
    location: $("location").value.trim(),
    labor_hours: parseFloat($("labor-hours").value) || 4,
    materials: getCheckedMaterials(),
    contractor_name: contractorName,
    contractor_business: contractorBusiness,
    contractor_phone: $("contractor-phone").value.trim(),
    contractor_email: $("contractor-email").value.trim(),
    client_name: $("client-name").value.trim(),
    client_address: $("client-address").value.trim(),
    job_description: $("job-description").value.trim(),
    terms: "",
    ...(hasCustom && {
      custom_price_min: parseFloat(customMin),
      custom_price_max: parseFloat(customMax),
    }),
  };

  const btn = $("generate-btn");
  const spinner = $("generate-spinner");
  btn.disabled = true;
  spinner.classList.add("active");
  $("error-banner").classList.remove("show");

  try {
    const res = await fetch("/api/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "Generation failed");

    state.quoteId = data.quote_id;
    state.lineItems = data.line_items;
    state.totalMin = data.total_min;
    state.totalMax = data.total_max;

    renderResult();
    showStep(4);
  } catch (err) {
    $("error-banner").textContent = "❌ " + err.message;
    $("error-banner").classList.add("show");
  } finally {
    btn.disabled = false;
    spinner.classList.remove("active");
  }
}

// ── Render Result ────────────────────────────────────
function renderResult() {
  $("result-quote-id").textContent = "Quote #" + state.quoteId;

  // Range
  $("result-min").textContent = "$" + state.totalMin.toLocaleString();
  $("result-max").textContent = "$" + state.totalMax.toLocaleString();

  // Line items
  const container = $("result-line-items");
  container.innerHTML = "";
  state.lineItems.forEach(item => {
    const div = document.createElement("div");
    div.className = "line-item";
    div.innerHTML = `
      <div class="li-left">
        <div class="li-name">${item.description}</div>
        <div class="li-detail">${item.detail}</div>
      </div>
      <div class="li-price">$${item.min.toLocaleString()} – $${item.max.toLocaleString()}</div>
    `;
    container.appendChild(div);
  });

  // Share URL
  const shareUrl = `${location.origin}/q/${state.quoteId}`;
  $("share-url").value = shareUrl;
}

// ── PDF Download ──────────────────────────────────────
function downloadPDF() {
  if (!state.quoteId) return;
  window.location.href = `/api/pdf/${state.quoteId}`;
}

// ── Copy Share Link ───────────────────────────────────
function copyShareLink() {
  const url = $("share-url").value;
  navigator.clipboard.writeText(url).then(() => {
    showToast("✅ Link copied to clipboard!");
  }).catch(() => {
    $("share-url").select();
    document.execCommand("copy");
    showToast("✅ Link copied!");
  });
}

// ── New Quote ─────────────────────────────────────────
function newQuote() {
  state = { step: 1, trade: null, jobType: null, quoteId: null, lineItems: [], totalMin: 0, totalMax: 0, customPricingOpen: false };
  document.querySelectorAll(".trade-card").forEach(c => c.classList.remove("selected"));
  document.querySelectorAll(".job-btn").forEach(b => b.classList.remove("selected"));
  document.querySelectorAll("input[type=checkbox]").forEach(c => c.checked = false);
  $("job-section").classList.add("hidden");
  // Clear job-specific fields but preserve contractor info
  ["client-name","client-address","location","job-description"].forEach(id => {
    const el = $(id); if (el) el.value = "";
  });
  $("property-size").value = "1500";
  $("labor-hours").value = "4";
  // Reset custom pricing
  const panel = $("custom-pricing-panel");
  if (panel) panel.classList.add("hidden");
  const chevron = $("custom-pricing-chevron");
  if (chevron) chevron.textContent = "▼";
  const cpMin = $("custom-price-min"); if (cpMin) cpMin.value = "";
  const cpMax = $("custom-price-max"); if (cpMax) cpMax.value = "";
  showStep(1);
}

// ── Toast ─────────────────────────────────────────────
function showToast(msg, duration = 2800) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), duration);
}
