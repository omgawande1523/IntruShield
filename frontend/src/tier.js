/* Quality tier from hardware hints. */
export function detectTier() {
  const cores = navigator.hardwareConcurrency || 4;
  const mem = navigator.deviceMemory || 4;
  const small = Math.min(innerWidth, innerHeight) < 700 || innerWidth < 820;
  const coarse = matchMedia('(pointer: coarse)').matches;
  const high = !small && !coarse && cores >= 6 && mem >= 4;
  return {
    name: high ? 'high' : 'low',
    high,
    dpr: Math.min(devicePixelRatio || 1, high ? 1.75 : 1.25),
    voxels: high ? 2400 : 1000,
    cloud: high ? 42000 : 16000,
    shards: high ? 1300 : 480,
    dashes: high ? 230 : 110,
    bloom: high,
    pin: high ? 1 : 0.6, // multiplier for pinned chapter length
    mobile: small,
  };
}
