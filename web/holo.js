/* ============================================================================
   HOLO-TABLE de JARVIS : ton vrai coin du monde en hologramme 3D.
   - relief réel (tuiles d'altitude Terrarium), carte OpenStreetMap transformée en hologramme et drapée dessus
   - vrais bâtiments qui sortent du sol, sommets nommés, rivières, remontées mécaniques avec cabines
   - soleil à sa vraie position (jour / nuit), météo réelle (nuages, pluie, neige, vent)
   - modes : holo, thermique, rayons X ; scan LIDAR, survol cinématique, drones, liaison satellite
   - clic (ou voix) sur un point : altitude, pente, distance, ligne de vue, profil
   Utilisé par plan_de_travail.html : pendant l'animation de démarrage (HOLO.bootDrive) et en plein écran (HOLO.open).
   ============================================================================ */
(function () {
"use strict";
const LIBS = ["three.min.js", "CopyShader.js", "LuminosityHighPassShader.js", "EffectComposer.js", "RenderPass.js",
  "ShaderPass.js", "UnrealBloomPass.js"];
const R_TABLE = 16;               // rayon de la table (km)
const EXT = 16.5;                 // demi-côté de la zone de relief (km)
const NS = 400;                   // mailles du relief
const EXAG = 1.3;                 // relief un peu accentué (plus lisible)
const EXAG_B = 4;                 // bâtiments très accentués (sinon invisibles à cette échelle)
const DEM_Z = 11, MAP_Z = 13;
const DET_Z = 15, DET_E = 3.5;
const VS_N = 256;                 // grille du champ de vision (125 m)    // carte détaillée (rues, maisons) autour du domicile : ±3,5 km
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const easeOut = (t, p = 3) => 1 - Math.pow(1 - t, p);
const D2R = Math.PI / 180;

const H = {
  ready: false, failed: false, active: false, mode: "boot", opts: null,
  lat0: 0, lon0: 0, KX: 1, KN: 111.32, hRef: 0, hMin: 0, hMax: 0, HG: null,
  three: null, scene: null, camera: null, renderer: null, composer: null, U: null,
  labels: [], peaks: [], rivers: [], lifts: [], buildingCount: 0,
};
window.HOLO = H;

/* ---------- chargement ---------- */
function loadScript(src) {
  return new Promise((ok, ko) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = ko; document.head.appendChild(s); });
}
function loadImg(src) {
  return new Promise((ok) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => ok(null); im.src = src; });
}
const mx = (lon, z) => (lon + 180) / 360 * 256 * (1 << z);
const my = (lat, z) => { const s = Math.sin(lat * D2R); return (.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * 256 * (1 << z); };
const tileLon = (x, z) => x / (1 << z) * 360 - 180;
const tileLat = (y, z) => { const n = Math.PI - 2 * Math.PI * y / (1 << z); return Math.atan(Math.sinh(n)) / D2R; };
const toXN = (lat, lon) => [(lon - H.lon0) * H.KX, (lat - H.lat0) * H.KN];

async function loadDEM() {
  const z = DEM_Z, latN = H.lat0 + EXT / H.KN, latS = H.lat0 - EXT / H.KN, lonW = H.lon0 - EXT / H.KX, lonE = H.lon0 + EXT / H.KX;
  const tx0 = Math.floor(mx(lonW, z) / 256), tx1 = Math.floor(mx(lonE, z) / 256), ty0 = Math.floor(my(latN, z) / 256), ty1 = Math.floor(my(latS, z) / 256);
  const cv = document.createElement("canvas"); cv.width = (tx1 - tx0 + 1) * 256; cv.height = (ty1 - ty0 + 1) * 256;
  const c = cv.getContext("2d", { willReadFrequently: true });
  let got = 0;
  const jobs = [];
  for (let tx = tx0; tx <= tx1; tx++) for (let ty = ty0; ty <= ty1; ty++)
    jobs.push(loadImg(`relief/${z}/${tx}/${ty}.png`).then((im) => { if (im) { c.drawImage(im, (tx - tx0) * 256, (ty - ty0) * 256); got++; } }));
  await Promise.all(jobs);
  if (!got) throw new Error("relief indisponible");
  const d = c.getImageData(0, 0, cv.width, cv.height).data, W = cv.width, Hh = cv.height;
  const hAt = (px, py) => {           // altitude (m) au pixel, bilinéaire
    px = clamp(px, 0, W - 1.001); py = clamp(py, 0, Hh - 1.001);
    const i = Math.floor(px), j = Math.floor(py), u = px - i, v = py - j;
    const g = (a, b) => { const k = (b * W + a) * 4; return d[k] * 256 + d[k + 1] + d[k + 2] / 256 - 32768; };
    return lerp(lerp(g(i, j), g(i + 1, j), u), lerp(g(i, j + 1), g(i + 1, j + 1), u), v);
  };
  const N1 = NS + 1, HG = new Float32Array(N1 * N1);
  let mn = 1e9, mxh = -1e9;
  for (let j = 0; j <= NS; j++) for (let i = 0; i <= NS; i++) {
    const x = -EXT + 2 * EXT * i / NS, n = -EXT + 2 * EXT * j / NS;
    const lat = H.lat0 + n / H.KN, lon = H.lon0 + x / H.KX;
    const h = hAt(mx(lon, z) - tx0 * 256, my(lat, z) - ty0 * 256);
    HG[j * N1 + i] = h; mn = Math.min(mn, h); mxh = Math.max(mxh, h);
  }
  H.HG = HG; H.hMin = mn; H.hMax = mxh;
  H.hRef = heightM(0, 0);
}
function heightM(x, n) {             // altitude réelle (m) en km locaux
  const N1 = NS + 1, fi = clamp((x + EXT) / (2 * EXT) * NS, 0, NS - 1e-4), fj = clamp((n + EXT) / (2 * EXT) * NS, 0, NS - 1e-4);
  const i = Math.floor(fi), j = Math.floor(fj), u = fi - i, v = fj - j, G = H.HG;
  return lerp(lerp(G[j * N1 + i], G[j * N1 + i + 1], u), lerp(G[(j + 1) * N1 + i], G[(j + 1) * N1 + i + 1], u), v);
}
const yOf = (hm) => (hm - H.hMin) / 1000 * EXAG;
const Y = (x, n) => yOf(heightM(x, n));
function slopeDeg(x, n) {
  const e = .08, gx = (heightM(x + e, n) - heightM(x - e, n)) / (2 * e * 1000), gn = (heightM(x, n + e) - heightM(x, n - e)) / (2 * e * 1000);
  return Math.atan(Math.hypot(gx, gn)) / D2R;
}

// Carte holographique drapée sur le relief. ext : demi-côté (km). Les tuiles sont converties en 512 px (contours fins).
async function buildTexture(tileFn, z, SIZE, ext) {
  const cv = document.createElement("canvas"); cv.width = cv.height = SIZE;
  const c = cv.getContext("2d");
  c.fillStyle = "rgb(2,12,26)"; c.fillRect(0, 0, SIZE, SIZE); c.imageSmoothingQuality = "high";
  const latN = H.lat0 + ext / H.KN, latS = H.lat0 - ext / H.KN, lonW = H.lon0 - ext / H.KX, lonE = H.lon0 + ext / H.KX;
  const tx0 = Math.floor(mx(lonW, z) / 256), tx1 = Math.floor(mx(lonE, z) / 256), ty0 = Math.floor(my(latN, z) / 256), ty1 = Math.floor(my(latS, z) / 256);
  const px = (x) => (x + ext) / (2 * ext) * SIZE, py = (n) => (ext - n) / (2 * ext) * SIZE;
  const list = [];
  for (let tx = tx0; tx <= tx1; tx++) for (let ty = ty0; ty <= ty1; ty++) list.push([tx, ty]);
  let i = 0;
  const worker = async () => {                       // 6 à la fois, en laissant respirer l'animation entre deux tuiles
    while (i < list.length) {
      const [tx, ty] = list[i++], img = await tileFn(z, tx, ty, { size: 512, dim: 1 });
      if (img) {
        const [x0, n0] = toXN(tileLat(ty, z), tileLon(tx, z)), [x1, n1] = toXN(tileLat(ty + 1, z), tileLon(tx + 1, z));
        c.drawImage(img, px(x0), py(n0), px(x1) - px(x0) + .6, py(n1) - py(n0) + .6);
      }
      await new Promise((r) => setTimeout(r, 0));
    }
  };
  await Promise.all(Array.from({ length: 6 }, worker));
  return cv;
}

/* ---------- soleil réel ---------- */
function sunPos(date, lat, lon) {          // azimut / hauteur (degrés), formule NOAA simplifiée
  const d = (date - Date.UTC(2000, 0, 1, 12)) / 864e5;
  const g = (357.529 + .98560028 * d) * D2R, q = 280.459 + .98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + .02 * Math.sin(2 * g)) * D2R, e = (23.439 - 3.6e-7 * d) * D2R;
  const RA = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L)), dec = Math.asin(Math.sin(e) * Math.sin(L));
  const gmst = (18.697374558 + 24.06570982441908 * d) % 24, lst = (gmst * 15 + lon) * D2R, ha = lst - RA;
  const la = lat * D2R;
  const alt = Math.asin(Math.sin(la) * Math.sin(dec) + Math.cos(la) * Math.cos(dec) * Math.cos(ha));
  const az = Math.atan2(-Math.sin(ha), Math.tan(dec) * Math.cos(la) - Math.sin(la) * Math.cos(ha));
  return { az: (az / D2R + 360) % 360, alt: alt / D2R };
}

