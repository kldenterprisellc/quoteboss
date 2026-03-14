/* QuoteBoss — app.js */

// Pricing data (injected from Flask)
const PRICING = window.__PRICING__ || {};

// Labor hour defaults (loaded from API)
const LABOR_DEFAULTS = {};

// Trade metadata
const TRADES = [
  { id: "HVAC",             emoji: "❄️",  label: "HVAC" },
  { id: "Plumbing",         emoji: "🔧",  label: "Plumbing" },
  { id: "Electrical",       emoji: "⚡",  label: "Electrical" },
  { id: "Roofing",          emoji: "🏠",  label: "Roofing" },
  { id: "Painting",         emoji: "🎨",  label: "Painting" },
  { id: "Pressure Washing", emoji: "💦",  label: "Pressure Washing" },
  { id: "General",          emoji: "🛠️",  label: "General Contractor" },
  { id: "Landscaping",      emoji: "🌿",  label: "Landscaping" },
];

// Custom job type labels for each trade (user-friendly, maps to PRICING keys in getTradeParams)
const TRADE_JOB_TYPES = {
  'Roofing': [
    { label: 'Full Replacement', value: 'replacement' },
    { label: 'Repair', value: 'repair' },
    { label: 'Gutters', value: 'gutters' },
  ],
  'HVAC': [
    { label: 'Install New System', value: 'install' },
    { label: 'Replace Existing', value: 'replace' },
    { label: 'Repair', value: 'repair' },
    { label: 'Tune-Up', value: 'tuneup' },
  ],
  'Plumbing': [
    { label: 'Water Heater', value: 'water_heater' },
    { label: 'Drain Cleaning', value: 'drain_cleaning' },
    { label: 'Pipe Repair', value: 'pipe_repair' },
    { label: 'Bathroom Remodel', value: 'bathroom_remodel' },
    { label: 'Full Repipe', value: 'full_repipe' },
    { label: 'Fixture Install', value: 'fixture_install' },
  ],
  'Electrical': [
    { label: 'Panel Upgrade', value: 'panel_upgrade' },
    { label: 'Whole Home Rewire', value: 'whole_home_rewire' },
    { label: 'EV Charger Install', value: 'ev_charger' },
    { label: 'Circuit Add', value: 'circuit_add' },
    { label: 'Fixture Install', value: 'fixture_install_elec' },
    { label: 'Service Upgrade', value: 'service_upgrade' },
  ],
  'Painting': [
    { label: 'Interior Painting', value: 'interior' },
    { label: 'Exterior Painting', value: 'exterior' },
    { label: 'Interior and Exterior', value: 'both' },
  ],
  'Pressure Washing': [
    { label: 'House Exterior', value: 'house_exterior' },
    { label: 'Driveway', value: 'driveway' },
    { label: 'Deck or Patio', value: 'deck_patio' },
    { label: 'Roof Soft Wash', value: 'roof_soft_wash' },
    { label: 'Fence', value: 'fence' },
    { label: 'Commercial Building', value: 'commercial' },
  ],
};

const MATERIALS = {
  HVAC:               ["Refrigerant", "Filters", "Ductwork", "Thermostat", "Capacitors", "Copper Line"],
  Plumbing:           ["PVC Pipe", "Copper Pipe", "Fittings", "Sealant", "Fixtures", "Water Heater"],
  Electrical:         ["Wire", "Breakers", "Outlets", "Junction Box", "Conduit", "Panel"],
  Roofing:            ["Shingles", "Underlayment", "Flashing", "Gutters", "Ice Shield", "Nails/Fasteners"],
  Painting:           ["Primer", "Interior Paint", "Exterior Paint", "Brushes/Rollers", "Tape/Drop Cloth", "Caulk"],
  Landscaping:        ["Sod", "Mulch", "Plants/Shrubs", "Irrigation Parts", "Soil", "Edging"],
  General:            ["Lumber", "Drywall", "Paint", "Fasteners", "Flooring", "Adhesives"],
  "Pressure Washing": ["Detergent", "Degreaser", "Soft Wash Solution", "Surface Cleaner", "Extension Wand"],
};

// Price confirmation state
let currentQuoteData = null;
let currentQuoteLink = null;

// Custom Line Items
let lineItems = [];

function addLineItem() {
  const id = Date.now();
  lineItems.push({id, description: '', amount: 0, markup: 0});
  renderLineItems();
}

function removeLineItem(id) {
  lineItems = lineItems.filter(li => li.id !== id);
  renderLineItems();
}

function renderLineItems() {
  const container = document.getElementById('line-items-list');
  if (!container) return;
  container.innerHTML = lineItems.map(li => `
    <div style="display:grid;grid-template-columns:1fr auto auto auto;gap:0.5rem;align-items:center;padding:0.5rem 0;border-bottom:1px solid #f0f0f0;">
      <input type="text" placeholder="Description (e.g. Labor, Materials, Permit)"
        value="${li.description}"
        onchange="updateLineItem(${li.id},'description',this.value)"
        style="padding:0.5rem;border:1px solid #e0e0e0;border-radius:6px;font-size:0.85rem;">
      <input type="number" placeholder="Amount $" value="${li.amount || ''}"
        onchange="updateLineItem(${li.id},'amount',parseFloat(this.value)||0)"
        style="width:100px;padding:0.5rem;border:1px solid #e0e0e0;border-radius:6px;font-size:0.85rem;">
      <input type="number" placeholder="Markup %" value="${li.markup || ''}"
        onchange="updateLineItem(${li.id},'markup',parseFloat(this.value)||0)"
        title="Optional markup percentage on this item"
        style="width:80px;padding:0.5rem;border:1px solid #e0e0e0;border-radius:6px;font-size:0.85rem;">
      <button onclick="removeLineItem(${li.id})" style="background:none;border:none;color:#e53935;font-size:1.1rem;cursor:pointer;padding:0.25rem;">x</button>
    </div>
  `).join('') + (lineItems.length ? '<div style="font-size:0.75rem;color:#aaa;padding:0.4rem 0;">Amount + Markup % = line item total on quote</div>' : '');
}

