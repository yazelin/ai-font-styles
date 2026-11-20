#!/usr/bin/env python3
"""daily_font 的佇列流程自我檢查:python tools/test_daily_font.py

只驗流程失敗分類與驗字請求格式；所有網路回應都由替身提供,不連網。
"""
import base64
import io
import json
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("CODEX_IMAGE_BASE_URL", "http://x")
os.environ.setdefault("CODEX_IMAGE_KEY", "x")
os.environ.setdefault("GEMINI_WEB_BASE_URL", "http://gemini-web")
os.environ.setdefault("GEMINI_WEB_KEY", "x")
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

# 5. gemini-web 回應與重試：成功回應解析 JSON、fence、success:false 與假成功文字
class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def fake_urlopen(seq):
    calls = []

    def _open(req, timeout=None):
        calls.append((req, timeout))
        e = seq[len(calls) - 1]
        if isinstance(e, BaseException):
            raise e
        return FakeResp(e)

    return _open, calls


import urllib.error  # noqa: E402

def answer(text, success=True):
    return {"success": success, "text": text, "prompt": "", "elapsed_seconds": 0.1}


daily_font.GEMINI_WEB_BASE_URL = "http://gemini-web"
daily_font.GEMINI_WEB_KEY = "test-key"
sleep_calls = []
daily_font.time.sleep = sleep_calls.append

# 正常通過，同時確認實際送出 PNG 縮圖、正確檔名、timeout 與驗證 header。
large = io.BytesIO()
Image.new("RGB", (2048, 1536), "white").save(large, "PNG")
daily_font.urllib.request.urlopen, calls = fake_urlopen([answer('{"pass": true, "issues": []}')])
ok, issues = daily_font.qa(large.getvalue(), "測試字", "白底")
assert (ok, issues) == (True, [])
assert len(calls) == 1
req, request_timeout = calls[0]
request_body = json.loads(req.data)
headers = {name.lower(): value for name, value in req.header_items()}
assert req.full_url == "http://gemini-web/api/chat-file", req.full_url
assert request_timeout == 300 and request_body["timeout"] == 240, (request_timeout, request_body)
assert request_body["filename"] == "qa.png"
assert headers["content-type"] == "application/json" and headers["x-goog-api-key"] == "test-key", headers
assert "測試字" in request_body["prompt"]
sent_image = Image.open(io.BytesIO(base64.b64decode(request_body["file"])))
assert sent_image.format == "PNG" and max(sent_image.size) <= 1024, sent_image.size
print(f"[正常通過／縮圖] 上傳 {sent_image.size} PNG")

# 回覆前後有文字，且 JSON 以 markdown fence 包住，仍取第一個 JSON 物件。
fenced = '檢查結果：\n```json\n{"pass": true, "issues": []}\n```\n完成'
daily_font.urllib.request.urlopen, calls = fake_urlopen([answer(fenced)])
assert daily_font.qa(PNG, "測試字", "白底") == (True, [])
assert len(calls) == 1
print("[JSON fence] 通過")

# 回覆內容的 JSON 被截斷時，維持原有「視為驗字未過」行為。
daily_font.urllib.request.urlopen, calls = fake_urlopen([answer('{"pass": true')])
assert daily_font.qa(PNG, "測試字", "白底") == (False, ["QA 回傳非合法 JSON"])
assert len(calls) == 1
print("[JSON 格式錯誤] 視為未過")

# success:false 是暫時性失敗，退避後成功。
sleep_calls.clear()
daily_font.urllib.request.urlopen, calls = fake_urlopen([
    answer("服務忙碌", success=False), answer('{"pass": true, "issues": []}')
])
assert daily_font.qa(PNG, "測試字", "白底") == (True, [])
assert len(calls) == 2 and sleep_calls == [30], (len(calls), sleep_calls)
print("[success:false 後重試] 呼叫 2 次")

# 503 與逾時都重試；退避時間依 attempt * 30 秒遞增。
sleep_calls.clear()
http503 = urllib.error.HTTPError("u", 503, "boom", None, None)
daily_font.urllib.request.urlopen, calls = fake_urlopen([
    http503, TimeoutError("read timed out"), answer('{"pass": true, "issues": []}')
])
assert daily_font.qa(PNG, "測試字", "白底") == (True, [])
assert len(calls) == 3 and sleep_calls == [30, 60], (len(calls), sleep_calls)
print("[503／逾時後成功] 呼叫 3 次")

# 上傳失敗型假成功不能當成驗字未過；用完重試必須 raise。
sleep_calls.clear()
daily_font.urllib.request.urlopen, calls = fake_urlopen([
    answer("我沒有看到附件") for _ in range(daily_font.QA_RETRIES)
])
try:
    daily_font.qa(PNG, "測試字", "白底")
except RuntimeError as e:
    assert "沒有收到附件" in str(e) or "沒看到附件" in str(e), e
else:
    raise AssertionError("假成功文字重試用盡後應 raise,不能當成驗字未過")
assert len(calls) == daily_font.QA_RETRIES
assert sleep_calls == [30, 60, 90, 120, 150], sleep_calls
print(f"[假成功耗盡] 呼叫 {len(calls)} 次後 raise")

# 負控制：模型有作答（帶 JSON），issues 裡剛好出現「沒有看到」「請提供」也要照判定走，不能誤判成上傳失敗。
sleep_calls.clear()
verdict = '{"pass": false, "issues": ["沒有看到圖片中的第三個字", "請提供完整筆畫"]}'
daily_font.urllib.request.urlopen, calls = fake_urlopen([answer(verdict)])
assert daily_font.qa(PNG, "測試字", "白底") == (False, ["沒有看到圖片中的第三個字", "請提供完整筆畫"])
assert len(calls) == 1 and sleep_calls == [], (len(calls), sleep_calls)
print("[issues 含上傳失敗字句] 照判定走，不重試")

# 非 429 的 4xx 直接 raise，不退避重試。
sleep_calls.clear()
http400 = urllib.error.HTTPError("u", 400, "bad request", None, None)
daily_font.urllib.request.urlopen, calls = fake_urlopen([http400])
try:
    daily_font.qa(PNG, "測試字", "白底")
except urllib.error.HTTPError as e:
    assert e.code == 400
else:
    raise AssertionError("HTTP 400 應直接 raise")
assert len(calls) == 1 and sleep_calls == [], (len(calls), sleep_calls)
print("[400 不重試] 呼叫 1 次後 raise")

print("OK")
