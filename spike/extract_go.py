# 从会话转录中恢复早前抓取的 Go 源码片段
import json
import sys

path = r"C:\Users\wzx\.claude\projects\D--claude-code-----\4d24e654-a877-45ec-b257-5af96516528e.jsonl"
hits = []
with open(path, encoding="utf-8", errors="replace") as f:
    for line in f:
        if "func rand64Init" in line or "isAAC64" in line:
            hits.append(line)

# 找包含最长代码段的记录
best_text = ""
for line in hits:
    try:
        obj = json.loads(line)
    except Exception:
        continue

    def scan(node):
        global best_text
        if isinstance(node, dict):
            for v in node.values():
                scan(v)
        elif isinstance(node, list):
            for v in node:
                scan(v)
        elif isinstance(node, str):
            if "func rand64Init" in node and len(node) > len(best_text):
                best_text = node

    scan(obj)

if not best_text:
    print("NOT FOUND")
    sys.exit(1)

i = best_text.find("func rand64Init")
if i < 0:
    i = best_text.find("package")
print(best_text[max(0, i - 400):i + 5000])
