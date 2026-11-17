# 在 v1 原始片段里找 media[0] 的完整 url_token（含 token/basedata/sign）
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
EKFP = os.environ.get("VIDEO_EKF", "")  # 真实 encfilekey 运行时用环境变量传入
best = ""
with open("probe_hits.jsonl", encoding="utf-8") as f:
    for line in f:
        if EKFP not in line:
            continue
        # v1 记录的 d 里是转义过的 JSON，url_token 以 url_token 形式出现
        i = line.find("url_token")
        if i < 0:
            continue
        frag = line[i:i + 1400]
        if len(frag) > len(best) and "token=" in frag:
            best = frag
print(best[:1400])
