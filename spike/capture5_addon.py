# SPIKE 第5轮：注入探针，找 decodeKey 的页面内通道
# - 拦截 channels.weixin.qq.com 页面壳(/web/pages/*)，剥离 CSP 并注入 probe.js
# - 拦截 /__probe_sink 上报（本地 204 短路，不转发）
# - 保留媒体分片落盘 + 全量摘要日志
import hashlib
import json
import os
import re
import sys

from mitmproxy import http

SPIKE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(SPIKE_DIR, "media")
LOG = os.path.join(SPIKE_DIR, "capture5.jsonl")
PROBE_HITS = os.path.join(SPIKE_DIR, "probe_hits.jsonl")
MAX_SAVE = 400 * 1024 * 1024

MEDIA_EXT = re.compile(r"\.(m3u8|ts|mp4|m4s|mpd|m4a|aac|mov)(\?|$)")
saved = 0

with open(os.path.join(SPIKE_DIR, "probe.js"), "r", encoding="utf-8") as f:
    PROBE_JS = f.read()

SHELL_HOSTS = ("channels.weixin.qq.com",)


def _log(obj):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def request(flow: http.HTTPFlow) -> None:
    # 探针上报端点：本地短路
    if flow.request.pretty_host in SHELL_HOSTS and flow.request.path.startswith("/__probe_sink"):
        try:
            body = flow.request.get_text(strict=False) or ""
        except Exception:
            body = ""
        rec = {"path": flow.request.path[:120], "body": body}
        with open(PROBE_HITS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        flow.response = http.Response.make(204, b"", {"Content-Type": "text/plain"})


def response(flow: http.HTTPFlow) -> None:
    try:
        _handle(flow)
    except Exception as e:
        _log({"addon_error": repr(e), "url": flow.request.url[:200]})


def _handle(flow: http.HTTPFlow) -> None:
    global saved
    req, resp = flow.request, flow.response
    host = req.pretty_host
    ct = resp.headers.get("content-type", "")
    body = b""
    try:
        body = resp.get_content(strict=False) or b""
    except Exception:
        pass

    # 页面壳：注入探针
    if host in SHELL_HOSTS and req.path.startswith("/web/pages/") and "html" in ct:
        for h in ("content-security-policy", "content-security-policy-report-only",
                  "x-content-type-options", "x-frame-options"):
            resp.headers.pop(h, None)
        try:
            text = body.decode("utf-8", "replace")
        except Exception:
            text = ""
        tag = "<script>%s</script>" % PROBE_JS
        if text and "<head" in text:
            i = text.find(">", text.find("<head")) + 1
            text = text[:i] + tag + text[i:]
            resp.set_text(text)
            _log({"injected": req.path[:150], "size": len(text)})
        return

    # 媒体分片：落盘
    is_media = ct.startswith(("video/", "audio/")) or "mpegurl" in ct or MEDIA_EXT.search(req.path)
    if is_media and saved < MAX_SAVE:
        name = hashlib.sha256((req.url + str(resp.status_code) + str(len(body))).encode()).hexdigest()[:16]
        p = os.path.join(MEDIA_DIR, name + ".bin")
        with open(p, "wb") as f:
            f.write(body)
        saved += len(body)
        with open(os.path.join(MEDIA_DIR, "manifest5.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "file": name + ".bin", "url": req.url[:400], "ct": ct,
                "range": req.headers.get("range", ""),
                "content_range": resp.headers.get("content-range", ""),
                "size": len(body),
            }, ensure_ascii=False) + "\n")

    _log({
        "host": host, "method": req.method, "path": req.path[:200], "status": resp.status_code,
        "ct": ct.split(";")[0], "size": len(body),
        "range": req.headers.get("range", ""), "content_range": resp.headers.get("content-range", ""),
    })
