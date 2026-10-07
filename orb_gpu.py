"""La sphère de Jarvis dessinée par la carte graphique (OpenGL), synchronisée sur ton écran (60, 144, 240 Hz...).

Même comportement que la sphère classique (orb.py : apparition, voix, écoute, réflexion, position, taille, fond noir),
mais l'image est calculée par la carte graphique à la résolution exacte de l'écran : aucun pixel agrandi, et une
image à chaque rafraîchissement de l'écran, donc aucune saccade.

Sans dépendance à installer : on parle directement à OpenGL de Windows (opengl32.dll).
Si quelque chose manque (pilote, carte), orb.create() revient tout seul à l'ancienne sphère.
Réglage : JARVIS_SPHERE_MOTEUR=cpu dans .env pour forcer l'ancienne sphère.
"""
from __future__ import annotations

import ctypes
import logging
import math
import random
import sys
import time
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw

import orb as O

log = logging.getLogger("jarvis")
SHADER = O.BASE / "orb_sphere.glsl"
VS = ("#version 330 core\n"
      "void main() { vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }\n")
MAX_PARTS = 72

# constantes OpenGL
GL_COLOR_BUFFER_BIT, GL_TRIANGLES = 0x4000, 0x0004
GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE = 0x0DE1, 0x1908, 0x1401
GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_LINEAR = 0x2801, 0x2800, 0x2601
GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE = 0x2802, 0x2803, 0x812F
GL_FRAGMENT_SHADER, GL_VERTEX_SHADER = 0x8B30, 0x8B31
GL_COMPILE_STATUS, GL_LINK_STATUS = 0x8B81, 0x8B82
GL_RENDERER, GL_VERSION, GL_TEXTURE0, GL_UNPACK_ALIGNMENT = 0x1F01, 0x1F02, 0x84C0, 0x0CF5
GL_BLEND, GL_DEPTH_TEST = 0x0BE2, 0x0B71


class PIXELFORMATDESCRIPTOR(ctypes.Structure):
    _fields_ = [("nSize", wintypes.WORD), ("nVersion", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("iPixelType", ctypes.c_ubyte), ("cColorBits", ctypes.c_ubyte),
                ("cRedBits", ctypes.c_ubyte), ("cRedShift", ctypes.c_ubyte),
                ("cGreenBits", ctypes.c_ubyte), ("cGreenShift", ctypes.c_ubyte),
                ("cBlueBits", ctypes.c_ubyte), ("cBlueShift", ctypes.c_ubyte),
                ("cAlphaBits", ctypes.c_ubyte), ("cAlphaShift", ctypes.c_ubyte),
                ("cAccumBits", ctypes.c_ubyte), ("cAccumRedBits", ctypes.c_ubyte),
                ("cAccumGreenBits", ctypes.c_ubyte), ("cAccumBlueBits", ctypes.c_ubyte),
                ("cAccumAlphaBits", ctypes.c_ubyte), ("cDepthBits", ctypes.c_ubyte),
                ("cStencilBits", ctypes.c_ubyte), ("cAuxBuffers", ctypes.c_ubyte),
                ("iLayerType", ctypes.c_ubyte), ("bReserved", ctypes.c_ubyte),
                ("dwLayerMask", wintypes.DWORD), ("dwVisibleMask", wintypes.DWORD),
                ("dwDamageMask", wintypes.DWORD)]


class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("fEnable", wintypes.BOOL),
                ("hRgnBlur", wintypes.HANDLE), ("fTransitionOnMaximized", wintypes.BOOL)]


