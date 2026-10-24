/* Scene orchestrator: renderer, post, loading, damped state -> objects, FPS watchdog. */
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { state, composeState } from '../state.js';
import { bakeAndNormalize } from './util.js';
import { createBrain } from './brain.js';
import { createShards } from './shards.js';
import { createField } from './field.js';
import { createVoxels } from './voxels.js';
import { createCloud } from './cloud.js';
import { createGlobe } from './globe.js';
import { createShield } from './shield.js';
import { createDashes } from './dashes.js';

const BASE = import.meta.env.BASE_URL || './';
const BG_BLACK = new THREE.Color('#030307'), BG_GREEN = new THREE.Color('#06140f');

export async function createScene(canvas, { tier, onProgress = () => {}, reduced = false }) {
  // ---------------- renderer
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance', alpha: false });
  renderer.setPixelRatio(tier.dpr);
  renderer.setSize(innerWidth, innerHeight, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const bg = BG_GREEN.clone();
  scene.background = bg;
  scene.fog = new THREE.Fog(bg, 16, 72);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.4;
  pmrem.dispose();

  const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 0.1, 140);
  camera.position.set(0, 0, 7);

  const key = new THREE.DirectionalLight(0xffe6c8, 2.3); key.position.set(-3, 4, 4); scene.add(key);
  const rim = new THREE.DirectionalLight(0x13d6c4, 1.6); rim.position.set(2, 1, -4); scene.add(rim);
  const fill = new THREE.DirectionalLight(0x8a6bff, 0.7); fill.position.set(3, -2, 2); scene.add(fill);
  scene.add(new THREE.HemisphereLight(0xfff1dc, 0x0d0b18, 0.25)); // soft "AO" tint for the voxel slabs

  const world = new THREE.Group();
  scene.add(world);

  // ---------------- load models
  const manager = new THREE.LoadingManager();
  manager.onProgress = (_, loaded, total) => onProgress((loaded / total) * 0.65);
  const loader = new GLTFLoader(manager);
  loader.setMeshoptDecoder(MeshoptDecoder);
  const load = (f) => new Promise((res, rej) => loader.load(`${BASE}models/${f}`, res, undefined, rej));
  const [brainG, earthG] = await Promise.all([load('brain.glb'), load('earth.glb')]);
  onProgress(0.7);

  const brainMesh = bakeAndNormalize(brainG.scene, 1.55);
  const earthMesh = bakeAndNormalize(earthG.scene, 1.5);
  if (earthMesh.material?.map) earthMesh.material.map.colorSpace = THREE.SRGBColorSpace;

  // ---------------- build (everything precomputed here; nothing allocated in the loop)
  const brain = createBrain(brainMesh); world.add(brain.group); onProgress(0.76);
  const shards = createShards(brainMesh, tier.shards, tier.high ? 60 : 30); world.add(shards.drift); onProgress(0.82);
  const field = createField(tier); scene.add(field.group); onProgress(0.88);
  const voxels = createVoxels(brainMesh, tier.voxels); world.add(voxels.mesh); onProgress(0.92);
  const cloud = createCloud(brainMesh, tier.cloud, tier.dpr); world.add(cloud.points); onProgress(0.95);
  const globe = createGlobe(earthMesh, 1.5); world.add(globe.group); onProgress(0.98);
  const shield = createShield(tier.dpr); world.add(shield.group);
  const dashes = createDashes(tier.dashes, tier.dpr); scene.add(dashes.points);
  renderer.compile(scene, camera);
  onProgress(1);

  // ---------------- post
  let composer = null, bloomOn = tier.bloom, bloomScale = 1;
  try {
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.6, 0.6, 0.72);
    const bloomSetSize = bloom.setSize.bind(bloom);   // lets the quality ladder render bloom at reduced resolution
    bloom.setSize = (w, h) => bloomSetSize(Math.max(64, Math.round(w * bloomScale)), Math.max(64, Math.round(h * bloomScale)));
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
  } catch (e) { composer = null; bloomOn = false; }
  // Quality ladder (instead of switching the glow off): half-res bloom -> pixel ratio 1 -> bloom off as a last resort
  let quality = 0;
  const degrade = (f) => {
    if (!composer || !bloomOn) return false;
    if (quality === 1) document.documentElement.classList.add('lite-glass');   // drop backdrop blur before touching the pixel ratio
    if (quality === 0) { bloomScale = 0.5; composer.setSize(innerWidth, innerHeight); }
    else if (quality === 1 && renderer.getPixelRatio() > 1) { renderer.setPixelRatio(1); composer.setPixelRatio(1); composer.setSize(innerWidth, innerHeight); }
    else if (quality <= 2 && f < 28) { bloomOn = false; }
    else if (quality === 1) { /* pixel ratio already 1: nothing to gain */ }
    else return false;
    quality++;
    console.info(`[scene] quality step ${quality} at ${f.toFixed(0)} fps (bloomScale=${bloomScale}, dpr=${renderer.getPixelRatio()}, bloom=${bloomOn})`);
    return true;
  };

  // ---------------- layout
  function layout() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    composer?.setSize(w, h);
    state.narrow = w / h < 1.15 ? 1 : 0;
  }
  layout();
  let rt = 0;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(layout, 150); });

  // ---------------- loop
  composeState();
  const cur = { ...state };
  cur.camZ = 10.5; cur.objScale = state.objScale * 0.8;          // intro zoom after the loader
  const keys = Object.keys(state).filter((k) => k !== 'chapter' && k !== 'narrow');
  const mouse = new THREE.Vector2(), mouseT = new THREE.Vector2();
  addEventListener('pointermove', (e) => mouseT.set((e.clientX / innerWidth) * 2 - 1, -((e.clientY / innerHeight) * 2 - 1)), { passive: true });
  const clock = new THREE.Clock();
  const fps = { frames: 0, t0: performance.now(), chapter: 1, log: {}, start0: performance.now() };
  let running = true, raf = 0;

  const shotMode = new URLSearchParams(location.search).has('shot');
  function render(dt, t, draw = true) {
    composeState();
    for (const k of keys) cur[k] = THREE.MathUtils.damp(cur[k], state[k], k === 'camZ' ? 2.2 : k === 'hoverBoost' ? 4 : 6, dt);
    world.position.set(cur.objX, cur.objY, 0);
    world.scale.setScalar(cur.objScale);
    mouse.lerp(mouseT, 0.05);
    camera.position.set(mouse.x * 0.3, mouse.y * 0.2, cur.camZ);
    camera.lookAt(0, 0, 0);
    bg.copy(BG_BLACK).lerp(BG_GREEN, cur.bgGreen);
    brain.update(cur, t, mouse); shards.update(cur, t); field.update(cur, mouse); voxels.update(cur, t);
    cloud.update(cur, t); globe.update(cur, dt, t); shield.update(cur, dt, t); dashes.update(cur, t);
    if (!draw) return;
    if (bloomOn && composer) composer.render(); else renderer.render(scene, camera);
  }
  function frame() {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    const dt = Math.min(clock.getDelta(), 0.05);
    render(dt, clock.elapsedTime);
    fps.frames++;
    const now = performance.now();
    if (state.chapter !== fps.chapter || now - fps.t0 > 2000) {
      const f = (fps.frames * 1000) / (now - fps.t0);
      const k = `chapter ${fps.chapter}`;
      fps.log[k] = fps.log[k] ? (fps.log[k] + f) / 2 : f;
      if (state.chapter !== fps.chapter) console.info(`[fps] ${k}: ${fps.log[k].toFixed(0)}`);
      if (now - fps.start0 > 4000 && f < 45 && degrade(f)) fps.start0 = now - 2000;   // re-measure after each step
      window.__quality = { step: quality, bloom: bloomOn, bloomScale, dpr: renderer.getPixelRatio() };
      fps.frames = 0; fps.t0 = now; fps.chapter = state.chapter;
    }
  }
  if (shotMode) {
    // deterministic capture for scripts/shoot.mjs: step the damping at 60 Hz, draw only the last frame
    let simT = 2;
    window.__settle = (frames = 150) => { for (let i = 0; i < frames; i++) { simT += 1 / 60; render(1 / 60, simT, i === frames - 1); } return true; };
    window.__settle(240);
  } else if (reduced) { cur.camZ = 7; cur.objScale = state.objScale; render(0.016, 0.5); }
  else frame();
  document.addEventListener('visibilitychange', () => {
    if (reduced || shotMode) return;
    if (document.hidden) { running = false; cancelAnimationFrame(raf); } else if (!running) { running = true; clock.getDelta(); frame(); }
  });
  window.__fps = fps.log;

  return {
    react: (kind) => shield.react(kind),
    dispose() {
      running = false; cancelAnimationFrame(raf);
      [brain, shards, field, voxels, cloud, globe, shield, dashes].forEach((o) => o.dispose());
      composer?.dispose(); renderer.dispose();
    },
  };
}
