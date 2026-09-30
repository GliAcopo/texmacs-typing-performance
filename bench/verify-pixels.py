#!/usr/bin/env python3
"""Pixel-exact comparison of two TeXmacs builds after the same edits.

usage: verify-pixels.py <doc.tm> <launcher-1> <launcher-2> [pages] [--clean-home] [--real-fonts]
       [--pref1=key=value] [--pref2=key=value]   (user preference for build 1 / 2)

Each build opens a scratch copy of the document on its own Xvfb, applies the fixed edit
sequence of verify.scm (typing, Return, a new section near the top, math, backspace, joining
paragraphs, undo), goes back to the start and then the driver pages through the document with
Page_Down, taking a screenshot of the whole screen after each page once TeXmacs is idle.
The screenshots of the two builds must be identical: unlike the geometric check of
verify.sh, this also catches wrong content of the same size (e.g. a stale section number).
--clean-home uses a fresh TEXMACS_HOME_PATH (synth/home-template: initialized, no welcome) (for documents that only need the stock styles).
"""
import os, sys, time, shutil, subprocess, glob
from Xlib import X, display, XK
from Xlib.ext import xtest
from PIL import Image, ImageChops

P = os.path.expanduser("~/Projects/texmacs-perf")
W = os.environ.get("TMBENCH_WORK", os.path.expanduser("~/.cache/tmbench"))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
doc, launchers = os.path.abspath(args[0]), args[1:3]
pages = int(args[3]) if len(args) > 3 else 40
clean_home = "--clean-home" in sys.argv
GEOM = "1920x1200x24"


def start_xvfb(disp, geom):
    """Start Xvfb on disp, removing a stale lock/socket left by a killed server first."""
    n = disp[1:]
    lock, sock = f"/tmp/.X{n}-lock", f"/tmp/.X11-unix/X{n}"
    if os.path.exists(lock):
        try:
            os.kill(int(open(lock).read().strip()), 0)
            raise SystemExit(f"display {disp} is in use")
        except (ProcessLookupError, ValueError):
            for f in (lock, sock):
                if os.path.exists(f): os.remove(f)
    xvfb = subprocess.Popen(["Xvfb", disp, "-screen", "0", geom, "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if xvfb.poll() is not None: raise SystemExit(f"Xvfb {disp} did not start")
        if os.path.exists(sock): return xvfb
        time.sleep(0.2)
    raise SystemExit(f"Xvfb {disp} did not start")


def cpu_ticks(pid):
    try:
        f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
        return int(f[11]) + int(f[12])
    except Exception:
        return 0


def wait_idle(pid, limit_s=300):
    # idle = less than 10 ticks (100 ms) of CPU during one second
    prev = cpu_ticks(pid); t_end = time.time() + limit_s
    while time.time() < t_end:
        time.sleep(1.0)
        cur = cpu_ticks(pid)
        if cur - prev < 10: return
        prev = cur


def shot(disp, path):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-video_size",
                    GEOM.rsplit("x", 1)[0], "-i", disp, "-frames:v", "1", path], check=True)


