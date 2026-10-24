/* Pointer interactions: glass spotlight, 3D tilt, magnetic buttons, and a "hover boost" the 3D scene reacts to.
   Everything writes either CSS variables or the individual `rotate` / `translate` properties, so it never
   fights GSAP (which owns `transform`). Disabled on touch devices and with prefers-reduced-motion. */
import { state } from './state.js';

export function initFx({ reduced }) {
  if (reduced || matchMedia('(pointer: coarse)').matches) return;

  // --- spotlight: one delegated, rAF-throttled listener
  let pending = null;
  addEventListener('pointermove', (e) => {
    pending = e;
    if (pending.__q) return;
    pending.__q = true;
    requestAnimationFrame(() => {
      const ev = pending; pending = null;
      const g = ev.target.closest?.('.glass');
      if (!g) return;
      const r = g.getBoundingClientRect();
      g.style.setProperty('--mx', `${ev.clientX - r.left}px`);
      g.style.setProperty('--my', `${ev.clientY - r.top}px`);
    });
  }, { passive: true });

  // --- 3D tilt
  document.querySelectorAll('.fx-tilt').forEach((el) => {
    el.addEventListener('pointermove', (e) => {
      const r = el.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width) * 2 - 1, ny = ((e.clientY - r.top) / r.height) * 2 - 1;
      const mag = Math.min(1, Math.hypot(nx, ny));
      el.classList.add('tilting');
      el.style.rotate = `${-ny} ${nx} 0 ${(mag * 7).toFixed(2)}deg`;
    });
    el.addEventListener('pointerleave', () => { el.classList.remove('tilting'); el.style.rotate = '0 0 1 0deg'; });
  });

  // --- magnetic buttons
  document.querySelectorAll('.pill, .btn, .outline-pill, .text-link').forEach((el) => {
    el.classList.add('fx-mag');
    el.addEventListener('pointermove', (e) => {
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
      el.classList.add('pulling');
      el.style.translate = `${(dx * 0.22).toFixed(1)}px ${(dy * 0.32).toFixed(1)}px`;
    });
    el.addEventListener('pointerleave', () => { el.classList.remove('pulling'); el.style.translate = '0 0'; });
  });

  // --- the scene glows harder while a call-to-action or a demo chip is hovered
  document.querySelectorAll('.pill, .btn-primary, .outline-pill, .chip, #chips').forEach((el) => {
    el.addEventListener('pointerenter', () => { state.hoverBoost = 1; });
    el.addEventListener('pointerleave', () => { state.hoverBoost = 0; });
  });
}
