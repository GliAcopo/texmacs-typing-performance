#!/usr/bin/env python3
"""CPU cost of animations (e.g. an animated GIF in <video>) while idle and while typing.

usage: anim-bench.py <doc.tm> <launcher> [--par=N] [--secs=S] [--tag=T] [--display=:N]

Opens a copy of the document's folder on a private Xvfb (2560x1600, Xft.dpi 168), with the
cursor far from the video (paragraph N), and measures the CPU used by TeXmacs:
  1. idle for S seconds, before the video was ever shown;
  2. idle and while typing 40 characters (one every 100 ms) with the video on screen
     (F10 moves the cursor to it);
  3. idle and while typing after moving back to paragraph N (the video has been shown).
"""
import os, sys, time, shutil, subprocess, glob
from Xlib import X, display, XK
from Xlib.ext import xtest

P = os.path.expanduser("~/Projects/texmacs-perf")
W = os.environ.get("TMBENCH_WORK", os.path.expanduser("~/.cache/tmbench"))
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1")
            for a in sys.argv[1:] if a.startswith("--"))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
doc, launcher = os.path.abspath(args[0]), args[1]
SECS = float(opts.get("secs", "10"))
tag = "anim-" + opts.get("tag", os.path.basename(launcher))
disp = opts.get("display", ":96")

def ticks(pid):
    if any(k.startswith('sample') for k in opts): return 0
    f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
    return int(f[11]) + int(f[12])

def press(d, name):
    c = d.keysym_to_keycode(XK.string_to_keysym(name))
    xtest.fake_input(d, X.KeyPress, c); xtest.fake_input(d, X.KeyRelease, c); d.sync()

def settle(pid, s=4.0): time.sleep(s)

ddir, home = f"{W}/{tag}-doc", f"{W}/{tag}-home"
for x in (ddir, home): shutil.rmtree(x, ignore_errors=True)
shutil.copytree(os.path.dirname(doc), ddir, symlinks=True)
subprocess.run(["rsync", "-a", "--exclude", "system/tmp", "--exclude", "system/cache",
                "--exclude", "system/boot_lock", os.path.expanduser("~/.TeXmacs/"), home + "/"], check=True)
prefs = f"{home}/system/preferences.scm"
if os.path.exists(prefs):  # saved window geometry is the one of the real screen
    keep = [l for l in open(prefs, encoding="latin-1")
            if not l.startswith(('("abscissa ', '("ordinate ', '("width ', '("height '))]
    open(prefs, "w", encoding="latin-1").writelines(keep)
rc = f"{home}/system/remember-cursor.scm"
if os.path.exists(rc): os.remove(rc)
ready = f"{W}/{tag}.ready"
if os.path.exists(ready): os.remove(ready)
n = disp[1:]
for f in (f"/tmp/.X{n}-lock", f"/tmp/.X11-unix/X{n}"):
    if os.path.exists(f): os.remove(f)
xvfb = subprocess.Popen(["Xvfb", disp, "-screen", "0", "2560x1600x24", "-nolisten", "tcp"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
subprocess.run(["xrdb", "-merge", "-display", disp], input="Xft.dpi: 168\n", text=True)
env = dict(os.environ, DISPLAY=disp, QT_QPA_PLATFORM="xcb", WAYLAND_DISPLAY="",
           TEXMACS_HOME_PATH=home, TMANIM_READY=ready, TMANIM_PAR=opts.get("par", "30"))
tm = subprocess.Popen([launcher, f"{ddir}/{os.path.basename(doc)}", "-x",
                       f'(load "{P}/bench/anim-bench.scm")'], env=env,
                      stdout=open(f"{W}/{tag}.log", "w"), stderr=subprocess.STDOUT)
try:
    t0 = time.time()
    while not os.path.exists(ready):
        if tm.poll() is not None or time.time() - t0 > 900: raise SystemExit("not ready")
        time.sleep(0.3)
    d = display.Display(disp); root = d.screen().root
    best = None
    for w in root.query_tree().children:
        try: a = w.get_attributes(); g = w.get_geometry()
        except Exception: continue
        if a.map_state == X.IsViewable and (best is None or g.width * g.height > best[1]):
            best = (w, g.width * g.height)
    best[0].set_input_focus(X.RevertToParent, X.CurrentTime)
    xtest.fake_input(d, X.MotionNotify, x=1, y=1); d.sync()
    def binpid():
        for p in os.listdir("/proc"):
            if p.isdigit():
                try:
                    if os.path.basename(os.readlink(f"/proc/{p}/exe")) == "texmacs.bin" and \
                       f"{os.path.basename(doc)}" in open(f"/proc/{p}/cmdline").read() and \
                       open(f"/proc/{p}/environ").read().find(home) >= 0:
                        return int(p)
                except Exception: pass
    def idle(label, sample=False):
        pid = binpid() if sample else None
        a = ticks(tm.pid)
        if pid:
            for i in range(int(SECS * 10)):
                time.sleep(0.1); os.kill(pid, 2)
        else: time.sleep(SECS)
        b = ticks(tm.pid)
        rss = 0
        try:
            bp = binpid()
            rss = int([l for l in open(f"/proc/{bp}/status") if l.startswith("VmRSS")][0].split()[1]) // 1024
        except Exception: pass
        print(f"{label:34s} {100.0 * (b - a) / (SECS * 100):6.1f} % of a core   RSS {rss} MB")
    def typing(label, sample=False):
        pid = binpid() if sample else None
        a = ticks(tm.pid); t = time.time()
        for i in range(40):
            press(d, "space" if i % 6 == 5 else "a"); time.sleep(0.05)
            if pid: os.kill(pid, 2)
            time.sleep(0.05)
        time.sleep(1.0)
        b = ticks(tm.pid)
        print(f"{label:34s} {(b - a) * 10 / 40:6.1f} ms cpu per key (incl. 1 s after)")
    time.sleep(3); idle("idle, video never shown")
    press(d, "F10"); time.sleep(3)
    for k in range(int(opts.get("down", "3"))): press(d, "Down"); time.sleep(0.3)
    time.sleep(3)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-video_size",
                    "2560x1600", "-i", disp, "-frames:v", "1", f"{W}/{tag}-video.png"])
    idle("idle, video on screen", "sample-idle" in opts)
    idle("idle, video on screen (again)")
    idle("idle, video on screen (again)")
    typing("typing, video on screen", "sample-typing" in opts)
    press(d, "F11"); time.sleep(4)
    idle("idle, video shown, now off screen")
    typing("typing, video off screen")
    # back to the video: it must play again
    press(d, "F10"); time.sleep(3)
    for k in range(int(opts.get("down", "3"))): press(d, "Down"); time.sleep(0.3)
    time.sleep(2)
    shots = []
    for k in range(2):
        f = f"{W}/{tag}-back{k}.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab", "-video_size",
                        "2560x1600", "-i", disp, "-frames:v", "1", f])
        shots.append(f); time.sleep(1.0)
    from PIL import Image, ImageChops
    box = ImageChops.difference(Image.open(shots[0]).convert("RGB"),
                                Image.open(shots[1]).convert("RGB")).getbbox()
    print(f"back on screen, frames 1 s apart differ in: {box}")
finally:
    if tm.poll() is None: tm.kill()
    xvfb.kill()
    shutil.rmtree(ddir, ignore_errors=True); shutil.rmtree(home, ignore_errors=True)
