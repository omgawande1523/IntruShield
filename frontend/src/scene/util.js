import * as THREE from 'three';

export const C = {
  purple: new THREE.Color('#7b5cff'), teal: new THREE.Color('#13d6c4'), gold: new THREE.Color('#f5b83d'),
  red: new THREE.Color('#ff4d5e'), brain: new THREE.Color('#6b4dff'), rim: new THREE.Color('#b9a6ff'), sheen: new THREE.Color('#b3a4ff'),
};

/* Ashima 3D simplex noise (MIT) */
export const SNOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 Cc=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,Cc.yyy)); vec3 x0=v-i+dot(i,Cc.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+Cc.xxx; vec3 x2=x0-i2+Cc.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

/* Bake world transforms into the first mesh's geometry, center it and scale to `radius`. Returns the mesh. */
export function bakeAndNormalize(root, radius) {
  root.updateMatrixWorld(true);
  let mesh = null;
  root.traverse((o) => { if (o.isMesh && !mesh) mesh = o; });
  const geo = mesh.geometry.clone();
  // KHR_mesh_quantization: attributes may be normalized int16; convert to float before transforming
  for (const name of ['position', 'normal', 'tangent', 'uv']) {
    const at = geo.getAttribute(name);
    if (!at || (at.array instanceof Float32Array && !at.normalized)) continue;
    const n = at.count, sz = at.itemSize, arr = new Float32Array(n * sz);
    for (let i = 0; i < n; i++) for (let j = 0; j < sz; j++) arr[i * sz + j] = at.getComponent(i, j);
    geo.setAttribute(name, new THREE.BufferAttribute(arr, sz));
  }
  geo.applyMatrix4(mesh.matrixWorld);
  geo.computeBoundingSphere();
  const s = geo.boundingSphere;
  geo.translate(-s.center.x, -s.center.y, -s.center.z);
  geo.scale(radius / s.radius, radius / s.radius, radius / s.radius);
  geo.computeBoundingSphere();
  geo.computeBoundingBox();
  const out = new THREE.Mesh(geo, mesh.material);
  return out;
}

export function softCircleTexture(size = 64) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.35, 'rgba(255,255,255,0.6)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export const rnd = (a = 0, b = 1) => a + Math.random() * (b - a);
export const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) * 1.2;
export const smooth = (t) => t * t * (3 - 2 * t);
export const clamp01 = (t) => (t < 0 ? 0 : t > 1 ? 1 : t);