/* ---------- scène ---------- */
function buildScene(texCanvas, zone, texDCanvas) {
  const T = THREE, U = {
    uTime: { value: 0 }, uTex: { value: null }, uReveal: { value: 0 }, uScanR: { value: -1 }, uScanC: { value: new T.Vector2() },
    uTarget: { value: new T.Vector2(999, 999) }, uSun: { value: new T.Vector3(0, 1, 0) }, uSunI: { value: 1 }, uNight: { value: 0 },
    uBaseT: { value: 10 }, uHRef: { value: H.hRef }, uHMin: { value: H.hMin }, uExag: { value: EXAG }, uThermMix: { value: 0 },
    uXMix: { value: 0 }, uRise: { value: 0 }, uSnow: { value: 2300 },
    uTexD: { value: null }, uDetE: { value: DET_E }, uDetOn: { value: texDCanvas ? 1 : 0 }, uPx: { value: .001 },
    uVS: { value: null }, uVSOn: { value: 0 }, uVSR: { value: 0 }, uVSC: { value: new T.Vector2() },
  };
  H.U = U;
  const tex = new T.CanvasTexture(texCanvas);
  tex.anisotropy = 16; tex.minFilter = T.LinearMipmapLinearFilter; U.uTex.value = tex;
  const texD = new T.CanvasTexture(texDCanvas || document.createElement("canvas"));
  texD.anisotropy = 16; texD.minFilter = T.LinearMipmapLinearFilter; U.uTexD.value = texD;
  const vsT = new T.DataTexture(new Uint8Array(VS_N * VS_N), VS_N, VS_N, T.LuminanceFormat);
  vsT.magFilter = vsT.minFilter = T.LinearFilter; U.uVS.value = vsT; H.vsTex = vsT;
  const scene = new T.Scene(); H.scene = scene;

  /* relief */
  const N1 = NS + 1, pos = new Float32Array(N1 * N1 * 3), uv = new Float32Array(N1 * N1 * 2), ah = new Float32Array(N1 * N1), sl = new Float32Array(N1 * N1);
  for (let j = 0; j <= NS; j++) for (let i = 0; i <= NS; i++) {
    const k = j * N1 + i, x = -EXT + 2 * EXT * i / NS, n = -EXT + 2 * EXT * j / NS, h = H.HG[k];
    pos[k * 3] = x; pos[k * 3 + 1] = yOf(h); pos[k * 3 + 2] = -n; uv[k * 2] = i / NS; uv[k * 2 + 1] = j / NS; ah[k] = h;
    const hx = H.HG[j * N1 + Math.min(i + 1, NS)] - H.HG[j * N1 + Math.max(i - 1, 0)], hn = H.HG[Math.min(j + 1, NS) * N1 + i] - H.HG[Math.max(j - 1, 0) * N1 + i];
    sl[k] = Math.atan(Math.hypot(hx, hn) / (2 * 2 * EXT / NS * 1000)) / D2R;
  }
  const idx = new Uint32Array(NS * NS * 6); let p = 0;
  for (let j = 0; j < NS; j++) for (let i = 0; i < NS; i++) { const a = j * N1 + i, b = a + 1, c = a + N1, d = c + 1; idx[p++] = a; idx[p++] = b; idx[p++] = c; idx[p++] = b; idx[p++] = d; idx[p++] = c; }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.BufferAttribute(pos, 3)); g.setAttribute("uv", new T.BufferAttribute(uv, 2));
  g.setAttribute("aH", new T.BufferAttribute(ah, 1)); g.setAttribute("aSlope", new T.BufferAttribute(sl, 1));
  g.setIndex(new T.BufferAttribute(idx, 1));
  const terrainMat = new T.ShaderMaterial({ uniforms: U, transparent: true, extensions: { derivatives: true },
    vertexShader: `attribute float aH; attribute float aSlope; varying vec3 vW; varying vec2 vUv; varying float vH; varying float vS;
      void main(){ vUv=uv; vH=aH; vS=aSlope; vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform sampler2D uTex,uTexD,uVS; uniform float uTime,uReveal,uScanR,uSunI,uNight,uBaseT,uHRef,uHMin,uThermMix,uXMix,uSnow,uDetE,uDetOn,uVSOn,uVSR;
      uniform vec2 uScanC,uTarget,uVSC; uniform vec3 uSun; varying vec3 vW; varying vec2 vUv; varying float vH; varying float vS;
      float iso(float v,float w){ float f=abs(fract(v-.5)-.5)/max(fwidth(v),1e-4); return 1.-min(f/w,1.); }
      vec3 ramp(float t){ t=clamp(t,0.,1.); vec3 a=vec3(.10,.02,.30),b=vec3(.10,.25,.95),c=vec3(.05,.85,.85),d=vec3(1.,.88,.22),e=vec3(1.,.22,.12);
        if(t<.25)return mix(a,b,t/.25); if(t<.5)return mix(b,c,(t-.25)/.25); if(t<.75)return mix(c,d,(t-.5)/.25); return mix(d,e,(t-.75)/.25); }
      void main(){
        float r=length(vW.xz);
        if(r>uReveal || r>${R_TABLE.toFixed(1)}) discard;
        vec3 N=normalize(cross(dFdx(vW),dFdy(vW))); if(N.y<0.) N=-N;
        float lam=max(dot(N,normalize(uSun)),0.);
        float shade=.1+.9*pow(lam,1.2)*uSunI+.08*N.y;
        float rim=pow(1.-max(dot(N,normalize(cameraPosition-vW)),0.),3.);
        vec3 map=texture2D(uTex,vUv).rgb;
        vec2 dq=vec2(vW.x,-vW.z)/uDetE; float dw=uDetOn*(1.-smoothstep(.82,1.,max(abs(dq.x),abs(dq.y))));
        if(dw>0.) map=mix(map,texture2D(uTexD,dq*.5+.5).rgb,dw);
        float minor=iso(vH/50.,1.), major=iso(vH/250.,1.5);
        vec2 gf=abs(fract(vW.xz-.5)-.5)/fwidth(vW.xz); float grid=1.-min(min(gf.x,gf.y),1.);
        float snow=smoothstep(uSnow-250.,uSnow+250.,vH)*(1.-smoothstep(38.,52.,vS));
        vec3 cy=vec3(.38,.9,1.);
        vec3 base=mix(vec3(.01,.05,.12),vec3(.03,.24,.46),smoothstep(uHMin,uHMin+2600.,vH));
        vec3 holo=base*(.35+1.1*shade) + map*(.22+.62*shade) + cy*(minor*.13+major*.55) + cy*grid*.05
                 + vec3(.6,.86,1.)*snow*.5*shade + cy*rim*.22;
        holo=mix(holo, holo*vec3(.55,.65,1.15), uNight);
        float Tm=uBaseT-6.5*(vH-uHRef)/1000.+3.*(lam*uSunI-.5);
        vec3 th=ramp((Tm+22.)/40.)*(.35+.65*shade)+vec3(1.)*major*.28;
        vec3 xr=vec3(.02,.08,.14)*shade+cy*(minor*.55+major*1.3)+cy*grid*.18;
        vec3 col=mix(holo,th,uThermMix); col=mix(col,xr,uXMix);
        float alpha=mix(.96,.42,uXMix);
        if(uVSOn>0.){                                   // champ de vision : vert = visible, rouge sombre = caché
          vec2 vq=vW.xz/${(2 * R_TABLE).toFixed(1)}+.5; float vis=texture2D(uVS,vec2(vq.x,1.-vq.y)).r;
          float dO=length(vW.xz-uVSC), on=uVSOn*smoothstep(uVSR,uVSR-.6,dO);
          float hatch=step(.5,fract((vW.x+vW.z)*7.));
          vec3 seen=col*.75+vec3(.15,1.,.55)*(.22+.1*hatch);
          vec3 hid=col*vec3(.55,.45,.52)+vec3(.5,.04,.1)*.16;
          float edgeV=1.-smoothstep(0.,fwidth(vis)*1.5+1e-4,abs(vis-.5));
          col=mix(col,mix(hid,seen,smoothstep(.35,.65,vis))+vec3(.5,1.,.7)*edgeV*.9,on);
          col+=vec3(.4,1.,.7)*exp(-pow((dO-uVSR)*3.,2.))*uVSOn*step(uVSR,${(R_TABLE + 1).toFixed(1)})*.9;
        }
        if(uScanR>0.){ float d=length(vW.xz-uScanC); float band=exp(-pow((d-uScanR)*4.,2.));
          float trail=smoothstep(uScanR-3.,uScanR,d)*step(d,uScanR); float fade=1.-smoothstep(12.,18.,uScanR);
          col+=vec3(.35,1.,.85)*(band*1.5+trail*.2*(minor+major))*fade; }
        col+=vec3(.5,1.,1.)*exp(-pow((r-uReveal)*2.5,2.))*1.4;
        float dt=length(vW.xz-uTarget);
        col+=vec3(1.,.7,.3)*exp(-pow((dt-.32-.04*sin(uTime*3.))*24.,2.))*1.1;
        col+=vec3(1.,.7,.3)*exp(-pow((dt-.62)*50.,2.))*.5*step(.5,fract(atan(vW.z-uTarget.y,vW.x-uTarget.x)*6./3.14159+uTime*.2));
        float dh=length(vW.xz); col+=vec3(.4,1.,.8)*exp(-pow((dh-.18-.1*fract(uTime*.6))*30.,2.))*(1.-fract(uTime*.6));
        alpha*=1.-smoothstep(${(R_TABLE - .9).toFixed(1)},${R_TABLE.toFixed(1)},r);
        gl_FragColor=vec4(col,alpha);
      }` });
  const terrain = new T.Mesh(g, terrainMat); terrain.renderOrder = 1; scene.add(terrain); H.terrain = terrain;

  /* table holographique */
  const disc = new T.Mesh(new T.CircleGeometry(R_TABLE + .9, 160), new T.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false,
    vertexShader: `varying vec2 vP; void main(){ vP=position.xy; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `uniform float uTime,uReveal; varying vec2 vP; void main(){ float r=length(vP), a=atan(vP.y,vP.x);
      float rings=smoothstep(.05,0.,abs(fract(r*.5)-.5)-.47)*.14+smoothstep(.05,0.,abs(r-${R_TABLE.toFixed(1)}))*.9+smoothstep(.04,0.,abs(r-${(R_TABLE + .7).toFixed(1)}))*.6;
      float sweep=pow(max(0.,1.-mod(a-uTime*.5,6.2832)/6.2832),6.)*step(r,${R_TABLE.toFixed(1)})*.22;
      float spokes=smoothstep(.006,0.,abs(fract(a*36./6.2832)-.5)-.49)*step(${R_TABLE.toFixed(1)},r)*step(r,${(R_TABLE + .7).toFixed(1)})*.8;
      float glow=exp(-r*.12)*.1; float v=rings+sweep+spokes+glow;
      gl_FragColor=vec4(vec3(.38,.9,1.)*v, v*.8*step(r,uReveal*1.08+.5)); }` }));
  disc.rotation.x = -Math.PI / 2; disc.position.y = -.03; scene.add(disc);
  const curtain = new T.Mesh(new T.CylinderGeometry(R_TABLE, R_TABLE, 5, 200, 1, true), new T.ShaderMaterial({ uniforms: U, transparent: true,
    depthWrite: false, side: T.DoubleSide, blending: T.AdditiveBlending,
    vertexShader: `varying vec2 vU; void main(){ vU=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `uniform float uTime,uReveal; varying vec2 vU; void main(){ float a=pow(1.-vU.y,3.)*.2;
      float l=smoothstep(0.,.3,abs(fract(vU.y*40.-uTime*.4)-.5))*.5+.5; float v=step(.5,fract(vU.x*240.))*.3+.7;
      gl_FragColor=vec4(vec3(.38,.9,1.)*a*l*v*step(${(R_TABLE - .5).toFixed(1)},uReveal),1.); }` }));
  curtain.position.y = 2.5; scene.add(curtain);
  const tk = [];
  for (let i = 0; i < 360; i += 2) { const a = i * D2R, r0 = i % 10 === 0 ? R_TABLE + .15 : R_TABLE + .35; tk.push(Math.cos(a) * r0, 0, Math.sin(a) * r0, Math.cos(a) * (R_TABLE + .65), 0, Math.sin(a) * (R_TABLE + .65)); }
  const tg = new T.BufferGeometry(); tg.setAttribute("position", new T.Float32BufferAttribute(tk, 3));
  const ticks = new T.LineSegments(tg, new T.LineBasicMaterial({ color: 0x62e6ff, transparent: true, opacity: .55, blending: T.AdditiveBlending }));
  ticks.position.y = -.01; scene.add(ticks); H.ticks = ticks;

  /* bâtiments réels */
  buildBuildings(zone);
  /* rivières, remontées, sommets */
  buildLines(zone);
  buildFixedLabels();
  /* domicile : faisceau + anneaux */
  const hy = yOf(H.hRef);
  const beamGrp = new T.Group(); beamGrp.position.set(0, hy, 0); scene.add(beamGrp); H.beam = beamGrp;
  const beam = new T.Mesh(new T.CylinderGeometry(.06, .06, 7, 24, 1, true), new T.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false,
    blending: T.AdditiveBlending, side: T.DoubleSide,
    vertexShader: `varying vec2 vU; void main(){ vU=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `uniform float uTime; varying vec2 vU; void main(){ float a=pow(1.-vU.y,1.6)*(.55+.45*step(.5,fract(vU.y*30.-uTime*1.5))); gl_FragColor=vec4(vec3(.5,1.,.85)*a,1.); }` }));
  beam.position.y = 3.5; beamGrp.add(beam);
  const ringMat = new T.MeshBasicMaterial({ color: 0x6dffc4, transparent: true, opacity: .9, side: T.DoubleSide, blending: T.AdditiveBlending, depthWrite: false });
  H.homeRings = [0, 1, 2].map((i) => { const r = new T.Mesh(new T.RingGeometry(.16 + i * .1, .175 + i * .1, 64, 1, 0, Math.PI * (1.2 + i * .25)), ringMat); r.rotation.x = -Math.PI / 2; r.position.y = .04 + i * .05; beamGrp.add(r); return r; });
  beamGrp.visible = false;
  /* cible */
  const tgtGrp = new T.Group(); scene.add(tgtGrp); H.tgt = tgtGrp; tgtGrp.visible = false;
  const tbeam = new T.Mesh(new T.CylinderGeometry(.035, .035, 5, 16, 1, true), new T.MeshBasicMaterial({ color: 0xffb24a, transparent: true, opacity: .55, blending: T.AdditiveBlending, depthWrite: false, side: T.DoubleSide }));
  tbeam.position.y = 2.5; tgtGrp.add(tbeam);

  /* poussière / météo / drones / satellite */
  buildAtmos();
  /* lumières de rendu */
  H.renderer = new T.WebGLRenderer({ canvas: H.opts.canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  H.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  H.renderer.setClearColor(0x01060c, 1);
  H.camera = new T.PerspectiveCamera(42, 1, .01, 300);
  try {
    if (T.EffectComposer && T.UnrealBloomPass) {
      H.composer = new T.EffectComposer(H.renderer); H.composer.addPass(new T.RenderPass(scene, H.camera));
      H.bloom = new T.UnrealBloomPass(new T.Vector2(256, 256), .75, .45, .42); H.composer.addPass(H.bloom);
    }
  } catch (e) { H.composer = null; }
  resize();
}

function buildBuildings(zone) {
  const T = THREE, list = (zone && zone.batiments) || [];
  const P = [], UVv = [], BASE = [], SEED = [], idx = [];
  let n = 0;
  for (const [hm, pts] of list) {
    let poly = pts.map(([la, lo]) => toXN(la, lo));
    if (poly.length > 3 && Math.hypot(poly[0][0] - poly[poly.length - 1][0], poly[0][1] - poly[poly.length - 1][1]) < 1e-6) poly.pop();
    if (poly.length < 3) continue;
    let base = 1e9; for (const [x, nn] of poly) base = Math.min(base, Y(x, nn));
    const top = base + hm / 1000 * EXAG_B, seed = Math.random();
    // murs
    for (let i = 0; i < poly.length; i++) {
      const [x0, n0] = poly[i], [x1, n1] = poly[(i + 1) % poly.length], k = P.length / 3;
      P.push(x0, base - .003, -n0, x1, base - .003, -n1, x1, top, -n1, x0, top, -n0);
      UVv.push(0, 0, 1, 0, 1, 1, 0, 1); BASE.push(base, base, base, base); SEED.push(seed, seed, seed, seed);
      idx.push(k, k + 1, k + 2, k, k + 2, k + 3);
    }
    // toit
    try {
      const contour = poly.map(([x, nn]) => new T.Vector2(x, nn));
      const tris = T.ShapeUtils.triangulateShape(contour, []);
      const k = P.length / 3;
      for (const [x, nn] of poly) { P.push(x, top, -nn); UVv.push(.5, 2); BASE.push(base); SEED.push(seed); }
      for (const t of tris) idx.push(k + t[0], k + t[1], k + t[2]);
    } catch (e) { /* toit impossible : murs seulement */ }
    n++;
  }
  H.buildingCount = n;
  if (!n) return;
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(P, 3)); g.setAttribute("uv", new T.Float32BufferAttribute(UVv, 2));
  g.setAttribute("aBase", new T.Float32BufferAttribute(BASE, 1)); g.setAttribute("aSeed", new T.Float32BufferAttribute(SEED, 1));
  g.setIndex(idx);
  const m = new T.ShaderMaterial({ uniforms: H.U, transparent: true, side: T.DoubleSide, extensions: { derivatives: true },
    vertexShader: `attribute float aBase; attribute float aSeed; uniform float uRise; varying vec2 vUv; varying float vSeed; varying vec3 vW;
      void main(){ vUv=uv; vSeed=aSeed; vec3 p=position; float rise=clamp(uRise*1.6-aSeed*.6,0.,1.); p.y=aBase+(p.y-aBase)*rise;
        vec4 w=modelMatrix*vec4(p,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uTime,uReveal,uThermMix,uXMix,uScanR; uniform vec2 uScanC; varying vec2 vUv; varying float vSeed; varying vec3 vW;
      void main(){ if(length(vW.xz)>uReveal) discard;
        bool roof=vUv.y>1.5; float e=roof?1.:min(min(vUv.x,1.-vUv.x),min(vUv.y,1.-vUv.y));
        float edge=roof?0.:1.-smoothstep(0.,fwidth(e)*1.6,e);
        float win=roof?0.:step(.6,fract(vUv.y*5.+vSeed))*step(.35,fract(vUv.x*4.+vSeed*3.))*step(.45,fract(vSeed*7.+floor(uTime*.25+vSeed*5.)*.37));
        vec3 cy=vec3(.38,.9,1.);
        vec3 holo=(roof?vec3(.05,.26,.46):vec3(.02,.1,.2))+cy*edge*.75+vec3(1.,.85,.5)*win*.22;
        vec3 th=(roof?vec3(1.,.85,.3):vec3(1.,.45,.12))*.8+vec3(1.,.95,.6)*edge+vec3(1.)*win*.4;
        vec3 xr=cy*edge*2.;
        vec3 col=mix(holo,th,uThermMix); col=mix(col,xr,uXMix);
        float al=mix(.88,edge*.95+.04,uXMix);
        if(uScanR>0.){ float d=length(vW.xz-uScanC); col+=vec3(.4,1.,.85)*exp(-pow((d-uScanR)*4.,2.))*2.; }
        gl_FragColor=vec4(col,al); }` });
  const mesh = new T.Mesh(g, m); mesh.renderOrder = 2; H.scene.add(mesh); H.buildings = mesh;
}

function drape(pts, off) {
  const T = THREE, out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, n0] = pts[i], [x1, n1] = pts[i + 1], L = Math.hypot(x1 - x0, n1 - n0), k = Math.max(1, Math.ceil(L / .06));
    for (let s = 0; s < k; s++) { const u = s / k, x = lerp(x0, x1, u), n = lerp(n0, n1, u); out.push(new T.Vector3(x, Y(x, n) + off, -n)); }
  }
  const [xl, nl] = pts[pts.length - 1]; out.push(new THREE.Vector3(xl, Y(xl, nl) + off, -nl));
  return out;
}
function lineObj(pts, color, op) {
  const T = THREE, l = new T.Line(new T.BufferGeometry().setFromPoints(pts),
    new T.LineBasicMaterial({ color, transparent: true, opacity: op, blending: T.AdditiveBlending, depthWrite: false }));
  l.renderOrder = 3; H.scene.add(l); return l;
}
function inTable(x, n, m = 0) { return Math.hypot(x, n) < R_TABLE - m; }

function buildLines(zone) {
  const T = THREE;
  for (const [, g] of (zone && zone.rivieres) || []) {
    const pts = g.map(([la, lo]) => toXN(la, lo)).filter(([x, n]) => inTable(x, n, .2));
    if (pts.length < 2) continue;
    const d = drape(pts, .006); lineObj(d, 0x3aa0ff, .95); H.rivers.push(new T.CatmullRomCurve3(d));
  }
  for (const [name, kind, g] of (zone && zone.remontees) || []) {
    const pts = g.map(([la, lo]) => toXN(la, lo));
    if (pts.length < 2 || !pts.every(([x, n]) => inTable(x, n, .3))) continue;
    const a = pts[0], b = pts[pts.length - 1], ya = Y(a[0], a[1]) + .02, yb = Y(b[0], b[1]) + .02, cur = [];
    for (let k = 0; k <= 40; k++) { const u = k / 40, x = lerp(a[0], b[0], u), n = lerp(a[1], b[1], u);
      const L = Math.hypot(b[0] - a[0], b[1] - a[1], (yb - ya)); cur.push(new T.Vector3(x, Math.max(lerp(ya, yb, u) - Math.sin(u * Math.PI) * L * .04, Y(x, n) + .01), -n)); }
    lineObj(cur, 0xffb24a, kind === "chair_lift" ? .45 : .85);
    H.lifts.push({ name, curve: new T.CatmullRomCurve3(cur), big: kind === "cable_car" || kind === "gondola" });
  }
  // sommets : les plus hauts, espacés
  const peaks = ((zone && zone.sommets) || []).map(([name, ele, la, lo]) => { const [x, n] = toXN(la, lo); return { name, ele: ele || heightM(x, n), x, n }; })
    .filter((p) => p.name && inTable(p.x, p.n, .5)).sort((a, b) => b.ele - a.ele);
  const keep = [];
  for (const p of peaks) { if (keep.length >= 16) break; if (keep.every((q) => Math.hypot(q.x - p.x, q.n - p.n) > 1.4)) keep.push(p); }
  H.peaks = keep;
  for (const p of keep) addLabel(new T.Vector3(p.x, Math.max(Y(p.x, p.n), yOf(p.ele)) + .03, -p.n), `${p.name}<small>${fmtAlt(p.ele)}</small>`, "peak");
}
function buildFixedLabels() {
  const T = THREE;
  H.homeLabel = addLabel(new T.Vector3(0, yOf(H.hRef) + .05, 0), `${(H.opts.ville || "Domicile").toUpperCase()}<small>DOMICILE · ${fmtAlt(H.hRef)}</small>`, "home");
  [["N", 0, -R_TABLE - 1.2], ["E", R_TABLE + 1.2, 0], ["S", 0, R_TABLE + 1.2], ["O", -R_TABLE - 1.2, 0]].forEach((c) => addLabel(new T.Vector3(c[1], 0, c[2]), c[0], "card"));
}

/* poussière, météo réelle, drones, satellite, particules mobiles (cabines, rivière) */
function dotTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 64; const x = c.getContext("2d");
  const g = x.createRadialGradient(32, 32, 0, 32, 32, 32); g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(.25, "rgba(255,255,255,.8)"); g.addColorStop(1, "rgba(255,255,255,0)");
  x.fillStyle = g; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
}
function buildAtmos() {
  const T = THREE, dot = dotTexture(); H.dot = dot;
  buildDyn();
  // météo : pluie / neige réelles
  const NP = 7000, pg = new T.BufferGeometry(), pp = new Float32Array(NP * 3), pv = new Float32Array(NP);
  for (let i = 0; i < NP; i++) { const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * (R_TABLE - .5); pp[i * 3] = Math.cos(a) * r; pp[i * 3 + 1] = Math.random() * 6; pp[i * 3 + 2] = Math.sin(a) * r; pv[i] = .5 + Math.random(); }
  pg.setAttribute("position", new T.BufferAttribute(pp, 3));
  H.precip = { pts: new T.Points(pg, new T.PointsMaterial({ size: .05, map: dot, color: 0xdff6ff, transparent: true, opacity: .75, depthWrite: false, blending: T.AdditiveBlending })), pp, pv, kind: "" };
  H.precip.pts.visible = false; H.scene.add(H.precip.pts);
  // couche de nuages (selon la couverture réelle)
  const cl = new T.Mesh(new T.CircleGeometry(R_TABLE, 96), new T.ShaderMaterial({ uniforms: Object.assign({ uCover: { value: 0 }, uWind: { value: new T.Vector2(.02, 0) } }, H.U),
    transparent: true, depthWrite: false,
    vertexShader: `varying vec2 vP; void main(){ vP=position.xy; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `uniform float uTime,uCover; uniform vec2 uWind; varying vec2 vP;
      float h(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
      float n(vec2 p){ vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f); return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y); }
      float fbm(vec2 p){ float s=0.,a=.5; for(int i=0;i<5;i++){ s+=a*n(p); p*=2.03; a*=.5; } return s; }
      void main(){ vec2 p=vP*.18+uWind*uTime; float c=smoothstep(1.-uCover*.85,1.05-uCover*.5,fbm(p));
        float edge=1.-smoothstep(${(R_TABLE - 2).toFixed(1)},${R_TABLE.toFixed(1)},length(vP));
        gl_FragColor=vec4(vec3(.62,.82,1.)*.55, c*.22*edge); }` }));
  cl.rotation.x = -Math.PI / 2; cl.position.y = yOf(H.hMin + 2900); cl.renderOrder = 5; cl.visible = false; H.scene.add(cl); H.clouds = cl;
  // drones
  H.droneGrp = new T.Group(); H.droneGrp.visible = false; H.scene.add(H.droneGrp); H.drones = [];
  for (let i = 0; i < 6; i++) {
    const m = new T.Mesh(new T.ConeGeometry(.05, .16, 3), new T.MeshBasicMaterial({ color: i === 0 ? 0xffb24a : 0x9ff3ff, transparent: true, blending: T.AdditiveBlending }));
    m.rotation.x = Math.PI / 2; const holder = new T.Group(); holder.add(m); H.droneGrp.add(holder);
    const tgm = new T.BufferGeometry(), tp = new Float32Array(60 * 3); tgm.setAttribute("position", new T.BufferAttribute(tp, 3));
    H.droneGrp.add(new T.Line(tgm, new T.LineBasicMaterial({ color: 0x62e6ff, transparent: true, opacity: .45, blending: T.AdditiveBlending, depthWrite: false })));
    H.drones.push({ h: holder, tp, tg: tgm, ph: i / 6 * Math.PI * 2, init: false });
  }
  // satellite
  H.satGrp = new T.Group(); H.satGrp.visible = false; H.scene.add(H.satGrp);
  const orbit = []; for (let i = 0; i <= 256; i++) { const a = i / 256 * Math.PI * 2; orbit.push(new T.Vector3(Math.cos(a) * 24, 0, Math.sin(a) * 24)); }
  const piv = new T.Group(); piv.position.set(0, 13, 0); piv.rotation.set(.35, 0, .2); H.satGrp.add(piv); H.satPivot = piv;
  piv.add(new T.Line(new T.BufferGeometry().setFromPoints(orbit), new T.LineBasicMaterial({ color: 0x62e6ff, transparent: true, opacity: .3 })));
  H.sat = new T.Mesh(new T.OctahedronGeometry(.3), new T.MeshBasicMaterial({ color: 0xd6f5ff, wireframe: true })); piv.add(H.sat);
  const ug = new T.BufferGeometry(); ug.setAttribute("position", new T.BufferAttribute(new Float32Array(6), 3));
  H.uplink = new T.Line(ug, new T.LineBasicMaterial({ color: 0x6dffc4, transparent: true, opacity: .85, blending: T.AdditiveBlending })); H.satGrp.add(H.uplink);
}

