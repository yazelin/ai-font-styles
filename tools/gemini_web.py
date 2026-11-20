#!/usr/bin/env python3
"""呼叫自架 gemini-web 的檔案聊天介面，並重試暫時性失敗。"""
import base64
import json
import time
import urllib.error
import urllib.request


_UPLOAD_FAILURE_PHRASES = (
    "沒看到附件", "沒有看到附件", "没有看到附件", "請提供", "请提供",
    "沒有收到", "没有收到", "可能沒真的傳上去", "可能沒有真的傳上去",
    "可能没真的传上去", "沒看到圖片", "沒有看到圖片", "没有看到图片",
)


class _TemporaryResponseError(RuntimeError):
    """服務回應不完整或失敗，可透過重試恢復。"""


def _first_json_object(text: str) -> str:
    """從可能帶有前後文字的回應中取第一個完整 JSON 物件。"""
    start = text.find("{")
    if start < 0:
        raise ValueError("回應中沒有 JSON 物件")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("回應中的 JSON 物件不完整")


def _parse_response(raw: bytes) -> dict:
    text = raw.decode("utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = json.loads(_first_json_object(text))
    if not isinstance(value, dict):
        raise ValueError("回應不是 JSON 物件")
    return value


def chat_file(
    prompt: str,
    data: bytes,
    filename: str,
    *,
    base_url: str,
    key: str,
    retries: int = 6,
    sleep=time.sleep,
    timeout: int = 240,
) -> str:
    """上傳一個檔案給 gemini-web，遇到暫時性失敗時退避重試。"""
    url = f"{base_url.rstrip('/')}/api/chat-file"
    body = json.dumps({
        "prompt": prompt,
        "file": base64.b64encode(data).decode("ascii"),
        "filename": filename,
        "timeout": timeout,
    }).encode("utf-8")
    last_error = None

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(req, timeout=timeout).read()
            try:
                result = _parse_response(response)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
                raise _TemporaryResponseError(f"gemini-web 回應 JSON 無法解析：{e}") from e

            text = result.get("text")
            if result.get("success") is not True or not isinstance(text, str) or not text.strip():
                raise _TemporaryResponseError(
                    f"gemini-web 回報 success:false 或缺少文字回應：{text!r}"
                )
            if any(phrase in text for phrase in _UPLOAD_FAILURE_PHRASES):
                raise _TemporaryResponseError(f"gemini-web 疑似沒有收到附件：{text[:200]}")
            return text
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            last_error = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
        except _TemporaryResponseError as e:
            last_error = e

        if attempt == retries:
            raise last_error
        print(f"  gemini-web 呼叫失敗（{last_error}），{attempt * 30} 秒後重試", flush=True)
        sleep(attempt * 30)

    raise last_error or RuntimeError("gemini-web 呼叫失敗")
