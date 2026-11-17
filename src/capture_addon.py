# 生产版 mitmdump addon：
#  - 拦截 channels.weixin.qq.com 页面壳(/web/pages/*)，剥离 CSP 并注入 probe.js v3
#  - 拦截 /__probe_sink 上报，落盘到 <ROOT>/records.jsonl（orchestrator 监听该文件）
#  - 不录流量、不存媒体分片（spike 已完成取证，生产不需要）
import json
import os

from mitmproxy import http

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC_DIR)
RECORDS = os.path.join(ROOT, "records.jsonl")
CAPTURE_LOG = os.path.join(SRC_DIR, "capture_log.jsonl")

SHELL_HOSTS = ("channels.weixin.qq.com",)

with open(os.path.join(SRC_DIR, "probe.js"), "r", encoding="utf-8") as f:
    PROBE_JS = f.read()


def _clog(obj):
    with open(CAPTURE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def request(flow: http.HTTPFlow) -> None:
    if flow.request.pretty_host in SHELL_HOSTS and flow.request.path.startswith("/__probe_sink"):
        try:
            body = flow.request.get_text(strict=False) or ""
        except Exception:
            body = ""
        with open(RECORDS, "a", encoding="utf-8") as f:
            f.write(body + "\n")
        flow.response = http.Response.make(204, b"", {"Content-Type": "text/plain"})


def response(flow: http.HTTPFlow) -> None:
    try:
        _handle(flow)
    except Exception as e:
        _clog({"addon_error": repr(e), "url": flow.request.url[:200]})


def _handle(flow: http.HTTPFlow) -> None:
    req, resp = flow.request, flow.response
    if req.pretty_host not in SHELL_HOSTS or not req.path.startswith("/web/pages/"):
        return
    ct = resp.headers.get("content-type", "")
    if "html" not in ct:
        return
    for h in ("content-security-policy", "content-security-policy-report-only",
              "x-content-type-options", "x-frame-options"):
        resp.headers.pop(h, None)
    body = resp.get_content(strict=False) or b""
    text = body.decode("utf-8", "replace")
    tag = "<script>%s</script>" % PROBE_JS
    if text and "<head" in text:
        i = text.find(">", text.find("<head")) + 1
        text = text[:i] + tag + text[i:]
        resp.set_text(text)
        _clog({"injected": req.path[:150], "size": len(text)})
