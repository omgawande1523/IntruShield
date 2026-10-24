/* Scroll story: Lenis + GSAP ScrollTrigger. Pinned chapters write numbers into `state`; the scene damps toward them. */
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';
import Lenis from 'lenis';
import { state, prog } from './state.js';

gsap.registerPlugin(ScrollTrigger, SplitText);

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const NR = { immediateRender: false };

export function initScroll({ tier, reduced }) {
  const nav = $('#nav'), bar = $('#progress-bar'), num = $('#chapter-num');
  let lenis = null;
  if (!reduced) {
    lenis = new Lenis({ lerp: 0.075, smoothWheel: true });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
    let navOn = false;
    lenis.on('scroll', () => {
      bar.style.transform = `scaleX(${lenis.progress})`;
      const on = lenis.scroll > 60;
      if (on !== navOn) { navOn = on; nav.classList.toggle('scrolled', on); }
    });
  } else {
    addEventListener('scroll', () => { bar.style.transform = `scaleX(${scrollY / Math.max(1, document.body.scrollHeight - innerHeight)})`; nav.classList.toggle('scrolled', scrollY > 60); }, { passive: true });
  }
  $$('a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
    const el = $(a.getAttribute('href')); if (!el) return;
    e.preventDefault();
    if (lenis) lenis.scrollTo(el, { duration: 1.5, easing: (x) => 1 - Math.pow(1 - x, 3) }); else el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' });
  }));

  // dot-matrix grid
  const dg = $('#dotgrid');
  if (dg) { let s = ''; for (let y = 0; y < 10; y++) for (let x = 0; x < 10; x++) s += `<circle cx="${6 + x * 12}" cy="${6 + y * 12}" r="1"/>`; dg.innerHTML = s; }

  const setChapter = (n) => { if (state.chapter !== n) { state.chapter = n; num.textContent = String(n).padStart(2, '0'); } };
  const splitLines = (el) => new SplitText(el, { type: 'lines', mask: 'lines', linesClass: 'line' }).lines;

  if (reduced) {
    $$('.chapter').forEach((el) => ScrollTrigger.create({ trigger: el, start: 'top 60%', onToggle: (s) => s.isActive && setChapter(+el.dataset.chapter) }));
    return { lenis, refresh: () => ScrollTrigger.refresh(), revealHero() {} };
  }

  const pinLen = (pct) => `+=${Math.round(pct * tier.pin)}%`;
  const chapter = (id, n, len) => gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: { trigger: id, start: 'top top', end: pinLen(len), pin: true, scrub: 1, anticipatePin: 1, onToggle: (s) => s.isActive && setChapter(n) },
  });
  const reveal = (targets, trigger, extra = {}) => gsap.fromTo(targets,
    { yPercent: 110, opacity: 0, filter: 'blur(8px)' },
    { yPercent: 0, opacity: 1, filter: 'blur(0px)', stagger: 0.08, duration: 0.95, ease: 'power3.out', clearProps: 'filter', scrollTrigger: { trigger, start: 'top 70%', toggleActions: 'play none none reverse' }, ...extra });
  const drawDeco = (tl, sel, at = 0) => { const p = $(sel); if (p) tl.fromTo(p, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.5, ...NR }, at); };

  // 01 HERO (short pin so the brain holds on screen)
  const hero = chapter('#hero', 1, 60);
  hero.fromTo(prog, { hero: 0 }, { hero: 1, duration: 1, ...NR }, 0);
  drawDeco(hero, '.deco-hero path', 0);

  // 02 PROBLEM: brain disintegrates into voxels -> slabs; lines reveal one by one
  const problem = chapter('#problem', 2, 160);
  problem.fromTo(prog, { problem: 0 }, { problem: 1, duration: 1, ...NR }, 0);
  $$('#problem .line-item').forEach((li, i) => problem.fromTo(li, { yPercent: 40, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.18, ease: 'power2.out', ...NR }, 0.18 + i * 0.24));
  problem.fromTo('#dotgrid circle', { opacity: 0 }, { opacity: 1, stagger: { each: 0.004, from: 'start' }, duration: 0.1, ...NR }, 0.1);
  reveal(splitLines('#problem .display'), '#problem');

  // 03 INTRO: dense cluster, red cubes ejected
  const intro = chapter('#intro', 3, 110);
  intro.fromTo(prog, { intro: 0 }, { intro: 1, duration: 1, ...NR }, 0);
  drawDeco(intro, '.deco-intro path', 0);
  reveal(splitLines('#intro .display'), '#intro');
  gsap.from('#intro .br', { y: 24, opacity: 0, duration: 0.9, ease: 'power3.out', scrollTrigger: { trigger: '#intro', start: 'top 60%', toggleActions: 'play none none reverse' } });

  // 04 PURPOSE: voxels gather into the point-cloud brain; cards
  const purpose = chapter('#purpose', 4, 120);
  purpose.fromTo(prog, { purpose: 0 }, { purpose: 1, duration: 1, ...NR }, 0);
  reveal(splitLines('#purpose .display'), '#purpose');
  purpose.fromTo('#purpose .card', { y: 40, opacity: 0 }, { y: 0, opacity: 1, stagger: 0.08, duration: 0.3, ease: 'power3.out', ...NR }, 0.15);

  // 05 HOW: point cloud explodes into nebula, condenses into the dark globe; steps
  const how = chapter('#how', 5, 180);
  how.fromTo(prog, { how: 0 }, { how: 1, duration: 1, ...NR }, 0);
  reveal(splitLines('#how .display'), '#how');
  $$('#how .step').forEach((st, i) => how.fromTo(st, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.2, ease: 'power3.out', ...NR }, 0.12 + i * 0.22));

  // 06 DEMO (not pinned, interactive): globe -> shield
  gsap.fromTo(prog, { demo: 0 }, { demo: 1, ease: 'none', ...NR, scrollTrigger: { trigger: '#demo', start: 'top 85%', end: 'top 25%', scrub: 1 } });
  ScrollTrigger.create({ trigger: '#demo', start: 'top 60%', end: 'bottom 60%', onToggle: (s) => s.isActive && setChapter(6) });
  reveal(splitLines('#demo .display'), '#demo');
  gsap.from('#demo .lede, #demo .demo-grid, #demo .ticker-wrap', { y: 30, opacity: 0, stagger: 0.12, duration: 0.9, ease: 'power3.out', scrollTrigger: { trigger: '#demo .demo-grid', start: 'top 85%', toggleActions: 'play none none none' } });

  // 07 IMPACT: shield -> slowly rotating globe
  const impact = chapter('#impact', 7, 90);
  impact.fromTo(prog, { impact: 0 }, { impact: 1, duration: 1, ...NR }, 0);
  reveal(splitLines('#impact .display'), '#impact');
  impact.fromTo('#impact .stat, #impact .honest', { y: 30, opacity: 0 }, { y: 0, opacity: 1, stagger: 0.06, duration: 0.25, ease: 'power3.out', ...NR }, 0.1);

  // footer wordmark
  gsap.from('.wordmark', { yPercent: 30, opacity: 0, duration: 1.2, ease: 'power3.out', scrollTrigger: { trigger: '#footer', start: 'top 80%' } });

  document.fonts?.ready.then(() => ScrollTrigger.refresh());

  return {
    lenis,
    refresh: () => ScrollTrigger.refresh(),
    revealHero() {
      const lines = splitLines('#hero .display');
      gsap.timeline()
        .fromTo(lines, { yPercent: 110, filter: 'blur(10px)' }, { yPercent: 0, filter: 'blur(0px)', stagger: 0.09, duration: 1.15, ease: 'power4.out', clearProps: 'filter' }, 0.25)
        .from('#hero .label, #hero .br > *', { y: 20, opacity: 0, stagger: 0.1, duration: 0.8, ease: 'power3.out' }, 0.6);
    },
  };
}

/* Count-up for the impact numbers (values come from /api/metrics). */
export function initCountUps(metrics, reduced) {
  const fmt = { pct: (v) => `${(v * 100).toFixed(1)}%`, auc: (v) => v.toFixed(3), us: (v) => `${v.toFixed(1)}<small> µs</small>` };
  const els = $$('[data-count]');
  const render = (el, v) => { el.innerHTML = fmt[el.dataset.fmt](v); };
  ScrollTrigger.create({
    trigger: '#impact', start: 'top 60%', once: true,
    onEnter: () => els.forEach((el, i) => {
      const target = metrics[el.dataset.count];
      if (typeof target !== 'number') { el.textContent = '—'; return; }
      if (reduced) { render(el, target); return; }
      const o = { v: 0 };
      gsap.to(o, { v: target, duration: 1.8, delay: 0.3 + i * 0.12, ease: 'power3.out', onUpdate: () => render(el, o.v) });
    }),
  });
}
