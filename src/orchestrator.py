# -*- coding: utf-8 -*-
"""
生产版总控：每周下载.bat 调用本文件。

职责（单进程树，崩溃时 finally + 外置 watchdog 双保险）：
  1. 启动 mitmdump（仅白名单域名，addon 注入探针），崩溃自动重启（≤5 次）
  2. 打开系统代理；结束时务必关闭
  3. 监听 records.jsonl，发现新视频对象：
     - 逐 media 变体嗅探（12MB 前缀 → 解密 → ffprobe 实际分辨率）
     - 择优（有音轨 > 分辨率）→ Range 续传下载 → 解密前 128KB → 校验 → 归档
  4. 归档命名 归档/YYYY-MM-DD_序号.mp4（日期 = createtime，北京时间）
  5. index.json 记录已归档对象；同对象发现更高清变体时自动升级替换

用法：
  python orchestrator.py            # 正常每周流程
  python orchestrator.py --dry      # 不起代理/mitmdump，处理现有 records 一次后退出
  python orchestrator.py --offline  # --dry 且不真正下载（只打印决策，离线测试用）
"""
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from isaac64 import keystream

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
ARCHIVE = os.path.join(ROOT, "归档")
TMPDIR = os.path.join(ROOT, "下载中")
RECORDS = os.path.join(ROOT, "records.jsonl")
INDEX = os.path.join(ARCHIVE, "index.json")
SET_PROXY = os.path.join(SRC, "set_proxy.ps1")
FFPROBE = os.path.join(SRC, "bin", "ffprobe.exe")

PORT = 8899
ENC_PREFIX = 131072          # 仅文件前 128KB 加密
SNIFF = 12 * 1024 * 1024     # 嗅探前缀（实测 moov 最大 9.4MB）
CHUNK = 8 * 1024 * 1024      # 下载分块
IDLE_EXIT = 20 * 60          # 无新记录且无下载 20 分钟 → 收摊
HARD_EXIT = 45 * 60          # 最长运行 45 分钟
MAX_RESTART = 5

DRY = "--dry" in sys.argv or "--offline" in sys.argv
OFFLINE = "--offline" in sys.argv


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def beijing_date(ts):
    if not ts:
        return "1970-01-01"
    try:
        d = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc) + datetime.timedelta(hours=8)
        return d.strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"


# ---------------------------------------------------------------- 代理/mitmdump
def find_mitmdump():
    p = shutil.which("mitmdump")
    if p:
        return p
    for c in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\Scripts\mitmdump.exe"),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\Scripts\mitmdump.exe")):
        if os.path.exists(c):
            return c
    return None


def set_proxy(state):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", SET_PROXY, "-State", state],
                   capture_output=True)


