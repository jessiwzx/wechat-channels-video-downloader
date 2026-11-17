# SPIKE: 从 traffic_round4.flow 中提取 feed API JSON（找 decodeKey）+ 媒体分片清单
# 用法: python analyze_flow.py
import io as _io
import json
import re
import sys

from mitmproxy import io as mio
from mitmproxy.exceptions import FlowReadException

FLOW = r"D:\claude code\视频获取\spike\traffic_round4.flow"

def walk_find_media(node, out, path=""):
    """递归找所有含 url/decodeKey 的 dict（feed media 结构）"""
    if isinstance(node, dict):
        if "decodeKey" in node and ("url" in node or "urlToken" in node):
            out.append((path, node))
        for k, v in node.items():
            walk_find_media(v, out, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk_find_media(v, out, f"{path}[{i}]")

def main():
    medias = []          # (flow_url, path, media_dict)
    api_hits = []        # 含 decodeKey 的 API 响应概览
    media_reqs = []      # finder.video.qq.com 分片请求

    with open(FLOW, "rb") as f:
        reader = mio.FlowReader(f)
        n = 0
        for flow in reader.stream():
            n += 1
            if flow.type != "http":
                continue
            req, resp = flow.request, flow.response
            if resp is None:
                continue
            host = req.pretty_host
            body = b""
            try:
                body = resp.get_content() or b""
            except Exception:
                pass
            if host.endswith("channels.weixin.qq.com"):
                if b"decodeKey" in body:
                    api_hits.append((req.method, req.path, len(body), resp.status_code))
                    try:
                        data = json.loads(body)
                    except Exception:
                        # 可能被包了一层，找 JSON 起始点
                        m = re.search(rb"[{\[]", body)
                        if not m:
                            continue
                        try:
                            data = json.loads(body[m.start():])
                        except Exception:
                            print(f"[!] JSON 解析失败: {req.path} ({len(body)}B)")
                            continue
                    found = []
                    walk_find_media(data, found)
                    for path, media in found:
                        medias.append((str(req.url), path, media))
            elif host.endswith("finder.video.qq.com"):
                cr = resp.headers.get("content-range", "")
                rg = req.headers.get("range", "")
                media_reqs.append((req.path.split("?")[0], req.query.get("encfilekey", "")[:40],
                                   rg, cr, len(body), resp.status_code))

    print(f"总 flow 数: {n}")
    print(f"\n=== 含 decodeKey 的 API 响应: {len(api_hits)} 个 ===")
    for m, p, sz, sc in api_hits:
        print(f"  [{sc}] {m} {p}  ({sz}B)")
    print(f"\n=== 提取到的 media 对象: {len(medias)} 个 ===")
    for url, path, media in medias:
        print(f"\n  API: {url[:110]}")
        print(f"  路径: {path}")
        for k in ("url", "urlToken", "decodeKey", "fileSize", "videoPlayLen", "coverUrl", "thumbUrl"):
            v = media.get(k)
            if isinstance(v, str) and len(v) > 100:
                v = v[:100] + "..."
            print(f"    {k}: {v}")
        # 上层信息（feed 的 description/createtime 在父节点，这里只打 media 层）
    print(f"\n=== finder.video.qq.com 分片请求: {len(media_reqs)} 个 ===")
    by_key = {}
    for p, ek, rg, cr, sz, sc in media_reqs:
        by_key.setdefault((p, ek), []).append((rg, cr, sz))
    for (p, ek), lst in by_key.items():
        total = sum(x[2] for x in lst)
        print(f"  {p} encfilekey={ek}... 分片{len(lst)}个 共{total/1048576:.1f}MB")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