class _GL:
    """Les fonctions OpenGL utilisées, chargées depuis opengl32.dll (et le pilote de la carte)."""

    def __init__(self) -> None:
        self.dll = ctypes.WinDLL("opengl32")
        d = self.dll
        d.wglGetProcAddress.restype = ctypes.c_void_p
        d.wglGetProcAddress.argtypes = [ctypes.c_char_p]
        d.wglCreateContext.restype = ctypes.c_void_p
        d.wglCreateContext.argtypes = [ctypes.c_void_p]
        d.wglMakeCurrent.restype = wintypes.BOOL
        d.wglMakeCurrent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        d.wglDeleteContext.argtypes = [ctypes.c_void_p]
        u, i, f, p = ctypes.c_uint, ctypes.c_int, ctypes.c_float, ctypes.c_void_p
        for name, res, args in [
            ("glViewport", None, [i, i, i, i]), ("glClearColor", None, [f, f, f, f]), ("glClear", None, [u]),
            ("glDrawArrays", None, [u, i, i]), ("glGenTextures", None, [i, ctypes.POINTER(u)]),
            ("glBindTexture", None, [u, u]), ("glTexParameteri", None, [u, u, i]),
            ("glTexImage2D", None, [u, i, i, i, i, i, u, u, p]), ("glPixelStorei", None, [u, i]),
            ("glGetString", ctypes.c_char_p, [u]), ("glDisable", None, [u]), ("glGetError", u, []),
            ("glFlush", None, []),
        ]:
            fn = getattr(d, name)
            fn.restype, fn.argtypes = res, args

    def bind_extensions(self) -> None:
        """Fonctions OpenGL modernes : disponibles seulement une fois le contexte créé."""
        u, i, f = ctypes.c_uint, ctypes.c_int, ctypes.c_float
        P = ctypes.POINTER
        spec = {
            "glCreateShader": (u, [u]), "glShaderSource": (None, [u, i, P(ctypes.c_char_p), P(i)]),
            "glCompileShader": (None, [u]), "glGetShaderiv": (None, [u, u, P(i)]),
            "glGetShaderInfoLog": (None, [u, i, P(i), ctypes.c_char_p]), "glCreateProgram": (u, []),
            "glAttachShader": (None, [u, u]), "glLinkProgram": (None, [u]), "glGetProgramiv": (None, [u, u, P(i)]),
            "glGetProgramInfoLog": (None, [u, i, P(i), ctypes.c_char_p]), "glUseProgram": (None, [u]),
            "glGetUniformLocation": (i, [u, ctypes.c_char_p]), "glUniform1f": (None, [i, f]),
            "glUniform2f": (None, [i, f, f]), "glUniform4f": (None, [i, f, f, f, f]), "glUniform1i": (None, [i, i]),
            "glUniform4fv": (None, [i, i, P(f)]), "glActiveTexture": (None, [u]),
            "glGenVertexArrays": (None, [i, P(u)]), "glBindVertexArray": (None, [u]),
        }
        for name, (res, args) in spec.items():
            setattr(self, name, self._ext(name, res, args))
        try:
            self.wglSwapIntervalEXT = self._ext("wglSwapIntervalEXT", wintypes.BOOL, [ctypes.c_int])
        except OSError:
            self.wglSwapIntervalEXT = None

    def _ext(self, name: str, res, args):
        addr = self.dll.wglGetProcAddress(name.encode())
        if not addr or addr in (1, 2, 3) or addr == ctypes.c_void_p(-1).value:
            raise OSError(f"fonction OpenGL absente : {name}")
        return ctypes.WINFUNCTYPE(res, *args)(addr)

    def __getattr__(self, name: str):
        return getattr(self.dll, name)


