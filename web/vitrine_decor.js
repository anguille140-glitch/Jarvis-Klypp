/* Décor de la vitrine : un village italien de nuit sous la pluie (création originale, dans l'esprit des vieux
   villages méditerranéens), avec une couche futuriste. Tout est fabriqué ici, sans image extérieure :
   ruelle pavée mouillée et flaques, façades ocre usées avec volets, fenêtres allumées, lierre et mousse,
   toits de tuiles, lanternes, guirlandes, arche, clocher avec horloge holographique, néons, panneau défilant,
   drone éclaireur, socle holographique avec anneaux et rayon de scan, pluie, éclaboussures, éclairs. */
(function () {
  "use strict";
  const D = {};
  let THREE;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

  function canvas(w, h) { const c = document.createElement("canvas"); c.width = w; c.height = h; return [c, c.getContext("2d")]; }
  function tex(c, srgb = true, rep) {
    const t = new THREE.CanvasTexture(c); if (srgb) t.encoding = THREE.sRGBEncoding;
    if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); }
    t.anisotropy = D.aniso || 4; return t;
  }
  function radial(stops, size = 128) {
    const [c, x] = canvas(size, size), g = x.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    for (const [o, col] of stops) g.addColorStop(o, col); x.fillStyle = g; x.fillRect(0, 0, size, size); return tex(c);
  }
  function vgrad(stops, w = 8, h = 256) {
    const [c, x] = canvas(w, h), g = x.createLinearGradient(0, 0, 0, h);
    for (const [o, col] of stops) g.addColorStop(o, col); x.fillStyle = g; x.fillRect(0, 0, w, h); return tex(c);
  }
  function leaves(x, cx, cy, r, n, rnd, dark) {        // lierre / mousse : amas de petites feuilles
    for (let i = 0; i < n; i++) {
      const a = rnd() * 6.283, d = Math.sqrt(rnd()) * r, px = cx + Math.cos(a) * d, py = cy + Math.sin(a) * d * .8;
      const g = 40 + rnd() * 50 | 0;
      x.fillStyle = dark ? `rgba(${20 + rnd() * 20 | 0},${g},${18 + rnd() * 18 | 0},.9)` : `rgba(${45 + rnd() * 30 | 0},${g + 40},${25 + rnd() * 25 | 0},.9)`;
      x.beginPath(); x.ellipse(px, py, 2 + rnd() * 5, 1.5 + rnd() * 3.5, rnd() * 3, 0, 6.283); x.fill();
    }
  }

  /* ---------- textures ---------- */
  function cobbles() {
    const S = 1024, [c, x] = canvas(S, S), [r, rx] = canvas(S, S), rnd = rng(7);
    x.fillStyle = "#1b1a18"; x.fillRect(0, 0, S, S);
    rx.fillStyle = "rgb(150,150,150)"; rx.fillRect(0, 0, S, S);                 // rugosité : pavés mats...
    const rows = 22, rh = S / rows;
    for (let j = 0; j < rows; j++) {
      let px = (j % 2) * rh * .5 - rh;
      while (px < S + rh) {
        const w = rh * (.8 + rnd() * .55), cx = px + w / 2, cy = j * rh + rh / 2;
        const v = 52 + rnd() * 38 | 0, warm = rnd() * 10 | 0;
        x.fillStyle = `rgb(${v + warm},${v + warm * .6 | 0},${v - 4})`;
        x.beginPath(); x.ellipse(cx, cy, w * .46, rh * .42, (rnd() - .5) * .3, 0, 6.283); x.fill();
        x.fillStyle = "rgba(255,255,255,.07)"; x.beginPath(); x.ellipse(cx - w * .1, cy - rh * .12, w * .25, rh * .15, 0, 0, 6.283); x.fill();
        px += w + 3;
      }
    }
    for (let i = 0; i < 2600; i++) {                     // mousse dans les joints
      const px = rnd() * S, py = rnd() * S, g = 50 + rnd() * 40 | 0;
      x.fillStyle = `rgba(${28 + rnd() * 20 | 0},${g + 20},${20 + rnd() * 14 | 0},${.25 + rnd() * .4})`; x.fillRect(px, py, 2 + rnd() * 3, 1 + rnd() * 2);
    }
    for (let i = 0; i < 26; i++) {                       // flaques : très lisses (reflets) et un peu plus sombres
      const px = rnd() * S, py = rnd() * S, rr = 30 + rnd() * 110;
      const g = rx.createRadialGradient(px, py, 0, px, py, rr); g.addColorStop(0, "rgb(18,18,18)"); g.addColorStop(.7, "rgb(30,30,30)"); g.addColorStop(1, "rgba(150,150,150,0)");
      rx.fillStyle = g; rx.beginPath(); rx.ellipse(px, py, rr, rr * .6, rnd() * 3, 0, 6.283); rx.fill();
      const g2 = x.createRadialGradient(px, py, 0, px, py, rr); g2.addColorStop(0, "rgba(8,12,18,.55)"); g2.addColorStop(1, "rgba(8,12,18,0)");
      x.fillStyle = g2; x.beginPath(); x.ellipse(px, py, rr, rr * .6, rnd() * 3, 0, 6.283); x.fill();
    }
    return { map: tex(c, true, [9, 14]), rough: tex(r, false, [9, 14]), bump: tex(c, false, [9, 14]) };
  }
  const PLASTER = ["#c49a6c", "#d4ad80", "#b88a5e", "#cdb08e", "#a8805c", "#c9a07a", "#b9946e", "#d8bf9c"];
  const SHUTTER = ["#3d5a3a", "#5b3d28", "#46586a", "#6b4a2f", "#2f4a44"];
  function facade(w, h, seed, opts = {}) {
    const PX = 96, W = Math.round(w * PX), H = Math.round(h * PX), rnd = rng(seed);
    const [c, x] = canvas(W, H), [e, ex] = canvas(W, H);
    ex.fillStyle = "#000"; ex.fillRect(0, 0, W, H);
    x.fillStyle = PLASTER[seed % PLASTER.length]; x.fillRect(0, 0, W, H);
    for (let i = 0; i < 260; i++) {                      // enduit usé, taches, écaillures
      const px = rnd() * W, py = rnd() * H, r = 6 + rnd() * 50; x.fillStyle = rnd() < .6 ? `rgba(60,40,25,${.04 + rnd() * .08})` : `rgba(255,240,215,${.04 + rnd() * .06})`;
      x.beginPath(); x.ellipse(px, py, r, r * (.5 + rnd()), rnd() * 3, 0, 6.283); x.fill();
    }
    for (let i = 0; i < 40; i++) { const px = rnd() * W; x.fillStyle = `rgba(30,22,15,${.05 + rnd() * .08})`; x.fillRect(px, 0, 2 + rnd() * 5, H * (.3 + rnd() * .7)); }   // coulures de pluie
    const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "rgba(0,0,0,.35)"); g.addColorStop(.08, "rgba(0,0,0,0)"); g.addColorStop(.8, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(20,15,10,.45)");
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    // soubassement en pierre avec mousse
    const base = .95 * PX;
    for (let yy = H - base; yy < H; yy += 22) for (let xx = (yy / 22 % 2) * 20 - 20; xx < W; xx += 42) {
      const v = 95 + rnd() * 40 | 0; x.fillStyle = `rgb(${v},${v - 8},${v - 18})`; x.fillRect(xx + 2, yy + 2, 38, 18);
    }
    for (let i = 0; i < 18; i++) leaves(x, rnd() * W, H - rnd() * base * 1.2, 10 + rnd() * 26, 40, rnd, true);
    // étages : fenêtres à volets, certaines allumées
    const floors = Math.max(1, Math.floor((h - 1.4) / 2.5)), per = Math.max(1, Math.floor(w / 1.7));
    for (let f = 0; f < floors; f++) for (let k = 0; k < per; k++) {
      const ww = .78 * PX, wh = 1.25 * PX, cx = (k + .5) * W / per, top = H - (1.6 + f * 2.5 + 1.25) * PX - .2 * PX;
      if (top < 30) continue;
      const lit = rnd() < .42, open = rnd() < .6, col = SHUTTER[(seed + f + k) % SHUTTER.length];
      x.fillStyle = "#e3d6bf"; x.fillRect(cx - ww / 2 - 6, top - 6, ww + 12, wh + 14);          // encadrement
      x.fillStyle = lit ? "#f0b860" : "#0d1016"; x.fillRect(cx - ww / 2, top, ww, wh);
      if (lit) {
        const lg = x.createLinearGradient(0, top, 0, top + wh); lg.addColorStop(0, "#ffd890"); lg.addColorStop(1, "#c77a2c"); x.fillStyle = lg; x.fillRect(cx - ww / 2, top, ww, wh);
        ex.fillStyle = "rgb(255,190,100)"; ex.fillRect(cx - ww / 2, top, ww, wh);
        x.fillStyle = "rgba(90,40,20,.55)"; x.fillRect(cx - ww / 2, top, ww * .3, wh); x.fillRect(cx + ww * .2, top, ww * .3, wh);   // rideaux
      }
      x.strokeStyle = "rgba(40,30,20,.9)"; x.lineWidth = 3; x.strokeRect(cx - ww / 2, top, ww, wh);
      x.beginPath(); x.moveTo(cx, top); x.lineTo(cx, top + wh); x.moveTo(cx - ww / 2, top + wh * .45); x.lineTo(cx + ww / 2, top + wh * .45); x.stroke();
      const sw = ww * .5;                                // volets ouverts de chaque côté, ou fermés
      x.fillStyle = col;
      if (open) { x.fillRect(cx - ww / 2 - sw - 6, top, sw, wh); x.fillRect(cx + ww / 2 + 6, top, sw, wh); }
      else { x.fillRect(cx - ww / 2, top, ww, wh); ex.fillStyle = "#000"; ex.fillRect(cx - ww / 2, top, ww, wh); }
      x.strokeStyle = "rgba(0,0,0,.35)"; x.lineWidth = 2;
      for (let s = 0; s < wh; s += 9) { if (open) { x.beginPath(); x.moveTo(cx - ww / 2 - sw - 6, top + s); x.lineTo(cx - ww / 2 - 6, top + s); x.moveTo(cx + ww / 2 + 6, top + s); x.lineTo(cx + ww / 2 + 6 + sw, top + s); x.stroke(); }
        else { x.beginPath(); x.moveTo(cx - ww / 2, top + s); x.lineTo(cx + ww / 2, top + s); x.stroke(); } }
      x.fillStyle = "#cfc2aa"; x.fillRect(cx - ww / 2 - 10, top + wh + 6, ww + 20, 8);   // appui
      if (rnd() < .35) { for (let p = 0; p < 3; p++) leaves(x, cx - ww / 2 + p * ww / 2, top + wh + 2, 12, 26, rnd, false);    // jardinière
        for (let p = 0; p < 6; p++) { x.fillStyle = ["#c43a3a", "#e05a7a", "#f2d24a"][p % 3]; x.beginPath(); x.arc(cx - ww / 2 + rnd() * ww, top + wh - 4 + rnd() * 8, 3, 0, 6.283); x.fill(); } }
    }
    // rez-de-chaussée : porte en arc et parfois une vitrine allumée
    const dw = 1.15 * PX, dh = 2.2 * PX, dx = W * (.25 + rnd() * .5);
    x.fillStyle = "#e0d2b8"; x.beginPath(); x.moveTo(dx - dw / 2 - 8, H); x.lineTo(dx - dw / 2 - 8, H - dh + dw / 2); x.arc(dx, H - dh + dw / 2, dw / 2 + 8, Math.PI, 0); x.lineTo(dx + dw / 2 + 8, H); x.fill();
    x.fillStyle = "#4a2f1c"; x.beginPath(); x.moveTo(dx - dw / 2, H); x.lineTo(dx - dw / 2, H - dh + dw / 2); x.arc(dx, H - dh + dw / 2, dw / 2, Math.PI, 0); x.lineTo(dx + dw / 2, H); x.fill();
    x.strokeStyle = "rgba(0,0,0,.4)"; for (let s = dx - dw / 2 + 10; s < dx + dw / 2; s += 14) { x.beginPath(); x.moveTo(s, H); x.lineTo(s, H - dh + dw / 2 + 6); x.stroke(); }
    if (opts.shop) {
      const sx = dx > W / 2 ? W * .18 : W * .62, sw2 = W * .22;
      x.fillStyle = "#f5c070"; x.fillRect(sx, H - 2 * PX, sw2, 1.3 * PX); ex.fillStyle = "rgb(255,180,90)"; ex.fillRect(sx, H - 2 * PX, sw2, 1.3 * PX);
      x.fillStyle = "rgba(60,30,15,.6)"; for (let s = 0; s < 4; s++) x.fillRect(sx + s * sw2 / 4 + 6, H - 1.2 * PX, sw2 / 4 - 12, .3 * PX);
    }
    // lierre qui grimpe
    if (rnd() < .65) { let px = rnd() * W, py = H; for (let s = 0; s < 34; s++) { leaves(x, px, py, 14, 30, rnd, s % 2 === 0); px += (rnd() - .5) * 26; py -= 12 + rnd() * 16; } }
    return { map: tex(c), emissive: tex(e) };
  }
  function roofTex() {
    const [c, x] = canvas(512, 512), rnd = rng(11);
    x.fillStyle = "#5a2a1a"; x.fillRect(0, 0, 512, 512);
    for (let j = 0; j < 16; j++) for (let i = 0; i < 12; i++) {
      const v = rnd(); x.fillStyle = `rgb(${130 + v * 50 | 0},${55 + v * 25 | 0},${35 + v * 15 | 0})`;
      const px = i * 44 + (j % 2) * 22, py = j * 32; x.beginPath(); x.ellipse(px, py + 16, 20, 18, 0, 0, Math.PI); x.fill();
      x.fillStyle = "rgba(0,0,0,.25)"; x.fillRect(px - 20, py + 28, 40, 4);
    }
    for (let i = 0; i < 40; i++) leaves(x, rnd() * 512, rnd() * 512, 8, 14, rnd, true);
    return tex(c, true, [2, 1]);
  }
  function skyTex() {
    const W = 2048, H = 1024, [c, x] = canvas(W, H), rnd = rng(3);
    const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#020309"); g.addColorStop(.42, "#0a1222"); g.addColorStop(.5, "#1a2234"); g.addColorStop(.56, "#0b0f18"); g.addColorStop(1, "#040507");
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    const mx = W * .62, my = H * .2;                    // lune voilée derrière les nuages
    const mg = x.createRadialGradient(mx, my, 0, mx, my, 260); mg.addColorStop(0, "rgba(200,215,240,.55)"); mg.addColorStop(.08, "rgba(170,190,225,.28)"); mg.addColorStop(1, "rgba(80,100,140,0)");
    x.fillStyle = mg; x.fillRect(0, 0, W, H);
    for (let i = 0; i < 900; i++) {                      // nuages de pluie
      const px = rnd() * W, py = H * (.05 + rnd() * .42), r = 30 + rnd() * 120, near = Math.hypot(px - mx, py - my) < 420;
      x.fillStyle = near ? `rgba(120,135,165,${.03 + rnd() * .05})` : `rgba(40,50,70,${.04 + rnd() * .06})`;
      x.beginPath(); x.ellipse(px, py, r * 1.8, r * .6, 0, 0, 6.283); x.fill();
    }
    return tex(c);
  }
  function textTex(text, color, w = 512, h = 128, font = "700 72px 'Barlow Condensed', 'Arial Narrow', sans-serif") {
    const [c, x] = canvas(w, h);
    x.font = font; x.textAlign = "center"; x.textBaseline = "middle";
    x.shadowColor = color; x.shadowBlur = 24; x.fillStyle = color; x.fillText(text, w / 2, h / 2);
    x.shadowBlur = 6; x.fillStyle = "#ffffff"; x.globalAlpha = .7; x.fillText(text, w / 2, h / 2);
    return tex(c);
  }
  function hexTex() {
    const S = 512, [c, x] = canvas(S, S); x.strokeStyle = "rgba(255,255,255,.9)"; x.lineWidth = 1.5;
    const r = 18, hh = r * Math.sqrt(3);
    for (let j = -1; j < S / hh + 1; j++) for (let i = -1; i < S / (r * 1.5) + 1; i++) {
      const cx = i * r * 1.5, cy = j * hh + (i % 2 ? hh / 2 : 0); x.beginPath();
      for (let k = 0; k <= 6; k++) { const a = k * Math.PI / 3; k ? x.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a)) : x.moveTo(cx + r * Math.cos(a), cy + r * Math.sin(a)); }
      x.stroke();
    }
    x.globalCompositeOperation = "destination-in";
    const g = x.createRadialGradient(S / 2, S / 2, S * .1, S / 2, S / 2, S / 2); g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(.85, "rgba(0,0,0,.6)"); g.addColorStop(1, "rgba(0,0,0,0)");
    x.fillStyle = g; x.fillRect(0, 0, S, S);
    x.globalCompositeOperation = "source-over"; x.strokeStyle = "rgba(255,255,255,1)"; x.lineWidth = 4;
    for (const rr of [.47, .43, .3]) { x.beginPath(); x.arc(S / 2, S / 2, S * rr, 0, 6.283); x.stroke(); }
    for (let k = 0; k < 72; k++) { const a = k / 72 * 6.283, r1 = S * .47, r2 = r1 - (k % 6 ? 8 : 20); x.beginPath(); x.moveTo(S / 2 + Math.cos(a) * r1, S / 2 + Math.sin(a) * r1); x.lineTo(S / 2 + Math.cos(a) * r2, S / 2 + Math.sin(a) * r2); x.stroke(); }
    return tex(c);
  }

  /* ---------- construction ---------- */
  D.build = function (o) {
    THREE = o.THREE; const scene = o.scene, FLOOR = o.FLOOR, R = o.R;
    D.aniso = R.capabilities.getMaxAnisotropy();
    const add = (m) => { scene.add(m); return m; };
    const listeners = {};
    const emit = (n, v) => (listeners[n] || []).forEach((f) => { try { f(v); } catch (e) {} });
    scene.fog = new THREE.FogExp2(0x070c15, .034);
    // ciel
    const skyMat = new THREE.MeshBasicMaterial({ map: skyTex(), side: THREE.BackSide, fog: false, toneMapped: false });
    const sky = add(new THREE.Mesh(new THREE.SphereGeometry(60, 48, 24), skyMat)); sky.rotation.y = -.4;
    // lumières d'ambiance nocturnes
    const hemi = add(new THREE.HemisphereLight(0x4a5c84, 0x140e08, .16));
    const moon = add(new THREE.DirectionalLight(0x8fa6d8, .28)); moon.position.set(4, 9, -6);
    const flashL = add(new THREE.DirectionalLight(0xdfe8ff, 0)); flashL.position.set(-6, 12, 4);
    // sol pavé mouillé (un peu transparent sous la vitrine : on y voit le reflet du skin)
    const cb = cobbles();
    const ground = add(new THREE.Mesh(new THREE.PlaneGeometry(40, 60), new THREE.MeshStandardMaterial({ map: cb.map, roughnessMap: cb.rough, bumpMap: cb.bump,
      bumpScale: .035, roughness: 1, metalness: 0, color: 0xb8b4ac, envMapIntensity: 1.6 })));
    ground.rotation.x = -Math.PI / 2; ground.position.set(0, FLOOR, -18);
    // rangées de maisons de chaque côté de la ruelle
    const roof = roofTex(), rnd = rng(42);
    const lanterns = [], houses = [];
    for (const side of [-1, 1]) {
      let z = 4.5, n = 0;
      while (z > -36) {
        const w = 3.6 + rnd() * 2.2, h = 6.5 + rnd() * 4.5, d = 6, x = side * (4.6 + rnd() * .45 + d / 2);
        const fa = facade(w, h, (side + 3) * 17 + n * 5, { shop: rnd() < .35 });
        const plain = new THREE.MeshStandardMaterial({ color: PLASTER[n % PLASTER.length], roughness: .92 });
        const front = new THREE.MeshStandardMaterial({ map: fa.map, emissiveMap: fa.emissive, emissive: 0xffffff, emissiveIntensity: 1.25, roughness: .88, metalness: 0 });
        const mats = side < 0 ? [front, plain, plain, plain, plain, plain] : [plain, front, plain, plain, plain, plain];
        const b = add(new THREE.Mesh(new THREE.BoxGeometry(d, h, w), mats));
        b.position.set(x, FLOOR + h / 2, z - w / 2);
        // toit qui déborde au-dessus de la ruelle
        const rf = add(new THREE.Mesh(new THREE.PlaneGeometry(d + 1.4, w + .3), new THREE.MeshStandardMaterial({ map: roof, roughness: .55, side: THREE.DoubleSide })));
        rf.rotation.set(-Math.PI / 2, 0, 0); rf.rotateOnWorldAxis(new THREE.Vector3(0, 0, 1), side * .35);   // pente vers la ruelle
        rf.position.set(x - side * .5, FLOOR + h + .55, z - w / 2);
        const eave = add(new THREE.Mesh(new THREE.BoxGeometry(.25, .18, w + .3), new THREE.MeshStandardMaterial({ color: 0x3a2418, roughness: .8 })));
        eave.position.set(x - side * (d / 2 + .55), FLOOR + h + .12, z - w / 2);
        // balcon en fer forgé
        if (rnd() < .55 && h > 7) {
          const by = FLOOR + 4.1 + (rnd() < .5 ? 2.5 : 0), bz = z - w * (.3 + rnd() * .4);
          const slab = add(new THREE.Mesh(new THREE.BoxGeometry(.75, .1, 1.8), new THREE.MeshStandardMaterial({ color: 0xc9bca4, roughness: .8 })));
          slab.position.set(x - side * (d / 2 + .37), by, bz);
          const iron = new THREE.MeshStandardMaterial({ color: 0x141414, roughness: .4, metalness: .7 });
          const rail = add(new THREE.Mesh(new THREE.BoxGeometry(.04, .04, 1.8), iron)); rail.position.set(x - side * (d / 2 + .72), by + .8, bz);
          for (let k = 0; k <= 12; k++) { const bar = add(new THREE.Mesh(new THREE.BoxGeometry(.02, .8, .02), iron)); bar.position.set(x - side * (d / 2 + .72), by + .4, bz - .9 + k * .15); }
        }
        // lanterne murale
        if (n % 2 === (side < 0 ? 0 : 1) && z < 2 && z > -26) {
          const lx = x - side * (d / 2 + .35), ly = FLOOR + 3.3, lz = z - w * .5;
          const body = add(new THREE.Mesh(new THREE.BoxGeometry(.2, .32, .2), new THREE.MeshStandardMaterial({ color: 0x111111, metalness: .6, roughness: .4 })));
          body.position.set(lx, ly, lz);
          const glass = add(new THREE.Mesh(new THREE.BoxGeometry(.15, .22, .15), new THREE.MeshBasicMaterial({ color: new THREE.Color(2.2, 1.45, .7), toneMapped: false })));
          glass.position.set(lx, ly, lz);
          const arm = add(new THREE.Mesh(new THREE.BoxGeometry(.4, .03, .03), body.material)); arm.position.set(lx + side * .2, ly + .18, lz);
          const halo = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(255,200,120,.9)"], [.25, "rgba(255,160,70,.25)"], [1, "rgba(255,140,60,0)"]]),
            blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: false })));
          halo.position.set(lx, ly, lz); halo.scale.setScalar(2.4);
          lanterns.push({ pos: new THREE.Vector3(lx, ly, lz), halo, glass, ph: rnd() * 10 });
        }
        houses.push({ side, fx: x - side * d / 2, z0: z, z1: z - w, w, h, n });
        z -= w; n++;
      }
    }
    // lumières des 4 lanternes les plus proches (les autres brillent sans éclairer : rendu léger)
    lanterns.sort((a, b) => b.pos.z - a.pos.z);
    const lampLights = lanterns.slice(0, 4).map((l) => { const p = add(new THREE.PointLight(0xffa860, 7, 10, 2)); p.position.copy(l.pos).add(new THREE.Vector3(0, -.2, 0)); l.light = p; return p; });
    // guirlandes lumineuses au-dessus de la ruelle
    const bulbTex = radial([[0, "rgba(255,240,200,1)"], [.3, "rgba(255,200,120,.5)"], [1, "rgba(255,160,80,0)"]], 64);
    const bulbs = [];
    for (const gz of [-4.5, -10, -19]) {
      const pts = [], N = 22, y0 = FLOOR + 5.3;
      for (let i = 0; i <= N; i++) { const t = i / N, xx = -4.6 + 9.2 * t; pts.push(new THREE.Vector3(xx, y0 - Math.sin(t * Math.PI) * .9, gz + Math.sin(t * 3) * .2)); }
      add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x050505 })));
      for (let i = 1; i < N; i++) { const s = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: bulbTex, color: [0xffd08a, 0xffb060, 0xfff0c8][i % 3], blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })));
        s.position.copy(pts[i]).add(new THREE.Vector3(0, -.08, 0)); s.scale.setScalar(.34); s.userData.ph = Math.random() * 6; bulbs.push(s); }
    }
    // arche en pierre au-dessus de la ruelle
    const archShape = new THREE.Shape(); archShape.moveTo(-5.2, 0); archShape.lineTo(5.2, 0); archShape.lineTo(5.2, 7.6); archShape.lineTo(-5.2, 7.6); archShape.lineTo(-5.2, 0);
    const hole = new THREE.Path(); hole.moveTo(-3.2, 0); hole.lineTo(-3.2, 3.6); hole.absarc(0, 3.6, 3.2, Math.PI, 0, true); hole.lineTo(3.2, 0); hole.lineTo(-3.2, 0); archShape.holes.push(hole);
    const af = facade(10.4, 7.6, 99);
    const arch = add(new THREE.Mesh(new THREE.ExtrudeGeometry(archShape, { depth: 1.4, bevelEnabled: false }), new THREE.MeshStandardMaterial({ color: 0xb08a64, roughness: .9 })));
    arch.position.set(0, FLOOR, -15.5);
    const archFront = add(new THREE.Mesh(new THREE.ShapeGeometry(archShape), new THREE.MeshStandardMaterial({ map: af.map, roughness: .9 })));
    archFront.position.set(0, FLOOR, -15.5 + 1.41);
    archFront.geometry.computeBoundingBox(); { const uv = archFront.geometry.attributes.uv, p = archFront.geometry.attributes.position;
      for (let i = 0; i < uv.count; i++) uv.setXY(i, (p.getX(i) + 5.2) / 10.4, p.getY(i) / 7.6); }
    // clocher au fond, avec une horloge holographique à l'heure réelle
    const tower = new THREE.Group(); tower.position.set(-1.6, FLOOR, -40); scene.add(tower);
    const tf = facade(3.4, 16, 77);
    const tb = new THREE.Mesh(new THREE.BoxGeometry(3.4, 16, 3.4), new THREE.MeshStandardMaterial({ map: tf.map, roughness: .9 })); tb.position.y = 8; tower.add(tb);
    const belfry = new THREE.Mesh(new THREE.BoxGeometry(3.6, 2.6, 3.6), new THREE.MeshStandardMaterial({ color: 0x9e7a58, roughness: .9 })); belfry.position.y = 17.3; tower.add(belfry);
    const tRoof = new THREE.Mesh(new THREE.ConeGeometry(2.9, 3.4, 4), new THREE.MeshStandardMaterial({ map: roof, roughness: .6 })); tRoof.position.y = 20.3; tRoof.rotation.y = Math.PI / 4; tower.add(tRoof);
    const bellGlow = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 1.8), new THREE.MeshBasicMaterial({ color: new THREE.Color(.9, .55, .25), toneMapped: false })); bellGlow.position.set(0, 17.2, 1.81); tower.add(bellGlow);
    const [clk, clx] = canvas(256, 256), clockTex = tex(clk);
    const drawClock = () => {
      clx.clearRect(0, 0, 256, 256); clx.strokeStyle = "#4fd8ff"; clx.shadowColor = "#4fd8ff"; clx.shadowBlur = 16; clx.lineWidth = 6;
      clx.beginPath(); clx.arc(128, 128, 110, 0, 6.283); clx.stroke();
      for (let k = 0; k < 12; k++) { const a = k / 12 * 6.283; clx.beginPath(); clx.moveTo(128 + Math.cos(a) * 92, 128 + Math.sin(a) * 92); clx.lineTo(128 + Math.cos(a) * 104, 128 + Math.sin(a) * 104); clx.stroke(); }
      const d = new Date(), hA = ((d.getHours() % 12) + d.getMinutes() / 60) / 12 * 6.283 - Math.PI / 2, mA = d.getMinutes() / 60 * 6.283 - Math.PI / 2;
      clx.lineWidth = 8; clx.beginPath(); clx.moveTo(128, 128); clx.lineTo(128 + Math.cos(hA) * 55, 128 + Math.sin(hA) * 55); clx.stroke();
      clx.lineWidth = 5; clx.beginPath(); clx.moveTo(128, 128); clx.lineTo(128 + Math.cos(mA) * 85, 128 + Math.sin(mA) * 85); clx.stroke();
      clx.fillStyle = "#bff3ff"; clx.font = "700 30px 'Barlow Condensed', sans-serif"; clx.textAlign = "center";
      clx.fillText(d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }), 128, 182); clockTex.needsUpdate = true;
    };
    drawClock(); setInterval(drawClock, 20000);
    const clock = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 2.4), new THREE.MeshBasicMaterial({ map: clockTex, transparent: true, blending: THREE.AdditiveBlending, toneMapped: false, depthWrite: false }));
    clock.position.set(0, 13.4, 1.75); tower.add(clock);
    // néons (touche futuriste) et panneau holographique qui défile
    const neons = [];
    const neon = (text, color, x, y, z, ry, w = 2.6) => {
      const m = add(new THREE.Mesh(new THREE.PlaneGeometry(w, w / 4), new THREE.MeshBasicMaterial({ map: textTex(text, color), transparent: true, blending: THREE.AdditiveBlending, toneMapped: false, depthWrite: false })));
      m.position.set(x, y, z); m.rotation.y = ry; neons.push({ m, ph: Math.random() * 10 }); return m;
    };
    neon("ARMERIA", "#4fd8ff", -4.55, FLOOR + 3.1, -7.5, Math.PI / 2);
    neon("TRATTORIA", "#ff4f8b", 4.55, FLOOR + 3.4, -12.5, -Math.PI / 2);
    neon("VITRINE · 24/7", "#f2a93b", 4.55, FLOOR + 2.7, -3.2, -Math.PI / 2, 2.2);
    const [bc, bx] = canvas(1024, 128), boardTex = tex(bc);
    const board = add(new THREE.Mesh(new THREE.PlaneGeometry(4.2, .52), new THREE.MeshBasicMaterial({ map: boardTex, transparent: true, blending: THREE.AdditiveBlending, toneMapped: false, depthWrite: false })));
    board.position.set(-4.5, FLOOR + 5.6, -20); board.rotation.y = Math.PI / 2;
    let boardX = 0; const boardText = "  ARMURERIE DE KLYPP  ◆  MARCHÉ EN DIRECT  ◆  AWP · DRAGON LORE  ▲  KARAMBIT · FADE  ▲  M4A4 · HOWL  ▲  ";
    // socle holographique sous le skin
    const holo = new THREE.Group(); holo.position.y = FLOOR; scene.add(holo);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(1.15, 1.32, .2, 72), new THREE.MeshStandardMaterial({ color: 0x15181d, metalness: .85, roughness: .3 }));
    base.position.y = .1; holo.add(base);
    const rarityMats = [];
    const lip = new THREE.Mesh(new THREE.TorusGeometry(1.14, .018, 12, 128), new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false })); lip.rotation.x = Math.PI / 2; lip.position.y = .205; holo.add(lip); rarityMats.push(lip.material);
    const hex = new THREE.Mesh(new THREE.PlaneGeometry(2.3, 2.3), new THREE.MeshBasicMaterial({ map: hexTex(), transparent: true, opacity: .4, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    hex.rotation.x = -Math.PI / 2; hex.position.y = .215; holo.add(hex); rarityMats.push(hex.material);
    const ground2 = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), new THREE.MeshBasicMaterial({ map: radial([[0, "rgba(255,255,255,.5)"], [.35, "rgba(255,255,255,.12)"], [1, "rgba(255,255,255,0)"]]),
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    ground2.rotation.x = -Math.PI / 2; ground2.position.y = .01; holo.add(ground2); rarityMats.push(ground2.material);
    const orbits = [1.75, 2.0, 2.3].map((r, i) => {
      const t = new THREE.Mesh(new THREE.TorusGeometry(r, .003 + i * .0015, 8, 160, Math.PI * (1.2 + i * .25)), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: .2, blending: THREE.AdditiveBlending, toneMapped: false }));
      t.position.y = .38 + i * .08; t.rotation.x = Math.PI / 2 + (i - 1) * .08; holo.add(t); rarityMats.push(t.material); return t;
    });
    const column = new THREE.Mesh(new THREE.CylinderGeometry(1.02, 1.08, 3.4, 64, 1, true), new THREE.MeshBasicMaterial({ map: vgrad([[0, "rgba(255,255,255,0)"], [.7, "rgba(255,255,255,.35)"], [1, "rgba(255,255,255,.9)"]]),
      transparent: true, opacity: .045, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    column.position.y = 1.9; holo.add(column); rarityMats.push(column.material);
    const scanMat = new THREE.MeshBasicMaterial({ map: radial([[0, "rgba(255,255,255,0)"], [.8, "rgba(255,255,255,.15)"], [.97, "rgba(255,255,255,.95)"], [1, "rgba(255,255,255,0)"]], 256),
      transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
    const scan = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 3.6), scanMat); scan.rotation.x = -Math.PI / 2; holo.add(scan); rarityMats.push(scanMat);
    const NP = 160, pp = new Float32Array(NP * 3), pv = new Float32Array(NP);
    for (let i = 0; i < NP; i++) { const a = Math.random() * 6.283, r = Math.random() * 1.0; pp[i * 3] = Math.cos(a) * r; pp[i * 3 + 1] = .2 + Math.random() * 3.4; pp[i * 3 + 2] = Math.sin(a) * r; pv[i] = .2 + Math.random() * .5; }
    const pgeo = new THREE.BufferGeometry(); pgeo.setAttribute("position", new THREE.BufferAttribute(pp, 3));
    const motes = new THREE.Points(pgeo, new THREE.PointsMaterial({ size: .04, map: radial([[0, "rgba(255,255,255,1)"], [1, "rgba(255,255,255,0)"]], 32), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }));
    holo.add(motes); rarityMats.push(motes.material);
    // drone éclaireur qui patrouille au-dessus de la place
    const drone = new THREE.Group(); scene.add(drone);
    const dmat = new THREE.MeshStandardMaterial({ color: 0x1c2026, metalness: .8, roughness: .35 });
    drone.add(new THREE.Mesh(new THREE.SphereGeometry(.16, 24, 16), dmat));
    for (let k = 0; k < 4; k++) { const arm = new THREE.Mesh(new THREE.BoxGeometry(.5, .025, .04), dmat); arm.rotation.y = k * Math.PI / 2 + Math.PI / 4; drone.add(arm);
      const rot = new THREE.Mesh(new THREE.TorusGeometry(.1, .008, 6, 24), new THREE.MeshBasicMaterial({ color: 0x4fd8ff, toneMapped: false })); rot.rotation.x = Math.PI / 2;
      rot.position.set(Math.cos(k * Math.PI / 2 + Math.PI / 4) * .25, .02, Math.sin(k * Math.PI / 2 + Math.PI / 4) * .25); drone.add(rot); }
    const blink = new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(255,60,60,1)"], [1, "rgba(255,0,0,0)"]], 32), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
    blink.scale.setScalar(.35); blink.position.y = .12; drone.add(blink);
    const beam = new THREE.Mesh(new THREE.ConeGeometry(1.4, 6, 32, 1, true), new THREE.MeshBasicMaterial({ map: vgrad([[0, "rgba(255,255,255,.0)"], [.15, "rgba(255,255,255,.5)"], [1, "rgba(255,255,255,0)"]]),
      color: 0x9fe6ff, transparent: true, opacity: .09, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    beam.position.y = -3; drone.add(beam);
    const spot = new THREE.SpotLight(0xbfefff, 9, 14, .32, .7, 1.6); drone.add(spot); spot.position.set(0, -.1, 0); drone.add(spot.target); spot.target.position.set(0, -6, 0);
    // pluie (traits fins qui brillent près des lanternes) et éclaboussures sur les pavés
    const NR = 3200, rs = new Float32Array(NR * 2 * 4), tip = new Float32Array(NR * 2), rpos = new Float32Array(NR * 2 * 3);
    for (let i = 0; i < NR; i++) { const s = [(Math.random() - .5) * 22, Math.random() * 14, -32 + Math.random() * 38, 7 + Math.random() * 5];
      for (let k = 0; k < 2; k++) { rs.set(s, (i * 2 + k) * 4); tip[i * 2 + k] = k; } }
    const rgeo = new THREE.BufferGeometry(); rgeo.setAttribute("position", new THREE.BufferAttribute(rpos, 3)); rgeo.setAttribute("seed", new THREE.BufferAttribute(rs, 4)); rgeo.setAttribute("tip", new THREE.BufferAttribute(tip, 1));
    const L = lanterns.slice(0, 6).map((l) => l.pos);
    while (L.length < 6) L.push(new THREE.Vector3(0, -50, 0));
    const rainMat = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uFloor: { value: FLOOR }, uH: { value: 14 }, uWind: { value: new THREE.Vector2(.9, .25) }, uFlash: { value: 0 }, uL: { value: L } },
      vertexShader: `uniform float uT, uFloor, uH, uFlash; uniform vec2 uWind; uniform vec3 uL[6]; attribute vec4 seed; attribute float tip; varying float vA; varying vec3 vC;
        void main(){ float y = uFloor + mod(seed.y - uT * seed.w, uH);
          vec3 p = vec3(seed.x + uWind.x * (uFloor + uH - y) * .06, y, seed.z + uWind.y * (uFloor + uH - y) * .06);
          float len = .22 + .22 * fract(seed.x * 13.17);
          p += tip * vec3(uWind.x * len * .12, len, uWind.y * len * .12);
          float lit = 0.; for (int i = 0; i < 6; i++) { vec3 d = p - uL[i]; lit += 1.4 / (1. + dot(d, d) * 1.2); }
          vC = mix(vec3(.55, .65, .8), vec3(1., .78, .5), clamp(lit, 0., 1.)) * (1. + lit * 1.2 + uFlash * 3.);
          vec4 mv = modelViewMatrix * vec4(p, 1.); gl_Position = projectionMatrix * mv;
          float dist = -mv.z; vA = mix(.38, .04, tip) * smoothstep(34., 3., dist) * smoothstep(.8, 2.2, dist); }`,
      fragmentShader: "varying float vA; varying vec3 vC; void main(){ gl_FragColor = vec4(vC, vA); }",
      transparent: true, depthWrite: false,
    });
    const rain = add(new THREE.LineSegments(rgeo, rainMat)); rain.frustumCulled = false;
    const NS = 900, ss = new Float32Array(NS * 4), spos = new Float32Array(NS * 3);
    for (let i = 0; i < NS; i++) { const near = i < 500; ss.set([near ? (Math.random() - .5) * 6 : (Math.random() - .5) * 9, near ? 2 - Math.random() * 6 : 3 - Math.random() * 30, Math.random(), .8 + Math.random() * 1.6], i * 4); }
    const sgeo = new THREE.BufferGeometry(); sgeo.setAttribute("position", new THREE.BufferAttribute(spos, 3)); sgeo.setAttribute("seed", new THREE.BufferAttribute(ss, 4));
    const splashMat = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uFloor: { value: FLOOR }, uScale: { value: innerHeight * .5 }, uFlash: { value: 0 } },
      vertexShader: `uniform float uT, uFloor, uScale; attribute vec4 seed; varying float vT;
        void main(){ vT = fract(uT * seed.w + seed.z); vec4 mv = modelViewMatrix * vec4(seed.x, uFloor + .012, seed.y, 1.);
          gl_Position = projectionMatrix * mv; gl_PointSize = (.06 + vT * .22) * uScale / -mv.z; }`,
      fragmentShader: `uniform float uFlash; varying float vT; void main(){ vec2 p = gl_PointCoord * 2. - 1.; p.y *= 3.2; float r = length(p);
          float ring = smoothstep(.7, .86, r) * smoothstep(1., .9, r); float a = ring * (1. - vT / .45) * step(vT, .45) * .55;
          if (a <= .001) discard; gl_FragColor = vec4(vec3(.75, .82, .95) * (1. + uFlash * 2.), a); }`,
      transparent: true, depthWrite: false,
    });
    const splashes = add(new THREE.Points(sgeo, splashMat)); splashes.frustumCulled = false;


    /* ---------- détails du village (stores, terrasse, linge, plantes, caisses, réverbères, toits) ---------- */
    const extraUpd = [];
    const stripeTex = (a, b) => { const [c, x] = canvas(128, 64); for (let i = 0; i < 8; i++) { x.fillStyle = i % 2 ? a : b; x.fillRect(i * 16, 0, 16, 64); }
      x.fillStyle = "rgba(0,0,0,.25)"; x.fillRect(0, 56, 128, 8); return tex(c); };
    const awnCols = [["#9b2a2a", "#e8dcc4"], ["#2f5a3a", "#e8dcc4"], ["#2c4566", "#d9cfb8"], ["#8a5a1c", "#eadfc8"]];
    houses.forEach((hs, i) => {
      if (i % 3 !== 1) return;
      const zc = (hs.z0 + hs.z1) / 2, [ca, cb2] = awnCols[i % awnCols.length];
      const aw = add(new THREE.Mesh(new THREE.PlaneGeometry(1.0, Math.min(2.2, hs.w * .55)), new THREE.MeshStandardMaterial({ map: stripeTex(ca, cb2), roughness: .8, side: THREE.DoubleSide })));
      aw.rotation.set(-Math.PI / 2, 0, 0); aw.rotateOnWorldAxis(new THREE.Vector3(0, 0, 1), hs.side * .42);
      aw.position.set(hs.fx - hs.side * .46, FLOOR + 2.7, zc);
      const val = add(new THREE.Mesh(new THREE.PlaneGeometry(Math.min(2.2, hs.w * .55), .22), aw.material)); val.rotation.y = hs.side * Math.PI / 2;
      val.position.set(hs.fx - hs.side * .92, FLOOR + 2.4, zc);
    });
    // terrasse de café sous un parasol
    const wood = new THREE.MeshStandardMaterial({ color: 0x5b3a22, roughness: .7 }), ironM = new THREE.MeshStandardMaterial({ color: 0x18191b, metalness: .7, roughness: .4 });
    [[3.1, -6.2], [3.4, -8.4]].forEach(([tx, tz], k) => {
      const top = add(new THREE.Mesh(new THREE.CylinderGeometry(.42, .42, .04, 24), new THREE.MeshStandardMaterial({ color: 0xd8d2c4, roughness: .3 }))); top.position.set(tx, FLOOR + .75, tz);
      const leg = add(new THREE.Mesh(new THREE.CylinderGeometry(.03, .05, .75, 8), ironM)); leg.position.set(tx, FLOOR + .375, tz);
      for (let c = 0; c < 2; c++) { const ch = add(new THREE.Mesh(new THREE.BoxGeometry(.42, .05, .42), wood)); ch.position.set(tx + (c ? .65 : -.65), FLOOR + .46, tz);
        const bk = add(new THREE.Mesh(new THREE.BoxGeometry(.05, .5, .42), wood)); bk.position.set(tx + (c ? .86 : -.86), FLOOR + .72, tz); }
      if (k === 0) { const pole = add(new THREE.Mesh(new THREE.CylinderGeometry(.025, .025, 2.4, 8), ironM)); pole.position.set(tx, FLOOR + 1.2, tz);
        const um = add(new THREE.Mesh(new THREE.ConeGeometry(1.5, .55, 8, 1, true), new THREE.MeshStandardMaterial({ map: stripeTex("#e8dcc4", "#9b2a2a"), side: THREE.DoubleSide, roughness: .8 })));
        um.position.set(tx, FLOOR + 2.45, tz); }
      const cnd = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(255,210,140,1)"], [1, "rgba(255,150,60,0)"]], 32), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })));
      cnd.position.set(tx, FLOOR + .84, tz); cnd.scale.setScalar(.35); extraUpd.push((dt, t) => { cnd.material.opacity = .7 + .3 * Math.sin(t * 17 + k * 3) * Math.sin(t * 7.1); });
    });
    // linge tendu entre les façades
    const clothCols = [0xd9d2c0, 0x7b2d2d, 0x2e4e74, 0xc9a23a, 0xe7e2d6, 0x3f6a45];
    [-8.5, -21].forEach((lz, j) => {
      const y0 = FLOOR + 6.3 + j * .4, pts = [];
      for (let i = 0; i <= 16; i++) { const t = i / 16; pts.push(new THREE.Vector3(-4.6 + 9.2 * t, y0 - Math.sin(t * Math.PI) * .45, lz)); }
      add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x0a0a0a })));
      for (let i = 2; i < 15; i += 2) {
        const cl = add(new THREE.Mesh(new THREE.PlaneGeometry(.45 + rnd() * .25, .6 + rnd() * .35), new THREE.MeshStandardMaterial({ color: clothCols[(i + j) % clothCols.length], roughness: .9, side: THREE.DoubleSide })));
        cl.geometry.translate(0, -.32, 0); cl.position.copy(pts[i]); const ph = rnd() * 6; extraUpd.push((dt, t) => { cl.rotation.x = Math.sin(t * 1.3 + ph) * .12; });
      }
    });
    // cyprès et oliviers en pots, caisses et tonneaux
    const foliage = (() => { const [c, x] = canvas(128, 256), r2 = rng(5); x.fillStyle = "#16261a"; x.fillRect(0, 0, 128, 256); for (let i = 0; i < 40; i++) leaves(x, r2() * 128, r2() * 256, 18, 30, r2, i % 2 === 0); return tex(c); })();
    const pot = new THREE.MeshStandardMaterial({ color: 0x8e4a2c, roughness: .8 });
    [[-3.85, -8.2], [3.9, -16.5], [-3.9, -12.5]].forEach(([px, pz], k) => {
      const pp = add(new THREE.Mesh(new THREE.CylinderGeometry(.32, .25, .55, 16), pot)); pp.position.set(px, FLOOR + .27, pz);
      const tr = add(new THREE.Mesh(k === 1 ? new THREE.SphereGeometry(.75, 16, 12) : new THREE.ConeGeometry(.42, 3.1, 12), new THREE.MeshStandardMaterial({ map: foliage, roughness: .9 })));
      tr.position.set(px, FLOOR + (k === 1 ? 1.4 : 2.05), pz); const ph = k * 2; extraUpd.push((dt, t) => { tr.rotation.z = Math.sin(t * .9 + ph) * .02; });
    });
    const crateTex = (() => { const [c, x] = canvas(128, 128); x.fillStyle = "#6a4a2a"; x.fillRect(0, 0, 128, 128); x.strokeStyle = "#3a2614"; x.lineWidth = 6;
      x.strokeRect(3, 3, 122, 122); for (let k = 0; k < 4; k++) { x.beginPath(); x.moveTo(0, k * 32 + 16); x.lineTo(128, k * 32 + 16); x.lineWidth = 2; x.stroke(); }
      x.lineWidth = 6; x.beginPath(); x.moveTo(6, 6); x.lineTo(122, 122); x.stroke(); return tex(c); })();
    [[-3.7, -6.8, 0], [-3.4, -7.3, 1], [3.75, -11.6, 0]].forEach(([cx, cz, k]) => {
      const cr = add(new THREE.Mesh(new THREE.BoxGeometry(.6, .6, .6), new THREE.MeshStandardMaterial({ map: crateTex, roughness: .85 }))); cr.position.set(cx, FLOOR + .3 + k * .6, cz); cr.rotation.y = k * .4;
    });
    [[-3.75, -9.4], [3.8, -4.4]].forEach(([bx2, bz]) => { const br = add(new THREE.Mesh(new THREE.CylinderGeometry(.3, .3, .85, 16), new THREE.MeshStandardMaterial({ color: 0x4a3020, roughness: .7 }))); br.position.set(bx2, FLOOR + .43, bz); });
    // réverbères en fer forgé
    [[-3.55, -10.8], [3.55, -14.2]].forEach(([lx, lz]) => {
      const pole = add(new THREE.Mesh(new THREE.CylinderGeometry(.045, .07, 3.8, 10), ironM)); pole.position.set(lx, FLOOR + 1.9, lz);
      const head = add(new THREE.Mesh(new THREE.CylinderGeometry(.16, .1, .34, 6), ironM)); head.position.set(lx, FLOOR + 3.9, lz);
      const gl = add(new THREE.Mesh(new THREE.CylinderGeometry(.12, .08, .22, 6), new THREE.MeshBasicMaterial({ color: new THREE.Color(2, 1.35, .7), toneMapped: false }))); gl.position.copy(head.position);
      const hl = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(255,200,120,.85)"], [.3, "rgba(255,160,70,.2)"], [1, "rgba(255,140,60,0)"]]), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: false })));
      hl.position.copy(head.position); hl.scale.setScalar(2.6);
    });
    // toits : cheminées, antennes, paraboles (touche futuriste) avec feux clignotants
    const chimM = new THREE.MeshStandardMaterial({ color: 0x7a5a44, roughness: .9 });
    houses.forEach((hs, i) => {
      const zc = (hs.z0 + hs.z1) / 2, rx = hs.fx + hs.side * 2.2;
      if (i % 2 === 0) { const ch = add(new THREE.Mesh(new THREE.BoxGeometry(.5, 1.1, .5), chimM)); ch.position.set(rx, FLOOR + hs.h + 1.1, zc - .6); }
      if (i % 3 === 0) {
        const an = add(new THREE.Mesh(new THREE.CylinderGeometry(.015, .015, 2.2, 6), ironM)); an.position.set(rx + hs.side * .6, FLOOR + hs.h + 1.9, zc + .4);
        for (let k = 0; k < 3; k++) { const bar = add(new THREE.Mesh(new THREE.BoxGeometry(.6 - k * .15, .015, .015), ironM)); bar.position.set(an.position.x, an.position.y + .4 + k * .25, an.position.z); }
        const red = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(255,60,50,1)"], [1, "rgba(255,0,0,0)"]], 32), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: false })));
        red.position.set(an.position.x, an.position.y + 1.15, an.position.z); red.scale.setScalar(.45); const ph = i * .37;
        extraUpd.push((dt, t) => { red.material.opacity = ((t + ph) % 1.6) < .18 ? 1 : .08; });
      }
      if (i % 4 === 2) {
        const dish = add(new THREE.Mesh(new THREE.SphereGeometry(.55, 20, 10, 0, Math.PI * 2, 0, Math.PI / 3.2), new THREE.MeshStandardMaterial({ color: 0xc8ccd2, metalness: .6, roughness: .35, side: THREE.DoubleSide })));
        dish.position.set(rx, FLOOR + hs.h + 1.4, zc); dish.rotation.set(-hs.side * .9, 0, hs.side * .5);
        const tip = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(120,230,255,1)"], [1, "rgba(0,160,255,0)"]], 32), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: false })));
        tip.position.copy(dish.position).add(new THREE.Vector3(-hs.side * .3, .25, 0)); tip.scale.setScalar(.3);
        extraUpd.push((dt, t) => { tip.material.opacity = .5 + .5 * Math.sin(t * 3 + i); });
      }
    });
    // au loin : collines sombres et lumières d'autres villages
    const hills = (() => { const W = 2048, H = 256, [c, x] = canvas(W, H), r2 = rng(9);
      const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(.5, "rgba(30,45,70,.25)"); g.addColorStop(1, "rgba(40,60,90,.35)"); x.fillStyle = g; x.fillRect(0, 0, W, H);
      x.fillStyle = "#05080e"; x.beginPath(); x.moveTo(0, H);
      for (let i = 0; i <= 64; i++) { const px = i / 64 * W; x.lineTo(px, H * (.38 + .22 * Math.sin(i * .41) * Math.sin(i * .13 + 1) + r2() * .06)); }
      x.lineTo(W, H); x.fill();
      for (let i = 0; i < 260; i++) { const px = r2() * W, py = H * (.62 + r2() * .36); x.fillStyle = r2() < .8 ? `rgba(255,${190 + r2() * 50 | 0},120,${.5 + r2() * .5})` : "rgba(160,220,255,.8)"; x.fillRect(px, py, 2, 2); }
      return tex(c); })();
    const hillM = add(new THREE.Mesh(new THREE.CylinderGeometry(55, 55, 16, 64, 1, true, Math.PI * .6, Math.PI * .8), new THREE.MeshBasicMaterial({ map: hills, transparent: true, fog: false, side: THREE.BackSide, depthWrite: false })));
    hillM.position.set(0, FLOOR + 4, -18);
    // brume au ras du sol
    const mistTex = (() => { const [c, x] = canvas(256, 128), r2 = rng(12); for (let i = 0; i < 60; i++) { const px = r2() * 256, py = 40 + r2() * 60, r = 20 + r2() * 40;
      const g = x.createRadialGradient(px, py, 0, px, py, r); g.addColorStop(0, "rgba(170,190,215,.18)"); g.addColorStop(1, "rgba(170,190,215,0)"); x.fillStyle = g; x.fillRect(0, 0, 256, 128); } return tex(c); })();
    for (let i = 0; i < 9; i++) {
      const m = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: mistTex, transparent: true, depthWrite: false, opacity: .3 })));
      m.scale.set(9, 2.2, 1); const z0 = -6 - i * 3.2, sp = .12 + rnd() * .2, x0 = (rnd() - .5) * 8;
      extraUpd.push((dt, t) => { m.position.set(((x0 + t * sp + 10) % 20) - 10, FLOOR + .55, z0); });
    }
    // vapeur qui sort d'une grille d'égout
    const grate = add(new THREE.Mesh(new THREE.PlaneGeometry(.7, .45), new THREE.MeshStandardMaterial({ map: (() => { const [c, x] = canvas(64, 64); x.fillStyle = "#111"; x.fillRect(0, 0, 64, 64);
      x.fillStyle = "#333"; for (let k = 0; k < 8; k++) x.fillRect(4 + k * 7.5, 4, 3, 56); return tex(c); })(), metalness: .6, roughness: .5 })));
    grate.rotation.x = -Math.PI / 2; grate.position.set(-2.9, FLOOR + .006, -4.6);
    const steamTex = radial([[0, "rgba(200,210,225,.35)"], [1, "rgba(200,210,225,0)"]], 64), puffs = [];
    for (let i = 0; i < 18; i++) { const sp = add(new THREE.Sprite(new THREE.SpriteMaterial({ map: steamTex, transparent: true, depthWrite: false }))); sp.userData.ph = i / 18; puffs.push(sp); }
    extraUpd.push((dt, t) => { for (const sp of puffs) { const q = (t * .18 + sp.userData.ph) % 1; sp.position.set(-2.9 + Math.sin(q * 5 + sp.userData.ph * 9) * .25, FLOOR + q * 3.2, -4.6);
      sp.scale.setScalar(.4 + q * 1.8); sp.material.opacity = Math.sin(q * Math.PI) * .55; } });
    // caniveau où l'eau de pluie s'écoule
    const water = (() => { const [c, x] = canvas(64, 512), r2 = rng(4); x.fillStyle = "#0b1622"; x.fillRect(0, 0, 64, 512);
      for (let i = 0; i < 160; i++) { x.strokeStyle = `rgba(150,190,230,${.1 + r2() * .25})`; x.lineWidth = 1 + r2() * 2; const px = r2() * 64, py = r2() * 512; x.beginPath(); x.moveTo(px, py); x.lineTo(px + (r2() - .5) * 6, py + 10 + r2() * 30); x.stroke(); }
      const t2 = tex(c, true, [1, 18]); return t2; })();
    const gutter = add(new THREE.Mesh(new THREE.PlaneGeometry(.4, 40), new THREE.MeshStandardMaterial({ map: water, roughness: .05, metalness: .2, envMapIntensity: 1.2 })));
    gutter.rotation.x = -Math.PI / 2; gutter.position.set(-3.95, FLOOR + .008, -16);
    extraUpd.push((dt) => { water.offset.y -= dt * .9; });

    /* ---------- couche futuriste : projecteurs, véhicule volant, panneaux holo, flux de données ---------- */
    const beams = [];
    [[-14, -42], [16, -46]].forEach(([bx2, bz], k) => {
      const b = add(new THREE.Mesh(new THREE.ConeGeometry(2.4, 60, 24, 1, true), new THREE.MeshBasicMaterial({ map: vgrad([[0, "rgba(255,255,255,0)"], [.85, "rgba(255,255,255,.6)"], [1, "rgba(255,255,255,.9)"]]),
        color: k ? 0x9fd8ff : 0xbfe8ff, transparent: true, opacity: .05, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false })));
      b.geometry.translate(0, -30, 0); b.position.set(bx2, FLOOR, bz); beams.push(b);
    });
    extraUpd.push((dt, t) => { beams.forEach((b, k) => { b.rotation.z = Math.PI + Math.sin(t * .23 + k * 2) * .5; b.rotation.x = Math.sin(t * .17 + k) * .25; }); });
    const ship = new THREE.Group(); scene.add(ship);
    const hull = new THREE.Mesh(new THREE.BoxGeometry(2.2, .35, .9), new THREE.MeshStandardMaterial({ color: 0x1a1d22, metalness: .8, roughness: .3 })); ship.add(hull);
    const strip = new THREE.Mesh(new THREE.BoxGeometry(2.25, .05, .92), new THREE.MeshBasicMaterial({ color: new THREE.Color(.3, 1.6, 2.2), toneMapped: false })); strip.position.y = -.1; ship.add(strip);
    for (const sx of [-1.1, 1.1]) { const th = new THREE.Sprite(new THREE.SpriteMaterial({ map: radial([[0, "rgba(160,230,255,1)"], [1, "rgba(0,140,255,0)"]], 64), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: false }));
      th.position.set(sx, -.15, 0); th.scale.setScalar(1.4); ship.add(th); }
    let shipT = -1, nextShip = 6 + rnd() * 10;
    ship.visible = false;
    extraUpd.push((dt, t) => {
      if (shipT < 0 && t > nextShip) { shipT = 0; ship.visible = true; emit("vaisseau"); }
      if (shipT >= 0) { shipT += dt / 7; const q = shipT; ship.position.set(-26 + 52 * q, FLOOR + 11 + Math.sin(q * 3) * .6, -24 + q * 6); ship.rotation.z = -.08; ship.rotation.y = -.2;
        if (q >= 1) { shipT = -1; ship.visible = false; nextShip = t + 22 + rnd() * 25; } }
    });
    const holoBoard = (lines, color, w, h, x0, y0, z0, ry) => {
      const [c, x] = canvas(512, 512 * h / w | 0), H = c.height;
      x.strokeStyle = color; x.lineWidth = 6; x.shadowColor = color; x.shadowBlur = 18; x.strokeRect(8, 8, 496, H - 16);
      x.fillStyle = color; x.globalAlpha = .12; x.fillRect(8, 8, 496, H - 16); x.globalAlpha = 1;
      x.font = "700 54px 'Barlow Condensed', 'Arial Narrow', sans-serif"; x.textAlign = "center"; x.fillStyle = "#e9fbff";
      lines.forEach((l, i) => x.fillText(l, 256, 80 + i * 64));
      for (let k = 0; k < H; k += 6) { x.fillStyle = "rgba(0,0,0,.18)"; x.fillRect(8, k, 496, 2); }
      const m = add(new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex(c), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false, side: THREE.DoubleSide })));
      m.position.set(x0, y0, z0); m.rotation.y = ry; const ph = rnd() * 9;
      extraUpd.push((dt, t) => { const gl = Math.sin(t * 23 + ph) > .96; m.material.opacity = gl ? .35 : .85 + .15 * Math.sin(t * 2 + ph); m.position.x = x0 + (gl ? (Math.random() - .5) * .06 : 0); m.position.y = y0 + Math.sin(t * .8 + ph) * .05; });
    };
    holoBoard(["OUVERTURE DE CAISSE", "★ CHANCE x2 ★", "CE SOIR"], "#f2a93b", 2.2, 1.3, 3.9, FLOOR + 4.6, -9.6, -Math.PI / 2 + .25);
    holoBoard(["FINALE MAJOR", "21:00", "EN DIRECT"], "#4fd8ff", 1.9, 1.15, -3.95, FLOOR + 4.9, -13.4, Math.PI / 2 - .25);
    const streamTex = (() => { const [c, x] = canvas(32, 512), r2 = rng(21); for (let i = 0; i < 90; i++) { x.fillStyle = `rgba(120,230,255,${.2 + r2() * .8})`; x.fillRect(r2() * 28, r2() * 512, 3, 4 + r2() * 20); } return tex(c, true, [1, 2]); })();
    [[-3.1, -15.4 + 1.42], [3.1, -15.4 + 1.42]].forEach(([sx2, sz]) => {
      const sm = add(new THREE.Mesh(new THREE.PlaneGeometry(.35, 7), new THREE.MeshBasicMaterial({ map: streamTex, transparent: true, opacity: .7, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false })));
      sm.position.set(sx2 + (sx2 < 0 ? -1.3 : 1.3), FLOOR + 3.6, sz + .02);
    });
    extraUpd.push((dt) => { streamTex.offset.y -= dt * .35; });

    // « studio » de reflets pour la laque et le métal : la nuit du village, plus une lumière douce
    D.envScene = function () {
      const s = new THREE.Scene();
      s.add(new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16), new THREE.MeshBasicMaterial({ map: skyMat.map, side: THREE.BackSide })));
      const box = (w, h, x, y, z, r, g, b) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(r, g, b), side: THREE.DoubleSide })); m.position.set(x, y, z); m.lookAt(0, 0, 0); s.add(m); };
      box(5, 2.4, -4, 5, 3, 3.2, 3.1, 3.4);              // lumière douce de lune au-dessus
      box(1.4, 3, -6, 1, -2, 3.5, 2.2, 1.1); box(1.4, 3, 6, 1.2, -3, 3.5, 2.2, 1.1);   // fenêtres chaudes
      box(3, .4, 5, 2, 2, .5, 2.4, 3.2);                 // néon cyan
      box(2.4, .35, -5, 2.4, -1, 3, .6, 1.4);            // néon rose
      box(9, .8, 0, 6, -5, 1.2, 1.3, 1.6);               // contre-jour du ciel
      return s;
    };

    /* ---------- animation ---------- */
    let nextBolt = performance.now() / 1000 + 9 + Math.random() * 10, bolt = null, scanT = 0, dronePh = 0;
    D.update = function (dt, t, cam) {
      rainMat.uniforms.uT.value = t; splashMat.uniforms.uT.value = t;
      // éclairs : deux ou trois flashs, puis le tonnerre (joué par la page)
      if (!bolt && t > nextBolt) { bolt = { t0: t, power: .6 + Math.random() * .4 }; emit("eclair", bolt.power); }
      let flash = 0;
      if (bolt) {
        const q = t - bolt.t0; flash = (q < .08 ? 1 : q < .16 ? .15 : q < .26 ? .75 : q < .5 ? .3 * (1 - (q - .26) / .24) : 0) * bolt.power;
        if (q > .6) { bolt = null; nextBolt = t + 14 + Math.random() * 22; }
      }
      flashL.intensity = flash * 4; hemi.intensity = .16 + flash * 1.4;
      skyMat.color.setScalar(1 + flash * 2.6);
      rainMat.uniforms.uFlash.value = flash; splashMat.uniforms.uFlash.value = flash;
      // lanternes qui vacillent, guirlandes, néons qui grésillent
      for (const l of lanterns) { const f = .85 + .15 * Math.sin(t * 13 + l.ph) * Math.sin(t * 7.3 + l.ph * 2); l.halo.material.opacity = f; if (l.light) l.light.intensity = 7 * f; }
      for (const b of bulbs) b.material.opacity = .75 + .25 * Math.sin(t * 2 + b.userData.ph);
      for (const n of neons) { const g = Math.sin(t * 40 + n.ph) > .97 || (Math.sin(t * .7 + n.ph) > .995) ? .25 : 1; n.m.material.opacity = g; }
      boardX = (boardX + dt * 120) % 2400;
      bx.clearRect(0, 0, 1024, 128); bx.font = "700 64px 'Barlow Condensed', 'Arial Narrow', sans-serif"; bx.textBaseline = "middle";
      bx.shadowColor = "#4fd8ff"; bx.shadowBlur = 16; bx.fillStyle = "#9fe9ff";
      bx.fillText(boardText + boardText, -boardX, 66); bx.strokeStyle = "rgba(79,216,255,.8)"; bx.lineWidth = 4; bx.strokeRect(2, 2, 1020, 124); boardTex.needsUpdate = true;
      // socle holographique : anneaux qui tournent, rayon de scan toutes les 7 s
      hex.rotation.z = t * .15; orbits.forEach((o, i) => { o.rotation.z = t * (.25 + i * .12) * (i % 2 ? -1 : 1); });
      lip.material.opacity = 1;
      const pa = motes.geometry.attributes.position;
      for (let i = 0; i < NP; i++) { let y = pa.getY(i) + pv[i] * dt; if (y > 3.6) y = .2; pa.setY(i, y); }
      pa.needsUpdate = true;
      scanT += dt; const sq = scanT % 7;
      if (sq < 1.6) { scan.position.y = .25 + 3.0 * (sq / 1.6); scanMat.opacity = Math.sin(sq / 1.6 * Math.PI) * .9; if (sq < dt * 1.5) emit("scan"); } else scanMat.opacity = 0;
      // drone en patrouille
      dronePh += dt * .18;
      drone.position.set(Math.sin(dronePh) * 3.4, FLOOR + 5.2 + Math.sin(dronePh * 2.3) * .3, -6 + Math.cos(dronePh) * 3.2);
      drone.rotation.y = -dronePh; drone.rotation.z = Math.sin(dronePh * 1.7) * .08;
      blink.material.opacity = (t % 1.2) < .12 ? 1 : 0;
      for (const f of extraUpd) f(dt, t, flash);
      return flash;
    };
    // la nuit : les reflets « studio » sont réservés au skin, le village garde sa pénombre
    scene.traverse((m) => {
      const mats = m.material ? (Array.isArray(m.material) ? m.material : [m.material]) : [];
      for (const mt of mats) if (mt.isMeshStandardMaterial) { mt.envMapIntensity = m === ground ? .7 : .12; if (m !== ground && !mt.metalness) mt.color.multiply(new THREE.Color(.62, .64, .74)); }
    });
    D.setRarity = function (hex) { const c = new THREE.Color(hex); for (const m of rarityMats) m.color.copy(c); };
    D.on = (n, f) => { (listeners[n] = listeners[n] || []).push(f); };
    D.lampLights = lampLights;
    return D;
  };

  window.VitrineDecor = D;
})();
