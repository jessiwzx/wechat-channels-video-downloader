# 最终验证：media[0].url + 完整 url_token + decode_key → 下载前缀 → 解密 → 验 MP4 头
import json
import os
import sys
import urllib.request

from isaac64 import keystream

sys.stdout.reconfigure(encoding="utf-8")

EKFP = os.environ.get("VIDEO_EKF", "")  # 真实 encfilekey 运行时用环境变量传入

# 从 probe_hits 取目标视频的完整记录（顶层 url_token 不截断）
rec = None
with open("probe_hits.jsonl", encoding="utf-8") as f:
    for line in f:
        if EKFP not in line:
            continue
        try:
            o = json.loads(json.loads(line)["body"])
        except Exception:
            continue
        if o.get("k") == "video" and o.get("url_token") and len(o.get("url_token", "")) > 500:
            rec = o
            break

assert rec, "未找到含完整 url_token 的记录"
url = rec["url"] + rec["url_token"]
key = int(rec["decode_key"])
print(f"URL 总长 {len(url)}, key={key}")
print("token 尾部:", rec["url_token"][-120:])

req = urllib.request.Request(url, headers={"Range": "bytes=0-131071", "User-Agent": "Mozilla/5.0"})
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
r = op.open(req, timeout=30)
data = r.read()
print(f"HTTP {r.status}, Content-Range: {r.headers.get('Content-Range','')}, 实收 {len(data)}B")
print("加密头:", data[:20].hex())

ks = keystream(key, min(131072, len(data)))
dec = bytes(a ^ b for a, b in zip(data, ks))
print("解密头:", dec[:20].hex())
print("解密头(ascii):", dec[:24])
hits = [m for m in (b"ftyp", b"moov", b"mdat", b"free", b"styp") if m in dec[:64]]
if hits:
    print("✓✓✓ MP4 特征:", hits, "🎉 解密链路全线打通！")
    open("decrypted_head.bin", "wb").write(dec)
else:
    print("✗ 仍未解出")
