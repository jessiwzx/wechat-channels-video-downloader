# -*- coding: utf-8 -*-
"""
SPIKE 临时抓包脚本（验证可行性用，正式版会重写）

用途：mitmdump 加载本脚本后，记录所有请求摘要，并把媒体/JSON 响应体存档，
     用于事后定位视频号视频请求和解密线索。

用法：mitmdump -p 8899 -s capture_addon.py
产出：spike/capture.jsonl        —— 所有请求摘要（host/path/类型/大小）
      spike/media/<sha>.bin      —— 媒体或 JSON 响应体
      spike/media/manifest.jsonl —— 存档文件与 URL 的对应关系
"""
import hashlib
import json
import os
import re
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

JSONL = os.path.join(BASE, "capture.jsonl")
MANIFEST = os.path.join(MEDIA_DIR, "manifest.jsonl")

MEDIA_EXT = re.compile(r"\.(m3u8|ts|mp4|m4s|mpd|m4a|aac|mov)(\?|$)", re.I)
HLS_CT = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/dash+xml",
}
MAX_SAVE = 200 * 1024 * 1024  # 单个响应体最多存 200MB


def response(flow):
    try:
        _handle(flow)
    except Exception as e:  # 保证抓包不因单条请求出错而中断
        with open(JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"addon_error": str(e)}, ensure_ascii=False) + "\n")


def _handle(flow):
    req = flow.request
    resp = flow.response
    ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    size = len(resp.content) if resp.content else 0

    entry = {
        "ts": round(time.time(), 3),
        "host": req.host,
        "method": req.method,
        "path": req.path[:800],
        "status": resp.status_code,
        "content_type": ct,
        "size": size,
    }
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 判定是否值得保存响应体：
    # 1) 视频/音频流、HLS/DASH 清单、常见媒体扩展名
    # 2) 腾讯系域名的 JSON（视频号 API 元数据可能含地址/密钥线索）
    want = (
        ct.startswith("video/")
        or ct.startswith("audio/")
        or ct in HLS_CT
        or bool(MEDIA_EXT.search(req.path))
    )
    if not want and "json" in ct and req.host.endswith((".qq.com", ".qpic.cn")):
        want = True

    if not want or not resp.content or size > MAX_SAVE:
        return

    h = hashlib.sha256(resp.content).hexdigest()[:16]
    fn = h + ".bin"
    with open(os.path.join(MEDIA_DIR, fn), "wb") as f:
        f.write(resp.content)
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"file": fn, "url": req.url, "ct": ct, "size": size},
                ensure_ascii=False,
            )
            + "\n"
        )