function buildDyn() {                      // cabines qui montent et descendent + eau qui coule
  const T = THREE;
  if (H.dynPts) { H.scene.remove(H.dynPts); H.dynPts.geometry.dispose(); }
  const NC = H.lifts.length * 2, NR = Math.min(320, H.rivers.length * 60), N = Math.max(1, NC + NR);
  const g = new T.BufferGeometry(), pos = new Float32Array(N * 3), col = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) col.set(i < NC ? [1, .85, .55] : [.4, .75, 1], i * 3);
  g.setAttribute("position", new T.BufferAttribute(pos, 3)); g.setAttribute("color", new T.BufferAttribute(col, 3));
  H.dyn = { g, pos, NC, NR };
  H.dynPts = new T.Points(g, new T.PointsMaterial({ size: .07, map: H.dot, vertexColors: true, transparent: true, depthWrite: false, blending: T.AdditiveBlending }));
  H.dynPts.renderOrder = 4; H.scene.add(H.dynPts);
}

/* ---------- routes : rubans lumineux posés exactement sur le relief ---------- */
function heightTri(x, n) {             // altitude sur les triangles du maillage (même découpe que l'affichage)
  const N1 = NS + 1, fi = clamp((x + EXT) / (2 * EXT) * NS, 0, NS - 1e-4), fj = clamp((n + EXT) / (2 * EXT) * NS, 0, NS - 1e-4);
  const i = Math.floor(fi), j = Math.floor(fj), u = fi - i, v = fj - j, G = H.HG;
  const a = G[j * N1 + i], b = G[j * N1 + i + 1], c = G[(j + 1) * N1 + i], d = G[(j + 1) * N1 + i + 1];
  return u + v <= 1 ? a + u * (b - a) + v * (c - a) : d + (1 - u) * (c - d) + (1 - v) * (b - d);
}
// largeur réelle (km) et largeur minimale à l'écran (px) par type : autoroute, nationale, départementale, locale, rue, chemin, sentier
const ROAD_W = [.032, .024, .019, .014, .009, .006, .004], ROAD_PX = [2.6, 2.2, 1.9, 1.6, 1.2, 1.1, 1];
function buildRoads(list) {
  const T = THREE;
  if (H.roads) { H.scene.remove(H.roads); H.roads.geometry.dispose(); }
  const P = [], NRM = [], SIDE = [], DIST = [], KIND = [], idx = [];
  let km = 0, id = 0;
  for (const [kind, , tunnel, g] of list) {
    const pts = g.map(([la, lo]) => toXN(la, lo));
    // découpe en morceaux à l'intérieur de la table, puis ré-échantillonnage tous les ~20 m (suit le relief)
    let run = [];
    const flush = () => {
      if (run.length >= 2) {
        const res = [];
        for (let i = 0; i < run.length - 1; i++) {
          const [x0, n0] = run[i], [x1, n1] = run[i + 1], L = Math.hypot(x1 - x0, n1 - n0), k = Math.max(1, Math.ceil(L / .02));
          for (let q = 0; q < k; q++) res.push([lerp(x0, x1, q / k), lerp(n0, n1, q / k)]);
        }
        res.push(run[run.length - 1]);
        let dist = 0; const seed = (id++ * 0.618) % 1 * 50;
        for (let i = 0; i < res.length; i++) {
          const [x, n] = res[i], a = res[Math.max(0, i - 1)], b = res[Math.min(res.length - 1, i + 1)];
          let tx = b[0] - a[0], tn = b[1] - a[1]; const tl = Math.hypot(tx, tn) || 1; tx /= tl; tn /= tl;
          if (i) dist += Math.hypot(x - res[i - 1][0], n - res[i - 1][1]);
          const y = yOf(heightTri(x, n)) + .0025, k0 = P.length / 3;
          for (const sd of [-1, 1]) { P.push(x, y, -n); NRM.push(-tn, -tx); SIDE.push(sd); DIST.push(dist + seed); KIND.push(kind + (tunnel ? 10 : 0)); }
          if (i) idx.push(k0 - 2, k0 - 1, k0, k0 - 1, k0 + 1, k0);
        }
        km += dist;
      }
      run = [];
    };
    for (const pt of pts) { if (inTable(pt[0], pt[1], .25)) run.push(pt); else flush(); }
    flush();
  }
  H.roadKm = km;
  if (!P.length) return;
  const geo = new T.BufferGeometry();
  geo.setAttribute("position", new T.Float32BufferAttribute(P, 3)); geo.setAttribute("aN", new T.Float32BufferAttribute(NRM, 2));
  geo.setAttribute("aSide", new T.Float32BufferAttribute(SIDE, 1)); geo.setAttribute("aDist", new T.Float32BufferAttribute(DIST, 1));
  geo.setAttribute("aKind", new T.Float32BufferAttribute(KIND, 1)); geo.setIndex(idx);
  const m = new T.ShaderMaterial({ uniforms: H.U, transparent: true, depthWrite: false, extensions: { derivatives: true },
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4, side: T.DoubleSide,
    vertexShader: `attribute vec2 aN; attribute float aSide, aDist, aKind; uniform float uPx;
      varying float vSide, vDist, vKind, vCam; varying vec3 vW;
      float W[7]; float PX[7];
      void main(){ ${ROAD_W.map((v, i) => `W[${i}]=${v.toFixed(4)}; PX[${i}]=${ROAD_PX[i].toFixed(2)};`).join(" ")}
        int k=int(mod(aKind,10.)+.5); float w=0., px=1.;
        for(int i=0;i<7;i++){ if(i==k){ w=W[i]; px=PX[i]; } }
        vec4 c=modelMatrix*vec4(position,1.); float d=length(cameraPosition-c.xyz); vCam=d;
        float hw=max(w, uPx*d*px)*.5*2.2;                // ruban un peu plus large que la route : place pour le halo
        c.xz+=aN*aSide*hw; c.y+=.0006*d;                 // de loin, on le soulève à peine (pas de clignotement)
        vSide=aSide; vDist=aDist; vKind=aKind; vW=c.xyz; gl_Position=projectionMatrix*viewMatrix*c; }`,
    fragmentShader: `uniform float uTime,uReveal,uNight,uThermMix,uXMix; varying float vSide, vDist, vKind, vCam; varying vec3 vW;
      void main(){
        float r=length(vW.xz); if(r>uReveal || r>${(R_TABLE - .2).toFixed(1)}) discard;
        float tun=step(9.5,vKind), k=mod(vKind,10.), s=abs(vSide);
        float body=1.-smoothstep(.38,.48,s), glow=exp(-s*s*6.)*.55, core=1.-smoothstep(.0,.12,s);
        vec3 col; float a;
        if(k<.5){ col=vec3(1.,.66,.25); }                 // autoroute : ambre
        else if(k<1.5){ col=vec3(1.,.78,.36); }            // nationale
        else if(k<2.5){ col=vec3(.95,.9,.55); }            // départementale
        else if(k<3.5){ col=vec3(.62,.95,1.); }            // route locale : cyan
        else if(k<4.5){ col=vec3(.5,.86,1.); }             // rue
        else if(k<5.5){ col=vec3(.45,.95,.7); }            // chemin : vert
        else { col=vec3(.75,1.,.8); }                      // sentier
        float lum=(body*.55+core*.9)+glow;
        if(k>4.5){ float dash=step(.45,fract(vDist*(k>5.5?90.:45.))); lum*=dash; lum*=1.-smoothstep(5.,9.,vCam); }
        if(k>3.5 && k<4.5) lum*=1.-smoothstep(9.,16.,vCam);
        // circulation : feux blancs dans un sens, feux rouges dans l'autre (grands axes)
        if(k<2.5 && tun<.5){ float lane=step(0.,vSide);
          float f=fract(vDist*(k<.5?7.:4.)+uTime*(lane>.5?.22:-.22)*(k<.5?1.5:1.));
          float car=smoothstep(.0,.04,f)*(1.-smoothstep(.04,.12,f))*(1.-smoothstep(.15,.42,s));
          col=mix(col, lane>.5?vec3(1.,.96,.85):vec3(1.,.25,.2), car*.9); lum+=car*1.6; }
        lum*=1.+uNight*.6;                                // la nuit, les routes s'allument
        if(tun>.5) lum*=.35*step(.5,fract(vDist*30.));     // tunnel : pointillés discrets
        vec3 th=vec3(1.,.55,.15)*lum; vec3 xr=vec3(.38,.9,1.)*lum*.6;
        vec3 c=mix(col*lum,th,uThermMix*.7); c=mix(c,xr,uXMix);
        a=clamp(lum,0.,1.)*(1.-smoothstep(${(R_TABLE - 1.2).toFixed(1)},${(R_TABLE - .2).toFixed(1)},r));
        gl_FragColor=vec4(c,a); }` });
  const mesh = new T.Mesh(geo, m); mesh.renderOrder = 2.5; H.scene.add(mesh); H.roads = mesh;
}

