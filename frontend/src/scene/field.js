import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { rnd } from './util.js';

const GOLD = new THREE.Color('#f6c445'), TEAL = new THREE.Color('#1fd1a5'), PURPLE = new THREE.Color('#8a5cff');

/* Fly-through field: chunky slabs (rounded cubes + spheres), dim dot-matrix grids and warp lines.
   All matrices are written once; per frame only the group transform moves (zero allocations). */
export function createField(tier) {
  const group = new THREE.Group();
  const nSlabs = tier.high ? 46 : 24, nGrids = tier.high ? 42 : 22, nLines = tier.high ? 70 : 40;
  const CELL = 0.34;

  // pick a position outside the central corridor so the vanishing point stays clear
  const place = (zMin, zMax) => {
    let x, y;
    do { x = rnd(-9.5, 9.5); y = rnd(-5, 5); } while (Math.abs(x) < 2.4 && Math.abs(y) < 1.6);
    return [x, y, rnd(zMin, zMax)];
  };

  const cubes = [], spheres = [];
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), v = new THREE.Vector3(), s = new THREE.Vector3(1, 1, 1);
  for (let k = 0; k < nSlabs; k++) {
    const r = Math.random(), base = r < 0.5 ? GOLD : r < 0.88 ? TEAL : PURPLE;
    const w = (rnd(3, 10)) | 0, h = (rnd(2, 6)) | 0, d = Math.random() < 0.4 ? 2 : 1;
    const [cx, cy, cz] = place(-100, -6);
    e.set(rnd(-0.15, 0.15), rnd(-0.35, 0.35), 0); q.setFromEuler(e);
    for (let z = 0; z < d; z++) for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (Math.random() < 0.06) continue;                     // a few gaps
      v.set((x - (w - 1) / 2) * CELL, (y - (h - 1) / 2) * CELL, -z * CELL).applyQuaternion(q).add(new THREE.Vector3(cx, cy, cz));
      const dark = Math.random() < 0.07;
      const ao = (z > 0 ? 0.72 : 1) * rnd(0.82, 1.08) * (y === 0 ? 0.85 : 1);
      const col = base.clone().multiplyScalar(dark ? 0.28 : ao);
      (Math.random() < 0.42 ? spheres : cubes).push({ p: v.clone(), q: q.clone(), c: col, s: rnd(0.9, 1.05) });
    }
  }
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.08 });
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', `#include <common>
      varying float vDepth;`).replace('#include <project_vertex>', `#include <project_vertex>
      vDepth = -mvPosition.z;`);
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
      varying float vDepth;`).replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
      float nearFade = smoothstep(2.2, 5.5, vDepth);
      float dither = fract(sin(dot(floor(gl_FragCoord.xy), vec2(12.9898, 78.233))) * 43758.5453);
      if (nearFade < dither) discard;`);
  };
  mat.customProgramCacheKey = () => 'field-nearfade';
  const build = (geo, list) => {
    const im = new THREE.InstancedMesh(geo, mat, Math.max(1, list.length));
    list.forEach((it, i) => { s.setScalar(it.s); m.compose(it.p, it.q, s); im.setMatrixAt(i, m); im.setColorAt(i, it.c); });
    im.count = list.length;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    im.frustumCulled = false;
    return im;
  };
  const cubeGeo = new RoundedBoxGeometry(0.31, 0.31, 0.31, 2, 0.07);
  const sphereGeo = new THREE.SphereGeometry(0.17, 14, 10);
  group.add(build(cubeGeo, cubes), build(sphereGeo, spheres));

  // dot-matrix grids of small grey spheres
  const dots = [];
  for (let k = 0; k < nGrids; k++) {
    const n = (rnd(6, 11)) | 0, gap = 0.17;
    const [cx, cy, cz] = place(-105, -4);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) dots.push(new THREE.Vector3(cx + (x - (n - 1) / 2) * gap, cy + (y - (n - 1) / 2) * gap, cz));
  }
  const dotMat = new THREE.MeshStandardMaterial({ color: '#5d5d6b', roughness: 0.45, metalness: 0.2 });
  const dotMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(0.03, 8, 6), dotMat, dots.length);
  dots.forEach((p, i) => { m.makeTranslation(p.x, p.y, p.z); dotMesh.setMatrixAt(i, m); });
  dotMesh.frustumCulled = false;
  group.add(dotMesh);

  // warp lines: segments parallel to the view axis converge on the vanishing point
  const lp = new Float32Array(nLines * 6), lc = new Float32Array(nLines * 6);
  for (let i = 0; i < nLines; i++) {
    const a = rnd(0, Math.PI * 2), rad = rnd(1.6, 9);
    const x = Math.cos(a) * rad * 1.3, y = Math.sin(a) * rad * 0.8, z1 = rnd(-110, -10), z2 = z1 + rnd(10, 30);
    lp.set([x, y, z1, x, y, z2], i * 6);
    const b = rnd(0.35, 0.9);
    lc.set([0, 0, 0, b, b, b], i * 6);                         // fade towards the vanishing point
  }
  const lgeo = new THREE.BufferGeometry();
  lgeo.setAttribute('position', new THREE.BufferAttribute(lp, 3));
  lgeo.setAttribute('color', new THREE.BufferAttribute(lc, 3));
  const lmat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending });
  group.add(new THREE.LineSegments(lgeo, lmat));
  group.visible = false;

  return {
    group,
    update(cur, mouse) {
      group.visible = cur.flyVis > 0.01;
      if (!group.visible) return;
      group.position.z = -30 + cur.fly * 140;
      group.rotation.z = cur.fly * 0.35;
      group.rotation.y = mouse.x * 0.05;
      lmat.opacity = 0.55 * cur.flyVis;
    },
    dispose() { cubeGeo.dispose(); sphereGeo.dispose(); mat.dispose(); dotMat.dispose(); dotMesh.geometry.dispose(); lgeo.dispose(); lmat.dispose(); },
  };
}
