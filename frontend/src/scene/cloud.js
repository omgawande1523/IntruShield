import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import { gauss } from './util.js';

/* Dense speckled point-cloud brain: tiny rotated triangles in gold / orange / violet / teal / white,
   additive with bloom. uMorph explodes it into a wide spiral galaxy. */
const VERT = /* glsl */ `
uniform float uTime, uMorph, uSize, uPixelRatio;
attribute vec3 aNeb, aColor;
attribute float aRand;
varying vec3 vC; varying float vA, vRot;
void main() {
  float d = aRand * 0.45;
  float t = smoothstep(d, d + 0.55, uMorph);
  vec3 p = mix(position, aNeb, t);
  float bulge = sin(t * 3.14159) * (0.4 + aRand * 1.2);
  p += normalize(p + 0.001) * bulge;
  p += 0.025 * vec3(sin(uTime * 0.8 + aRand * 20.0), cos(uTime * 0.6 + aRand * 13.0), sin(uTime * 0.7 + aRand * 7.0)) * (1.0 + t * 4.0);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * uPixelRatio * (0.7 + aRand * 0.8) * (30.0 / -mv.z);
  vC = aColor;
  vRot = aRand * 6.2831 + uTime * (aRand - 0.5);
  vA = (0.5 + 0.5 * sin(uTime * 2.0 + aRand * 40.0)) * (1.0 - 0.35 * sin(t * 3.14159)) * 0.42;
}`;
const FRAG = /* glsl */ `
uniform float uOpacity;
varying vec3 vC; varying float vA, vRot;
void main() {
  vec2 q = gl_PointCoord - 0.5;
  float c = cos(vRot), s = sin(vRot);
  q = vec2(c * q.x - s * q.y, s * q.x + c * q.y);
  // equilateral triangle SDF (Inigo Quilez), soft edge
  const float k = 1.7320508;
  q.y += 0.1; q *= 2.6;
  q.x = abs(q.x) - 1.0; q.y = q.y + 1.0 / k;
  if (q.x + k * q.y > 0.0) q = vec2(q.x - k * q.y, -k * q.x - q.y) / 2.0;
  q.x -= clamp(q.x, -2.0, 0.0);
  float dist = -length(q) * sign(q.y);
  float a = smoothstep(0.12, -0.05, dist);
  if (a < 0.02) discard;
  gl_FragColor = vec4(vC, a * vA * uOpacity);
}`;

export function createCloud(brainMesh, N, dpr) {
  const sampler = new MeshSurfaceSampler(brainMesh).build();
  const pal = ['#ffb43d', '#ff8a3d', '#ffd25a', '#8a6bff', '#b7a5ff', '#1fd1a5', '#5aa8ff', '#fff2dd'].map((c) => new THREE.Color(c));
  const w = [0.24, 0.16, 0.14, 0.14, 0.1, 0.09, 0.06, 0.07];
  const pick = () => { let r = Math.random(); for (let i = 0; i < w.length; i++) { r -= w[i]; if (r <= 0) return pal[i]; } return pal[0]; };
  const pos = new Float32Array(N * 3), neb = new Float32Array(N * 3), col = new Float32Array(N * 3), rand = new Float32Array(N);
  const p = new THREE.Vector3();
  for (let i = 0; i < N; i++) {
    sampler.sample(p);
    pos.set([p.x, p.y, p.z], i * 3);
    const c = pick(); col.set([c.r, c.g, c.b], i * 3);
    rand[i] = Math.random();
    // spiral galaxy: 3 arms, thin disc tilted toward the camera
    const arm = (i % 3) * (Math.PI * 2 / 3), r = 0.5 + Math.pow(Math.random(), 0.8) * 5.2;
    const a = arm + r * 0.75 + gauss() * 0.22;
    const y = gauss() * (0.25 + 0.05 * r);
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    neb.set([x * 0.95, y + z * 0.28, z * 0.55 - 0.8], i * 3);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aNeb', new THREE.BufferAttribute(neb, 3));
  geo.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
  geo.setAttribute('aRand', new THREE.BufferAttribute(rand, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 20);
  const uniforms = { uTime: { value: 0 }, uMorph: { value: 0 }, uSize: { value: 1.1 }, uPixelRatio: { value: dpr }, uOpacity: { value: 0 } };
  const mat = new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  return {
    points,
    update(cur, t) {
      points.visible = cur.cloudVis > 0.01;
      uniforms.uTime.value = t; uniforms.uMorph.value = cur.cloudMorph; uniforms.uOpacity.value = Math.min(1, cur.cloudVis * 1.2);
      points.rotation.y = -0.5 + t * 0.05;
    },
    dispose() { geo.dispose(); mat.dispose(); },
  };
}
