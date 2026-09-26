#!/usr/bin/env python3
"""Side-by-side typing video of two TeXmacs builds.

usage: video.py <doc.tm> <start|par|end> <label1> <launcher1> <label2> <launcher2> <out.mp4>
                [--text=lorem|enter] [--keys=N] [--gap=MS] [--clean-home] [--crop=WxH+X+Y]

Both builds open a scratch copy of the same document on their own Xvfb, the cursor is put at
the requested place (see keystroke.scm), and then the same X key events are sent to both at the
same moment, every GAP ms.  Each screen is recorded; the result shows them side by side with
a clock and a mark at the moment the last key was sent, so that the time each build needs to
catch up with the typing is visible.  Nothing is saved: the scratch copies are thrown away.
"""
import os, sys, time, shutil, subprocess, glob
from Xlib import X, display, XK
from Xlib.ext import xtest

P = os.path.expanduser("~/Projects/texmacs-perf")
W = os.environ.get("TMBENCH_WORK", os.path.expanduser("~/.cache/tmbench")) + "/video"
os.makedirs(W, exist_ok=True)
pos_args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
doc, pos, lab1, l1, lab2, l2, out = pos_args[:7]
doc = os.path.abspath(doc)
LOREM = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
         "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. ")
text = LOREM
if opts.get("text") == "enter":
    text = "Lorem ipsum dolor sit amet.\nConsectetur adipiscing elit.\nSed do eiusmod tempor.\n"
NKEYS = int(opts.get("keys", len(text)))
GAP = float(opts.get("gap", 80)) / 1000
GEOM = tuple(map(int, opts.get("geom", "1920x1080").split("x")))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


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


def fit_window(home):
    """Make the main window of the scratch configuration fit the virtual screen."""
    pf = f"{home}/system/preferences.scm"
    want = {"abscissa TeXmacs": 0, "ordinate TeXmacs": 0,
            "width TeXmacs": GEOM[0], "height TeXmacs": GEOM[1]}
    # latin-1 keeps the raw bytes (TeXmacs writes some values in its own encoding)
    lines = open(pf, encoding="latin-1").read().splitlines() if os.path.exists(pf) else []
    keep = [l for l in lines if not any(l.startswith(f'("{k}"') or l.startswith(f'("{k}:')
                                        for k in want)]
    keep += [f'("{k}" "{v}")' for k, v in want.items()]
    open(pf, "w", encoding="latin-1").write("\n".join(keep) + "\n")


