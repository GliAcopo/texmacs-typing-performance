#!/usr/bin/env python3
"""Pixel self-check of incremental repainting: what is on screen after each edit must be
identical to a full repaint of the window.

usage: shift-check.py <doc.tm> <launcher> [keys] [--par=N] [--geom=WxH] [--dpi=N] [--real-fonts]

The document copy is opened on a private Xvfb (2560x1600 at Xft.dpi 168 by default, like the
real desktop), the cursor is put at the end of body paragraph N (shift-check.scm), and then
for each key of the comma separated list (X keysym names, e.g. "Return,a,BackSpace"; a "+"
joins modifiers: "Control_L+BackSpace") the driver presses the key, waits until TeXmacs is
idle and takes a screenshot, then presses F12 (bound to refresh-window: full repaint), waits
again and takes a second screenshot.  The two must be identical.  A key ending in "!"
is also followed by C-F12 (full retypeset of the document): the screen must not change.  Differences are saved
(both screenshots and a diff crop) in the output folder.
"""
import os, sys, time, shutil, subprocess, glob
from Xlib import X, display, XK
from Xlib.ext import xtest
from PIL import Image, ImageChops

P = os.path.expanduser("~/Projects/texmacs-perf")
W = os.environ.get("TMBENCH_WORK", os.path.expanduser("~/.cache/tmbench"))
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1")
            for a in sys.argv[1:] if a.startswith("--"))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
doc, launcher = os.path.abspath(args[0]), args[1]
keys = (args[2] if len(args) > 2 else
        "Return,a,Return,BackSpace,BackSpace,BackSpace,Return,Return,BackSpace").split(",")
GEOM = opts.get("geom", "2560x1600")
DPI = opts.get("dpi", "168")
STATUS_H = int(opts.get("status-bar", "60"))
tag = "shift-" + opts.get("tag", os.path.basename(launcher))


def start_xvfb(disp, geom):
    n = disp[1:]
    lock, sock = f"/tmp/.X{n}-lock", f"/tmp/.X11-unix/X{n}"
    if os.path.exists(lock):
        try:
            os.kill(int(open(lock).read().strip()), 0)
            raise SystemExit(f"display {disp} is in use")
        except (ProcessLookupError, ValueError):
            for f in (lock, sock):
                if os.path.exists(f): os.remove(f)
    xvfb = subprocess.Popen(["Xvfb", disp, "-screen", "0", geom + "x24", "-nolisten", "tcp"],
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
    # idle = less than 3 ticks (30 ms) of CPU during 0.7 s
    prev = cpu_ticks(pid); t_end = time.time() + limit_s
    while time.time() < t_end:
        time.sleep(0.7)
        cur = cpu_ticks(pid)
        if cur - prev < 3: return
        prev = cur


def shot(disp, path):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-video_size",
                    GEOM, "-i", disp, "-frames:v", "1", path], check=True)


def press(d, spec):
    codes = [d.keysym_to_keycode(XK.string_to_keysym(k)) for k in spec.split("+")]
    for c in codes: xtest.fake_input(d, X.KeyPress, c)
    for c in reversed(codes): xtest.fake_input(d, X.KeyRelease, c)
    d.sync()


ddir, home, out = f"{W}/{tag}-doc", f"{W}/{tag}-home", f"{W}/{tag}-out"
for x in (ddir, home, out): shutil.rmtree(x, ignore_errors=True)
shutil.copytree(os.path.dirname(doc), ddir, symlinks=True)
for f in glob.glob(f"{ddir}/*~"): os.remove(f)
subprocess.run(["rsync", "-a", "--exclude", "system/tmp", "--exclude", "system/cache",
                "--exclude", "system/boot_lock", os.path.expanduser("~/.TeXmacs/"), home + "/"],
               check=True)
if os.path.exists(f"{home}/system/remember-cursor.scm"): os.remove(f"{home}/system/remember-cursor.scm")
# saved window geometry is the one of the real screen: drop it
prefs = f"{home}/system/preferences.scm"
if os.path.exists(prefs):
    keep = [l for l in open(prefs, encoding="latin-1")
            if not l.startswith(('("abscissa ', '("ordinate ', '("width ', '("height '))]
    open(prefs, "w", encoding="latin-1").writelines(keep)
