/* Live demo: curated chips, crafted sliders, result card, live-traffic ticker.
   Every number shown comes from the FastAPI backend (real models). */

const $ = (s, r = document) => r.querySelector(s);
const API = '';

const CLASS_WORD = { Normal: 'Normal', DoS: 'DoS flood', Probe: 'Network scan', R2L: 'Remote break-in', U2R: 'Privilege escalation' };
const POPULAR_SERVICES = ['http', 'private', 'ftp_data', 'smtp', 'telnet', 'ecr_i', 'domain_u', 'ftp', 'pop_3', 'other'];

const fmtBytes = (n) => {
  if (n < 1024) return `${Math.round(n)} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
};
const sliderToBytes = (v) => Math.max(0, Math.round(Math.pow(10, (v / 1000) * 7) - 1));
const bytesToSlider = (b) => Math.round((Math.log10(Math.max(0, b) + 1) / 7) * 1000);
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

export async function initDemo({ onResult } = {}) {
  const els = {
    chips: $('#chips'), card: $('#result'), verdict: $('#verdict'), family: $('#family'), kicker: $('#result-kicker'),
    ring: $('#ring-fg'), prob: $('#prob'), latency: $('#latency'), truth: $('#truth'), reasons: $('#reasons'), error: $('#result-error'),
    src: $('#ctl-src'), dst: $('#ctl-dst'), count: $('#ctl-count'), err: $('#ctl-err'), service: $('#ctl-service'),
    outSrc: $('#out-src'), outDst: $('#out-dst'), outCount: $('#out-count'), outErr: $('#out-err'), reset: $('#btn-reset'),
  };

  const state = { baseline: null, samples: [], current: null, overrides: {}, activeChip: null, ctrl: null };

  // ------------------------------------------------------------------ load samples
  let data;
  try {
    const r = await fetch(`${API}/api/samples`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    data = await r.json();
  } catch (e) {
    els.chips.innerHTML = '';
    showError(`Could not reach the IntruShield server (${e.message}). Start it with web/run_site.bat.`);
    return;
  }
  state.baseline = data.baseline;
  state.samples = data.samples;

  // services dropdown: popular first, then the rest
  const rest = data.services.filter((s) => !POPULAR_SERVICES.includes(s));
  els.service.innerHTML = [...POPULAR_SERVICES.filter((s) => data.services.includes(s)), ...rest]
    .map((s) => `<option value="${s}">${s}</option>`).join('');

  // chips
  els.chips.innerHTML = '';
  for (const s of state.samples) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `chip ${s.true_class === 'Normal' ? 'is-normal' : 'is-attack'}`;
    b.setAttribute('aria-pressed', 'false');
    b.dataset.id = s.id;
    const tag = !s.seen_in_train ? '<span class="tag">never seen in training</span>' : s.id === 'hard' ? '<span class="tag" style="background:#ff4d5e;color:#fff">hard case</span>' : '';
    b.innerHTML = `<span>${s.title}</span><small>${s.true_class === 'Normal' ? 'normal traffic' : `${s.true_class} · ${s.attack_blurb}`}</small>${tag}`;
    b.addEventListener('click', () => pickSample(s));
    els.chips.appendChild(b);
  }

  // ------------------------------------------------------------------ sliders
  function setControlsFrom(features) {
    els.src.value = bytesToSlider(features.src_bytes);
    els.dst.value = bytesToSlider(features.dst_bytes);
    els.count.value = features.count;
    els.err.value = Math.round((features.serror_rate || 0) * 100);
    if ([...els.service.options].some((o) => o.value === features.service)) els.service.value = features.service;
    refreshOutputs();
  }
  function refreshOutputs() {
    els.outSrc.value = fmtBytes(sliderToBytes(+els.src.value));
    els.outDst.value = fmtBytes(sliderToBytes(+els.dst.value));
    els.outCount.value = els.count.value;
    els.outErr.value = `${els.err.value}%`;
  }
  function overridesFromControls() {
    const rate = +els.err.value / 100;
    return {
      src_bytes: sliderToBytes(+els.src.value),
      dst_bytes: sliderToBytes(+els.dst.value),
      count: +els.count.value,
      serror_rate: rate,
      dst_host_serror_rate: rate,
      service: els.service.value,
    };
  }
  const onCraft = debounce(() => {
    state.overrides = overridesFromControls();
    predict({ sample_id: state.current?.id, features: { ...state.current?.features, ...state.overrides } }, state.current, true);
  }, 140);
  for (const el of [els.src, els.dst, els.count, els.err]) el.addEventListener('input', () => { refreshOutputs(); onCraft(); });
  els.service.addEventListener('change', onCraft);
  els.reset.addEventListener('click', () => {
    state.current = null; state.overrides = {};
    setActiveChip(null);
    setControlsFrom(state.baseline);
    predict({ features: state.baseline }, null, false);
  });

  function setActiveChip(id) {
    state.activeChip = id;
    for (const c of els.chips.querySelectorAll('.chip')) c.setAttribute('aria-pressed', String(c.dataset.id === id));
  }

  async function pickSample(s) {
    state.current = s; state.overrides = {};
    setActiveChip(s.id);
    setControlsFrom(s.features);
    await predict({ sample_id: s.id }, s, false);
  }

  // ------------------------------------------------------------------ predict
  async function predict(body, sample, crafted) {
    if (state.ctrl) state.ctrl.abort();
    const ctrl = (state.ctrl = new AbortController());
    els.card.classList.add('loading');
    try {
      const r = await fetch(`${API}/api/predict`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: ctrl.signal,
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || j.error || `HTTP ${r.status}`);
      renderResult(j, sample, crafted);
      onResult?.(j);
    } catch (e) {
      if (e.name === 'AbortError') return;
      showError(`Prediction failed: ${e.message}`);
    } finally {
      if (state.ctrl === ctrl) els.card.classList.remove('loading');
    }
  }

  function showError(msg) { els.error.textContent = msg; els.error.hidden = false; }

  function renderResult(res, sample, crafted) {
    els.error.hidden = true;
    const attack = res.verdict === 'ATTACK';
    els.card.classList.remove('is-normal', 'is-attack');
    void els.card.offsetWidth; // restart shake animation
    els.card.classList.add(attack ? 'is-attack' : 'is-normal');
    els.kicker.textContent = crafted ? 'Verdict · crafted connection' : sample ? 'Verdict · real connection' : 'Verdict';
    els.verdict.textContent = res.verdict;
    els.family.innerHTML = attack
      ? `<b>${CLASS_WORD[res.pred_class] || res.pred_class}</b> · ${res.family}`
      : res.family;
    const pct = res.probability * 100;
    els.prob.textContent = pct < 0.1 && pct > 0 ? '<0.1%' : `${pct.toFixed(pct < 10 ? 1 : 0)}%`;
    const C = 326.7;
    els.ring.style.strokeDashoffset = String(C - (C * Math.max(0.015, res.probability)));
    els.latency.textContent = res.latency_ms.toFixed(1);

    if (sample && !crafted && res.truth) {
      const t = res.truth;
      const truthWord = t.true_class === 'Normal' ? 'Normal' : `${CLASS_WORD[t.true_class]} (${t.attack_name})`;
      const correct = (t.true_class === 'Normal') === !attack;
      els.truth.hidden = false;
      els.truth.className = `truth ${correct ? '' : 'wrong'}`;
      els.truth.textContent = `true label (demo data): ${truthWord}${t.seen_in_train ? '' : ' · never seen in training'}${correct ? ' ✓' : ' · missed'}`;
    } else {
      els.truth.hidden = true;
    }

    els.reasons.innerHTML = '';
    for (const rs of res.reasons) {
      const li = document.createElement('li');
      li.className = rs.direction === 'attack' ? 'toward-attack' : 'toward-normal';
      const val = typeof rs.value === 'number'
        ? (rs.raw_feature.endsWith('bytes') ? fmtBytes(rs.value) : rs.raw_feature.includes('rate') ? `${Math.round(rs.value * 100)}%` : String(rs.value))
        : rs.value;
      li.innerHTML = `<span>${cap(rs.friendly_label)} <span class="val">(${val})</span></span><span class="dir">${rs.direction === 'attack' ? 'points to attack' : 'looks normal'}</span><span class="bar"><i></i></span>`;
      els.reasons.appendChild(li);
      requestAnimationFrame(() => requestAnimationFrame(() => { li.querySelector('i').style.width = `${Math.max(8, rs.strength * 100)}%`; }));
    }
  }

  // initial state: the baseline normal connection
  setControlsFrom(state.baseline);
  predict({ features: state.baseline }, null, false);

  initTicker();
  return { pickSample, samples: state.samples };
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// ---------------------------------------------------------------------- ticker
function initTicker() {
  const strip = $('#ticker');
  const counters = { scanned: $('#c-scanned'), caught: $('#c-caught'), missed: $('#c-missed'), false_alarm: $('#c-false') };
  const pauseBtn = $('#btn-pause');
  const n = { scanned: 0, caught: 0, missed: 0, false_alarm: 0 };
  let queue = [], paused = false, visible = false, fetching = false, timer = null;

  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; schedule(); }, { threshold: 0.05 });
  io.observe(strip);
  pauseBtn.addEventListener('click', () => {
    paused = !paused;
    pauseBtn.textContent = paused ? 'Resume' : 'Pause';
    pauseBtn.setAttribute('aria-pressed', String(paused));
    schedule();
  });
  document.addEventListener('visibilitychange', schedule);

  async function refill() {
    if (fetching || queue.length > 8) return;
    fetching = true;
    try {
      const r = await fetch(`/api/stream?n=16`);
      if (r.ok) queue.push(...(await r.json()).items);
    } catch (_) { /* server down: just idle */ }
    fetching = false;
  }

  function tick() {
    timer = null;
    if (paused || !visible || document.hidden) return;
    if (queue.length < 6) refill();
    const item = queue.shift();
    if (item) {
      n.scanned++;
      if (item.outcome !== 'clean') n[item.outcome]++;
      counters.scanned.textContent = n.scanned;
      counters.caught.textContent = n.caught;
      counters.missed.textContent = n.missed;
      counters.false_alarm.textContent = n.false_alarm;
      const label = { clean: 'normal', caught: 'attack caught', missed: 'attack missed', false_alarm: 'false alarm' }[item.outcome];
      const d = document.createElement('div');
      d.className = `tick ${item.outcome}`;
      d.innerHTML = `<b>${label}</b><span>${item.service} · ${item.protocol} · ${item.true_class === 'Normal' ? 'normal' : item.attack_name}</span>`;
      strip.prepend(d);
      while (strip.children.length > 24) strip.lastChild.remove();
    }
    timer = setTimeout(tick, 250);
  }
  function schedule() { if (!timer) tick(); }
  refill().then(schedule);
}
