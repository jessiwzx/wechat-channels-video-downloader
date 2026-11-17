# SPIKE 终极验证：完整URL → 下载前128KB → ISAAC-64解密 → 检查MP4头
import os
import sys
import urllib.request

from isaac64 import decrypt_prefix
from mitmproxy import io as mio

FLOW = os.environ.get("FLOW", os.path.join(os.path.dirname(os.path.abspath(__file__)), "traffic_round5_1.flow"))
VIDEO_EKF = os.environ.get("VIDEO_EKF", "")  # 真实 encfilekey 运行时用环境变量传入
KEY = int(os.environ.get("DECODE_KEY", "0"))  # 真实 decode_key 运行时用环境变量传入
PREFIX = 131072


def find_full_urls():
    urls = {}
    with open(FLOW, "rb") as f:
        for flow in mio.FlowReader(f).stream():
            if flow.type != "http":
                continue
            req = flow.request
            if req.pretty_host != "finder.video.qq.com":
                continue
            ek = req.query.get("encfilekey", "")
            if ek.startswith(VIDEO_EKF):
                hy = req.query.get("hy", "")
                urls.setdefault(hy, str(req.url))
    return urls


def fetch_prefix(url):
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{PREFIX-1}",
                                               "User-Agent": "Mozilla/5.0"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 直连不走代理
    with opener.open(req, timeout=30) as r:
        return r.read(), r.status, r.headers.get("Content-Range", "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    urls = find_full_urls()
    print("找到的流:", {k: v[:90] + "..." for k, v in urls.items()})
    hy, url = ("SH", urls["SH"]) if "SH" in urls else next(iter(urls.items()))
    data, st, cr = fetch_prefix(url)
    print(f"\n[{hy}] HTTP {st}  Content-Range: {cr}  实收 {len(data)}B")
    print("加密头(前32B):", data[:32].hex())
    buf = bytearray(data[:PREFIX])
    decrypt_prefix(buf, min(PREFIX, len(buf)), KEY)
    print("解密头(前32B):", bytes(buf[:32]).hex())
    print("解密头(ASCII):", bytes(buf[:32]))
    head = bytes(buf[:64])
    for magic in (b"ftyp", b"styp", b"moov", b"mdat", b"free"):
        if magic in head:
            print(f"✓ 检测到 MP4 box: {magic.decode()}")
            return True
    print("✗ 未检测到 MP4 特征")
    return False


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
