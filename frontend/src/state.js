/* Plain numeric state. Scroll timelines write per-chapter progress into `prog`; composeState() turns that
   into target values in `state`; the render loop damps toward `state` (never touched by ScrollTrigger). */
export const state = {
  chapter: 1,
  narrow: 0,                                 // set by the scene on resize (portrait / phone layout)
  brainVis: 1, brainDissolve: 0.12, shardVis: 1,
  flyVis: 0, fly: 0,                         // fly-through field
  voxVis: 0, voxMode: 2, voxEject: 0,        // 2 spinning cluster, 3 gather into the point cloud
  cloudVis: 0, cloudMorph: 0, driftVis: 0,   // point-cloud brain -> galaxy (+ drifting data shards)
  globeVis: 0, globeSpin: 1,
  shieldVis: 0,
  bgGreen: 1,                                // hero backdrop tint (0 = pure black)
  objX: 0, objY: 0, objScale: 1, camZ: 7,
};
export const prog = { hero: 0, problem: 0, intro: 0, purpose: 0, how: 0, demo: 0, impact: 0 };

const K = ['brainVis', 'brainDissolve', 'shardVis', 'flyVis', 'fly', 'voxVis', 'voxMode', 'voxEject', 'cloudVis', 'cloudMorph',
  'driftVis', 'globeVis', 'globeSpin', 'shieldVis', 'bgGreen', 'objX', 'objY', 'objScale'];
const base = { brainVis: 0, brainDissolve: 1.1, shardVis: 0, flyVis: 0, fly: 0, voxVis: 0, voxMode: 2, voxEject: 0, cloudVis: 0, cloudMorph: 0,
  driftVis: 0, globeVis: 0, globeSpin: 1, shieldVis: 0, bgGreen: 0, objX: 0, objY: 0, objScale: 1 };
const T = (o) => ({ ...base, ...o });
export const TARGETS = {
  hero:     T({ brainVis: 1, brainDissolve: 0.12, shardVis: 1, bgGreen: 1, objX: 0.75, objY: 0.4, objScale: 1.15 }),
  heroEnd:  T({ brainVis: 1, brainDissolve: 0.2, shardVis: 1, bgGreen: 1, objX: 0.75, objY: 0.4, objScale: 1.2 }),
  problem:  T({ brainVis: 0, brainDissolve: 1.1, shardVis: 0, flyVis: 1, fly: 0.5, objX: 0.8, objY: 0.42, objScale: 1.25 }),
  intro:    T({ flyVis: 1, fly: 0.7, voxVis: 1, objX: 2.35, objY: 0, objScale: 1 }),
  introEnd: T({ flyVis: 1, fly: 0.82, voxVis: 1, voxEject: 1, objX: 2.35, objY: 0, objScale: 1 }),
  purpose:  T({ flyVis: 1, fly: 1, voxMode: 3, cloudVis: 1, objX: 2.2, objY: 0.15, objScale: 1.45 }),
  howMid:   T({ fly: 1, cloudVis: 0.6, cloudMorph: 1, driftVis: 1, objX: 1.6, objY: 0.35, objScale: 0.85 }),
  howEnd:   T({ fly: 1, cloudMorph: 1, driftVis: 0.4, globeVis: 1, objX: 2.4, objY: 0.35, objScale: 0.95 }),
  demo:     T({ fly: 1, shieldVis: 1, objX: 2.55, objY: 0.3, objScale: 0.72 }),
  impact:   T({ fly: 1, globeVis: 1, globeSpin: 0.5, driftVis: 0.3, objX: 2.9, objY: 0.85, objScale: 0.82 }),
};
/* ordered segments: [chapter progress key, from, to, (optional) sub-range of that chapter's progress] */
const SEGMENTS = [
  ['hero', 'hero', 'heroEnd'],
  ['problem', 'heroEnd', 'problem'],
  ['intro', 'problem', 'intro', 0, 0.45],        // voxels assemble into the cluster mid-flight...
  ['intro', 'intro', 'introEnd', 0.45, 1],        // ...then the red ones (attacks) get ejected
  ['purpose', 'introEnd', 'purpose'],
  ['how', 'purpose', 'howMid', 0, 0.5],
  ['how', 'howMid', 'howEnd', 0.5, 1],
  ['demo', 'howEnd', 'demo'],
  ['impact', 'demo', 'impact'],
];
const sub = (p, a = 0, b = 1) => Math.max(0, Math.min(1, (p - a) / (b - a)));

export function composeState() {
  for (const k of K) state[k] = TARGETS.hero[k];
  for (const [key, from, to, a, b] of SEGMENTS) {
    const p = sub(prog[key], a, b);
    if (p <= 0) continue;
    const F = TARGETS[from], To = TARGETS[to];
    for (const k of K) state[k] = F[k] + (To[k] - F[k]) * p;
  }
  if (state.narrow) { // phone / portrait: centre the object above the text block
    state.objX = 0;
    state.objY = state.objY * 0.3 + 1.25;
    state.objScale *= 0.5;
  }
}
