#!/usr/bin/env python3
"""佇列低水位時用 Gemini 產生候選，完整驗證後才寫入 queue.json。"""
import json
import os
import pathlib
import tempfile
import time
import unicodedata

from gemini_api import generate_content


REFILL_BELOW = 14
REFILL_COUNT = 20
MODEL_CANDIDATE_COUNT = 30
VALID_FIELDS = {"name", "tag", "group", "desc", "scenes", "app", "headline"}


class RefillRejected(ValueError):
    """候選批次未通過驗證，佇列維持原狀。"""


def normalize_name(name: str) -> str:
    """忽略大小寫、空白與標點後比較字體名稱。"""
    normalized = unicodedata.normalize("NFKC", name).casefold()
    return "".join(
        char for char in normalized
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def _nonempty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_candidate(item, group_count: int) -> None:
    if not isinstance(item, dict) or set(item) != VALID_FIELDS:
        raise RefillRejected("候選欄位不符合格式")
    for field in ("name", "tag", "desc", "app", "headline"):
        if not _nonempty_string(item[field]):
            raise RefillRejected(f"候選欄位 {field} 必須是非空字串")
    if type(item["group"]) is not int or not 0 <= item["group"] < group_count:
        raise RefillRejected("候選 group 必須是有效的分類索引")
    if normalize_name(item["headline"]) == normalize_name(item["name"]):
        raise RefillRejected("候選 headline 不可直接重複 name")
    scenes = item["scenes"]
    if (not isinstance(scenes, list) or len(scenes) < 2
            or any(not _nonempty_string(scene) for scene in scenes)):
        raise RefillRejected("候選 scenes 必須至少包含兩個非空場景")


def build_prompt(fonts: list, queue: list, groups: list) -> str:
    existing_names = [
        entry["name"] for entry in [*fonts, *queue]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]
    group_counts = [
        sum(1 for entry in [*fonts, *queue]
            if isinstance(entry, dict) and entry.get("group") == index)
        for index in range(len(groups))
    ]
    group_lines = [
        f"{index}：{group['title']}（目前共 {group_counts[index]} 筆）"
        for index, group in enumerate(groups)
    ]
    return (
        "請為台灣繁體中文 AI 生圖字體風格庫設計候選項目。\n"
        f"請回傳恰好 {MODEL_CANDIDATE_COUNT} 筆，並且只輸出 JSON 物件："
        '{"candidates":[{"name":"…","tag":"…","group":0,"desc":"…",'
        '"scenes":["…","…"],"app":"…","headline":"…"}]}。\n'
        "每筆候選都要有上述七個欄位；group 必須是下列分類索引之一：\n"
        + "\n".join(group_lines)
        + "\nname 是精簡且彼此有辨識度的風格名稱；tag 是簡短分類標籤；"
        "desc 要具體說明筆畫的構成或技法，也要點出風格需要的背景；"
        "scenes 至少列出兩種適合場景；app 要描述真實應用圖的場景與畫面細節；"
        "headline 要是 app 場景裡實際會出現的繁體中文標語，不可直接重複 name。\n"
        "優先分配到目前數量較少的分類，讓分類分布更平均。候選也要涵蓋不同書寫、結構、文化與使用情境，避免只做常見字體材質換皮。\n"
        "以下名稱已完成或已在候選佇列，請不要產生相同或只差空白、標點、全半形的名稱：\n"
        + "、".join(existing_names)
    )


def gemini_candidate_model(prompt: str, api_key: str | None = None) -> str:
    """可替換的模型邊界；回傳 Gemini 產生的 JSON 文字。"""
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RefillRejected("找不到 GEMINI_API_KEY")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "maxOutputTokens": 10000,
        },
    }).encode()
    response = generate_content(body, key, sleep=time.sleep)
    return response["candidates"][0]["content"]["parts"][0]["text"]


def parse_candidates(raw: str, fonts: list, queue: list, groups: list) -> list:
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise RefillRejected("模型回傳的內容不是合法 JSON") from error
    if not isinstance(decoded, dict) or set(decoded) != {"candidates"}:
        raise RefillRejected("模型回傳格式必須是含 candidates 陣列的 JSON 物件")
    proposed = decoded["candidates"]
    if not isinstance(proposed, list):
        raise RefillRejected("模型回傳的 candidates 必須是陣列")

    seen = {
        normalize_name(entry["name"])
        for entry in [*fonts, *queue]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        and normalize_name(entry["name"])
    }
    unique = []
    for item in proposed:
        validate_candidate(item, len(groups))
        key = normalize_name(item["name"])
        if not key:
            raise RefillRejected("候選名稱正規化後不可為空")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    if len(unique) < REFILL_COUNT:
        raise RefillRejected(
            f"去除重複後只有 {len(unique)} 筆合格候選，需要至少 {REFILL_COUNT} 筆")
    return unique[:REFILL_COUNT]


def refill_queue(queue_path="queue.json", fonts_path="fonts.json", model_call=gemini_candidate_model) -> int:
    queue_path = pathlib.Path(queue_path)
    fonts_path = pathlib.Path(fonts_path)
    queue_data = json.loads(queue_path.read_text(encoding="utf-8"))
    fonts_data = json.loads(fonts_path.read_text(encoding="utf-8"))
    queue = queue_data.get("queue")
    fonts = fonts_data.get("fonts")
    groups = fonts_data.get("groups")
    if not isinstance(queue, list) or not isinstance(fonts, list) or not isinstance(groups, list):
        raise RefillRejected("queue.json 或 fonts.json 結構不正確")
    if len(queue) >= REFILL_BELOW:
        print(f"佇列有 {len(queue)} 筆，未低於 {REFILL_BELOW} 筆門檻。")
        return 0

    prompt = build_prompt(fonts, queue, groups)
    try:
        raw = model_call(prompt)
        additions = parse_candidates(raw, fonts, queue, groups)
    except RefillRejected:
        raise
    except Exception as error:
        raise RefillRejected(f"模型呼叫或回應讀取失敗：{error}") from error

    updated = dict(queue_data)
    updated["queue"] = [*queue, *additions]
    serialized = json.dumps(updated, ensure_ascii=False, indent=1) + "\n"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=queue_path.parent,
        prefix=f".{queue_path.name}.", suffix=".tmp", delete=False
    ) as temporary:
        temporary.write(serialized)
        temporary_path = pathlib.Path(temporary.name)
    try:
        temporary_path.replace(queue_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f"候選佇列自動補入 {len(additions)} 筆，目前共 {len(updated['queue'])} 筆。")
    return len(additions)


def write_output(refilled: int) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"refilled={refilled}\n")


def main() -> None:
    try:
        refilled = refill_queue()
    except Exception as error:
        print(f"自動補貨未寫入，原佇列保留：{error}")
        refilled = 0
    write_output(refilled)


if __name__ == "__main__":
    main()
