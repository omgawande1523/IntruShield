import { initDemo } from './demo.js';
import { initScroll, initCountUps } from './scroll.js';
import { detectTier } from './tier.js';

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const forceStatic = new URLSearchParams(location.search).has('static');
const tier = detectTier();
const fmtInt = (n) => (typeof n === 'number' ? n.toLocaleString('en-US') : '—');

const loader = document.getElementById('loader'), loaderBar = document.getElementById('loader-bar'), loaderPct = document.getElementById('loader-pct');
const setProgress = (p) => { const v = Math.round(Math.max(0, Math.min(1, p)) * 100); loaderBar.style.width = `${v}%`; loaderPct.textContent = `${v}%`; };
const hideLoader = () => { setProgress(1); loader.classList.add('done'); setTimeout(() => loader.remove(), 700); };

async function loadMetrics() {
  try { const r = await fetch('/api/metrics'); if (!r.ok) throw new Error(`HTTP ${r.status}`); return await r.json(); }
  catch (e) { console.warn('[metrics] unavailable:', e.message); return null; }
}
function fillStaticNumbers(m) {
  if (!m) return;
  const map = { n_features: m.n_features, test_rows: fmtInt(m.test_set?.rows), unseen_attack_types: m.test_set?.unseen_attack_types };
  document.querySelectorAll('[data-metric]').forEach((el) => { const v = map[el.dataset.metric]; if (v !== undefined && v !== null) el.textContent = String(v); });
}
function initCursor() {
  const ring = document.getElementById('cursor');
  if (!ring || matchMedia('(pointer: coarse)').matches || reduced) return;
  let x = innerWidth / 2, y = innerHeight / 2, tx = x, ty = y, on = false;
  addEventListener('pointermove', (e) => { tx = e.clientX; ty = e.clientY; if (!on) { on = true; ring.classList.add('on'); } }, { passive: true });
  document.addEventListener('pointerleave', () => { on = false; ring.classList.remove('on'); });
  document.addEventListener('pointerover', (e) => ring.classList.toggle('hover', !!e.target.closest?.('a, button, input, select, .chip')));
  const tick = () => { x += (tx - x) * 0.16; y += (ty - y) * 0.16; ring.style.transform = `translate3d(${x}px, ${y}px, 0)`; requestAnimationFrame(tick); };
  tick();
}
const hasWebGL = () => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; } };

(async () => {
  const metricsP = loadMetrics();
  let scene = null;
  const demoP = initDemo({ onResult: (res) => scene?.react(res.verdict === 'ATTACK' ? 'attack' : 'normal') });

  const canvas = document.getElementById('bg');
  if (hasWebGL() && !forceStatic) {
    try {
      setProgress(0.05);
      const { createScene } = await import('./scene/index.js');
      scene = await createScene(canvas, { tier, reduced, onProgress: (p) => setProgress(0.05 + p * 0.95) });
    } catch (e) {
      console.warn('[scene] disabled:', e);
      scene = null;
      document.body.classList.add('static-bg');
    }
  } else {
    document.body.classList.add('static-bg');
  }

  const metrics = await metricsP;
  fillStaticNumbers(metrics);
  await (document.fonts?.ready || Promise.resolve());
  const story = initScroll({ tier, reduced });
  if (metrics) initCountUps(metrics, reduced);
  hideLoader();
  initCursor();
  story.revealHero();
  setTimeout(() => story.refresh(), 800);
  await demoP;
  console.info(`[IntruShield] tier=${tier.name} dpr=${tier.dpr} reduced=${reduced} webgl=${!!scene}`);
})();