function updateLineItem(id, field, value) {
  const li = lineItems.find(l => l.id === id);
  if (li) li[field] = value;
}

function getLineItemsTotal() {
  return lineItems.reduce((sum, li) => {
    const base = li.amount || 0;
    const markup = li.markup ? base * (li.markup / 100) : 0;
    return sum + base + markup;
  }, 0);
}

// State
let state = {
  step: 1,
  trade: null,
  jobType: null,
  jobTypes: [],
  quoteId: null,
  lineItems: [],
  totalMin: 0,
  totalMax: 0,
  customPricingOpen: false,
  paymentTerms: 'full',
};

// localStorage helpers
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

// DOM refs
const $ = id => document.getElementById(id);

// Init
document.addEventListener("DOMContentLoaded", () => {
  buildTradeGrid();
  setupStepIndicators();
  loadSharedQuote();
  loadContractorInfo();
  showStep(1);

  // Load labor defaults from API
  fetch('/api/labor-defaults').then(r => r.json()).then(d => Object.assign(LABOR_DEFAULTS, d));

  // Also load saved contractor info from qb_contractor key
  const saved = JSON.parse(localStorage.getItem('qb_contractor') || 'null');
  if (saved) {
    ['contractor-name','contractor-business','contractor-phone','contractor-email'].forEach(id => {
      const el = document.getElementById(id);
      if (el && saved[id]) el.value = saved[id];
    });
  }

  // Single-trade mode: auto-select trade and skip straight to scope of work
  if (window.singleTradeMode && window.primaryTrade) {
    setTimeout(() => {
      selectTrade(window.primaryTrade);
      // Hide trade grid, update step 1 title to "What type of job is this?"
      const tradeGrid = document.getElementById('trade-grid');
      if (tradeGrid) tradeGrid.style.display = 'none';
      const tradeCard = document.querySelector('.card:has(#trade-grid)');
      if (tradeCard) tradeCard.style.display = 'none';
      const jobTitle = document.querySelector('#job-section .card-title');
      if (jobTitle) jobTitle.textContent = 'What type of job is this?';
      const jobSubtitle = document.querySelector('#job-section .card-subtitle');
      if (jobSubtitle) jobSubtitle.textContent = 'Select all that apply to this quote';
    }, 50);
  } else if (window.primaryTrade && window.primaryTrade.length > 0) {
    // Multi-trade: pre-select but still show trade grid
    setTimeout(() => {
      const tradeCard = document.querySelector(`[data-trade="${window.primaryTrade}"]`);
      if (tradeCard) {
        selectTrade(window.primaryTrade);
      }
      // Rename trade step title for multi-trade contractors
      const tradeTitle = document.querySelector('#step-1 .card-title');
      if (tradeTitle) tradeTitle.textContent = 'What type of job is this?';
    }, 50);
  }
});

// Shared quote load
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

// Build Trade Grid
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

// Trade Selection
function selectTrade(tradeId) {
  state.trade = tradeId;
  state.jobType = null;
  state.jobTypes = [];
  document.querySelectorAll(".trade-card").forEach(c => c.classList.remove("selected"));
  const card = document.querySelector(`[data-trade="${tradeId}"]`);
  if (card) card.classList.add("selected");
  buildJobGrid(tradeId);
  buildMaterialsGrid(tradeId);
  updateTradeInputs(tradeId);
}

// Show/hide trade-specific input groups in Step 2
function updateTradeInputs(tradeId) {
  document.querySelectorAll('.trade-input-group').forEach(el => el.classList.add('hidden'));
  const inputEl = document.getElementById('trade-inputs-' + tradeId);
  if (inputEl) {
    inputEl.classList.remove('hidden');
  } else {
    // Fall back to General inputs
    const genEl = document.getElementById('trade-inputs-General');
    if (genEl) genEl.classList.remove('hidden');
  }
}

// Job Type Grid
function buildJobGrid(tradeId) {
  const jobs = TRADE_JOB_TYPES[tradeId];
  const grid = $("job-grid");
  grid.innerHTML = "";

  if (jobs) {
    // Use trade-specific user-friendly labels
    jobs.forEach(jt => {
      const btn = document.createElement("button");
      btn.className = "job-btn";
      btn.textContent = jt.label;
      btn.dataset.value = jt.value;
      btn.addEventListener("click", () => selectJob(jt.value, btn));
      grid.appendChild(btn);
    });
  } else {
    // Fall back to PRICING keys for General, Landscaping
    const pricingJobs = Object.keys(PRICING[tradeId] || {});
    pricingJobs.forEach(job => {
      const btn = document.createElement("button");
      btn.className = "job-btn";
      btn.textContent = job;
      btn.addEventListener("click", () => selectJob(job, btn));
      grid.appendChild(btn);
    });
  }

  $("job-section").classList.remove("hidden");
}

