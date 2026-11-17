# SPIKE: 扫描 flow 文件所有响应体，找 stodownload/encfilekey/decode 相关线索
import sys
from mitmproxy import io as mio

FLOW = r"D:\claude code\视频获取\spike\traffic_round4.flow"

def main():
    rows = []
    with open(FLOW, "rb") as f:
        for flow in mio.FlowReader(f).stream():
            if flow.type != "http":
                continue
            req, resp = flow.request, flow.response
            if resp is None:
                continue
            try:
                body = resp.get_content() or b""
            except Exception:
                body = b""
            hits = []
            for pat in (b"stodownload", b"encfilekey", b"decode", b"Decode", b"finder/video", b"feed"):
                if pat in body:
                    hits.append(pat.decode())
            if hits:
                rows.append((req.pretty_host, req.method, req.path[:90], resp.status_code,
                             len(body), resp.headers.get("content-type", ""), hits))
    print(f"命中 {len(rows)} 个响应：\n")
    for host, m, p, sc, sz, ct, hits in rows:
        print(f"[{sc}] {m} {host}{p}")
        print(f"     ct={ct} size={sz} hits={hits}")
    print()
    # 再列一遍全部 hosts+paths 概览（不含命中的也打出来，人工看漏了什么）
    print("=== 全部 HTTP 响应概览 ===")
    with open(FLOW, "rb") as f:
        for flow in mio.FlowReader(f).stream():
            if flow.type != "http":
                continue
            req, resp = flow.request, flow.response
            sc = resp.status_code if resp else "-"
            sz = 0
            if resp is not None:
                try:
                    sz = len(resp.get_content() or b"")
                except Exception:
                    pass
            print(f"[{sc}] {req.method} {req.pretty_host}{req.path[:100]} {sz}B")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