def run(launcher, idx):
    tag = f"px{idx}-{os.path.basename(launcher)}"
    ddir = f"{W}/{tag}-doc"
    shutil.rmtree(ddir, ignore_errors=True)
    shutil.copytree(os.path.dirname(doc), ddir, symlinks=True)
    for f in glob.glob(f"{ddir}/*~"): os.remove(f)
    home = f"{W}/{tag}-home"
    shutil.rmtree(home, ignore_errors=True)
    if clean_home: shutil.copytree(P + "/synth/home-template", home)  # initialized, window sized to the screen
    else:
        subprocess.run(["rsync", "-a", "--exclude", "system/tmp", "--exclude", "system/boot_lock",
                        os.path.expanduser("~/.TeXmacs/"), home + "/"], check=True)
    # saved window geometry is the one of the real screen: drop it; add --prefN=key=value
    prefs = f"{home}/system/preferences.scm"
    lines = open(prefs, encoding="latin-1").readlines() if os.path.exists(prefs) else []
    lines = [l for l in lines if not l.startswith(('("abscissa ', '("ordinate ', '("width ', '("height '))]
    extra = opts.get(f"pref{idx}")
    if extra:
        k, v = extra.split("=", 1)
        lines = [l for l in lines if not l.startswith(f'("{k}" ')] + [f'("{k}" "{v}")\n']
    os.makedirs(os.path.dirname(prefs), exist_ok=True)
    open(prefs, "w", encoding="latin-1").writelines(lines)
    outdir = f"{W}/{tag}-shots"
    shutil.rmtree(outdir, ignore_errors=True); os.makedirs(outdir)
    ready, done, dump = (f"{W}/{tag}.{k}" for k in ("ready", "done", "dump"))
    for f in (ready, done, dump):
        if os.path.exists(f): os.remove(f)
    disp = f":{93 + idx}"
    xvfb = start_xvfb(disp, GEOM)
    path = os.environ["PATH"] if "real-fonts" in opts else P + "/bench/fakebin:" + os.environ["PATH"]
    env = dict(os.environ, PATH=path, DISPLAY=disp,
               QT_QPA_PLATFORM="xcb", WAYLAND_DISPLAY="", TEXMACS_HOME_PATH=home,
               TMVERIFY_OUT=dump, TMVERIFY_READY=ready, TMVERIFY_DONE=done)
    tm = subprocess.Popen([launcher, f"{ddir}/{os.path.basename(doc)}", "-x",
                           f'(load "{P}/bench/verify.scm")'], env=env,
                          stdout=open(f"{W}/{tag}.log", "w"), stderr=subprocess.STDOUT)
    try:
        t0 = time.time()
        while not os.path.exists(ready):
            if tm.poll() is not None or time.time() - t0 > 900:
                raise SystemExit(f"{launcher}: not ready (see {W}/{tag}.log)")
            time.sleep(0.3)
        d = display.Display(disp); root = d.screen().root
        best = None
        for w in root.query_tree().children:
            try: a = w.get_attributes(); g = w.get_geometry()
            except Exception: continue
            if a.map_state == X.IsViewable and (best is None or g.width * g.height > best[1]):
                best = (w, g.width * g.height)
        best[0].set_input_focus(X.RevertToParent, X.CurrentTime)
        xtest.fake_input(d, X.MotionNotify, x=1, y=1); d.sync()   # pointer out of the text
        kc = d.keysym_to_keycode(XK.string_to_keysym("Next"))
        wait_idle(tm.pid)
        for k in range(pages + 1):
            shot(disp, f"{outdir}/{k:03d}.png")
            xtest.fake_input(d, X.KeyPress, kc); xtest.fake_input(d, X.KeyRelease, kc); d.sync()
            time.sleep(0.3)
            wait_idle(tm.pid)
        open(done, "w").close()
        try: tm.wait(timeout=60)
        except subprocess.TimeoutExpired: tm.kill()   # screenshots and dump are already taken
    finally:
        if tm.poll() is None: tm.kill()
        xvfb.kill()
        # the document folder may hold hundreds of MB of images
        shutil.rmtree(ddir, ignore_errors=True); shutil.rmtree(home, ignore_errors=True)
    return outdir, dump


(o1, d1), (o2, d2) = run(launchers[0], 1), run(launchers[1], 2)
same = diff = 0
for f in sorted(os.listdir(o1)):
    a, b = Image.open(f"{o1}/{f}").convert("RGB"), Image.open(f"{o2}/{f}").convert("RGB")
    box = ImageChops.difference(a, b).getbbox()
    if box is None: same += 1
    else:
        diff += 1
        print(f"page {f}: differs in {box}")
geo = open(d1).read().split("\n", 1)[1] == open(d2).read().split("\n", 1)[1]
# sanity: the edits went into the right buffer, and paging really moved through the document
for dmp in (d1, d2):
    if os.path.basename(doc) not in open(dmp).readline():
        print(f"WARNING: {dmp} is not a dump of {os.path.basename(doc)}")
fs = sorted(os.listdir(o1)); moved = 0
for f, g in zip(fs, fs[1:]):
    if ImageChops.difference(Image.open(f"{o1}/{f}").convert("RGB"),
                             Image.open(f"{o1}/{g}").convert("RGB")).getbbox(): moved += 1
print(f"paging: {moved} of {len(fs) - 1} Page_Down presses changed the screen")
print(f"{os.path.basename(doc)}: {same} identical screenshots, {diff} different; "
      f"geometry dump {'identical' if geo else 'DIFFERENT'}  ({o1} vs {o2})")
