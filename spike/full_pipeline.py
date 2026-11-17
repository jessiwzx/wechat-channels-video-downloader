# SPIKE 完整管线：probe数据 → 下载视频+音频 → 解密前128KB → 待ffmpeg合流
# 用法: python full_pipeline.py
import json
import os
import sys
import time
import urllib.request

from isaac64 import keystream

sys.stdout.reconfigure(encoding="utf-8")
SPIKE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(SPIKE, "download")
os.makedirs(DL, exist_ok=True)

# 本次实验目标的 encfilekey（逻辑文件 id）。真实值不入库，运行时用环境变量传入：
#   set VIDEO_EKF=xxxx  （值从 records.jsonl / probe_hits.jsonl 的 URL 里取）
VIDEO_EKF = os.environ.get("VIDEO_EKF", "")
PREFIX = 131072


def collect():
    """从 probe_hits 收集目标对象的 video/audio 两条 media（url+token+key 全量）"""
    found = {}
    with open(os.path.join(SPIKE, "probe_hits.jsonl"), encoding="utf-8") as f:
        for line in f:
            if not VIDEO_EKF or VIDEO_EKF not in line:
                continue
            try:
                o = json.loads(json.loads(line)["body"])
            except Exception:
                continue
            if o.get("k") != "video":
                continue
            tok = o.get("url_token") or ""
            if len(tok) < 500:  # 只要 token 完整的记录
                continue
            url = o["url"]
            if url.startswith("https://finder.video.qq.com/251/20302/") and VIDEO_EKF in url:
                found.setdefault("video", {"url": url + tok, "key": int(o["decode_key"]),
                                           "title": o.get("title", ""),
                                           **{k: v for k, v in (o.get("object_fields") or {}).items()
                                              if k in ("createtime", "id", "nickname")}})
    # 音频直接用已验证的 audio_target.json
    at = json.load(open(os.path.join(SPIKE, "audio_target.json"), encoding="utf-8"))
    found.setdefault("audio", {"url": at["url"], "key": int(at["key"])})
    return found


def download(name, url, key):
    """Range 分块下载全文件（可续传），完成后原地解密前128KB"""
    dest = os.path.join(DL, name)
    done_marker = dest + ".done"
    if os.path.exists(done_marker):
        print(f"[{name}] 已完成，跳过")
        return dest
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # 探总长
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "Mozilla/5.0"})
    with op.open(req, timeout=30) as r:
        cr = r.headers.get("Content-Range", "")
        total = int(cr.split("/")[-1])
    print(f"[{name}] 总长 {total/1048576:.1f}MB, 本地已有 {have/1048576:.1f}MB")
    t0 = time.time()
    while have < total:
        end = min(have + 8 * 1024 * 1024 - 1, total - 1)
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-{end}",
                                                   "User-Agent": "Mozilla/5.0"})
        try:
            with op.open(req, timeout=60) as r:
                chunk = r.read()
        except Exception as e:
            print(f"[{name}] 传输错误 {e}，3 秒后重试")
            time.sleep(3)
            continue
        if not chunk:
            break
        with open(dest, "ab") as f:
            f.write(chunk)
        have += len(chunk)
        speed = have / 1048576 / max(time.time() - t0, 0.1)
        print(f"\r[{name}] {have/1048576:.0f}/{total/1048576:.0f}MB ({speed:.1f}MB/s)", end="")
    print()
    # 原地解密前 128KB
    with open(dest, "r+b") as f:
        head = f.read(PREFIX)
        ks = keystream(key, min(PREFIX, len(head)))
        f.seek(0)
        f.write(bytes(a ^ b for a, b in zip(head, ks)))
    open(done_marker, "w").write("ok")
    print(f"[{name}] 下载+解密完成")
    return dest


def main():
    info = collect()
    print("收集到:", {k: {kk: str(vv)[:60] for kk, vv in v.items()} for k, v in info.items()})
    v = download("video.mp4", info["video"]["url"], info["video"]["key"])
    a = download("audio.m4a", info["audio"]["url"], info["audio"]["key"])
    # 校验头
    for p in (v, a):
        h = open(p, "rb").read(32)
        print(os.path.basename(p), "头:", h[:16].hex(), h[4:12])
    json.dump(info["video"], open(os.path.join(DL, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
