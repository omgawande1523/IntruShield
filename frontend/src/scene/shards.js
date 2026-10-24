import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import { DISSOLVE_DIR } from './brain.js';
import { rnd } from './util.js';

const GOLD = new THREE.Color('#ffd25a'), MINT = new THREE.Color('#9dffcf');
const DRIFT_COLORS = ['#ffd25a', '#ff9a3d', '#3de0a8', '#8a6bff', '#b7a5ff'].map((c) => new THREE.Color(c));

/* Faceted triangle: a flattened tetrahedron (flat-shaded so each facet catches light differently). */
function shardGeometry() {
  const g = new THREE.TetrahedronGeometry(1, 0);
  g.scale(1, 1, 0.22);
  g.computeVertexNormals();
  return g;
}
function emissiveMaterial(strength) {
  const m = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3, metalness: 0.15, flatShading: true });
  m.onBeforeCompile = (s) => {
    s.fragmentShader = s.fragmentShader.replace('#include <emissivemap_fragment>',
      `#include <emissivemap_fragment>\n#ifdef USE_INSTANCING_COLOR\n totalEmissiveRadiance += vColor * ${strength.toFixed(2)};\n#endif`);
  };
  m.customProgramCacheKey = () => `shard-${strength}`;
  return m;
}
const hash = (n) => { n = (n << 13) ^ n; return ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7fffffff) / 0x7fffffff; };

/* Two instanced systems:
   - burst: glowing shards breaking off the dissolving edge of the brain and drifting up-left (child of the brain mesh)
   - drift: a few big data shards floating in the galaxy / globe chapters (child of the world group) */
