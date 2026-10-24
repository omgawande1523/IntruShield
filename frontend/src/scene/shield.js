import * as THREE from 'three';
import { C, softCircleTexture, rnd } from './util.js';

/* Procedural extruded shield with clearcoat, teal edge emissive, orbiting particles and demo reactions. */
export function createShield(dpr) {
  const s = new THREE.Shape();
  s.moveTo(-1.35, 1.4); s.lineTo(1.35, 1.4);
  s.bezierCurveTo(1.35, 0.15, 1.1, -1.05, 0, -1.85);
  s.bezierCurveTo(-1.1, -1.05, -1.35, 0.15, -1.35, 1.4);
  const geo = new THREE.ExtrudeGeometry(s, { depth: 0.32, bevelEnabled: true, bevelThickness: 0.1, bevelSize: 0.09, bevelSegments: 4, curveSegments: 32 });
  geo.center();
  const mat = new THREE.MeshPhysicalMaterial({ color: '#0c1a26', metalness: 0.6, roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.1, emissive: C.teal, emissiveIntensity: 0.08, envMapIntensity: 1.2 });
  const u = { uEdge: { value: C.teal.clone() }, uPulse: { value: 0 } };
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, u);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform vec3 uEdge; uniform float uPulse;')
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        float fr = pow(1.0 - saturate(dot(normalize(vViewPosition), normal)), 2.5);
        totalEmissiveRadiance += uEdge * (fr * 0.9 + uPulse * 0.22);`);
  };
  mat.customProgramCacheKey = () => 'shield-edge';
  const mesh = new THREE.Mesh(geo, mat);
  const group = new THREE.Group();
  group.add(mesh);

  // orbiting particles
  const ON = 320, op = new Float32Array(ON * 3), orb = [];
  for (let i = 0; i < ON; i++) orb.push({ r: rnd(1.9, 2.6), a: rnd(0, 6.28), tilt: rnd(-0.6, 0.6), sp: rnd(0.2, 0.6) });
  const ogeo = new THREE.BufferGeometry(); ogeo.setAttribute('position', new THREE.BufferAttribute(op, 3));
  const tex = softCircleTexture(32);
  const omat = new THREE.PointsMaterial({ size: 0.07, map: tex, color: C.teal, transparent: true, opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending });
  const orbit = new THREE.Points(ogeo, omat); orbit.frustumCulled = false; group.add(orbit);

  // burst particles for attacks
  const BN = 220, bp = new Float32Array(BN * 3), bv = new Float32Array(BN * 3);
  const bgeo = new THREE.BufferGeometry(); bgeo.setAttribute('position', new THREE.BufferAttribute(bp, 3));
  const bmat = new THREE.PointsMaterial({ size: 0.1, map: tex, color: C.red, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending });
  const burst = new THREE.Points(bgeo, bmat); burst.frustumCulled = false; burst.visible = false; group.add(burst);

  const S = { pulse: 0, shake: 0, burstLife: 0, red: 0 };
  const edgeTeal = C.teal.clone(), edgeRed = C.red.clone();

  return {
    group,
    react(kind) {
      S.pulse = 1;
      if (kind === 'attack') {
        S.shake = 1; S.red = 1; S.burstLife = 1; burst.visible = true;
        for (let i = 0; i < BN; i++) { const th = rnd(0, 6.28), ph = rnd(-1, 1); const v = rnd(1.5, 3.5); bp.set([0, 0, 0.3], i * 3); bv.set([Math.cos(th) * Math.sqrt(1 - ph * ph) * v, Math.sin(th) * Math.sqrt(1 - ph * ph) * v, ph * v], i * 3); }
      }
    },
    update(cur, dt, t) {
      group.visible = cur.shieldVis > 0.01;
      if (!group.visible) return;
      S.pulse = Math.max(0, S.pulse - dt * 1.4); S.shake = Math.max(0, S.shake - dt * 2.5); S.red = Math.max(0, S.red - dt * 0.8);
      const sc = 0.68 * (0.5 + 0.5 * cur.shieldVis) * (1 + S.pulse * 0.05);
      group.scale.setScalar(sc);
      mesh.rotation.y = Math.sin(t * 0.5) * 0.35; mesh.rotation.x = Math.sin(t * 0.33) * 0.12;
      mesh.position.set(Math.sin(t * 50) * 0.06 * S.shake, Math.cos(t * 47) * 0.05 * S.shake, 0);
      u.uPulse.value = S.pulse;
      u.uEdge.value.copy(edgeTeal).lerp(edgeRed, S.red);
      mat.emissive.copy(edgeTeal).lerp(edgeRed, S.red);
      omat.color.copy(edgeTeal).lerp(edgeRed, S.red);
      for (let i = 0; i < ON; i++) { const o = orb[i]; const a = o.a + t * o.sp; const r = o.r * (1 + S.pulse * 0.25); op[i * 3] = Math.cos(a) * r; op[i * 3 + 1] = Math.sin(a) * r * Math.cos(o.tilt); op[i * 3 + 2] = Math.sin(a) * r * Math.sin(o.tilt); }
      ogeo.attributes.position.needsUpdate = true;
      omat.opacity = 0.75 * cur.shieldVis;
      if (burst.visible) {
        S.burstLife -= dt * 0.8;
        if (S.burstLife <= 0) burst.visible = false;
        else { for (let i = 0; i < BN * 3; i++) bp[i] += bv[i] * dt; bgeo.attributes.position.needsUpdate = true; bmat.opacity = S.burstLife; }
      }
    },
    dispose() { geo.dispose(); mat.dispose(); ogeo.dispose(); omat.dispose(); bgeo.dispose(); bmat.dispose(); },
  };
}
