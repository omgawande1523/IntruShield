import * as THREE from 'three';
import { C, softCircleTexture, rnd } from './util.js';

const VERT = /* glsl */ `
varying vec2 vUv; varying vec3 vN, vV;
void main() {
  vUv = uv;
  vN = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vV = -mv.xyz;
  gl_Position = projectionMatrix * mv;
}`;
const FRAG = /* glsl */ `
uniform sampler2D uDay; uniform vec3 uOcean, uTeal, uGold, uPurple; uniform float uTime;
varying vec2 vUv; varying vec3 vN, vV;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
  vec3 day = texture2D(uDay, vUv).rgb;
  float land = step(day.b, max(day.r, day.g) * 1.04);
  vec2 g = vUv * vec2(260.0, 130.0);
  vec2 cell = floor(g); vec2 f = fract(g) - 0.5;
  float d = smoothstep(0.30, 0.10, length(f));
  float h = hash(cell);
  float city = step(0.978, h);
  vec3 dotCol = mix(uTeal * (0.55 + 0.45 * h), uGold * 1.6, city);
  dotCol *= 1.0 + city * 0.6 * sin(uTime * 2.0 + h * 40.0);
  vec3 col = uOcean + land * 0.03 * uTeal + land * d * dotCol * 1.3;
  float fr = pow(1.0 - clamp(dot(normalize(vV), normalize(vN)), 0.0, 1.0), 2.6);
  col += mix(uTeal, uPurple, fr) * fr * 0.45;
  gl_FragColor = vec4(col, 1.0);
}`;
const ATMO_FRAG = /* glsl */ `
uniform vec3 uTeal, uPurple; varying vec3 vN, vV; varying vec2 vUv;
void main() {
  float fr = pow(clamp(dot(normalize(vV), normalize(vN)), 0.0, 1.0), 3.0);
  gl_FragColor = vec4(mix(uPurple, uTeal, fr) , fr * 0.55);
}`;

function landMaskFromTexture(tex) {
  try {
    const img = tex.image; if (!img) return null;
    const c = document.createElement('canvas'); c.width = 256; c.height = 128;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0, 256, 128);
    const d = g.getImageData(0, 0, 256, 128).data;
    const mask = new Uint8Array(256 * 128);
    for (let i = 0; i < mask.length; i++) { const r = d[i * 4], gg = d[i * 4 + 1], b = d[i * 4 + 2]; mask[i] = b <= Math.max(r, gg) * 1.04 && (r + gg + b) > 60 ? 1 : 0; }
    return { mask, flipY: tex.flipY };
  } catch { return null; }
}

/* Dark globe from earth.glb geometry: dotted glowing land, fresnel atmosphere, traffic arcs. */
export function createGlobe(earthMesh, R) {
  const geo = earthMesh.geometry;
  const dayTex = earthMesh.material?.map || null;
  const uniforms = { uDay: { value: dayTex }, uOcean: { value: new THREE.Color('#04060c') }, uTeal: { value: C.teal }, uGold: { value: C.gold }, uPurple: { value: C.purple }, uTime: { value: 0 } };
  const mat = new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG });
  const globe = new THREE.Mesh(geo, mat);
  const atmo = new THREE.Mesh(new THREE.SphereGeometry(R * 1.07, 48, 32), new THREE.ShaderMaterial({
    uniforms: { uTeal: { value: C.teal }, uPurple: { value: C.purple } }, vertexShader: VERT, fragmentShader: ATMO_FRAG,
    transparent: true, side: THREE.BackSide, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  const group = new THREE.Group();
  group.add(globe, atmo);

  // cities on land (sampled from the day texture), fallback random
  const lm = landMaskFromTexture(dayTex);
  const cities = [];
  let tries = 0;
  while (cities.length < 36 && tries++ < 4000) {
    const lon = rnd(-Math.PI, Math.PI), lat = rnd(-1.1, 1.3);
    if (lm) {
      const u = (lon + Math.PI) / (2 * Math.PI), vv = 0.5 - lat / Math.PI;
      const px = (u * 255) | 0, py = ((lm.flipY ? 1 - vv : vv) * 127) | 0;
      if (!lm.mask[py * 256 + px]) continue;
    }
    cities.push(new THREE.Vector3(Math.cos(lat) * Math.cos(lon), Math.sin(lat), -Math.cos(lat) * Math.sin(lon)).multiplyScalar(R * 1.01));
  }
  const arcs = [], flashes = [];
  const flashTex = softCircleTexture(32);
  for (let i = 0; i < 16; i++) {
    const a = cities[(Math.random() * cities.length) | 0], b = cities[(Math.random() * cities.length) | 0];
    if (!a || !b || a === b) continue;
    const red = i % 4 === 0;
    const mid = a.clone().add(b).normalize().multiplyScalar(R * (1.18 + a.distanceTo(b) * 0.22));
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    const lg = new THREE.BufferGeometry().setFromPoints(curve.getPoints(40));
    const lmat = new THREE.LineDashedMaterial({ color: red ? C.red : i % 3 === 0 ? C.gold : C.teal, dashSize: 0.3, gapSize: 0.5, transparent: true, opacity: 1.0, depthWrite: false });
    const line = new THREE.Line(lg, lmat);
    line.computeLineDistances();
    line.userData.speed = rnd(0.5, 1.2);
    group.add(line); arcs.push(line);
    if (red) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: flashTex, color: C.red, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
      sp.position.copy(b).multiplyScalar(1.03); sp.userData.phase = rnd(0, 6.28); sp.scale.setScalar(0.3);
      group.add(sp); flashes.push(sp);
    }
  }

  return {
    group,
    update(cur, dt, t) {
      group.visible = cur.globeVis > 0.01;
      if (!group.visible) return;
      const s = 0.4 + 0.6 * cur.globeVis;
      group.scale.setScalar(s);
      group.rotation.y += dt * 0.07 * cur.globeSpin;
      group.rotation.x = 0.2;
      uniforms.uTime.value = t;
      for (const l of arcs) { l.material.dashOffset -= dt * l.userData.speed; l.material.opacity = cur.globeVis; }
      for (const f of flashes) { const k = Math.max(0, Math.sin(t * 1.6 + f.userData.phase)); f.material.opacity = Math.pow(k, 6) * cur.globeVis; f.scale.setScalar(0.12 + Math.pow(k, 6) * 0.22); }
    },
    dispose() { mat.dispose(); atmo.geometry.dispose(); atmo.material.dispose(); for (const l of arcs) { l.geometry.dispose(); l.material.dispose(); } },
  };
}
