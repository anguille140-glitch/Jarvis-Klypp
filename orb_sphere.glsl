// Sphère de Jarvis, dessinée par la carte graphique (pixel par pixel, à la résolution de l'écran).
// Coquille de points en 3D qui tourne, rubans de lumière qui coulent, bord électrique, étincelles.
// Sortie en alpha prémultiplié : le noir est transparent, seule la lumière se pose sur l'écran.

out vec4 o;
uniform vec2 uRes;        // taille de la fenêtre (px)
uniform vec2 uC;          // centre de la sphère (px, origine en haut à gauche)
uniform float uR;         // rayon de la sphère (px)
uniform float uT;         // temps (s)
uniform float uLvl;       // intensité de la voix 0..1.2
uniform float uListen;    // 1 = écoute
uniform float uThink;     // 1 = réflexion
uniform float uRot;       // rotation accumulée
uniform float uFlow;      // écoulement accumulé
uniform float uGain;      // éclat global
uniform float uFade;      // opacité globale (apparition / disparition)
uniform vec4 uParts[72];  // particules en orbite : x, y (px), rayon (px), éclat
uniform int uNParts;
uniform sampler2D uText;  // textes sous la sphère (prémultipliés)
uniform vec4 uTextRect;   // x, y, largeur, hauteur (px)
uniform float uTextA;

const float PI = 3.14159265;