class Side:
    def __init__(self, idx, launcher):
        self.tag = f"v{idx}"
        self.disp = f":{80 + idx}"
        ddir = f"{W}/{self.tag}-doc"
        shutil.rmtree(ddir, ignore_errors=True)
        shutil.copytree(os.path.dirname(doc), ddir, symlinks=True)
        for f in glob.glob(f"{ddir}/*~"): os.remove(f)
        home = f"{W}/{self.tag}-home"
        shutil.rmtree(home, ignore_errors=True)
        if "clean-home" in opts: shutil.copytree(P + "/synth/home-template", home)  # initialized, window sized to the screen
        else:
            subprocess.run(["rsync", "-a", "--exclude", "system/tmp", "--exclude", "system/boot_lock",
                            os.path.expanduser("~/.TeXmacs/"), home + "/"], check=True)
            fit_window(home)
        self.ready, self.done, self.outf = (f"{W}/{self.tag}.{k}" for k in ("ready", "done", "out"))
        for f in (self.ready, self.done, self.outf):
            if os.path.exists(f): os.remove(f)
        self.xvfb = start_xvfb(self.disp, f"{GEOM[0]}x{GEOM[1]}x24")
        env = dict(os.environ, PATH=P + "/bench/fakebin:" + os.environ["PATH"], DISPLAY=self.disp,
                   QT_QPA_PLATFORM="xcb", WAYLAND_DISPLAY="", TEXMACS_HOME_PATH=home,
                   TMBENCH_MODE="xtest", TMBENCH_POS=pos, TMBENCH_DIR=P + "/bench",
                   TMBENCH_OUT=self.outf, TMBENCH_READY=self.ready, TMBENCH_DONE=self.done,
                   TEXMACS_BENCH_LOG=f"{W}/{self.tag}.cycles")   # used by instrumented builds only
        self.tm = subprocess.Popen([launcher, f"{ddir}/{os.path.basename(doc)}", "-x",
                                    f'(load "{P}/bench/keystroke.scm")'], env=env,
                                   stdout=open(f"{W}/{self.tag}.log", "w"), stderr=subprocess.STDOUT)
        self.rec = None

    def wait_ready(self):
        t0 = time.time()
        while not os.path.exists(self.ready):
            if self.tm.poll() is not None or time.time() - t0 > 600:
                raise SystemExit(f"{self.tag}: texmacs did not get ready (see {W}/{self.tag}.log)")
            time.sleep(0.3)
        self.d = display.Display(self.disp)
        root = self.d.screen().root
        best = None
        for w in root.query_tree().children:
            try: a = w.get_attributes(); g = w.get_geometry()
            except Exception: continue
            if a.map_state == X.IsViewable and (best is None or g.width * g.height > best[1]):
                best = (w, g.width * g.height)
        best[0].set_input_focus(X.RevertToParent, X.CurrentTime)
        xtest.fake_input(self.d, X.MotionNotify, x=1, y=1); self.d.sync()

    def idle(self, prev):
        cur = cpu_ticks(self.tm.pid)
        return cur - prev < 10, cur

    def start_rec(self):
        self.video = f"{W}/{self.tag}.mkv"
        self.rec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "x11grab",
                                     "-framerate", "30", "-video_size", f"{GEOM[0]}x{GEOM[1]}",
                                     "-i", self.disp, "-c:v", "libx264", "-preset", "ultrafast",
                                     "-crf", "18", self.video], stdin=subprocess.PIPE)

    def stop_rec(self):
        self.rec.communicate(b"q", timeout=60)

    def key(self, ch):
        ks = XK.string_to_keysym({" ": "space", "\n": "Return", ",": "comma", ".": "period"}.get(ch, ch))
        kc = self.d.keysym_to_keycode(ks)
        shift = ch.isupper()
        sk = self.d.keysym_to_keycode(XK.string_to_keysym("Shift_L"))
        if shift: xtest.fake_input(self.d, X.KeyPress, sk)
        xtest.fake_input(self.d, X.KeyPress, kc); xtest.fake_input(self.d, X.KeyRelease, kc)
        if shift: xtest.fake_input(self.d, X.KeyRelease, sk)
        self.d.sync()

    def close(self):
        open(self.done, "w").close()
        try: self.tm.wait(timeout=60)
        except Exception: self.tm.kill()
        # keystroke.scm writes the edited paragraph: check that the keys went into it
        if os.path.exists(self.outf):
            print(f"{self.tag}: paragraph now ends with ...{open(self.outf).read().strip()[-50:]!r}")
        else: print(f"{self.tag}: no paragraph dump")
        self.xvfb.kill()


def wait_all_idle(sides, limit_s=300):
    prev = [cpu_ticks(s.tm.pid) for s in sides]
    t_end = time.time() + limit_s
    while time.time() < t_end:
        time.sleep(1.0)
        res = [s.idle(p) for s, p in zip(sides, prev)]
        if all(r[0] for r in res): return
        prev = [r[1] for r in res]