/* ---------- champ de vision : tout ce qu'on voit depuis un point (courbure de la Terre comprise) ---------- */
function computeViewshed(ox, on, eye = .002) {
  const NR = 1440, STEP = .045, MAXD = Math.hypot(R_TABLE, R_TABLE) + Math.hypot(ox, on), NSTEP = Math.ceil(MAXD / STEP);
  const vis = new Uint8Array(NR * NSTEP), h0 = heightM(ox, on) + eye * 1000;
  let far = 0;
  for (let r = 0; r < NR; r++) {
    const a = r / NR * Math.PI * 2, dx = Math.sin(a), dn = Math.cos(a);
    let best = -1e9;
    for (let k = 1; k < NSTEP; k++) {
      const d = k * STEP, x = ox + dx * d, n = on + dn * d;
      if (Math.abs(x) > EXT || Math.abs(n) > EXT) break;
      const tan = (heightM(x, n) - .0683 * d * d - h0) / (d * 1000);
      if (tan >= best) { vis[r * NSTEP + k] = 1; best = tan; if (Math.hypot(x, n) < R_TABLE && d > far) far = d; }
    }
  }
  const look = (x, n) => { const d = Math.hypot(x - ox, n - on); if (d < STEP) return 1;
    const a = (Math.atan2(x - ox, n - on) + Math.PI * 2) % (Math.PI * 2), r = Math.round(a / (Math.PI * 2) * NR) % NR, k = Math.min(NSTEP - 1, Math.round(d / STEP));
    return vis[r * NSTEP + k]; };
  const data = H.vsTex.image.data; let seen = 0, tot = 0;
  for (let j = 0; j < VS_N; j++) for (let i = 0; i < VS_N; i++) {
    const x = -R_TABLE + 2 * R_TABLE * (i + .5) / VS_N, n = -R_TABLE + 2 * R_TABLE * (j + .5) / VS_N, v = look(x, n);
    data[j * VS_N + i] = v ? 255 : 0;
    if (Math.hypot(x, n) < R_TABLE) { tot++; seen += v; }
  }
  H.vsTex.needsUpdate = true;
  const peaks = H.peaks.filter((p) => look(p.x, p.n));
  return { pct: seen / Math.max(1, tot) * 100, far, peaks };
}
H.viewshed = function (x = 0, n = 0, name = "") {
  const t0 = performance.now(), r = computeViewshed(x, n);
  H.U.uVSC.value.set(x, -n); H.U.uVSR.value = 0; H.U.uVSOn.value = 1; H.vsOn = true;
  if (H.onViewshed) H.onViewshed(true);
  const pk = r.peaks.slice(0, 3).map((p) => p.name).join(", ");
  say(`Champ de vision depuis ${name || (H.opts.ville || "le domicile")} : ${r.pct.toFixed(0)} % de la table visible, jusqu'à ${r.far.toFixed(1)} km. `
    + (r.peaks.length ? `${r.peaks.length} sommet${r.peaks.length > 1 ? "s" : ""} en vue (${pk}${r.peaks.length > 3 ? "…" : ""}).` : "Aucun sommet nommé en vue.") + ` Calcul : ${Math.round(performance.now() - t0)} ms.`, "s");
  return r;
};
H.viewshedOff = function () { H.U.uVSOn.value = 0; H.vsOn = false; if (H.onViewshed) H.onViewshed(false); say("Champ de vision masqué."); };

