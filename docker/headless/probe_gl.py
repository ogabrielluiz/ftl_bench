#!/usr/bin/env python3
"""Headless display probe: exactly what FTL does at startup, minus the game.

Loads SDL2 via ctypes (no python binding needed), inits the video subsystem against the X
display (Xvfb), and creates a hidden window + an OpenGL context (served by Mesa's llvmpipe
software rasterizer). If this succeeds with no GPU and no visible display, FTL.amd64 can too.
Exits non-zero with the SDL error on any failure.
"""
import ctypes
import sys

SDL_INIT_VIDEO = 0x00000020
SDL_WINDOW_OPENGL = 0x00000002
SDL_WINDOW_HIDDEN = 0x00000008


def err(sdl) -> str:
    sdl.SDL_GetError.restype = ctypes.c_char_p
    return (sdl.SDL_GetError() or b"").decode("utf-8", "replace")


def main() -> int:
    try:
        sdl = ctypes.CDLL("libSDL2-2.0.so.0")
    except OSError as e:
        print(f"cannot load libSDL2-2.0.so.0: {e}")
        return 1

    if sdl.SDL_Init(SDL_INIT_VIDEO) != 0:
        print(f"SDL_Init(VIDEO) failed: {err(sdl)}")
        return 1

    sdl.SDL_CreateWindow.restype = ctypes.c_void_p
    sdl.SDL_CreateWindow.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    win = sdl.SDL_CreateWindow(b"probe", 0, 0, 320, 240,
                               SDL_WINDOW_OPENGL | SDL_WINDOW_HIDDEN)
    if not win:
        print(f"SDL_CreateWindow(OPENGL) failed: {err(sdl)}")
        return 1

    sdl.SDL_GL_CreateContext.restype = ctypes.c_void_p
    sdl.SDL_GL_CreateContext.argtypes = [ctypes.c_void_p]
    ctx = sdl.SDL_GL_CreateContext(ctypes.c_void_p(win))
    if not ctx:
        print(f"SDL_GL_CreateContext failed: {err(sdl)}")
        return 1

    # Report the GL strings the context resolved to (proves a real GL context, not a stub).
    try:
        gl = ctypes.CDLL("libGL.so.1")
        gl.glGetString.restype = ctypes.c_char_p
        for name, enum in (("GL_VENDOR", 0x1F00), ("GL_RENDERER", 0x1F01), ("GL_VERSION", 0x1F02)):
            s = gl.glGetString(enum)
            print(f"  {name}: {(s or b'?').decode('utf-8', 'replace')}")
    except OSError:
        pass

    print("SDL2 video + OpenGL context OK (headless)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
