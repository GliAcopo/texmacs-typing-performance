#!/usr/bin/env python3
"""Re-score shift-check output folders, ignoring the status bar (bottom 60 px)."""
import sys, glob, os
from PIL import Image, ImageChops
for d in sys.argv[1:]:
    bad = []
    for a in sorted(glob.glob(f"{d}/*-a.png")):
        b = a.replace("-a.png", "-b.png")
        A, B = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
        h = A.height - 60
        box = ImageChops.difference(A.crop((0, 0, A.width, h)), B.crop((0, 0, B.width, h))).getbbox()
        if box: bad.append((os.path.basename(a)[:2], box))
    print(os.path.basename(d), "canvas mismatches:", bad or "none")
