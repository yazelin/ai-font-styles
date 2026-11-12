#!/usr/bin/env python3
"""共用 Gemini generateContent 呼叫與暫時性錯誤重試。"""
import json
import time
import urllib.error
import urllib.request


GEMINI_MODEL = "gemini-flash-latest"


def generate_content(body: bytes, api_key: str, retries: int = 6, sleep=time.sleep) -> dict:
    """沿用每日驗字的 Gemini API、驗證方式與退避重試。"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError) as e:
            retriable = not isinstance(e, urllib.error.HTTPError) or e.code >= 500 or e.code == 429
            if attempt == retries or not retriable:
                raise
            print(f"  Gemini 呼叫失敗（{e}），{attempt * 30} 秒後重試", flush=True)
            sleep(attempt * 30)
