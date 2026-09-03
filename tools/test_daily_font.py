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


REPO = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = json.load(open(REPO / "fonts.json"))["templates"]


def setup(tmp):
    os.chdir(tmp)
    pathlib.Path("samples/apps").mkdir(parents=True)
    json.dump({"templates": TEMPLATES, "groups": [], "fonts": [{"n": 114, "name": "既有字"}]},
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

# 4. 模板契約:欄位要跟 pipeline 與 index.html 兩邊填的完全一致(少一個 JS 會留 {xxx} 在剪貼簿,
#    多一個 Python .format 會炸),而且那句「筆畫本身要是該技法構成」不能被誰順手刪掉
import re  # noqa: E402

FIELDS = {"pure": {"name", "count", "desc"}, "app": {"headline", "count", "desc", "scene"}}
for key, want in FIELDS.items():
    got = set(re.findall(r"\{(\w+)\}", TEMPLATES[key]))
    assert got == want, (key, got, want)
    assert "不能只是在制式字體外觀上貼一層材質貼皮" in TEMPLATES[key], key
    assert "一字不多一字不少" in TEMPLATES[key], key

html = (REPO / "index.html").read_text()
assert "TMPL = data.templates" in html, "index.html 沒接上 fonts.json 的模板"
assert "設計一張" not in html, "index.html 又出現手寫短版提示詞"

# 5. Gemini 抖動:503 與逾時要重試,不要一次就把整天的擴充炸掉;非 5xx(如 400 金鑰錯)照樣炸
class FakeResp:
    def read(self):
        return b'{"candidates":[{"content":{"parts":[{"text":"{\\"pass\\": true}"}]}}]}'


def fake_urlopen(seq):
    calls = []

    def _open(req, timeout=None):
        calls.append(req)
        e = seq[len(calls) - 1]
        if e is not None:
            raise e
        return FakeResp()

    return _open, calls


daily_font.time.sleep = lambda s: None
import urllib.error  # noqa: E402

http503 = urllib.error.HTTPError("u", 503, "boom", None, None)
http400 = urllib.error.HTTPError("u", 400, "bad key", None, None)

for case, seq, want_ok, want_calls in [
    ("503 後成功", [http503, TimeoutError("read timed out"), None], True, 3),
    ("連續都掛", [http503] * daily_font.QA_RETRIES, None, daily_font.QA_RETRIES),
    ("400 不重試", [http400], None, 1),
]:
    daily_font.urllib.request.urlopen, calls = fake_urlopen(seq)
    try:
        ok, _ = daily_font.qa(PNG, "測試字", "白底")
    except urllib.error.HTTPError as e:
        ok = None
        assert want_ok is None, (case, e)
    assert ok == want_ok and len(calls) == want_calls, (case, ok, len(calls))
    print(f"[{case}] 呼叫 {len(calls)} 次 → {ok}")

print("OK")