/* ---------- étiquettes ---------- */
const fmtAlt = (m) => Math.round(m).toLocaleString("fr-FR").replace(/ | /g, " ") + " m";
function addLabel(pos, html, cls) {
  const el = document.createElement("div"); el.className = "hpoi" + (cls ? " " + cls : ""); el.innerHTML = `<div class="tag">${html}</div>`;
  H.opts.labels.appendChild(el); const L = { el, pos, vis: false, on: cls !== "home" }; L.el.style.opacity = 0; H.labels.push(L); return L;
}
const tmpV = { v: null };
function updateLabels(show) {
  const w = H.opts.canvas.clientWidth, h = H.opts.canvas.clientHeight, v = tmpV.v || (tmpV.v = new THREE.Vector3());
  for (const L of H.labels) {
    v.copy(L.pos).project(H.camera);
    const on = show && L.on && v.z < 1 && v.z > -1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05 && Math.hypot(L.pos.x, L.pos.z) < H.U.uReveal.value + .5;
    if (on !== L.vis) { L.el.style.opacity = on ? 1 : 0; L.vis = on; }
    if (on) L.el.style.transform = `translate(${((v.x + 1) / 2 * w).toFixed(1)}px,${((1 - v.y) / 2 * h).toFixed(1)}px)`;
  }
}

