#!/usr/bin/env python3
"""daily_font 的佇列流程自我檢查:python tools/test_daily_font.py

只驗「哪種失敗要卡住、哪種要換下一筆」這段——生圖跟驗字都是假的,不打任何 API。
"""
import io
import json
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("CODEX_IMAGE_BASE_URL", "http://x")
os.environ.setdefault("CODEX_IMAGE_KEY", "x")
os.environ.setdefault("GEMINI_API_KEY", "x")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import daily_font  # noqa: E402
from PIL import Image  # noqa: E402

PNG = io.BytesIO()
Image.new("RGB", (8, 8), "white").save(PNG, "PNG")
PNG = PNG.getvalue()

QUEUE = [
    {"name": "極光流光字", "tag": "光影", "group": 6, "desc": "極光", "scenes": ["旅遊"],
     "app": "旅遊封面", "headline": "極光之旅"},
    {"name": "橡皮印章字", "tag": "印刷", "group": 3, "desc": "印章", "scenes": ["文具"],
     "app": "文具包裝", "headline": "手作日"},
]


def setup(tmp):
    os.chdir(tmp)
    pathlib.Path("samples/apps").mkdir(parents=True)
    json.dump({"groups": [], "fonts": [{"n": 114, "name": "既有字"}]},
              open("fonts.json", "w"), ensure_ascii=False)
    json.dump({"queue": [dict(q) for q in QUEUE]}, open("queue.json", "w"), ensure_ascii=False)
    os.environ["GITHUB_OUTPUT"] = os.path.join(tmp, "out.txt")
    return lambda: json.load(open("queue.json"))["queue"], lambda: json.load(open("fonts.json"))["fonts"]


def run(case, gen_verified):
    with tempfile.TemporaryDirectory() as tmp:
        queue, fonts = setup(tmp)
        daily_font.gen_verified = gen_verified
        err = None
        try:
            daily_font.main()
        except Exception as e:  # noqa: BLE001 — 測試要拿到例外型別
            err = e
        outfile = pathlib.Path(os.environ["GITHUB_OUTPUT"])
        output = outfile.read_text() if outfile.exists() else ""
        written = sorted(str(p) for p in pathlib.Path("samples").rglob("*.webp"))
        print(f"[{case}] {err!r} 產出 {written}")
        return queue(), fonts(), output, err, written


# 1. 驗字連續未過:挪到佇列尾端、不加字、正常結束,workflow 仍要 commit 佇列變動
def fail_verify(*a, **k):
    raise daily_font.VerifyFailed("連續 3 次驗字未過:['背景不是白的']")


q, f, out, err, written = run("驗字未過", fail_verify)
assert err is None, err
assert [x["name"] for x in q] == ["橡皮印章字", "極光流光字"], q
assert len(f) == 1 and written == [], (f, written)
assert "commit_msg=" in out and "挪到佇列尾端" in out, out

# 2. 正常成功:pop 掉第一筆、fonts.json 加一筆、圖有落地
q, f, out, err, written = run("成功", lambda *a, **k: PNG)
assert err is None, err
assert [x["name"] for x in q] == ["橡皮印章字"], q
assert f[-1]["n"] == 115 and f[-1]["name"] == "極光流光字", f
assert written == ["samples/115-極光流光字.webp", "samples/apps/115-極光流光字.webp"], written
assert "commit_msg=每日擴充:#115 極光流光字" in out, out

# 3. 生圖服務掛掉(非驗字問題):要炸出來讓人看到,佇列原封不動
def infra_down(*a, **k):
    raise RuntimeError("job failed: 502")


q, f, out, err, written = run("服務掛掉", infra_down)
assert isinstance(err, RuntimeError) and not isinstance(err, daily_font.VerifyFailed), err
assert [x["name"] for x in q] == ["極光流光字", "橡皮印章字"], q
assert out == "", out

print("OK")
