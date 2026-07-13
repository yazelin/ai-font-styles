#!/usr/bin/env python3
"""把 fix-NNN.png 貼回對應 sheet 的格子(用偵測到的真實格線,整格覆蓋),補回編號"""
import glob, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRATCH = os.path.dirname(os.path.abspath(__file__))
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
WIN = 120

def boundary(soft, dark, ideal, lo, hi):
    lo, hi = max(lo, ideal - WIN), min(hi, ideal + WIN)
    lines = [y for y in range(lo, hi) if soft[y] > 0.55 and dark[y] < 0.10]
    if lines:
        groups = []
        for y in lines:
            if groups and y - groups[-1][-1] <= 5: groups[-1].append(y)
            else: groups.append([y])
        centers = [int(sum(g) / len(g)) for g in groups]
        return min(centers, key=lambda c: abs(c - ideal))
    blank = [y for y in range(lo, hi) if dark[y] < 0.02]
    if blank:
        runs = []
        for y in blank:
            if runs and y - runs[-1][-1] <= 2: runs[-1].append(y)
            else: runs.append([y])
        best = max(runs, key=len)
        return int(sum(best) / len(best))
    return ideal

def grid(sheet):
    g = np.asarray(sheet.convert("L"), dtype=float)
    h, w = g.shape
    rsoft = (g < 246).mean(axis=1); rdark = (g < 130).mean(axis=1)
    csoft = (g < 246).mean(axis=0); cdark = (g < 130).mean(axis=0)
    ys = [0] + [boundary(rsoft, rdark, round(h*i/5), 30, h-30) for i in range(1, 5)] + [h]
    xs = [0, boundary(csoft, cdark, w // 2, 30, w-30), w]
    return xs, ys

for f in sorted(glob.glob(f"{SCRATCH}/fix-*.png")):
    n = int(os.path.basename(f)[4:7])
    s = (n - 1) // 10 + 1
    i = (n - 1) % 10
    col, row = i % 2, i // 2
    sheet_path = f"{SCRATCH}/sheet-{s:02d}.png"
    sheet = Image.open(sheet_path).convert("RGB")
    xs, ys = grid(sheet)  # 每次重算:貼白格不影響格線偵測
    x0, x1, y0, y1 = xs[col], xs[col+1], ys[row], ys[row+1]

    # 整格塗白(留格線 3px),修正圖等比縮放置中
    line = 3
    cw, ch = x1 - x0 - 2*line, y1 - y0 - 2*line
    fix = Image.open(f).convert("RGB")
    fix.thumbnail((cw - 40, ch - 60), Image.LANCZOS)
    cellbg = Image.new("RGB", (cw, ch), (252, 252, 251))
    cellbg.paste(fix, ((cw - fix.width)//2, (ch - fix.height)//2))
    sheet.paste(cellbg, (x0 + line, y0 + line))
    d = ImageDraw.Draw(sheet)
    d.text((x0 + 34, y0 + 26), str(n), fill=(110, 110, 110), font=FONT)
    sheet.save(sheet_path)
    print(f"patched {n} -> sheet-{s:02d} cell=({x0},{y0})-({x1},{y1})")