sides = [Side(1, l1), Side(2, l2)]
try:
    for s in sides: s.wait_ready()
    wait_all_idle(sides)
    # warm-up before recording: the first keys at a new zoom level load fonts (and may run
    # mktexpk for missing ones), which would stall both builds and batch the measured keys
    for ch in opts.get("warmtext", "Warm up. ") * int(opts.get("warm", 2)):
        for s in sides: s.key(ch)
        time.sleep(0.15)
    wait_all_idle(sides)
    record = "no-video" not in opts
    if record:
        for s in sides: s.start_rec()
    t_rec = time.time()
    time.sleep(1.5)
    t_first = time.time() - t_rec
    ticks0 = [cpu_ticks(s.tm.pid) for s in sides]
    for i in range(NKEYS):
        ch = text[i % len(text)]
        for s in sides: s.key(ch)
        time.sleep(GAP)
    t_last = time.time() - t_rec
    # keep recording until both builds are idle again (they may lag behind the typing);
    # measure, per build, the CPU time used from the first key until it is idle again and
    # the time it keeps working after the last key (resolution: 1 s idle detection)
    idle_at = [None, None]
    prev = [cpu_ticks(s.tm.pid) for s in sides]
    t_end = time.time() + 600
    while None in idle_at and time.time() < t_end:
        time.sleep(0.25)
        for k, s in enumerate(sides):
            if idle_at[k] is None and time.time() - t_rec - t_last >= 0.25:
                cur = cpu_ticks(s.tm.pid)
                # idle: TeXmacs polls at 60 Hz (~1 ms each) even when idle, so allow
                # up to 4 ticks (40 ms) of CPU per 250 ms window
                if cur - prev[k] < 5 and time.time() - t_rec - t_last > 0.5:
                    idle_at[k] = (time.time() - t_rec, cur)
                prev[k] = cur
    ticks1 = [ia[1] if ia else cpu_ticks(s.tm.pid) for ia, s in zip(idle_at, sides)]
    for k, (s, lab) in enumerate(zip(sides, (lab1, lab2))):
        cpu_ms = (ticks1[k] - ticks0[k]) * 10
        lag = (idle_at[k][0] - t_last) if idle_at[k] else float("nan")
        print(f"{lab:28s} cpu {cpu_ms / NKEYS:6.1f} ms/key ({cpu_ms} ms for {NKEYS} keys), "
              f"busy until {lag:5.2f} s after the last key")
    wait_all_idle(sides)
    time.sleep(1.5)
    if record:
        for s in sides: s.stop_rec()
finally:
    for s in sides:
        if s.rec and s.rec.poll() is None: s.rec.kill()
        s.close()

if "no-video" in opts: sys.exit(0)
# compose: crop the document area of both screens, stack them, add labels, clock and marks
cw, ch, cx, cy = 1280, 720, 320, 0
if "crop" in opts:
    wh, cx, cy = opts["crop"].split("+"); cw, ch = map(int, wh.split("x")); cx, cy = int(cx), int(cy)
title = {"lorem": f"typing lorem ipsum, {NKEYS} keys, one every {GAP*1000:.0f} ms",
         "enter": f"typing with Return (new paragraphs), {NKEYS} keys, one every {GAP*1000:.0f} ms"}[opts.get("text", "lorem")]
where = {"start": "cursor at the start of the document", "par": "cursor near the start of the document",
         "end": "cursor at the end of the document"}[pos]


def dt(txt, x, y, size=30, extra=""):
    txt = txt.replace(":", r"\:").replace("'", "")
    return f"drawtext=fontfile={FONT}:text='{txt}':x={x}:y={y}:fontsize={size}:fontcolor=white:box=1:boxcolor=black@0.75:boxborderw=8{extra}"


marks = (dt("typing...", "w-tw-20", 20, 30, f":enable='between(t,{t_first:.2f},{t_last:.2f})'") + "," +
         dt("last key sent", "w-tw-20", 20, 30, f":enable='gte(t,{t_last:.2f})'"))
clock = dt("t = %{pts:hms}", 20, "h-th-20", 28)
flt = (f"[0:v]crop={cw}:{ch}:{cx}:{cy},{dt(lab1, 20, 20, 34)},{marks}[a];"
       f"[1:v]crop={cw}:{ch}:{cx}:{cy},{dt(lab2, 20, 20, 34)},{marks}[b];"
       f"[a][b]hstack=inputs=2,pad=iw:ih+60:0:60:color=black,"
       f"{dt(title + ' - ' + where, 20, 14, 28)},{clock}[v]")
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", sides[0].video, "-i", sides[1].video,
                "-filter_complex", flt, "-map", "[v]", "-c:v", "libx264", "-preset", "slow",
                "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
print(f"{out}: first key at {t_first:.2f}s, last key at {t_last:.2f}s")