function selectJob(job, btn) {
  // Toggle multi-select
  if (btn.classList.contains("selected")) {
    btn.classList.remove("selected");
    state.jobTypes = state.jobTypes.filter(j => j !== job);
  } else {
    btn.classList.add("selected");
    state.jobTypes.push(job);
  }
  // Keep jobType as last selected for backward compat
  state.jobType = state.jobTypes[state.jobTypes.length - 1] || null;

  // Update conditional inputs based on primary job type
  if (state.jobType) updateConditionalInputs(state.trade, state.jobType);

  // Update custom pricing hint
  updateCustomPricingHint();
}

// Show/hide conditional inputs based on job type
function showTradeSubInputs(tradePrefix, activeId) {
  document.querySelectorAll(`.${tradePrefix}-sub`).forEach(el => el.classList.remove('active'));
  const prompt = document.getElementById(`${tradePrefix}-prompt`);
  if (activeId) {
    const el = document.getElementById(activeId);
    if (el) { el.classList.add('active'); if (prompt) prompt.style.display = 'none'; }
    else { if (prompt) prompt.style.display = ''; }
  } else {
    if (prompt) prompt.style.display = '';
  }
}

function updateConditionalInputs(trade, jobType) {
  if (trade === 'HVAC') {
    const acJobs = ['install', 'replace'];
    if (acJobs.includes(jobType)) {
      showTradeSubInputs('hvac', 'hvac-inputs-ac');
    } else if (jobType === 'tuneup' || jobType === 'repair') {
      showTradeSubInputs('hvac', 'hvac-inputs-repair');
    } else {
      // Could be furnace or mini_split based on system type -- show AC as default
      showTradeSubInputs('hvac', 'hvac-inputs-ac');
    }
    // Also react to system type changes
    const sysType = document.getElementById('hvac-system-type');
    if (sysType) {
      sysType.onchange = () => {
        const st = sysType.value;
        if (st === 'mini_split') showTradeSubInputs('hvac', 'hvac-inputs-minisplit');
        else if (st === 'furnace') showTradeSubInputs('hvac', 'hvac-inputs-furnace');
        else showTradeSubInputs('hvac', 'hvac-inputs-ac');
      };
    }
  }

  if (trade === 'Electrical') {
    if (jobType === 'panel_upgrade' || jobType === 'service_upgrade') {
      showTradeSubInputs('elec', 'elec-inputs-panel');
    } else if (jobType === 'ev_charger') {
      showTradeSubInputs('elec', 'elec-inputs-ev');
    } else if (jobType === 'whole_home_rewire') {
      showTradeSubInputs('elec', 'elec-inputs-rewire');
    } else if (jobType === 'circuit_add') {
      showTradeSubInputs('elec', 'elec-inputs-circuit');
    } else if (jobType === 'fixture_install_elec') {
      showTradeSubInputs('elec', 'elec-inputs-lighting');
    } else {
      showTradeSubInputs('elec', 'elec-inputs-panel');
    }
  }

  if (trade === 'Roofing') {
    if (jobType === 'replacement') showTradeSubInputs('roof', 'roof-inputs-replacement');
    else if (jobType === 'metal') showTradeSubInputs('roof', 'roof-inputs-metal');
    else if (jobType === 'repair') showTradeSubInputs('roof', 'roof-inputs-repair');
    else if (jobType === 'gutters') showTradeSubInputs('roof', 'roof-inputs-gutters');
    else showTradeSubInputs('roof', 'roof-inputs-replacement');
  }

  if (trade === 'Plumbing') {
    if (jobType === 'water_heater') showTradeSubInputs('plumb', 'plumb-inputs-water-heater');
    else if (jobType === 'tankless') showTradeSubInputs('plumb', 'plumb-inputs-tankless');
    else if (jobType === 'bathroom_remodel') showTradeSubInputs('plumb', 'plumb-inputs-bath');
    else if (jobType === 'full_repipe') showTradeSubInputs('plumb', 'plumb-inputs-repipe');
    else showTradeSubInputs('plumb', 'plumb-inputs-general');
  }

  if (trade === 'Pressure Washing') {
    const sqftWrap = document.getElementById('pw-sqft-wrap');
    const flatNote = document.getElementById('pw-flat-note');
    const flatJobs = ['driveway', 'roof_soft_wash', 'fence'];
    if (sqftWrap) sqftWrap.style.display = flatJobs.includes(jobType) ? 'none' : '';
    if (flatNote) flatNote.style.display = flatJobs.includes(jobType) ? '' : 'none';
  }
}

