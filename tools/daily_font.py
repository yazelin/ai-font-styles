#!/usr/bin/env python3
"""每日字體擴充 pipeline:pop queue.json → 生純字+應用圖 → Gemini 驗字 → 更新 fonts.json

環境變數:CODEX_IMAGE_BASE_URL、CODEX_IMAGE_KEY、GEMINI_API_KEY
在 repo 根目錄執行。成功後由 workflow 負責 commit。
"""
import base64
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

from PIL import Image

BASE = os.environ["CODEX_IMAGE_BASE_URL"].rstrip("/")
CIMG_KEY = os.environ["CODEX_IMAGE_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-flash-latest"
MAX_ATTEMPTS = 3

PURE_TMPL = (
    "橫式構圖,乾淨的白色背景,畫面中只有這幾個大字置中呈現,無其他裝飾。"
    "所有中文字必須是筆畫正確的繁體中文字形,不能出現錯字、多字、漏字或簡體字。 "
    "文字:「{name}」(共{count}個字,一字不多一字不少)。字體風格:{desc}。"
)
APP_TMPL = (
    "橫式構圖的迷你設計成品,主標題文字大而清晰,可有少量小型輔助文字與裝飾。"
    "所有主標題中文字必須是筆畫正確的繁體中文字形,不能出現錯字、多字、漏字或簡體字。 "
    "主標題:「{name}」(共{count}個字,一字不多一字不少),{desc}。場景:{scene}。"
)


def gen_image(prompt: str) -> bytes:
    body = json.dumps({"prompt": prompt, "size": "1536x1024", "quality": "medium", "count": 1}).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/images/jobs", data=body,
        headers={"Authorization": f"Bearer {CIMG_KEY}", "Content-Type": "application/json"},
        method="POST")
    job = json.loads(urllib.request.urlopen(req, timeout=60).read())["id"]
    print(f"  job {job}", flush=True)
    for _ in range(40):  # 最長 ~13 分鐘
        time.sleep(20)
        req = urllib.request.Request(f"{BASE}/v1/images/jobs/{job}",
                                     headers={"Authorization": f"Bearer {CIMG_KEY}"})
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
        st = d.get("status")
        if st == "succeeded":
            url = d["images"][0]["url"]
            if url.startswith("/"):
                url = BASE + url
            return urllib.request.urlopen(url, timeout=120).read()
        if st in ("failed", "expired"):
            raise RuntimeError(f"job {st}: {d.get('error')}")
    raise RuntimeError("job timeout")


def qa(png: bytes, name: str, expect: str) -> tuple[bool, list]:
    prompt = (
        f"這張圖的主要文字應該是繁體中文「{name}」(共 {len(name)} 個字),{expect}。"
        "請檢查:1) 主要文字是否正確、無錯字漏字、無多餘字 "
        "2) 是否全為筆畫正確的繁體字形(不能有簡體字或自創字形) "
        "3) 風格是否大致符合描述。"
        '只回傳 JSON:{"pass": true/false, "issues": ["..."]}'
    )
    body = json.dumps({
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
        ]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=body, headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
    r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    text = r["candidates"][0]["content"]["parts"][0]["text"].strip()
    if text.startswith("```"):  # 偶爾 mime_type 被無視,夾 markdown fence
        text = text.strip("`").removeprefix("json").strip()
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        # ponytail: Gemini 偶爾吐壞 JSON,別炸掉整天——當成驗字沒過讓外層重試
        print(f"  QA JSON 解析失敗,視為未過:{text[:200]!r}", flush=True)
        return False, ["QA 回傳非合法 JSON"]
    return bool(verdict.get("pass")), verdict.get("issues", [])


def gen_verified(prompt: str, name: str, expect: str) -> bytes:
    last_issues = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  生成 attempt {attempt}/{MAX_ATTEMPTS}", flush=True)
        png = gen_image(prompt)
        ok, issues = qa(png, name, expect)
        if ok:
            print("  驗字通過", flush=True)
            return png
        last_issues = issues
        print(f"  驗字未過:{issues}", flush=True)
    raise RuntimeError(f"連續 {MAX_ATTEMPTS} 次驗字未過:{last_issues}")


def save_webp(png: bytes, path: str):
    Image.open(io.BytesIO(png)).convert("RGB").save(path, "WEBP", quality=85)


def main():
    data = json.load(open("fonts.json"))
    today = datetime.date.today().isoformat()
    if any(f.get("added") == today for f in data["fonts"]):
        print(f"今日({today})已擴充,跳過。")  # 讓多時段補跑冪等
        return
    qdata = json.load(open("queue.json"))
    if not qdata["queue"]:
        print("佇列已空,無事可做。請補充 queue.json。")
        return
    item = qdata["queue"][0]
    n = max(f["n"] for f in data["fonts"]) + 1
    name, desc = item["name"], item["desc"]
    nnn = f"{n:03d}"
    print(f"本日字體 #{n}:{name}", flush=True)

    print("[1/2] 純字圖", flush=True)
    pure = gen_verified(
        PURE_TMPL.format(name=name, count=len(name), desc=desc),
        name, f"以「{desc}」的風格呈現,白色背景")
    print("[2/2] 應用圖", flush=True)
    app = gen_verified(
        APP_TMPL.format(name=name, count=len(name), desc=desc, scene=item["app"]),
        name, f"套用在設計場景「{item['app']}」中,風格為「{desc}」")

    save_webp(pure, f"samples/{nnn}-{name}.webp")
    save_webp(app, f"samples/apps/{nnn}-{name}.webp")

    data["fonts"].append({
        "n": n, "name": name, "tag": item["tag"], "scenes": item["scenes"],
        "app": item["app"], "group": item["group"], "source": "expansion",
        "desc": desc, "added": datetime.date.today().isoformat(),
    })
    json.dump(data, open("fonts.json", "w"), ensure_ascii=False, indent=1)
    qdata["queue"] = qdata["queue"][1:]
    json.dump(qdata, open("queue.json", "w"), ensure_ascii=False, indent=1)
    print(f"完成:#{n} {name}(佇列剩 {len(qdata['queue'])} 筆)", flush=True)
    # 給 workflow 用的 commit 訊息素材
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"font_no={n}\nfont_name={name}\nadded=1\n")


if __name__ == "__main__":
    main()
