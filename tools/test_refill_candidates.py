#!/usr/bin/env python3
"""補候選流程的離線單元測試；所有模型回應都由測試替身提供。"""
import json
import pathlib
import tempfile

import refill_candidates as refill


GROUPS = [{"title": f"分類{index}"} for index in range(10)]


def candidate(index: int) -> dict:
    return {
        "name": f"新風格{index:02d}",
        "tag": "結構字體",
        "group": index % 10,
        "desc": "筆畫以交錯線條疊合，呈現清楚的幾何結構",
        "scenes": ["品牌封面", "活動海報"],
        "app": "設計活動主視覺，搭配實際場景物件與明確版面",
        "headline": f"一起探索{index:02d}",
    }


def fixture(tmp: str, queue: list | None = None):
    queue_path = pathlib.Path(tmp) / "queue.json"
    fonts_path = pathlib.Path(tmp) / "fonts.json"
    queue_data = {"_說明": "測試佇列", "queue": queue or []}
    fonts_data = {
        "groups": GROUPS,
        "fonts": [{"n": 1, "name": "既有字", "group": 0}],
    }
    queue_path.write_text(json.dumps(queue_data, ensure_ascii=False), encoding="utf-8")
    fonts_path.write_text(json.dumps(fonts_data, ensure_ascii=False), encoding="utf-8")
    return queue_path, fonts_path, queue_data


def response(items: list) -> str:
    return json.dumps({"candidates": items}, ensure_ascii=False)


# 一、正常補貨：20 筆格式正確且未重複的候選一次寫入。
with tempfile.TemporaryDirectory() as tmp:
    queue_path, fonts_path, _ = fixture(tmp, [candidate(90)])
    calls = []
    added = refill.refill_queue(
        queue_path, fonts_path,
        model_call=lambda prompt: calls.append(prompt) or response([candidate(i) for i in range(20)]),
    )
    saved = json.loads(queue_path.read_text(encoding="utf-8"))
    assert added == 20, added
    assert len(saved["queue"]) == 21, saved
    assert len(calls) == 1 and "fonts.json" not in calls[0], calls
    assert [item["name"] for item in saved["queue"][1:]] == [f"新風格{i:02d}" for i in range(20)]
    print("【正常補齊】新增 20 筆，原候選保留")


# 二、模型回覆重複名稱：含已完成名稱及正規化後相同的批次名稱，不足 20 筆時不寫入。
with tempfile.TemporaryDirectory() as tmp:
    queue_path, fonts_path, original = fixture(tmp)
    items = [candidate(i) for i in range(20)]
    items[0]["name"] = "既有・字"
    items[2]["name"] = "新風格01"
    items[1]["name"] = "新風格　０１"
    before = queue_path.read_text(encoding="utf-8")
    try:
        refill.refill_queue(queue_path, fonts_path, lambda prompt: response(items))
    except refill.RefillRejected as error:
        assert "只有 18 筆" in str(error), error
    else:
        raise AssertionError("重複候選不足目標數量時應拒絕整批")
    assert queue_path.read_text(encoding="utf-8") == before
    print("【重複候選】正規化去重後不足 20 筆，原佇列未變")


# 三、模型回覆格式錯誤：缺少必填欄位時不寫入。
with tempfile.TemporaryDirectory() as tmp:
    queue_path, fonts_path, _ = fixture(tmp)
    items = [candidate(i) for i in range(20)]
    del items[0]["headline"]
    before = queue_path.read_text(encoding="utf-8")
    try:
        refill.refill_queue(queue_path, fonts_path, lambda prompt: response(items))
    except refill.RefillRejected as error:
        assert "欄位不符合格式" in str(error), error
    else:
        raise AssertionError("缺少必填欄位時應拒絕整批")
    assert queue_path.read_text(encoding="utf-8") == before
    print("【壞格式】候選格式錯誤，原佇列未變")

print("OK")
