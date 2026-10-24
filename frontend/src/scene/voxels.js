import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { rnd, smooth } from './util.js';

const GOLD = new THREE.Color('#f0b52e'), TEAL = new THREE.Color('#1fd1a5'), PURPLE = new THREE.Color('#8a5cff'), RED = new THREE.Color('#ff4d5e');

/* "Introducing" cluster: a dense spinning sphere of gold voxels; red ones (attacks) get ejected.
   voxMode 2 = cluster, 3 = voxels gather onto the brain surface (hand-off to the point cloud). */
export function createVoxels(brainMesh, N) {
  const geo = new RoundedBoxGeometry(0.12, 0.12, 0.12, 2, 0.03);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.1 });
  mat.onBeforeCompile = (s) => {
    s.fragmentShader = s.fragmentShader.replace('#include <emissivemap_fragment>',
      '#include <emissivemap_fragment>\n#ifdef USE_INSTANCING_COLOR\n totalEmissiveRadiance += vColor * 0.05;\n#endif');
  };
  const mesh = new THREE.InstancedMesh(geo, mat, N);
  mesh.frustumCulled = false;

  const clusSlots = [];
  const sp = 0.15, R = 1.3;
  for (let x = -R; x <= R; x += sp) for (let y = -R; y <= R; y += sp) for (let z = -R; z <= R; z += sp)
    if (x * x + y * y + z * z <= R * R) clusSlots.push([x, y, z]);
  for (let i = clusSlots.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [clusSlots[i], clusSlots[j]] = [clusSlots[j], clusSlots[i]]; }

  const sampler = new MeshSurfaceSampler(brainMesh).build();
  const clus = new Float32Array(N * 3), gath = new Float32Array(N * 3), rand = new Float32Array(N), red = new Uint8Array(N);
  const p = new THREE.Vector3(), col = new THREE.Color();
  for (let i = 0; i < N; i++) {
    const cs = clusSlots[i % clusSlots.length];
    clus.set([cs[0], cs[1], cs[2]], i * 3);
    sampler.sample(p); gath.set([p.x, p.y, p.z], i * 3);
    rand[i] = Math.random();
    const r = Math.random();
    red[i] = r > 0.95 ? 1 : 0;
    col.copy(red[i] ? RED : r < 0.72 ? GOLD : r < 0.9 ? TEAL : PURPLE).multiplyScalar(rnd(0.7, 1.0));
    mesh.setColorAt(i, col);
  }
  mesh.instanceColor.needsUpdate = true;

  const dummy = new THREE.Object3D();
  return {
    mesh,
    update(cur, t) {
      mesh.visible = cur.voxVis > 0.01;
      if (!mesh.visible) return;
      const f = smooth(Math.min(1, Math.max(0, cur.voxMode - 2)));
      const a = t * 0.35, ca = Math.cos(a), sa = Math.sin(a);
      for (let i = 0; i < N; i++) {
        const i3 = i * 3;
        let x = clus[i3], y = clus[i3 + 1], z = clus[i3 + 2];
        const rx = x * ca - z * sa; z = x * sa + z * ca; x = rx;
        if (red[i]) { const e = cur.voxEject * (0.7 + rand[i] * 1.5); const l = Math.hypot(x, y, z) || 1; x += (x / l) * e; y += (y / l) * e; z += (z / l) * e; }
        x += (gath[i3] - x) * f; y += (gath[i3 + 1] - y) * f; z += (gath[i3 + 2] - z) * f;
        dummy.position.set(x, y, z);
        dummy.rotation.set(t * 0.4 * rand[i], t * 0.3 + rand[i] * 6, 0);
        const s = cur.voxVis * (1 - cur.cloudVis * 0.95) * (0.85 + rand[i] * 0.3);
        dummy.scale.setScalar(s + 1e-5);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    },
    dispose() { geo.dispose(); mat.dispose(); },
  };
}