/* ---------- caméra ---------- */
const cam = { tx: 0, ty: 0, tz: 0, r: 30, th: 0, ph: .05 };
const goal = { tx: 0, ty: 0, tz: 0, r: 7, th: Math.PI * .85, ph: 1.0 };
H.cam = cam; H.goal = goal;                       // (réglages de caméra accessibles pour les tests)
function applyCam() {
  const s = Math.sin(cam.ph);
  H.camera.position.set(cam.tx + cam.r * s * Math.sin(cam.th), cam.ty + cam.r * Math.cos(cam.ph), cam.tz + cam.r * s * Math.cos(cam.th));
  H.camera.lookAt(cam.tx, cam.ty, cam.tz);
}
function home() { return { tx: 0, ty: yOf(H.hRef), tz: 0 }; }

/* ---------- animation ---------- */
let last = 0, raf = 0, fly = null, scanT = -1, lockT = -1;
function frame(now) {
  raf = requestAnimationFrame(frame);
  if (!H.active) return;
  const dt = Math.min(.05, (now - (last || now)) / 1000); last = now;
  const t = now / 1000, U = H.U;
  U.uTime.value = t;
  if (H.mode === "atlas") {
    if (fly) flyStep(dt);
    const k = 1 - Math.exp(-dt * 5);
    for (const key of ["tx", "ty", "tz", "r", "th", "ph"]) cam[key] += (goal[key] - cam[key]) * k;
    if (!fly && !H.drag && H.autoOrbit) goal.th += dt * .04;
    U.uReveal.value = Math.min(R_TABLE + 1, U.uReveal.value + dt * 14);
    U.uRise.value = Math.min(1, U.uRise.value + dt * .7);
  }
  applyCam();
  if (H.U.uVSOn.value > 0 && H.U.uVSR.value < R_TABLE + 8) H.U.uVSR.value += dt * 9;
  H.U.uPx.value = 2 * Math.tan(H.camera.fov * D2R / 2) / Math.max(200, H.opts.canvas.clientHeight || innerHeight);
  if (scanT >= 0) { scanT += dt; U.uScanR.value = scanT * 7; if (scanT > 3) { scanT = -1; U.uScanR.value = -1; } }
  const modeK = 1 - Math.exp(-dt * 6);
  U.uThermMix.value += ((H.vision === 1 ? 1 : 0) - U.uThermMix.value) * modeK;
  U.uXMix.value += ((H.vision === 2 ? 1 : 0) - U.uXMix.value) * modeK;
  if (lockT >= 0) { lockT += dt; H.homeRings.forEach((r, i) => { r.rotation.z += dt * (i % 2 ? -1 : 1) * (1 + i * .5); }); }
  if (H.tgt.visible) H.tgt.rotation.y += dt;
  stepDynamic(t, dt);
  updateLabels(H.labelsOn);
  if (H.composer) H.composer.render(); else H.renderer.render(H.scene, H.camera);
  if (H.onFrame) H.onFrame(dt);
}
function stepDynamic(t, dt) {
  const D = H.dyn;
  if (D) {
    for (let i = 0; i < D.NC; i++) { const L = H.lifts[i % Math.max(1, H.lifts.length)]; if (!L) break;
      const u = ((t * (L.big ? .03 : .05) + i * .5) % 1); const p = L.curve.getPointAt(i % 2 ? u : 1 - u); D.pos.set([p.x, p.y - .015, p.z], i * 3); }
    for (let i = 0; i < D.NR; i++) { const c = H.rivers[i % H.rivers.length]; if (!c) break;
      const p = c.getPointAt(((t * .012 + i * .137) % 1)); D.pos.set([p.x, p.y + .004, p.z], (D.NC + i) * 3); }
    D.g.attributes.position.needsUpdate = true;
  }
  const P = H.precip;
  if (P.pts.visible) {
    const snow = P.kind === "neige", wind = H.windV || [0, 0];
    for (let i = 0; i < P.pv.length; i++) {
      let y = P.pp[i * 3 + 1] - dt * (snow ? .35 : 2.4) * P.pv[i];
      P.pp[i * 3] += dt * wind[0] * (snow ? .6 : .3); P.pp[i * 3 + 2] += dt * wind[1] * (snow ? .6 : .3);
      const x = P.pp[i * 3], z = P.pp[i * 3 + 2];
      if (y < Y(x, -z) || Math.hypot(x, z) > R_TABLE - .3) { const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * (R_TABLE - .5); P.pp[i * 3] = Math.cos(a) * r; P.pp[i * 3 + 2] = Math.sin(a) * r; y = 4 + Math.random() * 2; }
      P.pp[i * 3 + 1] = y;
    }
    P.pts.geometry.attributes.position.needsUpdate = true;
  }
  if (H.droneGrp.visible) H.drones.forEach((d, i) => {
    const a = t * .25 + d.ph, rr = 2.5 + 1.2 * Math.sin(t * .3 + i);
    const x = Math.cos(a) * rr, z = Math.sin(a * 1.3) * rr * .8, y = yOf(H.hRef) + 1.2 + .3 * Math.sin(t + i);
    d.h.position.set(x, y, z); d.h.lookAt(Math.cos(a + .1) * rr, y, Math.sin((a + .1) * 1.3) * rr * .8);
    if (!d.init) { for (let k = 0; k < 60; k++) d.tp.set([x, y, z], k * 3); d.init = true; }
    d.tp.copyWithin(3, 0, 57 * 3); d.tp.set([x, y, z], 0); d.tg.attributes.position.needsUpdate = true;
  });
  if (H.satGrp.visible) {
    const a = t * .12; H.sat.position.set(Math.cos(a) * 24, 0, Math.sin(a) * 24); H.sat.rotation.y += dt;
    const w = H.sat.getWorldPosition(new THREE.Vector3()), arr = H.uplink.geometry.attributes.position.array;
    arr.set([w.x, w.y, w.z, 0, yOf(H.hRef), 0]); H.uplink.geometry.attributes.position.needsUpdate = true;
  }
}

/* ---------- interface publique ---------- */
H.init = async function (opts) {
  if (H.ready || H.loading) return H.loading;
  H.opts = opts; H.lat0 = +opts.lat; H.lon0 = +opts.lon; H.KX = 111.32 * Math.cos(H.lat0 * D2R);
  H.loading = (async () => {
    try {
      for (const f of LIBS) if (!(f === "three.min.js" && window.THREE)) await loadScript("web/three/" + f);
      const zoneP = (async () => { for (let i = 0; i < 40; i++) {      // les données OSM arrivent parfois après
        try { const z = await (await fetch("zone", { cache: "no-store" })).json(); if (z.etat === "ok") return z; } catch (e) { /* on réessaie */ }
        await new Promise((r) => setTimeout(r, i < 3 ? 1500 : 4000)); if (H.ready && i > 3) return null; } return null; })();
      await loadDEM();
      const routesP = (async () => { for (let i = 0; i < 40; i++) {
        try { const z = await (await fetch("routes", { cache: "no-store" })).json(); if (z.etat === "ok") return z; } catch (e) { /* on réessaie */ }
        await new Promise((r) => setTimeout(r, i < 3 ? 2000 : 5000)); } return null; })();
      const [tex, texD] = await Promise.all([buildTexture(opts.tileImg, MAP_Z, 4096, EXT), buildTexture(opts.tileImg, DET_Z, 4096, DET_E)]);
      const zone = await Promise.race([zoneP, new Promise((r) => setTimeout(() => r(null), 4000))]);
      buildScene(tex, zone, texD);
      routesP.then((r) => { if (r && r.routes) { buildRoads(r.routes); if (H.active && H.mode === "atlas") say(`Réseau routier chargé : ${H.roadKm.toFixed(0)} km de routes et sentiers.`, "s"); } });
      H.zoneLate = zone ? null : zoneP;
      if (H.zoneLate) H.zoneLate.then((z) => { if (z && !H.buildings) { buildBuildings(z); buildLines(z); buildDyn();
        H.say && H.say(`Données OpenStreetMap reçues : ${H.buildingCount} bâtiments en 3D, ${H.peaks.length} sommets.`, "s"); } });
      H.ready = true; H.vision = 0; H.labelsOn = false; H.autoOrbit = true;
      setSunNow(); applyWeather(opts.meteo);
      raf = requestAnimationFrame(frame);
      return true;
    } catch (e) { H.failed = true; if (opts.report) opts.report("holo-table indisponible : " + (e && e.message || e)); return false; }
  })();
  return H.loading;
};
function resize() {
  if (!H.renderer) return;
  const c = H.opts.canvas, w = c.clientWidth || innerWidth, h = c.clientHeight || innerHeight;
  H.renderer.setSize(w, h, false); H.camera.aspect = w / h; H.camera.updateProjectionMatrix();
  if (H.composer) H.composer.setSize(w, h);
}
H.resize = resize;
addEventListener("resize", resize);

