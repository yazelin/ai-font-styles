#!/usr/bin/env python3
"""把 fix-NNN.png 貼回對應 sheet 的格子(用偵測到的真實格線,整格覆蓋),補回編號"""
import glob, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRATCH = os.path.dirname(os.path.abspath(__file__))
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
WIN = 120

def boundary(mean, soft, dark, ideal, lo, hi):
    lo, hi = max(lo, ideal - WIN), min(hi, ideal + WIN)
    def runs_center(idx):
        runs = []
        for y in idx:
            if runs and y - runs[-1][-1] <= 2: runs[-1].append(y)
            else: runs.append([y])
        runs = [r for r in runs if len(r) >= 3]
        if not runs: return None
        centers = [int(sum(r) / len(r)) for r in runs]
        return min(centers, key=lambda c: abs(c - ideal))
    # 1) 近白溝槽帶(應用滿版格之間的白縫)
    g = runs_center([y for y in range(lo, hi) if mean[y] > 249 and dark[y] < 0.02])
    if g is not None: return g
    # 2) 淺灰格線
    lines = [y for y in range(lo, hi) if soft[y] > 0.55 and dark[y] < 0.10]
    if lines:
        groups = []
        for y in lines:
            if groups and y - groups[-1][-1] <= 5: groups[-1].append(y)
            else: groups.append([y])
        centers = [int(sum(g2) / len(g2)) for g2 in groups]
        return min(centers, key=lambda c: abs(c - ideal))
    # 3) 無深色空白帶
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
    rmean = g.mean(axis=1); rsoft = (g < 246).mean(axis=1); rdark = (g < 130).mean(axis=1)
    cmean = g.mean(axis=0); csoft = (g < 246).mean(axis=0); cdark = (g < 130).mean(axis=0)
    ys = [0] + [boundary(rmean, rsoft, rdark, round(h*i/5), 30, h-30) for i in range(1, 5)] + [h]
    xs = [0, boundary(cmean, csoft, cdark, w // 2, 30, w-30), w]
    return xs, ys

for f in sorted(glob.glob(f"{SCRATCH}/appfix-*.png")):
    n = int(os.path.basename(f)[7:10])
    s = (n - 1) // 10 + 1
    i = (n - 1) % 10
    col, row = i % 2, i // 2
    sheet_path = f"{SCRATCH}/app-sheet-{s:02d}.png"
    sheet = Image.open(sheet_path).convert("RGB")
    xs, ys = grid(sheet)  # 每次重算:貼白格不影響格線偵測
    x0, x1, y0, y1 = xs[col], xs[col+1], ys[row], ys[row+1]

    # 應用格為滿版設計:cover 模式(放大填滿、置中裁掉溢出),無編號
    line = 3
    cw, ch = x1 - x0 - 2*line, y1 - y0 - 2*line
    fix = Image.open(f).convert("RGB")
    scale = max(cw / fix.width, ch / fix.height)
    fix = fix.resize((round(fix.width*scale), round(fix.height*scale)), Image.LANCZOS)
    fx, fy = (fix.width - cw)//2, (fix.height - ch)//2
    sheet.paste(fix.crop((fx, fy, fx+cw, fy+ch)), (x0 + line, y0 + line))
    sheet.save(sheet_path)
    print(f"patched {n} -> app-sheet-{s:02d} cell=({x0},{y0})-({x1},{y1})")
