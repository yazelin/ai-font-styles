#!/usr/bin/env python3
"""把 10 張 sheet(2欄×5列)裁成 100 張單獨樣本,輸出 webp 到 repo samples/"""
import os
from PIL import Image

SCRATCH = os.path.dirname(os.path.abspath(__file__))
OUT = "/home/ct/ai-font-styles/samples"
os.makedirs(OUT, exist_ok=True)

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
assert len(NAMES) == 100, len(NAMES)

INSET = 6  # 避開格線
for s in range(10):
    sheet = Image.open(f"{SCRATCH}/sheet-{s+1:02d}.png").convert("RGB")
    w, h = sheet.size
    cw, ch = w / 2, h / 5
    for i in range(10):
        col, row = i % 2, i // 2
        box = (int(col*cw)+INSET, int(row*ch)+INSET, int((col+1)*cw)-INSET, int((row+1)*ch)-INSET)
        n = s*10 + i + 1
        cell = sheet.crop(box)
        cell.save(f"{OUT}/{n:03d}-{NAMES[n-1]}.webp", "WEBP", quality=82)
print("done:", len(os.listdir(OUT)), "files")
