# SPIKE 解密变体排查：比对URL + 尝试不同密钥流变体
import json
import struct
import sys
import urllib.request

from isaac64 import RandCtx64
from mitmproxy import io as mio

FLOW = r"D:\claude code\视频获取\spike\traffic_round5_1.flow"
TARGET = json.load(open(r"D:\claude code\视频获取\spike\target_video.json", encoding="utf-8"))
PROBE_URL = TARGET["url"]
KEY = 1522607660


def flow_url():
    with open(FLOW, "rb") as f:
        for flow in mio.FlowReader(f).stream():
            if flow.type != "http":
                continue
            req = flow.request
            if req.pretty_host == "finder.video.qq.com" and req.query.get("hy") == "SH":
                return str(req.url)
    return None


def fetch(url):
    req = urllib.request.Request(url, headers={"Range": "bytes=0-131071",
                                               "User-Agent": "Mozilla/5.0"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=30) as r:
        return bytearray(r.read())


def ks_variants(key):
    """生成几种候选密钥流的前 32 字节"""
    out = {}
    # v1: 标准移植（desc 消费 + BE）
    ctx = RandCtx64(key)
    vals = [ctx.random() for _ in range(4)]
    out["desc_BE"] = b"".join(struct.pack(">Q", v) for v in vals)
    out["desc_LE"] = b"".join(struct.pack("<Q", v) for v in vals)
    # v2: 正序消费 Seed[0..] —— 重新生成一轮后正读
    ctx2 = RandCtx64(key)
    out["asc_BE"] = b"".join(struct.pack(">Q", ctx2.seed[i]) for i in range(4))
    out["asc_LE"] = b"".join(struct.pack("<Q", ctx2.seed[i]) for i in range(4))
    # v3: 不带初始 isAAC64 的原始 fill 状态（mm 层）
    ctx3 = RandCtx64(key)
    out["mm_BE"] = b"".join(struct.pack(">Q", ctx3.mm[i]) for i in range(4))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fu = flow_url()
    print("probe url 前 60:", PROBE_URL[:60])
    print("flow  url 前 60:", fu[:60] if fu else None)
    print("flow url 以 probe url 开头?", fu and fu.startswith(PROBE_URL[:120]))
    print("encfilekey 相同?",
          fu.split("encfilekey=")[1].split("&")[0] == PROBE_URL.split("encfilekey=")[1].split("&")[0])
    data = fetch(fu)
    print("加密头:", data[:16].hex())
    for name, ks in ks_variants(KEY).items():
        dec = bytes(a ^ b for a, b in zip(data[:32], ks + b"\0" * 64))
        ok = any(m in dec for m in (b"ftyp", b"moov", b"mdat", b"free"))
        print(f"{name:8}: {dec[:16].hex()}  {'✓MP4!' if ok else ''}")


if __name__ == "__main__":
    main()
