#!/usr/bin/env python3
"""把 fix-NNN.png 縮放貼回對應 sheet 的格子,補回左上角編號"""
import glob, os
from PIL import Image, ImageDraw, ImageFont

SCRATCH = os.path.dirname(os.path.abspath(__file__))
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)

for f in sorted(glob.glob(f"{SCRATCH}/fix-*.png")):
    n = int(os.path.basename(f)[4:7])
    s = (n - 1) // 10 + 1
    i = (n - 1) % 10
    col, row = i % 2, i // 2
    sheet_path = f"{SCRATCH}/sheet-{s:02d}.png"
    sheet = Image.open(sheet_path).convert("RGB")
    w, h = sheet.size
    cw, ch = w // 2, h // 5
    x0, y0 = col * cw, row * ch

    fix = Image.open(f).convert("RGB")
    # 內縮貼上,保留格線;等比縮到格內最大
    pad = 10
    bw, bh = cw - 2*pad, ch - 2*pad
    fix.thumbnail((bw, bh), Image.LANCZOS)
    # 白底墊滿格子(蓋掉舊內容),再置中貼修正圖
    cellbg = Image.new("RGB", (cw - 2*pad, ch - 2*pad), (252, 252, 252))
    cellbg.paste(fix, ((cellbg.width - fix.width)//2, (cellbg.height - fix.height)//2))
    sheet.paste(cellbg, (x0 + pad, y0 + pad))
    # 補編號
    d = ImageDraw.Draw(sheet)
    d.text((x0 + 34, y0 + 26), str(n), fill=(110, 110, 110), font=FONT)
    sheet.save(sheet_path)
    print(f"patched {n} -> sheet-{s:02d}")