function updateCustomPricingHint() {
  const note = $("custom-pricing-note");
  if (!note || !state.trade || !state.jobType) return;
  // For trades with custom job type mapping, look up by PRICING key
  const pricingTrade = state.trade === 'Painting' ? 'General' : state.trade;
  const p = (PRICING[pricingTrade] || {})[state.jobType];
  if (!p) return;
  const unit = p.unit === "job" ? "flat job" : p.unit;
  note.textContent = `National avg for this job: $${p.min.toLocaleString()}-$${p.max.toLocaleString()} (${unit})`;
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

// Materials Grid
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

// Step Navigation
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

// Step 1 to 2
function goToStep2() {
  if (!state.trade) {
    showToast("⚠️ Please select a trade first");
    document.getElementById('trade-grid')?.scrollIntoView({behavior:'smooth', block:'center'});
    return;
  }
  if (state.jobTypes.length === 0) {
    showToast("⚠️ Please select at least one scope of work below");
    document.getElementById('job-section')?.scrollIntoView({behavior:'smooth', block:'center'});
    const js = document.getElementById('job-section');
    if (js) { js.style.outline = '2px solid #FF6B00'; setTimeout(() => js.style.outline = '', 1500); }
    return;
  }
  showStep(2);
}

// Step 2 to 3
function goToStep3() {
  showStep(3);
}

function selectPaymentTerms(btn, terms) {
  document.querySelectorAll('.payment-term-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  state.paymentTerms = terms;
  const customRow = document.getElementById('custom-deposit-row');
  const fixedRow = document.getElementById('fixed-deposit-row');
  if (customRow) customRow.style.display = terms === 'custom_pct' ? 'block' : 'none';
  if (fixedRow) fixedRow.style.display = terms === 'fixed_deposit' ? 'block' : 'none';
}

function getPaymentTermsLabel() {
  const terms = state.paymentTerms;
  if (terms === 'full') return 'Payment in Full';
  if (terms === '50_50') return '50% Deposit, 50% on Completion';
  if (terms === '33_33_33') return '1/3 at Start, 1/3 at Midpoint, 1/3 on Completion';
  if (terms === 'custom_pct') {
    const pct = parseInt(document.getElementById('custom-deposit-pct')?.value || '25');
    return `${pct}% Deposit, ${100 - pct}% on Completion`;
  }
  if (terms === 'fixed_deposit') {
    const amt = parseFloat(document.getElementById('fixed-deposit-amt')?.value || '0');
    return amt > 0 ? `$${amt.toLocaleString()} Deposit, Balance on Completion` : 'Deposit, Balance on Completion';
  }
  return '';
}

function getDepositPct() {
  const terms = state.paymentTerms;
  if (terms === 'full') return 100;
  if (terms === '50_50') return 50;
  if (terms === '33_33_33') return 33;
  if (terms === 'custom_pct') return parseInt(document.getElementById('custom-deposit-pct')?.value || '25');
  if (terms === 'fixed_deposit') return null; // use fixed amount instead
  return 100;
}

function getFixedDepositAmt() {
  if (state.paymentTerms === 'fixed_deposit') {
    return parseFloat(document.getElementById('fixed-deposit-amt')?.value || '0') || null;
  }
  return null;
}

// Map raw UI job type values to PRICING dict keys for a given trade
function mapJobTypeToPricingKey(trade, rawJobType, baseParams) {
  const material = document.getElementById('roofing-material')?.value || 'asphalt';
  const systemType = document.getElementById('hvac-system-type')?.value || 'central_ac';

  const maps = {
    'Roofing': {
      replacement: material === 'metal' ? 'Full Replacement (Metal)' : 'Full Replacement (Asphalt)',
      repair: 'Repair (Minor)',
      gutters: 'Gutter Install/Replace',
    },
    'HVAC': {
      install: 'AC Install (Central)', replace: 'Full HVAC System',
      repair: systemType === 'furnace' ? 'Furnace Repair' : 'AC Repair',
      tuneup: systemType === 'furnace' ? 'Furnace Repair' : 'AC Repair',
    },
    'Plumbing': {
      water_heater: 'Water Heater (Tank)', drain_cleaning: 'Drain Cleaning',
      pipe_repair: 'Pipe Repair', bathroom_remodel: 'Bathroom Remodel (Plumbing)',
      full_repipe: 'Sewer Line Repair', fixture_install: 'Faucet/Fixture Install',
    },
    'Electrical': {
      panel_upgrade: 'Panel Upgrade', whole_home_rewire: 'Whole Home Rewire',
      ev_charger: 'EV Charger (Level 2)', circuit_add: 'Outlet Install',
      fixture_install_elec: 'Lighting Install', service_upgrade: 'Panel Upgrade',
    },
    'Painting': {
      interior: 'Interior Painting', exterior: 'Exterior Painting', both: 'Exterior Painting',
    },
    'Pressure Washing': {
      house_exterior: 'House Exterior Wash', driveway: 'Driveway Cleaning',
      deck_patio: 'Deck or Patio', roof_soft_wash: 'Roof Soft Wash',
      fence: 'Fence Cleaning', commercial: 'Commercial Building',
    },
  };
  const tradeMap = maps[trade];
  return (tradeMap && tradeMap[rawJobType]) ? tradeMap[rawJobType] : rawJobType;
}

// Collect trade-specific params for the API call
function getTradeParams() {
  const trade = state.trade;
  const jobType = state.jobType;
  const params = { trade_multiplier: 1.0 };

  if (trade === 'Roofing') {
    let pricingJobType, squares, pitchMult, tradeMult, loc, extraFields = {};

    if (jobType === 'replacement') {
      squares = parseFloat(document.getElementById('roofing-squares')?.value) || 25;
      const tier = document.getElementById('roofing-shingle-tier')?.value || 'architectural';
      const pitch = document.getElementById('roofing-pitch')?.value || 'medium';
      const tearoff = document.getElementById('roofing-tearoff')?.value || 'yes';
      loc = document.getElementById('location-state')?.value || '';
      pricingJobType = 'Full Replacement (Asphalt)';
      const tierMults = {3tab: 0.85, architectural: 1.0, premium: 1.35};
      pitchMult = {low: 0.9, medium: 1.0, steep: 1.2}[pitch] || 1.0;
      tradeMult = (tierMults[tier] || 1.0) * pitchMult;
      extraFields.include_tearoff = tearoff === 'yes';
      extraFields.roof_squares = squares;
    } else if (jobType === 'metal') {
      squares = parseFloat(document.getElementById('roofing-metal-squares')?.value) || 25;
      const metalType = document.getElementById('roofing-metal-type')?.value || 'standing_seam';
      const pitch = document.getElementById('roofing-metal-pitch')?.value || 'medium';
      loc = document.getElementById('location-state-metal')?.value || '';
      pricingJobType = 'Full Replacement (Metal)';
      const metalMults = {corrugated: 0.80, stone_coated: 1.0, standing_seam: 1.25};
      tradeMult = (metalMults[metalType] || 1.0) * ({low: 0.9, medium: 1.0, steep: 1.2}[pitch] || 1.0);
      extraFields.roof_squares = squares;
    } else if (jobType === 'repair') {
      const repairSqft = parseFloat(document.getElementById('roofing-repair-sqft')?.value) || 50;
      squares = repairSqft / 100;
      loc = document.getElementById('location-state-repair')?.value || '';
      pricingJobType = 'Repair (Minor)';
      tradeMult = Math.max(0.5, repairSqft / 50);
    } else {
      // Gutters
      const lf = parseFloat(document.getElementById('roofing-gutter-lf')?.value) || 150;
      const gutterMat = document.getElementById('roofing-gutter-material')?.value || 'aluminum';
      loc = document.getElementById('location-state-gutters')?.value || '';
      pricingJobType = 'Gutter Install/Replace';
      const gutterMults = {aluminum: 1.0, steel: 1.1, copper: 2.2};
      tradeMult = (gutterMults[gutterMat] || 1.0) * (lf / 150);
      squares = 0;
    }

    params.job_type = pricingJobType;
    params.property_size = (squares || 25) * 100;
    params.labor_hours = 0;
    params.trade_multiplier = tradeMult || 1.0;
    params.location = loc;
    Object.assign(params, extraFields);

  } else if (trade === 'HVAC') {
    const systemType = document.getElementById('hvac-system-type')?.value || 'central_ac';
    const repairSystem = document.getElementById('hvac-repair-system')?.value || 'central_ac';

    // Determine location from whichever sub-section is active
    const loc = document.getElementById('location-hvac-state')?.value ||
                document.getElementById('location-hvac-furnace-state')?.value ||
                document.getElementById('location-hvac-ms-state')?.value ||
                document.getElementById('location-hvac-repair-state')?.value || '';

    let pricingJobType, tradeMult;

    if (jobType === 'repair' || jobType === 'tuneup') {
      const rs = repairSystem || systemType;
      pricingJobType = (rs === 'furnace') ? 'Furnace Repair' : 'AC Repair';
      tradeMult = 1.0;
    } else if (systemType === 'furnace') {
      pricingJobType = (jobType === 'replace') ? 'Full HVAC System' : 'Furnace Install';
      const btu = parseInt(document.getElementById('hvac-btu')?.value) || 80000;
      const btuMults = {40000: 0.75, 60000: 0.85, 80000: 1.0, 100000: 1.15, 120000: 1.30};
      const fuelMults = {gas: 1.0, electric: 0.95, propane: 1.05};
      const fuel = document.getElementById('hvac-fuel')?.value || 'gas';
      tradeMult = (btuMults[btu] || 1.0) * (fuelMults[fuel] || 1.0);
    } else if (systemType === 'mini_split') {
      pricingJobType = 'Mini Split Install';
      const zones = parseInt(document.getElementById('hvac-zones')?.value) || 1;
      const mstons = parseFloat(document.getElementById('hvac-minisplit-tons')?.value) || 1.0;
      tradeMult = zones * (mstons / 1.0);
    } else if (systemType === 'full_system' || jobType === 'replace') {
      pricingJobType = 'Full HVAC System';
      const tons = parseFloat(document.getElementById('hvac-tons')?.value) || 2.5;
      const tonMults = {1.5: 0.65, 2: 0.80, 2.5: 1.0, 3: 1.25, 3.5: 1.40, 4: 1.55, 5: 1.85};
      tradeMult = tonMults[tons] || (tons / 2.5);
    } else {
      pricingJobType = 'AC Install (Central)';
      const tons = parseFloat(document.getElementById('hvac-tons')?.value) || 2.5;
      const tonMults = {1.5: 0.65, 2: 0.80, 2.5: 1.0, 3: 1.25, 3.5: 1.40, 4: 1.55, 5: 1.85};
      tradeMult = tonMults[tons] || (tons / 2.5);
    }

    params.job_type = pricingJobType;
    params.property_size = 1500;
    params.labor_hours = 0;
    params.trade_multiplier = tradeMult;
    params.location = loc;

  } else if (trade === 'Plumbing') {
    const fixtures = parseInt(document.getElementById('plumbing-fixtures')?.value) || 1;
    const homeSize = document.getElementById('plumbing-home-size')?.value || '1000_2000';
    const loc = document.getElementById('location-plumbing-state')?.value || '';

    const loc = document.getElementById('location-plumbing-state')?.value ||
                document.getElementById('location-plumbing-tankless-state')?.value ||
                document.getElementById('location-plumbing-bath-state')?.value ||
                document.getElementById('location-plumbing-repipe-state')?.value ||
                document.getElementById('location-plumbing-general-state')?.value || '';

    let pricingJobType, tradeMult;

    if (jobType === 'water_heater') {
      pricingJobType = 'Water Heater (Tank)';
      const whSize = parseInt(document.getElementById('plumbing-wh-size')?.value) || 40;
      const whFuel = document.getElementById('plumbing-wh-fuel')?.value || 'gas';
      const sizeMults = {30: 0.85, 40: 1.0, 50: 1.15, 75: 1.4, 80: 1.5};
      const fuelMults = {gas: 1.0, electric: 0.95, propane: 1.05};
      tradeMult = (sizeMults[whSize] || 1.0) * (fuelMults[whFuel] || 1.0);
    } else if (jobType === 'tankless') {
      pricingJobType = 'Water Heater (Tankless)';
      const gpm = parseInt(document.getElementById('plumbing-tankless-gpm')?.value) || 8;
      const tFuel = document.getElementById('plumbing-tankless-fuel')?.value || 'gas';
      const gpmMults = {6: 0.85, 8: 1.0, 10: 1.2, 12: 1.4};
      tradeMult = (gpmMults[gpm] || 1.0) * ({gas: 1.0, electric: 0.9, propane: 1.1}[tFuel] || 1.0);
    } else if (jobType === 'bathroom_remodel') {
      pricingJobType = 'Bathroom Remodel (Plumbing)';
      const bathFix = parseInt(document.getElementById('plumbing-bath-fixtures')?.value) || 3;
      tradeMult = {2: 0.8, 3: 1.0, 4: 1.3, 5: 1.6}[bathFix] || 1.0;
    } else if (jobType === 'full_repipe') {
      pricingJobType = 'Sewer Line Repair';
      const homeSize = document.getElementById('plumbing-home-size')?.value || '1000_2000';
      const homeMults = {under_1000: 0.7, '1000_2000': 1.0, '2000_3500': 1.5, '3500_plus': 2.2};
      tradeMult = homeMults[homeSize] || 1.0;
    } else if (jobType === 'drain_cleaning') {
      pricingJobType = 'Drain Cleaning'; tradeMult = 1.0;
    } else if (jobType === 'pipe_repair') {
      pricingJobType = 'Pipe Repair'; tradeMult = 1.0;
    } else {
      pricingJobType = 'Faucet/Fixture Install'; tradeMult = 1.0;
    }

    params.job_type = pricingJobType;
    params.property_size = 1500;
    params.labor_hours = 0;
    params.trade_multiplier = tradeMult;
    params.location = loc;

  } else if (trade === 'Electrical') {
    // Read location from whichever sub-section is active
    const loc = document.getElementById('location-electrical-state')?.value ||
                document.getElementById('location-elec-ev-state')?.value ||
                document.getElementById('location-elec-rewire-state')?.value ||
                document.getElementById('location-elec-circuit-state')?.value ||
                document.getElementById('location-elec-lighting-state')?.value || '';

    const jobMap = {
      panel_upgrade: 'Panel Upgrade', service_upgrade: 'Panel Upgrade',
      whole_home_rewire: 'Whole Home Rewire',
      ev_charger: 'EV Charger (Level 2)',
      circuit_add: 'Outlet Install',
      fixture_install_elec: 'Lighting Install',
    };

    params.job_type = jobMap[jobType] || 'Panel Upgrade';
    params.property_size = 1500;
    params.labor_hours = 0;
    params.location = loc;

    if (jobType === 'panel_upgrade' || jobType === 'service_upgrade') {
      const fromAmps = parseInt(document.getElementById('elec-current-amps')?.value) || 100;
      const toAmps = parseInt(document.getElementById('elec-new-amps')?.value) || 200;
      const panelMults = {'60_100': 0.75, '100_150': 0.85, '100_200': 1.0, '150_200': 0.90, '200_400': 1.6, '100_400': 1.8};
      params.trade_multiplier = panelMults[`${fromAmps}_${toAmps}`] || 1.0;
    } else if (jobType === 'ev_charger') {
      const evAmps = parseInt(document.getElementById('elec-ev-amps')?.value) || 30;
      const evLoc = document.getElementById('elec-ev-location')?.value || 'garage';
      const evAmpMults = {20: 0.75, 30: 1.0, 40: 1.15, 50: 1.3, 60: 1.5};
      const evLocMults = {garage: 1.0, exterior: 1.1, subpanel: 1.4};
      params.trade_multiplier = (evAmpMults[evAmps] || 1.0) * (evLocMults[evLoc] || 1.0);
    } else if (jobType === 'whole_home_rewire') {
      const rewireSize = document.getElementById('elec-rewire-size')?.value || '1000_2000';
      const rewireStories = parseInt(document.getElementById('elec-rewire-stories')?.value) || 1;
      const sizeMults = {under_1000: 0.7, '1000_2000': 1.0, '2000_3500': 1.5, '3500_plus': 2.1};
      params.trade_multiplier = (sizeMults[rewireSize] || 1.0) * (rewireStories === 3 ? 1.2 : rewireStories === 2 ? 1.1 : 1.0);
    } else if (jobType === 'circuit_add') {
      const circuits = parseInt(document.getElementById('elec-circuits')?.value) || 3;
      params.trade_multiplier = Math.max(1, circuits);
    } else if (jobType === 'fixture_install_elec') {
      const fixtures = parseInt(document.getElementById('elec-fixtures')?.value) || 5;
      params.trade_multiplier = Math.max(1, fixtures);
    }

  } else if (trade === 'Painting') {
    const sqft = parseFloat(document.getElementById('painting-sqft')?.value) || 1500;
    const stories = parseInt(document.getElementById('painting-stories')?.value) || 1;
    const prep = document.getElementById('painting-prep')?.value || 'moderate';
    const loc = document.getElementById('location-painting-state')?.value || '';

    const jobMap = { interior: 'Interior Painting', exterior: 'Exterior Painting', both: 'Exterior Painting' };
    params.job_type = jobMap[jobType] || 'Interior Painting';
    params.trade = 'General'; // remap Painting to General PRICING
    params.property_size = sqft;
    params.labor_hours = Math.round(sqft / 100);
    params.location = loc;

    const storiesMults = { 1: 1.0, 2: 1.15, 3: 1.30 };
    const prepMults = { minimal: 0.85, moderate: 1.0, heavy: 1.25 };
    let mult = (storiesMults[stories] || 1.0) * (prepMults[prep] || 1.0);
    if (jobType === 'both') mult *= 1.6;
    params.trade_multiplier = mult;

  } else if (trade === 'Pressure Washing') {
    const sqft = parseFloat(document.getElementById('pw-sqft')?.value) || 1500;
    const loc = document.getElementById('location-pw-state')?.value || '';

    const jobMap = {
      house_exterior: 'House Exterior Wash',
      driveway: 'Driveway Cleaning',
      deck_patio: 'Deck or Patio',
      roof_soft_wash: 'Roof Soft Wash',
      fence: 'Fence Cleaning',
      commercial: 'Commercial Building',
    };

    const pwHours = parseFloat(document.getElementById('pw-hours')?.value) || null;
    params.job_type = jobMap[jobType] || 'House Exterior Wash';
    params.property_size = sqft;
    params.labor_hours = pwHours || 2;
    params.job_hours = pwHours;
    params.trade_multiplier = 1.0;
    params.location = loc;

  } else if (trade === 'Landscaping') {
    const sqft = parseFloat(document.getElementById('landscaping-sqft')?.value) || 1500;
    const labor = parseFloat(document.getElementById('landscaping-labor')?.value) || 4;
    const loc = document.getElementById('location-landscaping-state')?.value || '';
    params.job_type = jobType;
    params.property_size = sqft;
    params.labor_hours = labor;
    params.location = loc;

  } else {
    // General Contractor
    const sqft = parseFloat(document.getElementById('property-size')?.value) || 1500;
    const labor = parseFloat(document.getElementById('labor-hours')?.value) || 4;
    const loc = document.getElementById('location-general-state')?.value || '';
    params.job_type = jobType;
    params.property_size = sqft;
    params.labor_hours = labor;
    params.location = loc;
  }

  return params;
}

// Step 3 to generate
async function generateQuote() {
  const contractorName = $("contractor-name").value.trim();
  const contractorBusiness = $("contractor-business").value.trim();
  if (!contractorName || !contractorBusiness) {
    showToast("⚠️ Please enter your name and business name");
    return;
  }

  saveContractorInfo();

  if (document.getElementById('save-contractor-info')?.checked) {
    const info = {};
    ['contractor-name','contractor-business','contractor-phone','contractor-email'].forEach(id => {
      info[id] = document.getElementById(id)?.value || '';
    });
    localStorage.setItem('qb_contractor', JSON.stringify(info));
  }

  // Collect trade-specific params
  const tradeParams = getTradeParams();

  // Custom pricing (toggle-based fields)
  const customMinToggle = $("custom-price-min")?.value;
  const customMaxToggle = $("custom-price-max")?.value;
  const hasCustomToggle = state.customPricingOpen && customMinToggle && customMaxToggle &&
                    parseFloat(customMinToggle) > 0 && parseFloat(customMaxToggle) >= parseFloat(customMinToggle);

  // Custom pricing (always-visible fields)
  const customMin = parseFloat(document.getElementById('custom-min')?.value);
  const customMax = parseFloat(document.getElementById('custom-max')?.value);
  const hasCustomDirect = !isNaN(customMin) && !isNaN(customMax) && customMin > 0 && customMax > 0;

  const payload = {
    trade: tradeParams.trade || state.trade,
    job_type: tradeParams.job_type || state.jobType,
    job_types: state.jobTypes.map(jt => mapJobTypeToPricingKey(state.trade, jt, tradeParams)),
    property_size: tradeParams.property_size || 1500,
    location: tradeParams.location || '',
    labor_hours: tradeParams.labor_hours !== undefined ? tradeParams.labor_hours : 4,
    job_hours: tradeParams.job_hours || null,
    trade_multiplier: tradeParams.trade_multiplier || 1.0,
    materials: getCheckedMaterials(),
    contractor_name: contractorName,
    contractor_business: contractorBusiness,
    contractor_phone: $("contractor-phone").value.trim(),
    contractor_email: $("contractor-email").value.trim(),
    client_name: $("client-name").value.trim(),
    client_address: $("client-address").value.trim(),
    job_description: $("job-description").value.trim(),
    terms: "",
    payment_terms: state.paymentTerms,
    payment_terms_label: getPaymentTermsLabel(),
    deposit_pct: getDepositPct(),
    fixed_deposit_amt: getFixedDepositAmt(),
    ...(hasCustomToggle && {
      custom_price_min: parseFloat(customMinToggle),
      custom_price_max: parseFloat(customMaxToggle),
    }),
    ...(hasCustomDirect && {
      custom_min: customMin,
      custom_max: customMax,
    }),
    line_items_custom: lineItems.map(li => ({
      description: li.description,
      amount: li.amount || 0,
      markup: li.markup || 0
    })),
    discount_flat: parseFloat(document.getElementById('discount-flat')?.value) || 0,
    discount_pct: parseFloat(document.getElementById('discount-pct')?.value) || 0,
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
    showPriceConfirm(data);
  } catch (err) {
    $("error-banner").textContent = "❌ " + err.message;
    $("error-banner").classList.add("show");
  } finally {
    btn.disabled = false;
    spinner.classList.remove("active");
  }
}

// Render Result
function renderResult() {
  $("result-quote-id").textContent = "Quote #" + state.quoteId;

  $("result-min").textContent = "$" + state.totalMin.toLocaleString();
  $("result-max").textContent = "$" + state.totalMax.toLocaleString();

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

  const shareUrl = `${location.origin}/q/${state.quoteId}`;
  const shareUrlEl = $("share-url");
  if (shareUrlEl) shareUrlEl.value = shareUrl;
}

// PDF Download
function downloadPDF() {
  if (!state.quoteId) return;
  window.location.href = `/api/pdf/${state.quoteId}`;
}

// Copy Share Link
function copyShareLink() {
  const url = $("share-url")?.value || currentQuoteLink;
  if (!url) return;
  navigator.clipboard.writeText(url).then(() => {
    showToast("✅ Link copied to clipboard!");
  }).catch(() => {
    if ($("share-url")) { $("share-url").select(); document.execCommand("copy"); }
    showToast("✅ Link copied!");
  });
}

// SMS share
function openSMS(e) {
  e.preventDefault();
  const link = $('share-url')?.value || currentQuoteLink || '';
  const biz = window.contractorBusiness || 'Your Contractor';
  window.location.href = `sms:?body=Hi, here is your quote from ${biz}: ${link}`;
}

// Email share
function openEmail(e) {
  e.preventDefault();
  const link = $('share-url')?.value || currentQuoteLink || '';
  const biz = window.contractorBusiness || 'Your Contractor';
  const subject = encodeURIComponent(`Your Quote from ${biz}`);
  const body = encodeURIComponent(`Hi,\n\nPlease find your quote here:\n${link}\n\nThis quote is valid for 30 days.\n\nThank you,\n${biz}`);
  window.location.href = `mailto:?subject=${subject}&body=${body}`;
}

// New Quote
function newQuote() {
  state = { step: 1, trade: null, jobType: null, jobTypes: [], quoteId: null, lineItems: [], totalMin: 0, totalMax: 0, customPricingOpen: false, paymentTerms: 'full' };
  document.querySelectorAll(".trade-card").forEach(c => c.classList.remove("selected"));
  document.querySelectorAll(".job-btn").forEach(b => b.classList.remove("selected"));
  document.querySelectorAll("input[type=checkbox]").forEach(c => c.checked = false);
  const saveInfo = $("save-contractor-info"); if (saveInfo) saveInfo.checked = true;
  $("job-section").classList.add("hidden");
  // Hide all trade input groups
  document.querySelectorAll('.trade-input-group').forEach(el => el.classList.add('hidden'));
  ["client-name","client-address","job-description"].forEach(id => {
    const el = $(id); if (el) el.value = "";
  });
  ["property-size"].forEach(id => {
    const el = $(id); if (el) el.value = "1500";
  });
  ["labor-hours", "landscaping-labor"].forEach(id => {
    const el = $(id); if (el) el.value = "4";
  });
  const panel = $("custom-pricing-panel");
  if (panel) panel.classList.add("hidden");
  const chevron = $("custom-pricing-chevron");
  if (chevron) chevron.textContent = "▼";
  const cpMin = $("custom-price-min"); if (cpMin) cpMin.value = "";
  const cpMax = $("custom-price-max"); if (cpMax) cpMax.value = "";
  const cmn = $("custom-min"); if (cmn) cmn.value = "";
  const cmx = $("custom-max"); if (cmx) cmx.value = "";
  const priceConfirm = document.getElementById('price-confirm-section');
  if (priceConfirm) priceConfirm.style.display = 'none';
  const shareSection = document.getElementById('share-section');
  if (shareSection) shareSection.style.display = 'none';
  currentQuoteData = null;
  currentQuoteLink = null;
  lineItems = [];
  renderLineItems();
  const dfFlat = document.getElementById('discount-flat'); if (dfFlat) dfFlat.value = '';
  const dfPct = document.getElementById('discount-pct'); if (dfPct) dfPct.value = '';
  showStep(1);
}

// Price Confirmation
function showPriceConfirm(quoteData) {
  currentQuoteData = quoteData;
  const min = quoteData.total_min;
  const max = Math.round(quoteData.total_max * 1.1);
  const mid = Math.round((quoteData.total_min + quoteData.total_max) / 2);

  const slider = document.getElementById('price-slider');
  slider.min = min;
  slider.max = max;
  slider.value = mid;

  document.getElementById('range-display').textContent =
    '$' + min.toLocaleString() + ' - $' + quoteData.total_max.toLocaleString();
  document.getElementById('slider-min-label').textContent = '$' + min.toLocaleString();
  document.getElementById('slider-max-label').textContent = '$' + max.toLocaleString();
  document.getElementById('final-price-display').textContent = '$' + mid.toLocaleString();

  slider.oninput = function() {
    document.getElementById('final-price-display').textContent =
      '$' + parseInt(this.value).toLocaleString();
  };

  document.getElementById('price-confirm-section').style.display = 'block';
  document.getElementById('price-confirm-section').scrollIntoView({behavior: 'smooth'});
}

async function confirmPrice() {
  const price = parseInt(document.getElementById('price-slider').value);
  const quoteId = currentQuoteData.quote_id;

  const res = await fetch('/api/quote/set-price', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({quote_id: quoteId, final_price: price})
  });
  const data = await res.json();
  if (data.success) {
    document.getElementById('price-confirm-section').style.display = 'none';
    showShareSection(quoteId, price);
  }
}

function showShareSection(quoteId, finalPrice) {
  currentQuoteLink = `${location.origin}/q/${quoteId}`;
  const shareUrlEl = $('share-url');
  if (shareUrlEl) shareUrlEl.value = currentQuoteLink;
  const shareSection = document.getElementById('share-section');
  if (shareSection) {
    shareSection.style.display = 'block';
    shareSection.scrollIntoView({behavior: 'smooth'});
  }
}

// Toast
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
