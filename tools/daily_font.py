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

# 模板放 fonts.json,index.html 複製提示詞時吃同一份。
# 曾經兩邊各寫一份,網頁那份少了「筆畫本身要是該技法構成」「字數鎖」「別做成簡報卡」,
# 使用者照抄生不出樣本圖的效果。要改提示詞就改 fonts.json,別搬回來這裡。


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


class VerifyFailed(RuntimeError):
    """驗字連續未過(圖生出來了但不合格)。跟生圖服務掛掉區分開:前者換一筆繼續,後者要炸給人看。"""


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
    raise VerifyFailed(f"連續 {MAX_ATTEMPTS} 次驗字未過:{last_issues}")


def out(line: str):
    """寫 workflow step output;有 commit_msg 就代表這輪有東西要 commit。"""
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(line + "\n")


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
    # ponytail: 舊佇列項目沒有 headline 欄位,退回用字體名稱(自我指涉但不會壞掉),
    # 補貨時應該一併寫 headline,別靠這個退路
    headline = item.get("headline") or name
    nnn = f"{n:03d}"
    print(f"本日字體 #{n}:{name}", flush=True)

    try:
        print("[1/2] 純字圖", flush=True)
        # 背景要求要跟 PURE_TMPL 同一套規則:硬寫「白色背景」會把天生深色的風格
        # (極光、夜光、黑板)全部判死,佇列就卡在那一筆再也不動
        pure = gen_verified(
            data["templates"]["pure"].format(name=name, count=len(name), desc=desc),
            name, f"以「{desc}」的風格呈現,背景是大面積單一色調的純底"
                  "(預設白底;風格天生需要深色或特定色調時用該色調也算合格),不含道具或情境場景")
        print("[2/2] 應用圖", flush=True)
        app = gen_verified(
            data["templates"]["app"].format(
                headline=headline, count=len(headline), desc=desc, scene=item["app"]),
            headline, f"套用在設計場景「{item['app']}」中,風格為「{desc}」")
    except VerifyFailed as e:
        # 這一筆生不出合格圖就挪到佇列尾端,換下一筆繼續。不這樣做的話單筆卡死=整條產線停擺
        # (2026-07-28 起 #115 極光流光字卡了三天,每天三個時段全掛)
        qdata["queue"] = qdata["queue"][1:] + [item]
        json.dump(qdata, open("queue.json", "w"), ensure_ascii=False, indent=1)
        print(f"跳過「{name}」:{e}(已挪到佇列尾端,下個時段換下一筆)", flush=True)
        out(f"commit_msg=chore: 「{name}」驗字未過,挪到佇列尾端")
        return

    save_webp(pure, f"samples/{nnn}-{name}.webp")
    save_webp(app, f"samples/apps/{nnn}-{name}.webp")

    data["fonts"].append({
        "n": n, "name": name, "tag": item["tag"], "scenes": item["scenes"],
        "app": item["app"], "group": item["group"], "source": "expansion",
        "desc": desc, "headline": headline, "added": datetime.date.today().isoformat(),
    })
    json.dump(data, open("fonts.json", "w"), ensure_ascii=False, indent=1)
    qdata["queue"] = qdata["queue"][1:]
    json.dump(qdata, open("queue.json", "w"), ensure_ascii=False, indent=1)
    print(f"完成:#{n} {name}(佇列剩 {len(qdata['queue'])} 筆)", flush=True)
    out(f"commit_msg=每日擴充:#{n} {name}")


if __name__ == "__main__":
    main()
