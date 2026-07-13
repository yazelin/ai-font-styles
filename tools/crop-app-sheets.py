#!/usr/bin/env python3
"""裁應用示例 sheet → samples/apps/NNN-名稱.webp(逐張偵測界線,同 crop-sheets.py)"""
import os, sys
import numpy as np
from PIL import Image

SCRATCH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRATCH)
OUT = "/home/ct/ai-font-styles/samples/apps"
os.makedirs(OUT, exist_ok=True)
WIN = 120
INSET = 8

NAMES = """極簡品牌字 現代知識字 清爽標題字 科技簡潔字 潮流品牌字 高級雜誌字 都市潮流字 先鋒設計字 溫柔細線字 高級知識字
未來細線字 輕奢細線字 雜誌襯線體 商業襯線體 輕奢封面字 深度專欄字 連續線稿體 草圖單線體 科技線框字 優雅單線字
清新手跡字 成長筆記字 個人簽名字 情緒手寫字 鋼筆楷書字 學生衡水體 批注手寫體 商務簽批體 柔和曲線字 女性美學字
音樂律動字 藝術曲線字 輪廓手繪體 插畫裝飾體 粗描海報體 童趣塗鴉體 抽象藝術字 展覽字 概念實驗字 創作者標題字
街頭塗鴉字 青年觀點字 泡泡潮流塗鴉字 爆裂搖滾塗鴉字 強衝擊標題字 爆款封面字 表情包標題字 強觀點誇張字 趣味標題字 搞笑封面字
創意課程字 兒童活動字 兒童繪本體 樂高玩具體 零食包裝字 剪紙拼貼字 復古遊戲字 街機遊戲字 像素字 方塊模塊字
科技標題字 液態未來字 虛擬空間字 賽博斷裂字 重工機械字 機甲裝甲字 工業銘牌字 機械切割字 球衣號碼字 賽車速度字
格鬥力量字 電競戰隊字 紀念碑刻字 建築立面字 水泥構築字 空間導視字 老電影字 霓虹舊街 復古廣告字 復古故事字
西部牛仔標題體 通緝令字體 賞金字 機車西部字 燈管字 夜市菜單字 便利貼字 電商促銷字 報頭提題體 狂草書法體
行書體 禪意體 東方瘦金體 國風牌匾體 潮流篆意體 東方海報 暗黑標題字 中世紀字 黑金屬尖刺字 華麗哥特飾字""".split()
assert len(NAMES) == 100

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

# 這 4 張的列高偏離等分達 140~174px,超出自動偵測窗;溝槽位置為實測值
ROW_OVERRIDES = {
    1: [384, 768, 1061, 1301],
    6: [445, 866, 1254, 1563],
    9: [409, 789, 1112, 1386],
    10: [443, 884, 1216, 1505],
}

for s in range(10):
    sheet = Image.open(f"{SCRATCH}/app-sheet-{s+1:02d}.png").convert("RGB")
    g = np.asarray(sheet.convert("L"), dtype=float)
    h, w = g.shape
    rmean = g.mean(axis=1); rsoft = (g < 246).mean(axis=1); rdark = (g < 130).mean(axis=1)
    cmean = g.mean(axis=0); csoft = (g < 246).mean(axis=0); cdark = (g < 130).mean(axis=0)
    if s + 1 in ROW_OVERRIDES:
        ys = [0] + ROW_OVERRIDES[s + 1] + [h]
    else:
        ys = [0] + [boundary(rmean, rsoft, rdark, round(h*i/5), 30, h-30) for i in range(1, 5)] + [h]
    xs = [0, boundary(cmean, csoft, cdark, w // 2, 30, w-30), w]
    print(f"app{s+1:02d} rows={ys[1:-1]} col={xs[1]}")
    for i in range(10):
        col, row = i % 2, i // 2
        box = (xs[col]+INSET, ys[row]+INSET, xs[col+1]-INSET, ys[row+1]-INSET)
        n = s*10 + i + 1
        sheet.crop(box).save(f"{OUT}/{n:03d}-{NAMES[n-1]}.webp", "WEBP", quality=82)
print("done")
