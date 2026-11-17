# SPIKE: 列出 flow 文件里非 HTTP 的流（tcp 隧道等），找 feed JSON 走的通道
import sys
from mitmproxy import io as mio
from mitmproxy import tcp

FLOW = r"D:\claude code\视频获取\spike\traffic_round4.flow"

def main():
    counts = {}
    rows = []
    with open(FLOW, "rb") as f:
        for flow in mio.FlowReader(f).stream():
            t = flow.type
            counts[t] = counts.get(t, 0) + 1
            if t == "http":
                continue
            # tcp 流：目标地址 + 消息数/字节数
            peer = f"{flow.client_conn.peername}"
            dst = ""
            try:
                sni = flow.client_conn.sni or ""
            except Exception:
                sni = ""
            msgs = getattr(flow, "messages", None) or []
            n_in = sum(len(m.content) for m in msgs if m.from_client)
            n_out = sum(len(m.content) for m in msgs if not m.from_client)
            # 目的地
            try:
                dst = str(flow.server_conn.address)
            except Exception:
                dst = "?"
            rows.append((t, sni, dst, len(msgs), n_in, n_out))
    print("流类型统计:", counts, "\n")
    for t, sni, dst, nm, n_in, n_out in rows:
        print(f"[{t}] sni={sni or '-'} dst={dst} msgs={nm} c->s={n_in}B s->c={n_out}B")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
