/* Vitrine CS2 en 3D (three.js r128, local) — le skin devient un vrai objet 3D :
   épaisseur et arêtes arrondies tirées de sa silhouette, relief de la peinture, laque / métal qui reflètent la
   lumière, sol réfléchissant, cône de lumière, braises 3D, halo et paillettes, bloom façon cinéma.
   L'image officielle Steam sert de peinture : rien n'est inventé sur le skin lui-même. */
(function () {
  "use strict";
  const T = () => window.THREE;
  const V = { ready: false };
  const FLOOR = -1.0;
  let R, scene, cam, composer, finalPass, bgTex, glow, ring, cone, embers, emberVel, keyL, rimA, rimB, sweepL, holder;
  let items = [], rarity = null, lastNow = 0, decor = null, SKIN_Y = .22, CAM_Y = .2, LOOK_Y = .02;
  const st = { yaw: 0, pitch: 0, vy: 0, vp: 0, drag: null, lastUser: -1e9, zoom: 1, inspect: false, mx: 0, my: 0, smx: 0, smy: 0 };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const ease = (t) => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const easeOutBack = (t) => { const c = 1.45; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };

  function gradTex(stops, w = 256, h = 256, radial = true) {
    const c = document.createElement("canvas"); c.width = w; c.height = h; const x = c.getContext("2d");
    const g = radial ? x.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2) : x.createLinearGradient(0, 0, 0, h);
    for (const [o, col] of stops) g.addColorStop(o, col);
    x.fillStyle = g; x.fillRect(0, 0, w, h);
    return new (T().CanvasTexture)(c);
  }

  /* ---------- un « studio photo » invisible qui se reflète dans la laque et le métal ---------- */
  function envScene() {
    const THREE = T(), s = new THREE.Scene();
    const sky = gradTex([[0, "#4a505a"], [.42, "#1c2026"], [.55, "#0c0e11"], [1, "#050607"]], 64, 256, false);
    s.add(new THREE.Mesh(new THREE.SphereGeometry(10, 32, 16), new THREE.MeshBasicMaterial({ map: sky, side: THREE.BackSide })));
    const box = (w, h, x, y, z, r, g, b) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(r, g, b), side: THREE.DoubleSide }));
      m.position.set(x, y, z); m.lookAt(0, 0, 0); s.add(m);
    };
    box(7, 3.2, -4, 5, 3, 7, 5.6, 4.2);        // grande boîte à lumière chaude en haut à gauche
    box(1.2, 8, 6, 0, -1, 2.2, 3.6, 5.5);      // bande froide à droite (reflet long sur les lames)
    box(3, 1, 0, -2, 6, 1.6, 1.3, 1);          // petit rebond devant
    box(9, 1.2, 0, 7, -4, 3, 3, 3.2);          // contre-jour
    return s;
  }

  V.init = async function (canvas, bgCanvas) {
    const THREE = T();
    if (!THREE) throw new Error("three.js absent");
    R = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    R.setPixelRatio(Math.min(devicePixelRatio || 1, 1.75));
    R.setSize(innerWidth, innerHeight, false);
    R.outputEncoding = THREE.sRGBEncoding;
    R.toneMapping = THREE.ACESFilmicToneMapping;
    R.toneMappingExposure = 1.05;
    scene = new THREE.Scene();
    cam = new THREE.PerspectiveCamera(30, innerWidth / innerHeight, .1, 140);
    const pm = new THREE.PMREMGenerator(R);
    // décor du village de nuit (web/vitrine_decor.js) s'il est là, sinon le studio sombre d'origine
    try { decor = window.VitrineDecor ? await window.VitrineDecor.build({ THREE, scene, R, FLOOR }) : null; } catch (e) { console.error(e); decor = null; scene.fog = null; }
    if (decor) {
      SKIN_Y = .5; CAM_Y = .62; LOOK_Y = .32; V.on = decor.on;
      R.toneMappingExposure = .82;
      scene.environment = pm.fromScene(decor.envScene(), .035).texture;
      // éclairage de théâtre : seul le skin est dans la lumière, la ruelle reste dans la nuit
      keyL = new THREE.SpotLight(0xfff0dc, 10, 16, .36, .55, 1.2); keyL.position.set(-2.4, 5.4, 5.2); keyL.target.position.set(0, SKIN_Y, 0); scene.add(keyL, keyL.target);
      rimA = new THREE.PointLight(0xffffff, 3.4, 6, 1.6); rimB = new THREE.PointLight(0xffffff, 2.2, 6, 1.6);
    } else {
      bgTex = new THREE.CanvasTexture(bgCanvas); bgTex.encoding = THREE.sRGBEncoding;
      scene.background = bgTex;
      scene.environment = pm.fromScene(envScene(), .035).texture;
      scene.add(new THREE.HemisphereLight(0x8a96a8, 0x1a1208, .45));
      keyL = new THREE.DirectionalLight(0xffe4be, 2.4); keyL.position.set(-3, 4, 5); scene.add(keyL);
      rimA = new THREE.PointLight(0xffffff, 3.2, 14, 1.6); rimB = new THREE.PointLight(0xffffff, 2, 14, 1.6);
    }
    V.on = V.on || (() => {}); V.hasDecor = !!decor;
    cam.position.set(0, CAM_Y, 6);
    // contre-jours à la couleur de la rareté, et un reflet qui suit la souris
    rimA.position.set(3.4, 1.4, -2.2); scene.add(rimA);
    rimB.position.set(-3.6, -.6, -2.4); scene.add(rimB);
    sweepL = new THREE.PointLight(0xfff6e8, 2.2, 7, 1.8); sweepL.position.set(0, 0, 2.4); scene.add(sweepL);
    // halo derrière l'objet
    glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: gradTex([[0, "rgba(255,255,255,.95)"], [.35, "rgba(255,255,255,.28)"], [1, "rgba(255,255,255,0)"]]),
      blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: .3 }));
    glow.scale.set(6.5, 4.6, 1); glow.position.set(0, SKIN_Y, -1.6); scene.add(glow);
    if (decor) glow.material.opacity = .16;
    holder = new THREE.Group(); scene.add(holder);
    if (!decor) studio(THREE);
    composerSetup(THREE);
    // shaders compilés maintenant (pendant la caisse) plutôt qu'à la première image : pas d'à-coup à l'arrivée
    await new Promise((r) => setTimeout(r, 0));
    try { R.compile(scene, cam); } catch (e) {}
    V.ready = true;
    requestAnimationFrame(frame);
  };
  function studio(THREE) {
    // sol sombre et brillant (on voit le reflet de l'objet au travers), quadrillage discret
    const fc = document.createElement("canvas"); fc.width = fc.height = 1024; const fx = fc.getContext("2d");
    const fg = fx.createRadialGradient(512, 512, 0, 512, 512, 512);
    fg.addColorStop(0, "rgba(6,8,11,.74)"); fg.addColorStop(.55, "rgba(6,8,11,.86)"); fg.addColorStop(1, "rgba(6,8,11,0)");
    fx.fillStyle = fg; fx.fillRect(0, 0, 1024, 1024);
    fx.globalCompositeOperation = "source-atop"; fx.strokeStyle = "rgba(236,230,218,.035)"; fx.lineWidth = 2;
    for (let k = 0; k <= 1024; k += 64) { fx.beginPath(); fx.moveTo(k, 0); fx.lineTo(k, 1024); fx.moveTo(0, k); fx.lineTo(1024, k); fx.stroke(); }
    const floorTex = new THREE.CanvasTexture(fc); floorTex.anisotropy = R.capabilities.getMaxAnisotropy();
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), new THREE.MeshBasicMaterial({ map: floorTex, transparent: true, depthWrite: false }));
    floor.rotation.x = -Math.PI / 2; floor.position.y = FLOOR; floor.renderOrder = 2; scene.add(floor);
    ring = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), new THREE.MeshBasicMaterial({ map: gradTex([[0, "rgba(255,255,255,.55)"], [.4, "rgba(255,255,255,.12)"], [1, "rgba(255,255,255,0)"]]),
      blending: THREE.AdditiveBlending, transparent: true, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2; ring.position.y = FLOOR + .005; ring.renderOrder = 3; scene.add(ring);
    // cône de lumière qui tombe du plafond
    const coneTex = gradTex([[0, "rgba(255,255,255,0)"], [.25, "rgba(255,255,255,.55)"], [1, "rgba(255,255,255,0)"]], 8, 256, false);
    cone = new THREE.Mesh(new THREE.CylinderGeometry(.35, 2.6, 6.5, 64, 1, true), new THREE.MeshBasicMaterial({ map: coneTex, color: 0xffe0b0,
      transparent: true, opacity: .035, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    cone.position.set(0, 1.9, -.4); scene.add(cone);
    // braises en 3D
    const N = 320, pos = new Float32Array(N * 3); emberVel = new Float32Array(N);
    for (let i = 0; i < N; i++) { pos[i * 3] = (Math.random() - .5) * 12; pos[i * 3 + 1] = FLOOR + Math.random() * 6; pos[i * 3 + 2] = -4 + Math.random() * 6; emberVel[i] = .12 + Math.random() * .35; }
    const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    embers = new THREE.Points(eg, new THREE.PointsMaterial({ size: .035, map: gradTex([[0, "rgba(255,255,255,1)"], [.3, "rgba(255,200,120,.6)"], [1, "rgba(255,160,60,0)"]], 64, 64),
      color: 0xffb060, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    scene.add(embers);
  }
  function composerSetup(THREE) {
    // rendu cinéma : bloom + aberration chromatique légère + vignette + grain
    composer = new THREE.EffectComposer(R);
    composer.addPass(new THREE.RenderPass(scene, cam));
    composer.addPass(new THREE.UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .5, .5, .86));
    finalPass = new THREE.ShaderPass({
      uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uRes: { value: new THREE.Vector2(innerWidth, innerHeight) }, uDim: { value: 0 }, uFlash: { value: 0 } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: `uniform sampler2D tDiffuse; uniform float uTime; uniform vec2 uRes; uniform float uDim; uniform float uFlash; varying vec2 vUv;
        void main(){ vec2 c = vUv - .5; float d = dot(c, c); vec2 o = c * d * .016;
          vec3 col = vec3(texture2D(tDiffuse, vUv + o).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - o).b);
          col *= 1. - d * (.95 + uDim); col += vec3(.55, .65, .9) * uFlash * .12; col = pow(max(col, 0.), vec3(1. / 2.2));
          float n = fract(sin(dot(floor(vUv * uRes) + floor(uTime * 24.), vec2(12.9898, 78.233))) * 43758.5453);
          gl_FragColor = vec4(col + (n - .5) * .03, 1.); }`,
    });
    composer.addPass(finalPass);
    addEventListener("resize", () => {
      R.setSize(innerWidth, innerHeight, false); composer.setSize(innerWidth, innerHeight);
      cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); finalPass.uniforms.uRes.value.set(innerWidth, innerHeight);
    });
  }

  /* ---------- HOLOGRAMME VOLUMÉTRIQUE ----------
     On n'a pas les modèles 3D de Valve : extruder l'image donnait des tranches étirées et moches de profil.
     À la place : l'image officielle (rendu 3D du vrai skin par Steam), nette et fidèle, projetée en hologramme :
     contour lumineux à la couleur de la rareté, reflet qui glisse quand il tourne, et une « profondeur de lumière »
     (couches translucides derrière) qui donne du volume quand on le fait pivoter. */
  function analyse(img) {
    const W0 = img.naturalWidth, H0 = img.naturalHeight;
    const c = document.createElement("canvas"); c.width = W0; c.height = H0;
    const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(img, 0, 0);
    const d = x.getImageData(0, 0, W0, H0).data;
    let x0 = W0, y0 = H0, x1 = 0, y1 = 0;
    for (let y = 0; y < H0; y += 2) for (let xx = 0; xx < W0; xx += 2) if (d[(y * W0 + xx) * 4 + 3] > 24) { if (xx < x0) x0 = xx; if (xx > x1) x1 = xx; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 <= x0) { x0 = 0; y0 = 0; x1 = W0 - 1; y1 = H0 - 1; }
    const pad = Math.round(Math.max(W0, H0) * .03);
    x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(W0 - 1, x1 + pad); y1 = Math.min(H0 - 1, y1 + pad);
    const cw = x1 - x0 + 1, ch = y1 - y0 + 1;
    const tex = document.createElement("canvas"); tex.width = cw; tex.height = ch;
    tex.getContext("2d").drawImage(c, x0, y0, cw, ch, 0, 0, cw, ch);
    // masque basse définition pour savoir si la souris touche le skin
    const aw = Math.min(256, cw), ah = Math.max(8, Math.round(ch * aw / cw));
    const a = document.createElement("canvas"); a.width = aw; a.height = ah; const ax = a.getContext("2d", { willReadFrequently: true });
    ax.drawImage(tex, 0, 0, aw, ah); const ad = ax.getImageData(0, 0, aw, ah).data, alpha = new Float32Array(aw * ah);
    for (let i = 0; i < aw * ah; i++) alpha[i] = ad[i * 4 + 3] / 255;
    const spots = [];
    for (let k = 0; k < 600 && spots.length < 8; k++) { const i = Math.random() * aw * ah | 0; if (alpha[i] > .9) spots.push([(i % aw) / aw, (i / aw | 0) / ah]); }
    return { tex, aspect: cw / ch, aw, ah, alpha, spots, px: new (T().Vector2)(1 / cw, 1 / ch) };
  }
  function sample(arr, aw, ah, u, v) {
    const x = clamp(u * (aw - 1), 0, aw - 1), y = clamp(v * (ah - 1), 0, ah - 1), x0 = x | 0, y0 = y | 0, x1 = Math.min(aw - 1, x0 + 1), y1 = Math.min(ah - 1, y0 + 1), fx = x - x0, fy = y - y0;
    return (arr[y0 * aw + x0] * (1 - fx) + arr[y0 * aw + x1] * fx) * (1 - fy) + (arr[y1 * aw + x0] * (1 - fx) + arr[y1 * aw + x1] * fx) * fy;
  }
  const HOLO_VS = `varying vec2 vUv; varying vec3 vN; varying vec3 vV;
    void main(){ vUv = uv; vec4 w = modelMatrix * vec4(position, 1.); vN = normalize(mat3(modelMatrix) * normal); vV = normalize(cameraPosition - w.xyz);
      gl_Position = projectionMatrix * viewMatrix * w; }`;
  // la peinture : couleurs fidèles, contour lumineux, reflet qui balaie, fines lignes d'hologramme
  const FACE_FS = `uniform sampler2D uMap; uniform vec3 uRar; uniform float uTime, uSweep, uFade, uBack; uniform vec2 uPx;
    varying vec2 vUv; varying vec3 vN; varying vec3 vV;
    void main(){
      vec4 c = texture2D(uMap, vUv); float a = c.a;
      float m = min(min(texture2D(uMap, vUv + vec2(uPx.x * 3., 0.)).a, texture2D(uMap, vUv - vec2(uPx.x * 3., 0.)).a),
                    min(texture2D(uMap, vUv + vec2(0., uPx.y * 3.)).a, texture2D(uMap, vUv - vec2(0., uPx.y * 3.)).a));
      float edge = clamp(a - m, 0., 1.);
      if (a < .04 && edge < .02) discard;
      vec3 col = pow(c.rgb, vec3(2.2)) * .92;                        // l'image Steam telle quelle (linéaire)
      float facing = abs(dot(normalize(vN), normalize(vV)));
      float band = exp(-pow((vUv.x + vUv.y * .35 - uSweep) * 5., 2.));  // reflet qui glisse quand il tourne
      col += vec3(1.) * band * .16 * a;
      col += uRar * edge * 1.6;                                      // contour lumineux (couleur de la rareté)
      col += uRar * pow(1. - facing, 2.) * .35 * a;                  // vu de biais : il s'allume comme un hologramme
      float scan = .965 + .035 * sin(vUv.y * 900. + uTime * 6.);
      col *= scan;
      col = mix(col, col * .45 + uRar * .12, uBack);                 // de dos : image fantôme, plus sombre
      gl_FragColor = vec4(col * uFade, max(a, edge) * uFade);
    }`;
  // couches de lumière derrière la peinture : le « volume » de l'hologramme
  const SLICE_FS = `uniform sampler2D uMap; uniform vec3 uRar; uniform float uK, uFade, uTime; varying vec2 vUv; varying vec3 vN; varying vec3 vV;
    void main(){ float a = texture2D(uMap, vUv).a; if (a < .3) discard;
      float facing = abs(dot(normalize(vN), normalize(vV)));
      float side = .25 + .75 * pow(1. - facing, 1.5);               // presque invisibles de face, lumineuses de profil
      float flick = .85 + .15 * sin(uTime * 3. + uK * 20.);
      gl_FragColor = vec4(uRar * (1. - uK) * .22 * side * flick * uFade, 1.); }`;
  const NSL = 12;
  function build(an, skin) {
    const THREE = T(), width = Math.min(2.9, 1.75 * an.aspect), h = width / an.aspect;
    const map = new THREE.CanvasTexture(an.tex); map.anisotropy = R.capabilities.getMaxAnisotropy();
    map.minFilter = THREE.LinearMipmapLinearFilter;
    const rar = new THREE.Color(skin.couleur || "#4b69ff");
    const geo = new THREE.PlaneGeometry(width, h);
    const U = { uMap: { value: map }, uRar: { value: rar }, uTime: { value: 0 }, uSweep: { value: 0 }, uFade: { value: 1 }, uBack: { value: 0 }, uPx: { value: an.px } };
    const mkFace = (back) => new THREE.ShaderMaterial({ uniforms: { ...U, uBack: { value: back ? 1 : 0 } }, vertexShader: HOLO_VS, fragmentShader: FACE_FS,
      transparent: true, depthWrite: !back, side: back ? THREE.BackSide : THREE.FrontSide, toneMapped: false });
    const front = new THREE.Mesh(geo, mkFace(false)), back = new THREE.Mesh(geo, mkFace(true));
    front.renderOrder = 3; back.renderOrder = 2;
    const g = new THREE.Group(); g.add(back, front);
    const slices = [];
    const depth = skin.categorie === "gants" ? .26 : skin.categorie === "couteau" ? .12 : .18;
    for (let k = 1; k <= NSL; k++) {
      const m = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms: { uMap: { value: map }, uRar: { value: rar }, uK: { value: k / NSL }, uFade: U.uFade, uTime: U.uTime },
        vertexShader: HOLO_VS, fragmentShader: SLICE_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
      m.position.z = -depth * k / NSL; m.renderOrder = 1; g.add(m); slices.push(m);
    }
    const mirror = new THREE.Group(); mirror.add(new THREE.Mesh(geo, front.material)); mirror.matrixAutoUpdate = false;
    const flares = [];
    if (skin.nom.startsWith("★") || skin.rarete === "Contrebande") {
      const ftex = gradTex([[0, "rgba(255,255,255,1)"], [.12, "rgba(255,240,200,.8)"], [.4, "rgba(255,220,150,.08)"], [1, "rgba(0,0,0,0)"]], 128, 128);
      for (const [u, v] of an.spots) {
        const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: ftex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0 }));
        sp.position.set((u - .5) * width, (.5 - v) * h, .02); sp.userData.ph = Math.random() * 6; g.add(sp); flares.push(sp);
      }
    }
    return { g, mirror, front, back, slices, an, width, flares, U, maps: [map], geo };
  }
  function dispose(it) {
    holder.remove(it.g); holder.remove(it.mirror);
    it.geo.dispose(); it.front.material.dispose(); it.back.material.dispose();
    for (const m of it.slices) m.material.dispose();
    for (const t of it.maps) t.dispose();
    for (const f of it.flares) f.material.dispose();
  }

  function loadImage(url) {
    return new Promise((res, rej) => { const im = new Image(); im.decoding = "async"; im.onload = () => res(im); im.onerror = rej; im.src = url; });
  }
  let showSeq = 0;
  V.show = async function (skin, url, dir = 1) {
    let im; const seq = ++showSeq;
    try { im = await loadImage(url); } catch (e) { return false; }
    if (seq !== showSeq) return false;                // un autre skin a été demandé entre-temps : on ne l'affiche pas en retard
    const an = analyse(im), it = build(an, skin);
    it.t0 = performance.now(); it.dir = dir; it.state = "enter";
    for (const o of items) if (o.state !== "leave") { o.state = "leave"; o.tl = performance.now(); }
    it.mirror.visible = !decor;
    holder.add(it.g, it.mirror); items.push(it);
    V.setRarity(skin.couleur);
    st.yaw = 0; st.pitch = 0; st.vy = st.vp = 0; st.zoom = 1;
    return true;
  };
  V.setRarity = function (hex) {
    const c = new (T().Color)(hex); rarity = c;
    rimA.color.copy(c); rimB.color.copy(c).lerp(new (T().Color)(0xffffff), .35);
    glow.material.color.copy(c); if (ring) ring.material.color.copy(c); if (decor) decor.setRarity(hex);
  };
  V.inspect = (on) => { st.inspect = on; };
  V.mouse = (nx, ny) => { st.mx = nx; st.my = ny; };
  V.zoom = (dy) => { st.zoom = clamp(st.zoom * (dy < 0 ? 1.08 : .93), .6, 2.6); };
  V.dragStart = (x, y) => { st.drag = { x, y }; st.lastUser = performance.now(); };
  V.dragMove = (x, y) => {
    if (!st.drag) return; const dx = x - st.drag.x, dy = y - st.drag.y; st.drag = { x, y };
    st.yaw += dx * .0095; st.pitch = clamp(st.pitch + dy * .0075, -1.2, 1.2); st.vy = dx * .0095; st.vp = dy * .0075; st.lastUser = performance.now();
  };
  V.dragEnd = () => { if (!st.drag) return 0; st.drag = null; st.lastUser = performance.now(); if (Math.abs(st.vy) > .12) st.vy *= 1.8; return Math.abs(st.vy); };
  // l'objet est-il sous la souris ? (en tenant compte des parties transparentes de l'image)
  V.hit = function (cx, cy) {
    const THREE = T(), it = items.find((o) => o.state !== "leave"); if (!it) return false;
    const rc = new THREE.Raycaster(); rc.setFromCamera(new THREE.Vector2(cx / innerWidth * 2 - 1, -(cy / innerHeight) * 2 + 1), cam);
    const hits = rc.intersectObjects([it.front]);
    return hits.some((h) => h.uv && sample(it.an.alpha, it.an.aw, it.an.ah, h.uv.x, 1 - h.uv.y) > .5);
  };

  /* ---------- chaque image ---------- */
  function frame(now) {
    requestAnimationFrame(frame);
    if (V.paused) { lastNow = now; return; }          // écran de caisse par-dessus : rien à dessiner
    const THREE = T(), dt = Math.min(.05, (now - (lastNow || now)) / 1000); lastNow = now;
    const t = now / 1000;
    st.smx += (st.mx - st.smx) * Math.min(1, dt * 4); st.smy += (st.my - st.smy) * Math.min(1, dt * 4);
    // inertie de la rotation à la main, puis retour doux à la chorégraphie
    if (!st.drag) {
      st.yaw += st.vy; st.pitch = clamp(st.pitch + st.vp, -1.2, 1.2); st.vy *= .955; st.vp *= .9;
      if (now - st.lastUser > 3500 && Math.abs(st.vy) < .01) {          // retour doux vers l'avant (tour complet le plus proche)
        const k = Math.min(1, dt * 1.4), full = Math.round(st.yaw / (Math.PI * 2)) * Math.PI * 2;
        st.yaw += (full - st.yaw) * k; st.pitch += (0 - st.pitch) * k;
        if (Math.abs(full - st.yaw) < .002) st.yaw = 0;
      }
    }
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i], g = it.g, tt = (now - it.t0) / 1000;
      // chorégraphie : balancement de trois quarts à trois quarts, léger flottement
      let yaw = Math.sin(tt * .45) * (st.inspect ? .5 : .36) + Math.sin(tt * .17) * .08;
      if (!st.inspect && now - st.lastUser > 3500) yaw += Math.PI * 2 * ease(clamp((tt - 4.2) / 2.6, 0, 1));   // un tour complet au milieu
      let x = 0, s = 1, extraYaw = 0;
      if (it.state === "enter") {
        const e = clamp(tt / 1.15, 0, 1); x = it.dir * 4.6 * Math.pow(1 - e, 3); extraYaw = -it.dir * .9 * (1 - easeOutBack(e)); s = .55 + .45 * easeOutBack(e);
        if (e >= 1) it.state = "idle";
      } else if (it.state === "leave") {
        const q = clamp((now - it.tl) / 650, 0, 1); x = -it.dir * 5.2 * q * q; extraYaw = it.dir * .8 * q; s = 1 - .45 * q;
        if (q >= 1) { dispose(it); items.splice(i, 1); continue; }
      }
      g.position.set(x, SKIN_Y + Math.sin(t * 1.15) * .055, 0);
      g.rotation.set(Math.sin(tt * .6) * .07 + st.pitch, yaw + extraYaw + st.yaw, Math.sin(tt * .38) * .035, "YXZ");
      g.scale.setScalar(s);
      g.updateMatrix();
      it.mirror.matrix.makeTranslation(0, 2 * FLOOR, 0).multiply(new THREE.Matrix4().makeScale(1, -1, 1)).multiply(g.matrix);
      it.mirror.matrixWorldNeedsUpdate = true;
      it.U.uTime.value = t; it.U.uSweep.value = ((g.rotation.y % 6.283) + 6.283) % 6.283 / 6.283 * 3. - .9;   // reflet suit la rotation
      it.U.uFade.value = it.state === "leave" ? 1 - clamp((now - it.tl) / 650, 0, 1) : clamp(tt / .5, 0, 1);
      for (const f of it.flares) {                   // scintillements
        const ph = (t * .7 + f.userData.ph) % 3.2, a = ph < .5 ? Math.sin(ph / .5 * Math.PI) : 0;
        f.material.opacity = a; f.scale.setScalar(.15 + .55 * a); f.material.rotation = t;
      }
    }
    // caméra : lente avancée cinématographique, parallaxe avec la souris, rapprochée en inspection
    const cur = items.find((o) => o.state !== "leave"), tt = cur ? (now - cur.t0) / 1000 : 0;
    const dz = (6.1 - .55 * ease(clamp(tt / 9, 0, 1))) * (st.inspect ? .78 : 1) / st.zoom;
    cam.position.x += (st.smx * .32 - cam.position.x) * Math.min(1, dt * 3);
    cam.position.y += (CAM_Y - st.smy * .16 - cam.position.y) * Math.min(1, dt * 3);
    cam.position.z += (dz - cam.position.z) * Math.min(1, dt * 2.5);
    cam.lookAt(0, LOOK_Y, 0);
    // lumières vivantes
    sweepL.position.set(st.smx * 3.2 + Math.sin(t * .7) * 1.6, -st.smy * 2.2 + SKIN_Y + .4, 2.3);   // reflet qui glisse sur la peinture
    rimA.position.set(3.4 * Math.cos(t * .25), 1.4, -2.2 + Math.sin(t * .25));
    if (decor) { const fl = decor.update(dt, t, cam); glow.material.opacity = .16 + fl * .2; finalPass.uniforms.uFlash.value = fl; }
    else {
      glow.material.opacity = (st.inspect ? .2 : .3) + .05 * Math.sin(t * 1.3);
      ring.scale.setScalar(1 + .06 * Math.sin(t * 1.3));
      cone.rotation.y = t * .05;
      const p = embers.geometry.attributes.position;
      for (let i = 0; i < p.count; i++) {
        let y = p.getY(i) + emberVel[i] * dt; if (y > FLOOR + 6) y = FLOOR;
        p.setY(i, y); p.setX(i, p.getX(i) + Math.sin(t + i) * .002);
      }
      p.needsUpdate = true;
      bgTex.needsUpdate = true;
    }
    finalPass.uniforms.uTime.value = t;
    finalPass.uniforms.uDim.value += ((st.inspect ? .6 : 0) - finalPass.uniforms.uDim.value) * Math.min(1, dt * 3);
    composer.render();
  }

  window.Vitrine3D = V;
})();
