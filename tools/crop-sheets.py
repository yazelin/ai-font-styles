#!/usr/bin/env python3
"""把 10 張 sheet(2欄×5列)裁成 100 張單獨樣本,輸出 webp 到 repo samples/

格線由模型手畫、非等分,所以逐張偵測實際界線:
1) 淺灰連續橫線(softcov 高、darkcov 低)且落在理想位置 ±WIN 內
2) 找不到線 → 取窗口內最寬空白帶中心
3) 再不行 → 用理想等分位置
"""
import os
import numpy as np
from PIL import Image

SCRATCH = os.path.dirname(os.path.abspath(__file__))
OUT = "/home/ct/ai-font-styles/samples"
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

def boundary(soft, dark, ideal, lo, hi):
    lo, hi = max(lo, ideal - WIN), min(hi, ideal + WIN)
    # 1) 格線:淺灰連續、幾乎無深色
    lines = [y for y in range(lo, hi) if soft[y] > 0.55 and dark[y] < 0.10]
    if lines:
        groups = []
        for y in lines:
            if groups and y - groups[-1][-1] <= 5: groups[-1].append(y)
            else: groups.append([y])
        centers = [int(sum(g) / len(g)) for g in groups]
        return min(centers, key=lambda c: abs(c - ideal))
    # 2) 空白帶:最寬的連續無文字區段取中心
    blank = [y for y in range(lo, hi) if dark[y] < 0.02]
    if blank:
        runs = []
        for y in blank:
            if runs and y - runs[-1][-1] <= 2: runs[-1].append(y)
            else: runs.append([y])
        best = max(runs, key=len)
        return int(sum(best) / len(best))
    # 3) 理想等分
    return ideal

for s in range(10):
    sheet = Image.open(f"{SCRATCH}/sheet-{s+1:02d}.png").convert("RGB")
    g = np.asarray(sheet.convert("L"), dtype=float)
    h, w = g.shape
    rsoft = (g < 246).mean(axis=1); rdark = (g < 130).mean(axis=1)
    csoft = (g < 246).mean(axis=0); cdark = (g < 130).mean(axis=0)
    ys = [0] + [boundary(rsoft, rdark, round(h*i/5), 30, h-30) for i in range(1, 5)] + [h]
    xs = [0, boundary(csoft, cdark, w // 2, 30, w-30), w]
    print(f"sheet{s+1:02d} rows={ys[1:-1]} col={xs[1]}")
    for i in range(10):
        col, row = i % 2, i // 2
        box = (xs[col]+INSET, ys[row]+INSET, xs[col+1]-INSET, ys[row+1]-INSET)
        n = s*10 + i + 1
        sheet.crop(box).save(f"{OUT}/{n:03d}-{NAMES[n-1]}.webp", "WEBP", quality=82)
print("done")
