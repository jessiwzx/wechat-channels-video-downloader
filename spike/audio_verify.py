# 音频轨解密验证：audio_target.json 的 url + key → 前缀下载 → 解密 → 验容器头
import json
import sys
import urllib.request

from isaac64 import keystream

sys.stdout.reconfigure(encoding="utf-8")

t = json.load(open("audio_target.json", encoding="utf-8"))
url, key = t["url"], int(t["key"])
print(f"URL 总长 {len(url)}, key={key}")

req = urllib.request.Request(url, headers={"Range": "bytes=0-131071", "User-Agent": "Mozilla/5.0"})
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
r = op.open(req, timeout=30)
data = r.read()
print(f"HTTP {r.status}, Content-Range: {r.headers.get('Content-Range', '')}, 实收 {len(data)}B")
print("加密头:", data[:20].hex())

ks = keystream(key, min(131072, len(data)))
dec = bytes(a ^ b for a, b in zip(data, ks))
print("解密头:", dec[:20].hex())
print("解密头(ascii):", dec[:32])
hits = [m for m in (b"ftyp", b"moov", b"mdat", b"free", b"styp", b"mp4a", b"ESDS") if m in dec[:64]]
print("✓ 音频解密成功:" if hits else "✗ 未解出:", hits)