// pendant l'animation de démarrage : t = secondes depuis l'arrivée sur la carte
H.bootStart = function () {
  H.active = true; H.mode = "boot"; H.labelsOn = false; lockT = -1;
  H.U.uReveal.value = 0; H.U.uRise.value = 0; H.beam.visible = false; H.tgt.visible = false;
  Object.assign(cam, { ...home(), r: 34, th: Math.PI, ph: .04 });
  resize();
};
H.bootDrive = function (u, lockAt) {
  if (!H.ready) return;
  const U = H.U, hm = home();
  U.uReveal.value = (R_TABLE + 1) * easeOut(clamp(u / 2.4, 0, 1));
  const dive = ease(clamp((u - .2) / 3.2, 0, 1));
  cam.tx = hm.tx; cam.ty = hm.ty; cam.tz = hm.tz;
  cam.r = lerp(34, 6.5, dive); cam.ph = lerp(.04, 1.02, ease(clamp((u - .6) / 3, 0, 1))); cam.th = Math.PI + u * .16;
  U.uRise.value = clamp((u - 1.4) / 1.8, 0, 1);
  if (u >= lockAt && lockT < 0) { lockT = 0; H.beam.visible = true; H.labelsOn = true; H.homeLabel.on = true; scanT = 0; U.uScanC.value.set(0, 0); }
};
H.bootEnd = function () { if (H.mode === "boot") { H.active = false; H.labelsOn = false; updateLabels(false); } };

// plein écran interactif
H.open = function () {
  if (!H.ready) return false;
  H.active = true; H.mode = "atlas"; H.labelsOn = true; H.homeLabel.on = true; H.beam.visible = true; if (lockT < 0) lockT = 0;
  H.U.uRise.value = Math.max(H.U.uRise.value, .01);
  Object.assign(goal, { ...home(), r: 24, th: cam.th || Math.PI * .85, ph: .82 });
  if (cam.r > 40 || !isFinite(cam.r)) Object.assign(cam, { ...home(), r: 30, th: Math.PI, ph: .2 });
  resize(); return true;
};
H.close = function () { H.active = false; H.labelsOn = false; updateLabels(false); fly = null; };

/* ---------- commandes (boutons, console, voix) ---------- */
function say(text, cls) { if (H.say) H.say(text, cls); }
H.setVision = function (m) {
  H.vision = m;
  say(["Vision holographique standard.", "Imagerie thermique : gradient adiabatique de 6,5 °C par kilomètre.", "Rayons X : relief transparent, structures en fil de fer."][m]);
};
H.scan = function () {
  scanT = 0; H.U.uScanC.value.set(H.tgt.visible ? H.tgt.position.x : 0, H.tgt.visible ? H.tgt.position.z : 0);
  say(`Scan LIDAR : ${H.buildingCount} bâtiments, ${H.peaks.length} sommets, ${H.rivers.length} cours d'eau, ${H.lifts.length} remontées mécaniques analysés.`, "s");
};
H.recenter = function () { fly = null; Object.assign(goal, { ...home(), r: 24, th: goal.th, ph: .82 }); H.tgt.visible = false; H.U.uTarget.value.set(999, 999); say("Recentré sur le domicile."); };
H.toggleDrones = function (v) { H.droneGrp.visible = v ?? !H.droneGrp.visible; H.drones.forEach((d) => { d.init = false; });
  say(H.droneGrp.visible ? "Six drones de reconnaissance en orbite au-dessus du domicile." : "Drones rappelés."); return H.droneGrp.visible; };
H.toggleSat = function (v) { H.satGrp.visible = v ?? !H.satGrp.visible;
  say(H.satGrp.visible ? "Liaison satellite établie. Flux descendant : 1,2 Gb/s, chiffrement quantique actif." : "Liaison satellite coupée.", H.satGrp.visible ? "s" : ""); return H.satGrp.visible; };
H.toggleClouds = function (v) { H.clouds.visible = v ?? !H.clouds.visible; return H.clouds.visible; };
function applyWeather(m) {
  if (!m || !H.precip) return;
  const cover = (m.nuages || 0) / 100, wd = ((m.vent_dir || 0) + 180) * D2R, ws = (m.vent || 0) / 30;
  H.windV = [Math.sin(wd) * ws, -Math.cos(wd) * ws];
  H.clouds.material.uniforms.uCover.value = cover; H.clouds.material.uniforms.uWind.value.set(H.windV[0] * .05, -H.windV[1] * .05);
  H.clouds.visible = cover > .5;
  const kind = (m.neige || 0) > 0 || ((m.pluie || 0) > 0 && (m.temp ?? 5) <= 1) ? "neige" : (m.pluie || 0) > 0 ? "pluie" : "";
  H.precip.kind = kind; H.precip.pts.visible = !!kind;
  H.precip.pts.material.size = kind === "neige" ? .07 : .035;
  H.U.uBaseT.value = (m.temp ?? 10) + 6.5 * 0;            // température réelle au domicile
  H.U.uSnow.value = 2300 + ((m.temp ?? 8) - 8) * 60;
  H.weather = { kind, cover, temp: m.temp, vent: m.vent };
}
H.applyWeather = applyWeather;
H.weatherReport = function () {
  const w = H.weather || {};
  say(`Météo réelle : ${w.temp ?? "?"} °C, vent ${w.vent ?? "?"} km/h, ciel couvert à ${Math.round((w.cover || 0) * 100)} %${w.kind ? ", " + w.kind + " en cours" : ""}.`);
};
function setSun(date) {
  const s = sunPos(date, H.lat0, H.lon0), az = s.az * D2R, alt = Math.max(-10, s.alt) * D2R;
  H.U.uSun.value.set(Math.sin(az) * Math.cos(alt), Math.max(.05, Math.sin(alt)), -Math.cos(az) * Math.cos(alt));
  const day = clamp((s.alt + 4) / 14, 0, 1);
  H.U.uSunI.value = .3 + .7 * day; H.U.uNight.value = 1 - day;
  H.sunInfo = s;
  return s;
}
function setSunNow() { const s = setSun(new Date()); H.sunHour = new Date().getHours() + new Date().getMinutes() / 60; return s; }
H.setSunHour = function (hr) {
  const d = new Date(); d.setHours(Math.floor(hr), Math.round((hr % 1) * 60), 0, 0); H.sunHour = hr;
  const s = setSun(d); return s;
};
H.setSunNow = setSunNow;
H.sun = function () { const s = H.sunInfo || setSunNow(); say(`Soleil : hauteur ${s.alt.toFixed(0)}°, azimut ${s.az.toFixed(0)}°${s.alt < 0 ? " (nuit)" : ""}.`); };