float h21(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * .1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float h31(vec3 p3) { p3 = fract(p3 * .1031); p3 += dot(p3, p3.zyx + 31.32); return fract((p3.x + p3.y) * p3.z); }

float n2(vec2 x) {
  vec2 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
  return mix(mix(h21(i), h21(i + vec2(1, 0)), f.x), mix(h21(i + vec2(0, 1)), h21(i + vec2(1, 1)), f.x), f.y);
}
float n3(vec3 x) {
  vec3 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
  return mix(mix(mix(h31(i), h31(i + vec3(1, 0, 0)), f.x), mix(h31(i + vec3(0, 1, 0)), h31(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(h31(i + vec3(0, 0, 1)), h31(i + vec3(1, 0, 1)), f.x), mix(h31(i + vec3(0, 1, 1)), h31(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm2(vec2 p) { float a = .5, s = 0.; for (int i = 0; i < 3; i++) { s += a * n2(p); p = p * 2.03 + 17.1; a *= .5; } return s / .875; }
float fbm3(vec3 p) { float a = .5, s = 0.; for (int i = 0; i < 4; i++) { s += a * n3(p); p = p * 2.01 + 11.7; a *= .5; } return s / .9375; }

mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0, -s, 0, 1, 0, s, 0, c); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1, 0, 0, 0, c, s, 0, -s, c); }

// lumière d'un point de la surface (normale n) : points de la coquille + rubans qui coulent
vec3 shell(vec3 n, float zf, float px, float back) {
  // rubans : lignes fines là où le bruit croise 0.5
  vec3 flow = vec3(uFlow * .21, uFlow * .33, -uFlow * .17);
  float f1 = fbm3(n * 2.2 + flow);
  float f2 = fbm3(n * 4.3 - flow * 1.4 + 5.);
  float aa = px * 9.;
  float rib = 1. - smoothstep(0., .013 + aa, abs(f1 - .5));
  float rib2 = 1. - smoothstep(0., .009 + aa, abs(f2 - .5));
  float fold = smoothstep(.25, .75, f1);                      // grandes ondulations claires / sombres
  // coquille de points (bandes de latitude, autant de points par bande que la place le permet)
  float bands = 118.;
  float lat = asin(clamp(n.y, -1., 1.)), lon = atan(n.z, n.x);
  float st = PI / bands, i = floor((lat + PI * .5) / st), latc = (i + .5) * st - PI * .5;
  float cnt = max(1., floor(2. * bands * cos(latc) + .5)), ls = 2. * PI / cnt;
  float j = floor((lon + PI) / ls), lonc = (j + .5) * ls - PI;
  vec2 cell = vec2((lat - latc) / st, (lon - lonc) * cos(lat) / st);
  float hh = h21(vec2(i, j));
  float big = step(.986, hh);
  float rad = .15 + .12 * big + .03 * fold + .07 * rib;
  float paa = px / st / max(zf, .18) * 1.2;                   // 1 pixel en unités de cellule (anti-crénelage)
  float dotm = 1. - smoothstep(rad - paa, rad + paa, length(cell));
  float tw = .55 + .45 * sin(uT * (2. + 5. * hh) + hh * 40.);
  float fres = pow(1. - zf, 2.2);
  float dI = dotm * (.09 + .10 * fold + 1.15 * rib + .35 * rib2 + .75 * fres + big * 1.7 * tw);
  float lI = rib * (.26 + .45 * fres) + rib2 * .08;
  vec3 deep = vec3(.06, .28, 1.), cyan = vec3(.35, .78, 1.), white = vec3(.85, .95, 1.);
  vec3 c = dI * mix(deep, cyan, clamp(rib + .4 * fres + big, 0., 1.)) + lI * mix(cyan, white, rib * .6);
  return c * back;
}

void main() {
  vec2 fc = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 q = (fc - uC) / uR;
  float r = length(q), th = atan(q.y, q.x);
  vec2 cs = vec2(cos(th), sin(th));
  float px = 1. / uR;
  vec3 col = vec3(0.);
  float act = uLvl + .35 * uListen + .25 * uThink;

  // bord vivant : ondule doucement, vibre avec la voix
  float amp = .016 + .06 * uLvl + .014 * uThink + .01 * uListen;
  float wob = amp * (fbm2(cs * 1.7 + vec2(uT * .31, -uT * .23)) - .5) * 2.
            + uLvl * (.016 * sin(14. * th + 9. * uT) + .01 * sin(23. * th - 13. * uT)) * (.5 + n2(cs * 3. + uT * 1.7));
  float rr = 1. + wob;
  float d = r / rr;

  // halo bleu autour
  col += vec3(.04, .22, 1.) * (.16 + .55 * uLvl + .22 * uListen + .1 * uThink) * exp(-abs(d - 1.) * 6.5);
  col += vec3(.02, .1, .6) * .12 * exp(-max(d - 1., 0.) * 2.5) * step(1., d);

  // la sphère : face avant + face arrière vue par transparence
  if (d < 1.) {
    vec2 p = q / rr;
    float zf = sqrt(max(0., 1. - dot(p, p)));
    mat3 M = rotY(uRot) * rotX(.38 + .06 * sin(uT * .21));
    vec3 nf = M * vec3(p.x, -p.y, zf);
    vec3 nb = M * vec3(p.x, -p.y, -zf);
    col += shell(nf, zf, px, 1.);
    col += shell(nb, zf, px, .32);
    col += vec3(.03, .12, .9) * (.05 + .35 * uLvl) * exp(-dot(p, p) * 3.);   // cœur
    col += vec3(.05, .25, 1.) * .06 * (1. - zf);                              // voile intérieur
  }

  // brins électriques sur le bord
  if (abs(r - rr) < .32) {
    float spread = .065 + .09 * uLvl + .025 * uThink;
    for (int k = 0; k < 9; k++) {
      float fk = float(k);
      float off = (fbm2(cs * (1.6 + fk * .37) + vec2(fk * 3.1, uT * (.33 + .06 * fk))) - .5) * 2. * spread;
      float w = max((.004 + .003 * mod(fk, 3.)) * (1. + uLvl), px * 1.1);
      float e = (r - rr * (1. + off)) / w;
      float on = .35 + .65 * n2(cs * 2.6 + vec2(fk * 7.7, uT * .55 + fk));
      col += mix(vec3(.2, .6, 1.), vec3(.85, .97, 1.), on) * exp(-e * e) * on * (.75 + .6 * act);
    }
    col += vec3(.25, .65, 1.) * exp(-pow((d - 1.) / .018, 2.)) * (1.1 + .8 * act);   // liseré net
    col += vec3(.1, .45, 1.) * exp(-abs(d - 1.) * 16.) * (.45 + .5 * act);          // lueur du bord
  }

  // étincelles et poussière autour du bord, qui s'éloignent
  if (r > .82 && r < 1.34) {
    for (int L = 0; L < 2; L++) {
      float fl = float(L);
      float N = 150. + 90. * fl, Mr = 34. + 10. * fl;
      vec2 u = vec2((th / (2. * PI) + .5) * N, (r - 1.) * Mr - uT * (.25 + .2 * fl) * (1. + 1.5 * act));
      vec2 id = floor(u), fu = fract(u) - .5;
      float h = h21(id + fl * 37.);
      if (h > .7) {
        vec2 jit = vec2(h21(id + 3.1), h21(id + 7.7)) - .5;
        float ds = length((fu - jit * .6) * vec2(2. * PI * r / N, 1. / Mr)) / px;   // distance en pixels
        float sz = .7 + 1.6 * h * h;
        float fall = exp(-abs(r - 1.) * 9.) * (.5 + .5 * sin(uT * (3. + 6. * h) + h * 50.));
        col += mix(vec3(.2, .5, 1.), vec3(.7, .9, 1.), h * h) * (1. - smoothstep(sz - .8, sz + .8, ds)) * fall * 1.5;
      }
    }
  }

  // particules en orbite
  for (int i = 0; i < 72; i++) {
    if (i >= uNParts) break;
    vec4 P = uParts[i];
    float dd = length(fc - P.xy);
    if (dd > P.z * 7. + 2.) continue;
    col += vec3(.3, .55, 1.) * P.w * ((1. - smoothstep(P.z - .7, P.z + .7, dd)) + .35 * exp(-dd / (P.z * 1.8)));
  }

  col *= uGain;
  if (uListen > .5) col.g *= 1.1;
  col = vec3(1.) - exp(-col * 1.35);                          // tons doux, pas de blanc brûlé
  float a = clamp(max(col.r, max(col.g, col.b)) * 1.25, 0., 1.);
  vec4 res = vec4(min(col, vec3(a)), a);

  // textes (J.A.R.V.I.S, état, sous-titres)
  vec2 tu = (fc - uTextRect.xy) / uTextRect.zw;
  if (uTextA > 0. && tu.x >= 0. && tu.y >= 0. && tu.x <= 1. && tu.y <= 1.) {
    vec4 tx = texture(uText, tu) * uTextA;
    res = tx + res * (1. - tx.a);
  }
  o = res * uFade;
}