def port_alive():
    s = socket.socket()
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def kill_tree(pid):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def _clear_stray_mitmdump():
    """清掉上次异常退出残留的 mitmdump（启动器壳 + python 子进程），避免端口占用"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'mitmdump.exe') "
             "-or ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'mitmdump') } "
             "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            capture_output=True, timeout=30)
    except Exception:
        pass


class ProxySession:
    """mitmdump 生命周期 + supervisor + 内部 watchdog 线程"""

    def __init__(self):
        self.proc = None
        self.restart = 0
        self.stop = threading.Event()
        self.dead_reason = None
        self.sup_t = None
        self.wd_t = None

    def start_mitmdump(self):
        exe = find_mitmdump()
        if not exe:
            raise RuntimeError("找不到 mitmdump，请先安装 mitmproxy")
        _clear_stray_mitmdump()
        self.proc = subprocess.Popen(
            [exe, "-p", str(PORT), "-s", os.path.join(SRC, "capture_addon.py"), "-q"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            if port_alive():
                log(f"mitmdump 已就绪 (pid={self.proc.pid}, 端口 {PORT})")
                return
            if self.proc.poll() is not None:
                break
            time.sleep(1)
        raise RuntimeError(f"mitmdump 未在 30 秒内就绪 (exit={self.proc.poll()})")

    def _supervisor(self):
        while not self.stop.is_set():
            time.sleep(2)
            if self.proc and self.proc.poll() is not None and not self.stop.is_set():
                self.restart += 1
                if self.restart > MAX_RESTART:
                    self.dead_reason = "mitmdump 反复崩溃"
                    return
                log(f"! mitmdump 退出(code={self.proc.poll()})，第 {self.restart} 次重启")
                try:
                    self.start_mitmdump()
                except Exception as e:
                    self.dead_reason = f"mitmdump 重启失败: {e}"
                    return

    def _watchdog(self):
        fails = 0
        while not self.stop.is_set():
            time.sleep(10)
            if port_alive():
                fails = 0
            else:
                fails += 1
                if fails >= 3:
                    self.dead_reason = "端口 8899 连续 30 秒无监听（防断网保护触发）"
                    return

    def __enter__(self):
        self.start_mitmdump()
        set_proxy("on")
        log("系统代理已开启 → 127.0.0.1:8899（仅白名单域名走解密，其余透传）")
        self.sup_t = threading.Thread(target=self._supervisor, daemon=True)
        self.wd_t = threading.Thread(target=self._watchdog, daemon=True)
        self.sup_t.start()
        self.wd_t.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        set_proxy("off")
        if self.proc and self.proc.poll() is None:
            kill_tree(self.proc.pid)
        time.sleep(1)
        log(f"已收摊：代理关闭，直连{'正常' if _net_ok() else '异常(跑一下 修复网络.bat)'}")


def _net_ok():
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request("https://www.baidu.com", method="HEAD")
        with op.open(req, timeout=8):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------- 网络
def http_get(url, rng=None, timeout=60):
    headers = {"User-Agent": "Mozilla/5.0"}
    if rng:
        headers["Range"] = rng
    req = urllib.request.Request(url, headers=headers)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return op.open(req, timeout=timeout)


# ---------------------------------------------------------------- ffprobe
def probe(path):
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries",
             "stream=codec_type,width,height", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
        j = json.loads(r.stdout)
        v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
        a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
        if not v:
            return None
        return {
            "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0),
            "has_audio": a is not None,
            "duration": float(j.get("format", {}).get("duration") or 0),
        }
    except Exception:
        return None


# ---------------------------------------------------------------- 变体嗅探/下载
def is_ftyp(data):
    return len(data) > 12 and data[4:8] == b"ftyp"


def sniff(m, tag):
    """下载 12MB 前缀→解密→ffprobe，返回变体真实信息；失败返回 None"""
    url = m["url"] + m["url_token"]
    try:
        with http_get(url, f"bytes=0-{SNIFF - 1}", timeout=60) as r:
            data = bytearray(r.read())
    except Exception:
        return None
    ks = keystream(int(m["decode_key"]), min(ENC_PREFIX, len(data)))
    head = bytes(a ^ b for a, b in zip(data[:len(ks)], ks)) + bytes(data[len(ks):])
    if not is_ftyp(head):
        return None
    p = os.path.join(TMPDIR, f"sniff-{tag}.mp4")
    with open(p, "wb") as f:
        f.write(head)
    info = probe(p)
    os.remove(p)
    return info


def download_full(m, dest):
    """Range 续传下载到 dest，完成后原地解密前 128KB"""
    url = m["url"] + m["url_token"]
    key = int(m["decode_key"])
    with http_get(url, "bytes=0-0", timeout=30) as r:
        total = int(r.headers.get("Content-Range", "x/x").split("/")[-1])
    # 续传安全：残留的半成品必须同 key 同总长，否则弃用（防止变体混拼）
    meta_p = dest + ".meta"
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if have:
        try:
            old_meta = json.load(open(meta_p, encoding="utf-8"))
        except Exception:
            old_meta = {}
        if old_meta.get("key") != key or old_meta.get("total") != total:
            os.remove(dest)
            have = 0
    with open(meta_p, "w", encoding="utf-8") as f:
        json.dump({"key": key, "total": total}, f)
    t0 = time.time()
    last_log = 0
    while have < total:
        end = min(have + CHUNK - 1, total - 1)
        try:
            with http_get(url, f"bytes={have}-{end}", timeout=120) as r:
                chunk = r.read()
        except Exception:
            time.sleep(3)
            continue
        if not chunk:
            time.sleep(3)
            continue
        with open(dest, "ab") as f:
            f.write(chunk)
        have += len(chunk)
        if have - last_log >= 64 * 1024 * 1024 or have == total:
            spd = have / 1048576 / max(time.time() - t0, 0.1)
            log(f"    下载 {have/1048576:.0f}/{total/1048576:.0f}MB ({spd:.0f}MB/s)")
            last_log = have
    with open(dest, "r+b") as f:
        head = f.read(ENC_PREFIX)
        ks = keystream(key, min(ENC_PREFIX, len(head)))
        f.seek(0)
        f.write(bytes(a ^ b for a, b in zip(head, ks)))
    try:
        os.remove(meta_p)
    except OSError:
        pass
    return total


# ---------------------------------------------------------------- 归档
def load_index():
    if os.path.exists(INDEX):
        try:
            return json.load(open(INDEX, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_index(idx):
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)


def next_name(date):
    n = 1
    while os.path.exists(os.path.join(ARCHIVE, f"{date}_{n}.mp4")):
        n += 1
    return f"{date}_{n}.mp4"


def process_object(obj, idx, state):
    oid = obj["object"].get("id") or "?"
    title = (obj["object"].get("title") or "").replace("\n", " ")[:40]
    date = beijing_date(obj["object"].get("createtime"))
    medias = obj["media"]
    if not any(m.get("decode_key") for m in medias):
        log(f"  跳过《{title}》：无 decode_key（直播回放暂不支持）")
        return
    if OFFLINE:
        log(f"  [离线] 《{title}》 {len(medias)} 条变体，嗅探/下载跳过")
        return

    # 逐变体嗅探
    cands = []
    for i, m in enumerate(medias):
        if not m.get("decode_key") or not m.get("url_token"):
            continue
        info = sniff(m, f"{oid}-{i}")
        if info:
            cands.append((m, info))
            log(f"    变体{i}: {info['width']}x{info['height']} "
                f"{'含音轨' if info['has_audio'] else '无音轨'} "
                f"时长{int(info['duration'])}s")
        else:
            log(f"    变体{i}: 嗅探失败，忽略")
    if not cands:
        log(f"  ! 《{title}》无可下载变体")
        return

    # 择优：有音轨 > 像素数
    cands.sort(key=lambda c: (c[1]["has_audio"], c[1]["width"] * c[1]["height"]), reverse=True)
    best_m, best = cands[0]
    pixels = best["width"] * best["height"]

    old = idx.get(oid)
    if old:
        old_px = int(old.get("width", 0)) * int(old.get("height", 0))
        if old.get("file") and pixels <= old_px * 1.05:
            log(f"  跳过《{title}》：已归档 {old['file']}（{old['width']}x{old['height']}）")
            return
        log(f"  ↑ 发现更清晰版本（{best['width']}x{best['height']} > "
            f"{old.get('width')}x{old.get('height')}），升级替换")

    # 下载 + 校验
    tmp = os.path.join(TMPDIR, f"{oid}.mp4")
    log(f"  开始下载《{title}》 {best['width']}x{best['height']} "
        f"{int(best['duration'])//60}分{int(best['duration'])%60}秒")
    state["active"] += 1
    try:
        download_full(best_m, tmp)
        full = probe(tmp)
        play_len = int(next((m.get("video_play_len") or 0) for m in medias) or 0)
        if not full or not full["has_audio"]:
            log(f"  ! 校验失败（ffprobe={'无' if not full else '缺音轨'}），暂存 下载中/，下次重试")
            return
        if play_len and abs(full["duration"] - play_len) > 5:
            log(f"  ! 时长不符（文件 {int(full['duration'])}s vs 元数据 {play_len}s），暂存待查")
            return
        name = old["file"] if old and old.get("file") else next_name(date)
        dest = os.path.join(ARCHIVE, name)
        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(tmp, dest)
        idx[oid] = {
            "file": name, "title": title, "date": date,
            "createtime": obj["object"].get("createtime"),
            "nickname": obj["object"].get("nickname"),
            "width": best["width"], "height": best["height"],
            "duration": int(best["duration"]),
            "decode_key": best_m["decode_key"],
            "archived_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_index(idx)
        log(f"  ✅ 已归档 归档\\{name}")
    except Exception as e:
        log(f"  ! 下载失败：{e}（暂存 下载中/，下次重试）")
    finally:
        state["active"] -= 1


# ---------------------------------------------------------------- 主循环
def iter_records(state):
    """增量读取 records.jsonl，yield 合法 v3 记录"""
    while True:
        if not os.path.exists(RECORDS):
            yield None
            continue
        with open(RECORDS, encoding="utf-8") as f:
            f.seek(state["off"])
            lines = f.readlines()
            state["off"] = f.tell()
        for line in lines:
            line = line.strip()
            if not line or '"k":"video3"' not in line and '"k": "video3"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("k") == "video3" and o.get("media") and o.get("object"):
                state["last_record"] = time.time()
                yield o
        yield None


def main():
    # 真控制台走 WriteConsoleW（Unicode 原生，无需设置）；重定向/管道时用 UTF-8 落盘
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(ARCHIVE, exist_ok=True)
    os.makedirs(TMPDIR, exist_ok=True)
    idx = load_index()
    state = {"off": 0, "active": 0, "last_record": time.time()}
    done = set()

    log("=" * 56)
    log("视频号每周下载 — 生产版 v1")
    log(f"归档目录：{ARCHIVE}（已收录 {len(idx)} 条）")
    if DRY:
        log("[dry 模式] 不启动代理/mitmdump，仅处理现有 records")

    started = time.time()
    proxy = None
    try:
        if not DRY:
            proxy = ProxySession()
            proxy.__enter__()  # 启动 mitmdump + 开代理 + 自愈线程（finally 里 __exit__ 收摊）
            log("")
            log(">>> 现在请操作：打开电脑微信 → 视频号 → 朋友的主页，下拉刷新 <<<")
            log(">>> 发现新视频会自动下载；全部完成后按 Ctrl+C 收摊            <<<")
            log("")
        it = iter_records(state)
        while True:
            o = next(it)
            if o is not None:
                oid = o["object"].get("id")
                # 按 (oid, key) 去重：同一对象不同会话可能分到不同清晰度的变体，
                # 新变体要重新评估（可能触发升级替换）
                sig = (oid, tuple(sorted(m.get("decode_key") for m in o["media"])))
                if sig in done:
                    continue
                if oid:
                    done.add(sig)
                title = (o["object"].get("title") or "").replace("\n", " ")[:40]
                log(f"发现视频记录：《{title}》 {beijing_date(o['object'].get('createtime'))} "
                    f"({len(o['media'])} 条变体)")
                process_object(o, idx, state)
                continue
            # 无新记录
            if proxy and proxy.dead_reason:
                log(f"! 安全退出：{proxy.dead_reason}")
                break
            if DRY:
                log("[dry] records 处理完毕，退出")
                break
            if state["active"] == 0 and time.time() - state["last_record"] > IDLE_EXIT:
                log(f"{IDLE_EXIT//60} 分钟无新视频且无下载任务，自动收摊")
                break
            if time.time() - started > HARD_EXIT:
                log(f"已达最长运行 {HARD_EXIT//60} 分钟，自动收摊")
                break
            time.sleep(2)
    except KeyboardInterrupt:
        log("收到退出指令，正在恢复网络…")
    finally:
        if proxy:
            proxy.__exit__()
        else:
            set_proxy("off")
    log("本次运行结束。")


if __name__ == "__main__":
    main()