class GpuOrb(O.Orb):
    """La sphère classique, mais dessinée par la carte graphique dans une fenêtre OpenGL transparente."""
    MAX_DEFAULT = O.SIZE_MAX                             # toutes les tailles demandées à la voix sont possibles

    def __init__(self, presence: O.Presence | None = None) -> None:
        self.gl = None
        self.hglrc = None
        super().__init__(presence)                       # fenêtre, voile noir, placement : comme avant
        if self.full:
            raise RuntimeError("mode « papier » : réservé à l'ancienne sphère")
        self.rot = random.uniform(0, 6.28)
        self.flow = 0.0
        self.lvl = 0.0
        self.text_key = None
        self.text_size = (1, 1)
        self.parts = np.zeros((MAX_PARTS, 4), np.float32)
        self.gl.wglMakeCurrent(None, None)               # le contexte sera repris par le fil qui dessine

    # --- fenêtre OpenGL transparente (remplace la fenêtre « calque » de l'ancienne sphère)
    def _create_window(self) -> None:
        user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.WinDLL("gdi32"), ctypes.windll.kernel32
        self.user32, self.gdi = user32, gdi32
        self.gdi32 = ctypes.windll.gdi32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        def proc(h, m, w, lp):
            if m == 0x0084:                              # WM_NCHITTEST : la souris passe au travers
                return -1
            if m == 0x0014:                              # WM_ERASEBKGND : rien à effacer
                return 1
            return user32.DefWindowProcW(h, m, w, lp)

        self._wndproc = WNDPROC(proc)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                        ("hIconSm", wintypes.HICON)]

        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0x0020 | 0x0002 | 0x0001                  # CS_OWNDC | CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "JarvisSphereGL"
        user32.RegisterClassExW(ctypes.byref(wc))
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.GetDC.restype = wintypes.HDC
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte,
                                                      wintypes.DWORD]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        ex = 0x00000080 | 0x08000000                     # outil (pas dans la barre des tâches), sans focus
        if self.on_top:
            ex |= 0x00000008                             # toujours devant
        self.hwnd = user32.CreateWindowExW(ex, "JarvisSphereGL", "Jarvis", 0x80000000 | 0x02000000 | 0x04000000,
                                           self.x, self.y, self.W, self.H, None, None, hinst, None)
        if not self.hwnd:
            raise OSError("création de la fenêtre impossible")
        self.msg = wintypes.MSG()
        try:
            self._init_gl()
        except Exception:
            user32.DestroyWindow(self.hwnd)
            raise

    def _init_gl(self) -> None:
        g, gdi, user32 = _GL(), self.gdi, self.user32
        self.gl = g
        gdi.ChoosePixelFormat.restype = ctypes.c_int
        gdi.ChoosePixelFormat.argtypes = [wintypes.HDC, ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
        gdi.SetPixelFormat.restype = wintypes.BOOL
        gdi.SetPixelFormat.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
        gdi.DescribePixelFormat.restype = ctypes.c_int
        gdi.DescribePixelFormat.argtypes = [wintypes.HDC, ctypes.c_int, wintypes.UINT,
                                            ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
        gdi.SwapBuffers.restype = wintypes.BOOL
        gdi.SwapBuffers.argtypes = [wintypes.HDC]
        gdi.CreateRectRgn.restype = wintypes.HANDLE
        gdi.CreateRectRgn.argtypes = [ctypes.c_int] * 4
        gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        self.hdc = user32.GetDC(self.hwnd)
        pfd = PIXELFORMATDESCRIPTOR()
        pfd.nSize, pfd.nVersion = ctypes.sizeof(PIXELFORMATDESCRIPTOR), 1
        pfd.dwFlags = 0x0004 | 0x0020 | 0x0001 | 0x8000   # fenêtre, OpenGL, double tampon, composition
        pfd.iPixelType, pfd.cColorBits, pfd.cAlphaBits = 0, 24, 8
        fmt = gdi.ChoosePixelFormat(self.hdc, ctypes.byref(pfd))
        if not fmt or not gdi.SetPixelFormat(self.hdc, fmt, ctypes.byref(pfd)):
            raise OSError("format d'image OpenGL refusé")
        got = PIXELFORMATDESCRIPTOR()
        gdi.DescribePixelFormat(self.hdc, fmt, ctypes.sizeof(got), ctypes.byref(got))
        if got.cAlphaBits < 8:
            raise OSError("pas de transparence dans le format d'image")
        self.hglrc = g.wglCreateContext(self.hdc)
        if not self.hglrc or not g.wglMakeCurrent(self.hdc, self.hglrc):
            raise OSError("contexte OpenGL impossible")
        renderer = (g.glGetString(GL_RENDERER) or b"?").decode(errors="replace")
        version = (g.glGetString(GL_VERSION) or b"0").decode(errors="replace")
        major_minor = tuple(int(x) for x in version.split(" ")[0].split(".")[:2] if x.isdigit())
        if "GDI Generic" in renderer or major_minor < (3, 3):
            raise OSError(f"carte graphique non utilisable ({renderer}, OpenGL {version})")
        g.bind_extensions()
        # transparence pixel par pixel (même méthode que GLFW) + clics qui passent au travers
        dwm = ctypes.WinDLL("dwmapi")
        rgn = gdi.CreateRectRgn(0, 0, -1, -1)
        bb = DWM_BLURBEHIND(0x1 | 0x2, True, rgn, False)          # DWM_BB_ENABLE | DWM_BB_BLURREGION
        dwm.DwmEnableBlurBehindWindow.argtypes = [wintypes.HWND, ctypes.POINTER(DWM_BLURBEHIND)]
        hr = dwm.DwmEnableBlurBehindWindow(self.hwnd, ctypes.byref(bb))
        gdi.DeleteObject(rgn)
        if hr != 0:
            raise OSError(f"transparence refusée par Windows (code {hr & 0xFFFFFFFF:#x})")
        exs = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, exs | 0x00080000 | 0x00000020)   # WS_EX_LAYERED | WS_EX_TRANSPARENT
        user32.SetLayeredWindowAttributes(self.hwnd, 0, 0, 0)
        self.dwm_flush = dwm.DwmFlush
        # programme de dessin
        src = SHADER.read_text(encoding="utf-8")
        self.prog = self._program(VS, "#version 330 core\n" + src)
        g.glUseProgram(self.prog)
        vao = ctypes.c_uint(0)
        g.glGenVertexArrays(1, ctypes.byref(vao))
        g.glBindVertexArray(vao.value)
        tex = ctypes.c_uint(0)
        g.glGenTextures(1, ctypes.byref(tex))
        g.glActiveTexture(GL_TEXTURE0)
        g.glBindTexture(GL_TEXTURE_2D, tex.value)
        for k, v in ((GL_TEXTURE_MIN_FILTER, GL_LINEAR), (GL_TEXTURE_MAG_FILTER, GL_LINEAR),
                     (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE), (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)):
            g.glTexParameteri(GL_TEXTURE_2D, k, v)
        g.glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        g.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, (ctypes.c_ubyte * 4)())
        g.glDisable(GL_BLEND)
        g.glDisable(GL_DEPTH_TEST)
        self.U = {n: g.glGetUniformLocation(self.prog, n.encode()) for n in (
            "uRes", "uC", "uR", "uT", "uLvl", "uListen", "uThink", "uRot", "uFlow", "uGain", "uFade",
            "uParts", "uNParts", "uText", "uTextRect", "uTextA")}
        g.glUniform1i(self.U["uText"], 0)
        self.vsync = bool(g.wglSwapIntervalEXT and g.wglSwapIntervalEXT(1))
        log.info("Sphère dessinée par la carte graphique : %s (OpenGL %s, synchro écran %s).",
                 renderer, version.split(" ")[0], "oui" if self.vsync else "par Windows")

    def _program(self, vs: str, fs: str) -> int:
        g = self.gl

        def compile_(kind: int, src: str) -> int:
            sh = g.glCreateShader(kind)
            buf = ctypes.c_char_p(src.encode("utf-8"))
            g.glShaderSource(sh, 1, ctypes.byref(buf), None)
            g.glCompileShader(sh)
            ok = ctypes.c_int(0)
            g.glGetShaderiv(sh, GL_COMPILE_STATUS, ctypes.byref(ok))
            if not ok.value:
                logbuf = ctypes.create_string_buffer(4096)
                g.glGetShaderInfoLog(sh, 4096, None, logbuf)
                raise OSError("dessin de la sphère refusé par la carte : " + logbuf.value.decode(errors="replace"))
            return sh

        prog = g.glCreateProgram()
        g.glAttachShader(prog, compile_(GL_VERTEX_SHADER, vs))
        g.glAttachShader(prog, compile_(GL_FRAGMENT_SHADER, fs))
        g.glLinkProgram(prog)
        ok = ctypes.c_int(0)
        g.glGetProgramiv(prog, GL_LINK_STATUS, ctypes.byref(ok))
        if not ok.value:
            logbuf = ctypes.create_string_buffer(4096)
            g.glGetProgramInfoLog(prog, 4096, None, logbuf)
            raise OSError("assemblage du dessin refusé : " + logbuf.value.decode(errors="replace"))
        return prog

    # --- textes sous la sphère (refaits seulement quand ils changent)
    def _text_texture(self, status: str, sub: str) -> None:
        c = self.comp
        key = (status, sub, c.align)
        if key == self.text_key:
            return
        self.text_key = key
        s = c.scale
        TH = int(190 * s)
        img = Image.new("RGBA", (self.W, TH), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        al = c.align
        z = c.zoom
        tx = c.cx - c.D * z * .45 if al == "left" else c.cx + c.D * z * .45 if al == "right" else c.cx
        h1, h2 = {"left": ("lm", "la"), "right": ("rm", "ra")}.get(al, ("mm", "ma"))
        y0 = 20 * s
        d.text((tx, y0), "J . A . R . V . I . S", fill=(80, 215, 255, 255), font=c.f_title, anchor=h1)
        if status:
            d.text((tx, y0 + 30 * s), status, fill=(60, 120, 255, 255), font=c.f_status, anchor=h1)
        if sub:
            d.multiline_text((tx, y0 + 70 * s), O._wrap(sub, 46 if al != "center" else 60),
                             fill=(170, 205, 255, 255), font=c.f_sub, anchor=h2, align=al)
        a = np.asarray(img, dtype=np.uint16)
        pm = np.empty_like(a, dtype=np.uint8)
        pm[..., :3] = (a[..., :3] * a[..., 3:4] // 255).astype(np.uint8)       # alpha prémultiplié
        pm[..., 3] = a[..., 3]
        pm = np.ascontiguousarray(pm)
        self.gl.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.W, TH, 0, GL_RGBA, GL_UNSIGNED_BYTE,
                             pm.ctypes.data_as(ctypes.c_void_p))
        self.text_size = (self.W, TH)
        self.text_zoom = z

    # --- une image
    def _render(self, t: float, dt: float, mode: str, target: float, status: str, sub: str, appear: float) -> None:
        g, U, c = self.gl, self.U, self.comp
        k = 1 - math.exp(-dt * (24 if target > self.lvl else 6))            # montée rapide, descente douce
        self.lvl += (target - self.lvl) * k
        c.lvl = self.lvl
        e = appear * appear * (3 - 2 * appear)
        flare = 0.9 * math.sin(math.pi * min(1.0, appear)) ** 2
        lvl = min(1.2, self.lvl + flare * 0.6)
        listening, thinking = mode == "listening", mode == "thinking"
        z = c.zoom
        breathe = 0.018 * math.sin(t * 1.15) + 0.008 * math.sin(t * 2.7 + 1)
        scale = 1.0 + breathe + 0.13 * lvl + (0.05 if listening else 0) + (0.025 * math.sin(t * 6) if thinking else 0)
        R = c.D * z * (0.35 + 0.65 * e) / 2 * scale
        self.rot += dt * (0.12 + (1.1 if thinking else 0) + 0.5 * lvl)
        self.flow += dt * (0.25 + (1.2 if thinking else 0) + 1.3 * lvl)
        # particules en orbite (mêmes règles que l'ancienne sphère)
        Rp = c.D * z / 2
        speed = 1.0 + 3.0 * self.lvl + (2.5 if thinking else 0) + (1.0 if listening else 0)
        n = min(MAX_PARTS, len(c.parts))
        for i, p in enumerate(c.parts[:n]):
            p["a"] += p["v"] * speed * dt
            rr = Rp * (p["r"] + 0.03 * math.sin(t * 1.3 + p["ph"]) + 0.10 * self.lvl * math.sin(t * 7 + p["ph"]))
            rr *= 1 + 1.6 * (1 - e) * (0.6 + 0.4 * math.sin(p["ph"] * 3))
            pz = p["z"] * (1 + 0.8 * self.lvl) * c.scale * (0.5 + 0.5 * z) * 0.8
            self.parts[i] = (c.cx + rr * math.cos(p["a"]), c.cy + rr * math.sin(p["a"]), pz,
                             0.55 + 0.35 * math.sin(t * 2 + p["ph"]) ** 2)
        if e >= 0.6:
            self._text_texture(status, sub)
        ta = max(0.0, min(1.0, (e - 0.6) / 0.25)) * (0.85 + 0.15 * math.sin(t * 1.15) + 0.2 * self.lvl)
        y_text = c.cy + c.D * z * 0.60 - 20 * c.scale
        g.glViewport(0, 0, self.W, self.H)
        g.glClearColor(0.0, 0.0, 0.0, 0.0)
        g.glClear(GL_COLOR_BUFFER_BIT)
        g.glUniform2f(U["uRes"], self.W, self.H)
        g.glUniform2f(U["uC"], c.cx, c.cy)
        g.glUniform1f(U["uR"], max(4.0, R))
        g.glUniform1f(U["uT"], t)
        g.glUniform1f(U["uLvl"], lvl)
        g.glUniform1f(U["uListen"], 1.0 if listening else 0.0)
        g.glUniform1f(U["uThink"], 1.0 if thinking else 0.0)
        g.glUniform1f(U["uRot"], self.rot)
        g.glUniform1f(U["uFlow"], self.flow)
        g.glUniform1f(U["uGain"], 0.95 + 0.08 * math.sin(t * 0.9) + 0.8 * lvl + (0.25 if listening else 0)
                      + (0.12 if thinking else 0))
        g.glUniform1f(U["uFade"], min(1.0, self.fade * 1.6))
        g.glUniform4fv(U["uParts"], MAX_PARTS, self.parts.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
        g.glUniform1i(U["uNParts"], n)
        g.glUniform4f(U["uTextRect"], 0.0, y_text, float(self.text_size[0]), float(self.text_size[1]))
        g.glUniform1f(U["uTextA"], ta if self.text_key is not None else 0.0)
        g.glDrawArrays(GL_TRIANGLES, 0, 3)
        self.gdi.SwapBuffers(self.hdc)

    # --- boucle : une image par rafraîchissement de l'écran
    def run(self) -> None:
        if not self.gl.wglMakeCurrent(self.hdc, self.hglrc):
            raise OSError("contexte OpenGL indisponible dans ce fil")
        old_switch = sys.getswitchinterval()
        fast = False                                     # bascule rapide entre fils : seulement quand elle s'affiche
        try:
            import mode_jeu
            in_game = mode_jeu.ACTIF.is_set
        except ImportError:
            in_game = lambda: False                      # noqa: E731
        t0 = last = time.perf_counter()
        frames, fps_t = 0, t0
        self.fps_logged = False
        try:
            while not self.stop:
                start = time.perf_counter()
                dt, last = min(0.1, start - last), start
                self._pump()
                p = self.presence
                mode, target = p.level(time.monotonic())
                with p.lock:
                    want = (p.pinned or mode != "idle" or (time.monotonic() - p.last_active) < O.LINGER_S
                            or time.monotonic() < p.pinned_until) and not p.hidden
                    status, sub = p.status, p.subtitle
                    nb = p.style.get("fond_noir")
                if nb is not None:
                    self.black_max = nb / 100
                st = p.style
                if (st.get("ecran"), st.get("place"), st.get("taille")) != getattr(self, "_placed", None):
                    try:
                        self._place()
                    except Exception:  # noqa: BLE001
                        self._placed = (st.get("ecran"), st.get("place"), st.get("taille"))
                tz = self._target_zoom(mode)
                self.comp.zoom += (tz - self.comp.zoom) * min(1.0, dt * 5)
                if self.comp.align != "center" and abs(self.comp.zoom - getattr(self, "text_zoom", self.comp.zoom)) > .01:
                    self.text_key = None                 # texte à droite / à gauche : suit la taille
                if want:
                    self.fade = min(1.0, self.fade + dt / O.FADE_IN_S)
                else:
                    self.fade = max(0.0, self.fade - dt / O.FADE_OUT_S)
                self._set_black(self.fade)
                game = in_game()
                want_fast = self.fade > 0.0 and not game
                if want_fast != fast:                    # les autres fils de Jarvis ne retardent pas l'image
                    sys.setswitchinterval(0.0005 if want_fast else old_switch)
                    fast = want_fast
                if self.fade <= 0.0:
                    self._show(False)
                    time.sleep(0.05)                     # repos : ne consomme rien
                    last = fps_t = time.perf_counter()
                    frames = 0
                    continue
                try:
                    self._render(start - t0, dt, mode, target, status, sub, self.fade)
                    if not self.vsync:
                        self.dwm_flush()                 # attend l'affichage suivant de Windows
                    self._show(True)
                    if not self.on_top and start - self.last_sink > 1.0:
                        self._zorder()
                except Exception:  # noqa: BLE001
                    log.exception("Erreur d'animation de la sphère")
                    time.sleep(0.5)
                spent = time.perf_counter() - start
                floor = (1 / 60 if self.on_top else 1 / 20) if game else 0.002   # en jeu : la carte est au jeu
                if spent < floor:                        # (et synchro coupée dans le pilote : on ne s'emballe pas)
                    time.sleep(floor - spent)
                frames += 1
                if start - fps_t >= 5:
                    if not self.fps_logged:              # une mesure dans jarvis.log pour vérifier la fluidité
                        log.info("Sphère : %.0f images/s.", frames / (start - fps_t))
                        self.fps_logged = True
                    frames, fps_t = 0, start
        finally:
            sys.setswitchinterval(old_switch)
            self._show(False)
            self._set_black(0.0)
