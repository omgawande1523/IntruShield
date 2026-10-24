import * as THREE from 'three';
import { rnd } from './util.js';

/* Background particles: short glowing horizontal capsules (6-24px x 3px) at several depths.
   Far ones get a depth-of-field blur (wider soft edge, dimmer). They drift slowly sideways. */
const VERT = /* glsl */ `
uniform float uTime, uPixelRatio, uDrift;
attribute float aLen, aDepth, aSpeed; attribute vec3 aColor;
varying vec3 vC; varying float vSize, vBlur, vA;
void main() {
  vec3 p = position;
  p.x = mod(p.x + uTime * aSpeed + uDrift * (0.6 + aDepth) + 13.0, 26.0) - 13.0;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  vBlur = aDepth * 5.0 * uPixelRatio;                       // px of soft edge
  vSize = (aLen + 4.0 + aDepth * 10.0) * uPixelRatio;
  gl_PointSize = vSize;
  vC = aColor;
  vA = (1.0 - aDepth * 0.7) * (0.7 + 0.3 * sin(uTime * 1.3 + p.y * 7.0)) * 0.7;
}`;
const FRAG = /* glsl */ `
uniform float uOpacity, uPixelRatio;
varying vec3 vC; varying float vSize, vBlur, vA;
void main() {
  vec2 q = (gl_PointCoord - 0.5) * vSize;                    // pixels from sprite centre
  float h = 1.5 * uPixelRatio;                               // capsule half-height (3px tall)
  float halfLen = max(0.0, vSize * 0.5 - h - vBlur - 1.0);
  float d = length(vec2(max(abs(q.x) - halfLen, 0.0), q.y)) - h;
  float a = 1.0 - smoothstep(-0.6 - vBlur * 0.3, 0.6 + vBlur, d);
  if (a < 0.01) discard;
  gl_FragColor = vec4(vC * 1.6, a * vA * uOpacity);
}`;

export function createDashes(N, dpr) {
  const pal = ['#8a6bff', '#8a6bff', '#3de0a8', '#ffb347', '#8a6bff', '#3de0a8'].map((c) => new THREE.Color(c));
  const pos = new Float32Array(N * 3), col = new Float32Array(N * 3), len = new Float32Array(N), dep = new Float32Array(N), spd = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const depth = Math.pow(Math.random(), 0.8);               // 0 near (sharp) .. 1 far (blurred)
    const z = -1 - depth * 16;
    const spread = 4.5 + depth * 9;
    pos.set([rnd(-13, 13), rnd(-spread * 0.55, spread * 0.55), z], i * 3);
    const c = pal[(Math.random() * pal.length) | 0];
    col.set([c.r, c.g, c.b], i * 3);
    len[i] = rnd(6, 24); dep[i] = depth; spd[i] = rnd(0.04, 0.16) * (Math.random() < 0.5 ? -1 : 1);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
  geo.setAttribute('aLen', new THREE.BufferAttribute(len, 1));
  geo.setAttribute('aDepth', new THREE.BufferAttribute(dep, 1));
  geo.setAttribute('aSpeed', new THREE.BufferAttribute(spd, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 40);
  const uniforms = { uTime: { value: 0 }, uPixelRatio: { value: dpr }, uDrift: { value: 0 }, uOpacity: { value: 1 } };
  const mat = new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  points.renderOrder = -1;
  return {
    points,
    update(cur, t) { uniforms.uTime.value = t; uniforms.uDrift.value = cur.fly * 6; uniforms.uOpacity.value = 0.35 + 0.65 * Math.max(cur.bgGreen, cur.flyVis * 0.6); },
    dispose() { geo.dispose(); mat.dispose(); },
  };
}
