// Screenshot review loop: node scripts/shoot.mjs [baseUrl]
// Requires the app running (python main.py). Saves design/screens/desktop-XX.png (1440x900) and mobile-XX.png (390x844).
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8000';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../design/screens');
mkdirSync(OUT, { recursive: true });

// [label, section id, fraction through the pinned range (or px offset for unpinned), optional action]
const SHOTS = [
  ['hero', 'hero', 0],
  ['problem-in', 'problem', 0.3],
  ['problem-flight', 'problem', 0.75],
  ['intro-cluster', 'intro', 0.3],
  ['intro-eject', 'intro', 0.9],
  ['purpose', 'purpose', 0.7],
  ['how-galaxy', 'how', 0.32],
  ['how-globe', 'how', 0.95],
  ['demo', 'demo', 0],
  ['demo-attack', 'demo', 0, 'attack'],
  ['impact', 'impact', 0.85],
  ['footer', 'footer', 1],
];

async function run(name, viewport, mobile) {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); if (m.type() === 'info') console.log(`  [${name}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(`${BASE}/?shot`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => !document.getElementById('loader'), null, { timeout: 120000 });
  await page.waitForTimeout(1500);
  let i = 0;
  for (const [label, id, frac, action] of SHOTS) {
    if (mobile && (label === 'problem-in' || label === 'intro-cluster' || label === 'demo-attack')) continue;
    const y = await page.evaluate(([id, frac]) => {
      const el = document.getElementById(id);
      if (id === 'footer') return document.documentElement.scrollHeight;
      const wrap = el.parentElement.classList.contains('pin-spacer') ? el.parentElement : el;
      const top = wrap.getBoundingClientRect().top + scrollY;
      const pin = wrap.offsetHeight - el.offsetHeight;
      return Math.round(top + (pin > 0 ? frac * pin : 0));
    }, [id, frac]);
    await page.evaluate((y) => window.scrollTo(0, y), y);
    await page.waitForTimeout(1600);                        // GSAP scrub (1s) + text reveals finish
    if (action === 'attack') {
      await page.click('.chip[data-id="dos"]');
      await page.waitForTimeout(900);
      await page.evaluate(() => window.__settle?.(20));      // capture the red flash mid-pulse
    } else {
      await page.evaluate(() => window.__settle?.(150));
    }
    const file = path.join(OUT, `${name}-${String(++i).padStart(2, '0')}-${label}.png`);
    await page.screenshot({ path: file });
    console.log(`  saved ${path.basename(file)} (y=${y})`);
  }
  const fps = await page.evaluate(() => window.__fps || {});
  console.log(`  [${name}] fps log`, JSON.stringify(fps));
  console.log(`  [${name}] console errors: ${errors.length}`);
  errors.forEach((e) => console.log(`    ERROR ${e}`));
  await browser.close();
  return errors.length;
}

const only = process.env.SHOT_ONLY;
let errs = 0;
if (!only || only === 'desktop') errs += await run('desktop', { width: 1440, height: 900 }, false);
if (!only || only === 'mobile') errs += await run('mobile', { width: 390, height: 844 }, true);
process.exit(errs ? 1 : 0);