os.makedirs(out)
ready = f"{W}/{tag}.ready"
if os.path.exists(ready): os.remove(ready)
disp = opts.get("display", ":97")
xvfb = start_xvfb(disp, GEOM)
subprocess.run(["xrdb", "-merge", "-display", disp], input=f"Xft.dpi: {DPI}\n", text=True)
path = os.environ["PATH"] if "real-fonts" in opts else P + "/bench/fakebin:" + os.environ["PATH"]
env = dict(os.environ, PATH=path, DISPLAY=disp, QT_QPA_PLATFORM="xcb", WAYLAND_DISPLAY="",
           TEXMACS_HOME_PATH=home, TMSHIFT_READY=ready, TMSHIFT_PAR=opts.get("par", "30"))
log = open(f"{out}/texmacs.log", "w")
tm = subprocess.Popen([launcher, f"{ddir}/{os.path.basename(doc)}", "-x",
                       f'(load "{P}/bench/shift-check.scm")'], env=env,
                      stdout=log, stderr=subprocess.STDOUT)
bad = 0
try:
    t0 = time.time()
    while not os.path.exists(ready):
        if tm.poll() is not None or time.time() - t0 > 900:
            raise SystemExit(f"{launcher}: not ready (see {out}/texmacs.log)")
        time.sleep(0.3)
    d = display.Display(disp); root = d.screen().root
    best = None
    for w in root.query_tree().children:
        try: a = w.get_attributes(); g = w.get_geometry()
        except Exception: continue
        if a.map_state == X.IsViewable and (best is None or g.width * g.height > best[1]):
            best = (w, g.width * g.height)
    best[0].set_input_focus(X.RevertToParent, X.CurrentTime)
    wg = best[0].get_geometry()
    # the status bar (last shortcut, messages) at the bottom of the window is
    # not part of the canvas
    sb_y1, sb_y2 = wg.y + wg.height - STATUS_H, wg.y + wg.height
    def canvas_diff(a, b):
        d = ImageChops.difference(a, b)
        d.paste((0, 0, 0), (0, max(0, sb_y1), d.width, min(d.height, sb_y2)))
        return d.getbbox()
    xtest.fake_input(d, X.MotionNotify, x=1, y=1); d.sync()
    wait_idle(tm.pid)
    shot(disp, f"{out}/start.png")
    prev = Image.open(f"{out}/start.png").convert("RGB")
    for i, k in enumerate(keys):
        retypeset = k.endswith("!")
        k = k.rstrip("!")
        t0 = cpu_ticks(tm.pid)
        press(d, k); time.sleep(0.2); wait_idle(tm.pid)
        cpu = (cpu_ticks(tm.pid) - t0) * 10
        a_path, b_path = f"{out}/{i:02d}-a.png", f"{out}/{i:02d}-b.png"
        shot(disp, a_path)
        press(d, "F12"); time.sleep(0.2); wait_idle(tm.pid)
        shot(disp, b_path)
        a, b = Image.open(a_path).convert("RGB"), Image.open(b_path).convert("RGB")
        box = canvas_diff(a, b)
        moved = ImageChops.difference(prev, b).getbbox()
        if box is None:
            print(f"{i:02d} {k:12s} ok       {cpu:5d} ms cpu  (screen changed in {moved})")
            os.remove(a_path)
        else:
            bad += 1
            print(f"{i:02d} {k:12s} DIFFERS  {cpu:5d} ms cpu  in {box}  (screen changed in {moved})")
            ImageChops.difference(a, b).crop(box).point(lambda v: 255 if v else 0).save(
                f"{out}/{i:02d}-diff.png")
        if retypeset:
            # the incremental typesetting must give what a full retypeset gives
            press(d, "Control_L+F12"); time.sleep(0.5); wait_idle(tm.pid)
            c_path = f"{out}/{i:02d}-c.png"
            shot(disp, c_path)
            c = Image.open(c_path).convert("RGB")
            box2 = canvas_diff(b, c)
            if box2 is None:
                print(f"   {'':12s} retypeset ok")
                os.remove(c_path)
            else:
                bad += 1
                print(f"   {'':12s} RETYPESET DIFFERS in {box2}")
            b = c
        prev = b
finally:
    if tm.poll() is None: tm.kill()
    xvfb.kill()
    shutil.rmtree(ddir, ignore_errors=True); shutil.rmtree(home, ignore_errors=True)
print(f"{os.path.basename(doc)}: {len(keys) - bad} of {len(keys)} edits repainted exactly  ({out})")
sys.exit(1 if bad else 0)