function norm(s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim(); }
H.findPlace = function (q) {
  q = norm(q); if (!q) return null;
  if (/^(maison|domicile|chez moi|home|moi)$/.test(q)) return { x: 0, n: 0, name: (H.opts.ville || "Domicile") };
  let best = null, bs = 0;
  for (const p of H.peaks) { const n = norm(p.name); const sc = n === q ? 3 : n.includes(q) ? 2 : q.split(" ").filter((w) => w.length > 2 && n.includes(w)).length / 2; if (sc > bs) { bs = sc; best = p; } }
  for (const L of H.lifts) { const n = norm(L.name); if (n && (n.includes(q) || q.includes(n)) && bs < 1.5) { const p = L.curve.getPointAt(1); return { x: p.x, n: -p.z, name: L.name }; } }
  return best ? { x: best.x, n: best.n, name: best.name } : null;
};
function losFrom(x1, n1) {
  const y0 = yOf(H.hRef) + .004, y1 = Y(x1, n1) + .012;
  for (let i = 1; i < 240; i++) { const u = i / 240, x = x1 * u, n = n1 * u; if (Y(x, n) > lerp(y0, y1, u) + .003) return false; }
  return true;
}
H.target = function (x, n, name, user = true) {
  const h = heightM(x, n), y = yOf(h), sl = slopeDeg(x, n), dist = Math.hypot(x, n);
  H.U.uTarget.value.set(x, -n); H.tgt.position.set(x, y, -n); H.tgt.visible = true;
  const brg = (Math.atan2(x, n) / D2R + 360) % 360, card = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][Math.round(brg / 45) % 8];
  const los = dist < .05 || losFrom(x, n), T = (H.weather && H.weather.temp != null ? H.weather.temp : 10) - 6.5 * (h - H.hRef) / 1000;
  const risk = sl < 25 ? ["Faible", "p-low"] : sl < 30 ? ["Modéré", "p-mid"] : sl < 35 ? ["Marqué", "p-mid"] : sl < 45 ? ["Fort", "p-hi"] : ["Paroi", "p-hi"];
  const lat = H.lat0 + n / H.KN, lon = H.lon0 + x / H.KX;
  let nm = name;
  if (!nm) { let bd = .9; for (const p of H.peaks) { const d = Math.hypot(p.x - x, p.n - n); if (d < bd) { bd = d; nm = p.name; } } }
  const info = { x, n, name: nm || "Point non référencé", lat, lon, alt: h, slope: sl, risk, dist, brg, card, los, temp: T,
    dh: h - H.hRef, eta: Math.hypot(dist, (h - H.hRef) / 1000) / .68 };
  if (H.onTarget) H.onTarget(info);
  if (user) {
    Object.assign(goal, { tx: x, ty: y, tz: -n, r: Math.min(goal.r, 6), ph: Math.min(goal.ph, 1.05) });
    say(`Cible verrouillée : ${info.name}, ${fmtAlt(h)}. Pente ${sl.toFixed(0)}°, à ${dist.toFixed(1)} km au ${card}${los ? ", en vue directe depuis le domicile" : ", masquée par le relief"}.`);
  }
  return info;
};
H.pick = function (cx, cy) {
  const rect = H.opts.canvas.getBoundingClientRect(), v = new THREE.Vector2((cx - rect.left) / rect.width * 2 - 1, -((cy - rect.top) / rect.height) * 2 + 1);
  const ray = new THREE.Raycaster(); ray.setFromCamera(v, H.camera);
  const hit = ray.intersectObject(H.terrain, false)[0];
  if (!hit || Math.hypot(hit.point.x, hit.point.z) > R_TABLE - .2) return null;
  return { x: hit.point.x, n: -hit.point.z };
};
H.profile = function (cv, x, n, los) {
  const g = cv.getContext("2d"), W = cv.width, Hh = cv.height; g.clearRect(0, 0, W, Hh);
  const N = 180, pts = []; let mn = 1e9, mxh = -1e9;
  for (let i = 0; i <= N; i++) { const h = heightM(x * i / N, n * i / N); pts.push(h); mn = Math.min(mn, h); mxh = Math.max(mxh, h); }
  mn -= 80; mxh = Math.max(mxh, mn + 400) + 120;
  const YY = (h) => Hh - 14 - (h - mn) / (mxh - mn) * (Hh - 30), XX = (i) => 8 + i / N * (W - 16);
  g.strokeStyle = "rgba(98,230,255,.12)"; g.lineWidth = 1; g.fillStyle = "rgba(98,230,255,.55)"; g.font = "18px monospace";
  for (let a = Math.ceil(mn / 250) * 250; a < mxh; a += 250) { g.beginPath(); g.moveTo(0, YY(a)); g.lineTo(W, YY(a)); g.stroke(); g.fillText(String(a), W - 64, YY(a) - 4); }
  const gr = g.createLinearGradient(0, 0, 0, Hh); gr.addColorStop(0, "rgba(98,230,255,.45)"); gr.addColorStop(1, "rgba(98,230,255,.02)");
  g.beginPath(); g.moveTo(XX(0), Hh); pts.forEach((h, i) => g.lineTo(XX(i), YY(h))); g.lineTo(XX(N), Hh); g.closePath(); g.fillStyle = gr; g.fill();
  g.beginPath(); pts.forEach((h, i) => i ? g.lineTo(XX(i), YY(h)) : g.moveTo(XX(i), YY(h))); g.strokeStyle = "#62e6ff"; g.lineWidth = 2.5; g.stroke();
  g.setLineDash([8, 6]); g.beginPath(); g.moveTo(XX(0), YY(pts[0] + 3)); g.lineTo(XX(N), YY(pts[N] + 12)); g.strokeStyle = los ? "#6dffc4" : "#ff4a5c"; g.lineWidth = 2; g.stroke(); g.setLineDash([]);
  g.fillStyle = "#ffb24a"; g.beginPath(); g.arc(XX(N), YY(pts[N]), 6, 0, 7); g.fill();
  g.fillStyle = "#d6f5ff"; g.beginPath(); g.arc(XX(0), YY(pts[0]), 5, 0, 7); g.fill();
};

/* survol cinématique : domicile -> chaque sommet -> retour */
H.flyover = function () {
  const pts = [[0, 0]].concat(H.peaks.slice(0, 6).map((p) => [p.x, p.n])).concat([[0, 0]]);
  if (pts.length < 3) { say("Pas assez de sommets pour un survol."); return; }
  const curve = new THREE.CatmullRomCurve3(pts.map(([x, n]) => new THREE.Vector3(x, Y(x, n) + .35, -n)));
  fly = { curve, u: 0, len: curve.getLength() };
  say(`Survol cinématique : ${Math.min(6, H.peaks.length)} sommets au programme.`, "s");
};
function flyStep(dt) {
  fly.u += dt * .9 / fly.len;
  if (fly.u >= 1) { fly = null; H.recenter(); return; }
  const p = fly.curve.getPointAt(fly.u), q = fly.curve.getPointAt(Math.min(1, fly.u + .02));
  goal.tx = p.x; goal.ty = p.y; goal.tz = p.z; goal.r = 2.6; goal.ph = 1.1;
  goal.th = Math.atan2(p.x - q.x, p.z - q.z);
}

// contrôle à la souris (mode plein écran)
H.bindControls = function (el) {
  const ptr = new Map(); let pinch = 0, drag = null;
  el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); ptr.set(e.pointerId, { x: e.clientX, y: e.clientY });
    drag = { x: e.clientX, y: e.clientY, btn: e.button, shift: e.shiftKey, moved: 0 }; H.drag = true; fly = null;
    if (ptr.size === 2) { const p = [...ptr.values()]; pinch = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y); } });
  el.addEventListener("pointermove", (e) => {
    if (!drag) return; ptr.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (ptr.size === 2) { const p = [...ptr.values()], d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y); if (pinch > 0) goal.r = clamp(goal.r * pinch / d, .4, 60); pinch = d; drag.moved = 99; return; }
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy);
    if (drag.btn === 2 || drag.shift) { const k = goal.r * .0016; goal.tx -= (dx * Math.cos(goal.th) + dy * Math.sin(goal.th)) * k; goal.tz -= (-dx * Math.sin(goal.th) + dy * Math.cos(goal.th)) * k; }
    else { goal.th -= dx * .005; goal.ph = clamp(goal.ph - dy * .004, .1, 1.45); }
  });
  const end = (e) => { ptr.delete(e.pointerId); if (ptr.size < 2) pinch = 0;
    if (drag && ptr.size === 0) { if (drag.moved < 5 && drag.btn === 0) { const hit = H.pick(e.clientX, e.clientY); if (hit) H.target(hit.x, hit.n); } drag = null; H.drag = false; } };
  el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
  el.addEventListener("contextmenu", (e) => e.preventDefault());
  el.addEventListener("wheel", (e) => { e.preventDefault(); fly = null; goal.r = clamp(goal.r * Math.exp(e.deltaY * .0012), .4, 60); }, { passive: false });
};

/* commande texte (console ou voix) */
H.command = function (raw) {
  const c = norm(raw);
  if (!c) return;
  let m;
  if (/^(aide|help|\?)$/.test(c)) say("Commandes : cible <lieu>, champ de vision (depuis <lieu>), routes, scan, survol, thermique, rayons x, holo, drones, satellite, meteo, nuages, soleil <heure>, soleil maintenant, recentre, quitter.");
  else if (/champ de vision|champs? de vue|visibilite|ce que (?:je|on) voi|qu est ce qu on voit|vue depuis|viewshed|angle mort/.test(c)) {
    const off = /\b(off|coupe|enleve|cache|masque|stop|arrete|desactive|retire)\b/.test(c);
    const dep = c.match(/depuis (?:le |la |les |l )?(.+)$/);
    if (off || (H.vsOn && !dep)) H.viewshedOff();
    else if (dep && /^(cible|ici|la cible|le point)$/.test(dep[1]) && H.tgt.visible) H.viewshed(H.tgt.position.x, -H.tgt.position.z, "la cible");
    else if (dep) { const p = H.findPlace(dep[1]); if (p) { H.target(p.x, p.n, p.name, false); H.viewshed(p.x, p.n, p.name); } else say(`Je ne trouve pas « ${dep[1]} » sur la table.`, "w"); }
    else H.viewshed(0, 0);
  }
  else if (/^(?:affiche |montre |cache |masque |enleve )?(?:les )?(routes?|chemins?|sentiers?)\b/.test(c)) {
    if (H.roads) { H.roads.visible = /cache|masque|enleve/.test(c) ? false : /affiche|montre/.test(c) ? true : !H.roads.visible; if (H.onRoads) H.onRoads(H.roads.visible); say(H.roads.visible ? `Réseau routier affiché : ${H.roadKm.toFixed(0)} km.` : "Routes masquées."); }
    else say("Les routes sont encore en téléchargement.", "w");
  }
  else if (/thermi/.test(c)) H.setVision(1);
  else if (/rayon|x ?ray|transparen/.test(c)) H.setVision(2);
  else if (/^(holo|normal|standard)/.test(c)) H.setVision(0);
  else if (/scan|lidar|analyse/.test(c)) H.scan();
  else if (/survol|vol|cinema|tour/.test(c)) H.flyover();
  else if (/drone/.test(c)) H.toggleDrones();
  else if (/satell/.test(c)) H.toggleSat();
  else if (/nuage/.test(c)) { const v = H.toggleClouds(); say(v ? "Couche nuageuse affichée." : "Nuages masqués."); }
  else if (/meteo|temps qu il fait/.test(c)) H.weatherReport();
  else if ((m = c.match(/soleil (?:a )?(\d{1,2})(?: ?h ?(\d{1,2})?)?/))) { const s = H.setSunHour(+m[1] + (+(m[2] || 0)) / 60); say(`Soleil réglé sur ${m[1]} h : hauteur ${s.alt.toFixed(0)}°.`); if (H.onSun) H.onSun(); }
  else if (/soleil (maintenant|reel|actuel)|heure reelle/.test(c)) { setSunNow(); H.sun(); if (H.onSun) H.onSun(); }
  else if (/^soleil/.test(c)) H.sun();
  else if (/recentr|domicile|maison|reset/.test(c) && !/cible/.test(c)) H.recenter();
  else if ((m = c.match(/^(?:cible|cibler|vise|viser|va a|va sur|montre(?: moi)?|zoom(?:e)? sur|localise)\s+(?:le |la |les |l |sur )?(.+)$/))) {
    const p = H.findPlace(m[1]); if (p) H.target(p.x, p.n, p.name); else say(`Je ne trouve pas « ${m[1]} » sur la table.`, "w");
  } else if (/^(quitte|quitter|ferme|fermer|retour|sortir)/.test(c)) { if (H.onClose) H.onClose(); }
  else say(`Commande inconnue : « ${raw} ». Tape « aide ».`, "w");
};
})();