export function createShards(brainMesh, N, G) {
  const geo = shardGeometry();

  // --- burst: surface samples sorted by dissolve value, so the spawn band follows uDissolve
  const M = 9000, sampler = new MeshSurfaceSampler(brainMesh).build();
  const p = new THREE.Vector3(), tmp = [];
  for (let i = 0; i < M; i++) {
    sampler.sample(p);
    const bias = p.clone().normalize().dot(DISSOLVE_DIR) * 0.5 + 0.5;
    tmp.push({ x: p.x, y: p.y, z: p.z, v: (1 - bias) * 0.9 + Math.random() * 0.1 });
  }
  tmp.sort((a, b) => a.v - b.v);
  const sPos = new Float32Array(M * 3), sVal = new Float32Array(M);
  tmp.forEach((s, i) => { sPos[i * 3] = s.x; sPos[i * 3 + 1] = s.y; sPos[i * 3 + 2] = s.z; sVal[i] = s.v; });
  const lower = (x) => { let lo = 0, hi = M; while (lo < hi) { const mid = (lo + hi) >> 1; if (sVal[mid] < x) lo = mid + 1; else hi = mid; } return lo; };

  const burst = new THREE.InstancedMesh(geo, emissiveMaterial(1.45), N);
  burst.frustumCulled = false;
  const sp = new Float32Array(N), ph = new Float32Array(N), dist = new Float32Array(N), dir = new Float32Array(N * 3);
  const sc = new Float32Array(N * 3), rot = new Float32Array(N * 3), spin = new Float32Array(N * 3);
  const c = new THREE.Color();
  for (let i = 0; i < N; i++) {
    sp[i] = rnd(0.1, 0.22); ph[i] = Math.random() * 10; dist[i] = rnd(0.15, 0.85);
    const d = new THREE.Vector3(DISSOLVE_DIR.x * 1.2 + rnd(-0.5, 0.4), DISSOLVE_DIR.y * 0.55 + rnd(-0.4, 0.45), DISSOLVE_DIR.z + rnd(-0.5, 0.5)).normalize();
    dir.set([d.x, d.y, d.z], i * 3);
    const s = rnd(0.055, 0.17);
    sc.set([s * rnd(0.7, 1.5), s * rnd(0.6, 1.3), s], i * 3);
    rot.set([rnd(0, 6.28), rnd(0, 6.28), rnd(0, 6.28)], i * 3);
    spin.set([rnd(-2, 2), rnd(-2, 2), rnd(-1, 1)], i * 3);
    c.copy(GOLD).lerp(MINT, Math.pow(Math.random(), 1.8)).multiplyScalar(rnd(0.85, 1.15));
    burst.setColorAt(i, c);
  }
  burst.instanceColor.needsUpdate = true;

  // --- drift shards
  const drift = new THREE.InstancedMesh(geo, emissiveMaterial(0.9), G);
  drift.frustumCulled = false;
  const dPos = new Float32Array(G * 3), dRot = new Float32Array(G * 3), dSc = new Float32Array(G);
  for (let i = 0; i < G; i++) {
    const r = rnd(2.4, 6.5), a = rnd(0, 6.28), y = rnd(-2.2, 2.2);
    dPos.set([Math.cos(a) * r * 1.3, y, Math.sin(a) * r * 0.7 - 1.5], i * 3);
    dRot.set([rnd(0, 6.28), rnd(0, 6.28), rnd(0, 6.28)], i * 3);
    dSc[i] = rnd(0.08, 0.26);
    drift.setColorAt(i, DRIFT_COLORS[i % DRIFT_COLORS.length]);
  }
  drift.instanceColor.needsUpdate = true;

  const dummy = new THREE.Object3D();
  brainMesh.add(burst);

  return {
    burst, drift,
    update(cur, t) {
      burst.visible = cur.shardVis > 0.01 && cur.brainVis > 0.01;
      if (burst.visible) {
        const d = cur.brainDissolve;
        let lo = lower(d - 0.16), hi = lower(d + 0.02);
        if (hi - lo < 40) { lo = Math.max(0, lo - 20); hi = Math.min(M, hi + 20); }
        const span = Math.max(1, hi - lo);
        const vis = Math.min(1, cur.shardVis) * (1 + 0.45 * cur.hoverBoost);
        for (let i = 0; i < N; i++) {
          const life = t * sp[i] + ph[i], cyc = Math.floor(life), f = life - cyc;
          const k = lo + Math.floor(hash(i * 977 + cyc * 7919) * span);
          const i3 = i * 3, k3 = k * 3, travel = f * f * dist[i] + f * 0.15;
          dummy.position.set(sPos[k3] + dir[i3] * travel, sPos[k3 + 1] + dir[i3 + 1] * travel, sPos[k3 + 2] + dir[i3 + 2] * travel);
          dummy.rotation.set(rot[i3] + f * spin[i3] * 3, rot[i3 + 1] + f * spin[i3 + 1] * 3, rot[i3 + 2] + f * spin[i3 + 2] * 3);
          const life01 = Math.min(1, f * 10) * Math.pow(1 - f, 0.6); // pop in fast, linger, fade
          const s = life01 * vis;
          dummy.scale.set(sc[i3] * s + 1e-5, sc[i3 + 1] * s + 1e-5, sc[i3 + 2] * s + 1e-5);
          dummy.updateMatrix();
          burst.setMatrixAt(i, dummy.matrix);
        }
        burst.instanceMatrix.needsUpdate = true;
      }
      drift.visible = cur.driftVis > 0.01;
      if (drift.visible) {
        for (let i = 0; i < G; i++) {
          const i3 = i * 3;
          dummy.position.set(dPos[i3] + Math.sin(t * 0.2 + i) * 0.15, dPos[i3 + 1] + Math.cos(t * 0.17 + i) * 0.2, dPos[i3 + 2]);
          dummy.rotation.set(dRot[i3] + t * 0.3, dRot[i3 + 1] + t * 0.22, dRot[i3 + 2]);
          dummy.scale.setScalar(dSc[i] * cur.driftVis + 1e-5);
          dummy.updateMatrix();
          drift.setMatrixAt(i, dummy.matrix);
        }
        drift.instanceMatrix.needsUpdate = true;
      }
    },
    dispose() { geo.dispose(); burst.material.dispose(); drift.material.dispose(); },
  };
}
