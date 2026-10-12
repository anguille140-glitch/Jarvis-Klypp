/* Conversion des tuiles OpenStreetMap en hologramme, HORS du fil principal (l'animation reste fluide).
   - « tile »    : une tuile pour la carte plate du globe → ImageBitmap
   - « texture » : la grande carte drapée sur la holo-table (4096 px) → ImageBitmap, gardée sur le PC
     (cache) pour que les ouvertures suivantes soient instantanées. */
"use strict";
const HOLO_COL = [[2, 14, 32, 215], [5, 52, 112, 235], [4, 46, 52, 225], [14, 78, 122, 245], [62, 176, 232, 235], [255, 166, 60, 245], [200, 244, 255, 255]];
const ROAD_DIM = { 4: [22, 92, 140, 235], 5: [120, 92, 50, 235] };
const EDGE = { 1: [70, 170, 255], 2: [50, 210, 170], 3: [110, 235, 255] };

// fond / eau / verdure / bâtiments / routes / grands axes / texte (mêmes règles que plan_de_travail.html)
function holoTile(img, N, dim) {
  const c = new OffscreenCanvas(N, N), x = c.getContext("2d", { willReadFrequently: true });
  x.imageSmoothingQuality = "high"; x.drawImage(img, 0, 0, N, N);
  const d = x.getImageData(0, 0, N, N), p = d.data, cls = new Uint8Array(N * N);
  for (let k = 0, i = 0; k < N * N; k++, i += 4) {
    const r = p[i], gg = p[i + 1], bb = p[i + 2], mx = Math.max(r, gg, bb), mn = Math.min(r, gg, bb), l = (r + gg + bb) / 3;
    cls[k] = l < 115 ? 6
      : bb > r + 20 && bb >= gg - 4 ? 1
      : gg > r + 6 && gg > bb + 4 ? 2
      : mn > 246 ? 4
      : (r > 225 && gg > 140 && bb < 175 && r - bb > 45) || (r > 200 && r - gg > 50) || (r > 235 && gg > 235 && bb < 215) ? 5
      : mx - mn < 24 && l < 216 ? 3 : 0;
  }
  for (let k = 0, i = 0; k < N * N; k++, i += 4) {
    const c0 = cls[k], col = dim && (c0 === 4 || c0 === 5) ? ROAD_DIM[c0] : HOLO_COL[c0];
    p[i] = col[0]; p[i + 1] = col[1]; p[i + 2] = col[2]; p[i + 3] = col[3];
    const xx = k % N, yy = (k / N) | 0;
    if (xx < N - 1 && yy < N - 1) {
      const cr = cls[k + 1], cd = cls[k + N];
      const e = (c0 !== cr ? (EDGE[c0] ? c0 : EDGE[cr] ? cr : 0) : 0) || (c0 !== cd ? (EDGE[c0] ? c0 : EDGE[cd] ? cd : 0) : 0);
      if (e) { const ec = EDGE[e]; p[i] = ec[0]; p[i + 1] = ec[1]; p[i + 2] = ec[2]; p[i + 3] = 255; }
    }
  }
  x.putImageData(d, 0, 0);
  const hs = N >> 2, halo = new OffscreenCanvas(hs, hs), hx = halo.getContext("2d");    // halo : réduit puis agrandi = flou
  hx.drawImage(c, 0, 0, hs, hs);
  x.globalCompositeOperation = "lighter"; x.globalAlpha = .42; x.drawImage(halo, 0, 0, N, N);
  return c;
}
async function fetchBitmap(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("tuile " + r.status);
  return createImageBitmap(await r.blob());
}

const queue = [];
let busy = 0;
function pump() {
  while (busy < 4 && queue.length) {
    const job = queue.shift(); busy++;
    job().finally(() => { busy--; pump(); });
  }
}

onmessage = (e) => {
  const m = e.data;
  if (m.type === "tile") {
    queue.push(async () => {
      try {
        const c = holoTile(await fetchBitmap(m.url), m.size || 256, m.dim || 0), bmp = c.transferToImageBitmap();
        postMessage({ id: m.id, bmp }, [bmp]);
      } catch (err) { postMessage({ id: m.id, bmp: null }); }
    });
    pump();
  } else if (m.type === "texture") buildTexture(m);
};

async function buildTexture(m) {
  const t0 = performance.now();
  try {                                                      // déjà calculée une fois : lecture directe
    if (m.cache) {
      const r = await fetch(m.cache, { cache: "no-store" });
      if (r.ok) {
        const bmp = await createImageBitmap(await r.blob(), { imageOrientation: "flipY" });
        postMessage({ id: m.id, bmp, cached: true, ms: performance.now() - t0 }, [bmp]);
        return;
      }
    }
  } catch (err) { /* on recalcule */ }
  const S = m.size, c = new OffscreenCanvas(S, S), x = c.getContext("2d", { willReadFrequently: true });   // dessin sur le processeur : bien plus rapide ici
  x.fillStyle = "rgb(2,12,26)"; x.fillRect(0, 0, S, S); x.imageSmoothingQuality = "high";
  let i = 0, fail = 0, done = 0;
  const worker = async () => {
    while (i < m.tiles.length) {
      const [url, dx, dy, dw, dh] = m.tiles[i++];
      try { x.drawImage(holoTile(await fetchBitmap(url), 512, 1), dx, dy, dw, dh); } catch (err) { fail++; }
      done++;
      if (done % 8 === 0) postMessage({ id: m.id, progress: done / m.tiles.length });
    }
  };
  await Promise.all(Array.from({ length: 6 }, worker));
  let blob = null;
  if (!fail && m.cache) { try { blob = await c.convertToBlob({ type: "image/webp", quality: .92 }); } catch (err) { blob = null; } }
  const bmp = await createImageBitmap(c, { imageOrientation: "flipY" });
  postMessage({ id: m.id, bmp, cached: false, fail, ms: performance.now() - t0 }, [bmp]);
  if (blob) fetch(m.cache, { method: "POST", body: blob }).catch(() => {});   // gardée pour la prochaine fois
}
