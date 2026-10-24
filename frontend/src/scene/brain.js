import * as THREE from 'three';
import { SNOISE } from './util.js';

export const DISSOLVE_DIR = new THREE.Vector3(-1, 0.95, 0.3).normalize();

/* Glossy violet brain: clearcoat + sheen, fresnel lilac rim, screen-space CRT scanlines and a
   directional noise dissolve that eats the top-left lobe (the shards module spawns from that edge). */
export function createBrain(mesh) {
  const orig = mesh.material;
  const mat = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color('#5b3df5'), roughness: 0.42, metalness: 0.02,
    clearcoat: 0.75, clearcoatRoughness: 0.28,
    sheen: 0.55, sheenColor: new THREE.Color('#b7a5ff'), sheenRoughness: 0.45,
    normalMap: orig?.normalMap || null, normalScale: new THREE.Vector2(1.0, 1.0),
    envMapIntensity: 0.5, side: THREE.DoubleSide,
  });
  const u = {
    uDissolve: { value: 0.12 }, uTime: { value: 0 }, uBoost: { value: 0 },
    uDir: { value: DISSOLVE_DIR.clone() },
    uEdge: { value: new THREE.Color('#ffd25a') }, uRim: { value: new THREE.Color('#b7a5ff') },
  };
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vLPos;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvLPos = transformed;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        varying vec3 vLPos; uniform float uDissolve, uTime, uBoost; uniform vec3 uDir, uEdge, uRim;
        ${SNOISE}
        float dissolveValue(){ float bias = dot(normalize(vLPos), uDir) * 0.5 + 0.5; float n = snoise(vLPos * 2.2 + uTime * 0.05) * 0.5 + 0.5; return (1.0 - bias) * 0.9 + n * 0.1; }`)
      .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\nfloat dv = dissolveValue(); if (dv < uDissolve) discard;')
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        float edge = smoothstep(uDissolve + 0.035, uDissolve, dv);
        totalEmissiveRadiance += uEdge * edge * (0.55 + 0.9 * uBoost);
        float fr = pow(1.0 - saturate(dot(normalize(vViewPosition), normal)), 2.6);
        totalEmissiveRadiance += uRim * fr * (0.32 + 0.55 * uBoost);`)
      .replace('#include <dithering_fragment>', `#include <dithering_fragment>
        float scan = step(0.5, fract(gl_FragCoord.y * 0.5));
        gl_FragColor.rgb *= 1.0 - 0.12 * scan;`);
  };
  mat.customProgramCacheKey = () => 'brain-dissolve-scan';
  mesh.material = mat;

  const group = new THREE.Group();
  group.add(mesh);
  const inner = new THREE.PointLight(new THREE.Color('#7b5cff'), 2.0, 3.0, 1.5);
  group.add(inner);

  return {
    group, mesh, mat,
    update(cur, t, mouse) {
      u.uTime.value = t;
      u.uBoost.value = cur.hoverBoost;
      u.uDissolve.value = cur.brainDissolve + Math.sin(t * 0.5) * 0.012;
      const v = cur.brainVis > 0.01 && cur.brainDissolve < 1.05;
      group.visible = v;
      if (v) {
        mesh.rotation.y = -0.35 + Math.sin(t * 0.18) * 0.18 + mouse.x * 0.25;
        mesh.rotation.x = 0.08 + Math.sin(t * 0.23) * 0.04 - mouse.y * 0.12;
      }
    },
    dispose() { mat.dispose(); mesh.geometry.dispose(); },
  };
}
