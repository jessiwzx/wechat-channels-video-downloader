# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Windows 个人工具：自动下载并归档电脑版微信「视频号」中朋友主页的视频。链路：mitmproxy 本地代理 → 向视频号页面壳注入探针 JS → 钩住 WeixinJSBridge 抓元数据（url / url_token / decode_key）→ 直连 Range 下载 → ISAAC-64 解密前 128KB → ffprobe 校验 → 归档为 `归档/YYYY-MM-DD_序号.mp4`。

- `src/` = 生产代码；`spike/` = 已完结的取证实验（冻结、仅作参考，不要在其上继续开发；技术结论见 `spike/SPIKE_REPORT.md`，生产版蓝本 `spike/full_pipeline.py`）
- 无 git、无测试框架、无 linter；验证靠 `--dry` / `--offline` 模式 + 实跑
- `使用说明.md` 是给用户看的手册，改了用户可见行为要同步更新它

## 常用命令

```
每周下载.bat                            # 用户入口（外置 watchdog + orchestrator + 退出后强制关代理）
python src/orchestrator.py             # 等价正常流程：起 mitmdump + 开系统代理 + 主循环
python src/orchestrator.py --dry       # 不起代理/mitmdump，把现有 records.jsonl 处理一遍后退出
python src/orchestrator.py --offline   # --dry 且不真正下载，只打印决策（离线测试）
修复网络.bat                            # 杀 mitmdump + 关系统代理 + curl 检测（断网兜底）
```

依赖：Python 3.12（bat 优先找 `%LOCALAPPDATA%\Programs\Python\Python312`）、mitmproxy（`mitmdump` 在 PATH 或 Python Scripts 目录）、ffmpeg/ffprobe 已随仓库放在 `src/bin/`、mitmproxy CA 证书需已装入系统（一次性）。

## 架构：数据流

```
微信页面壳 channels.weixin.qq.com /web/pages/*
  → src/capture_addon.py（mitmdump addon，端口 8899）：剥 CSP + 在 <head> 后注入 probe.js
  → src/probe.js（探针 v3）：hook WeixinJSBridge.invoke("finderH5ExtTransfer")，
      解析 resp.jsapi_resp.resp_json，递归找 object_desc.media[]，
      按对象 id 去重后 POST /__probe_sink
  → capture_addon 落盘 <ROOT>/records.jsonl（每行一个 {"k":"video3",...}）
  → src/orchestrator.py：增量 tail records.jsonl（state["off"] 文件偏移），
      会话内按 (oid, decode_key 集合) 去重 —— 同对象不同会话可能分到不同清晰度变体
  → process_object：逐 media 变体嗅探（Range 拉 12MB 前缀 → 解密 → ffprobe 真实分辨率/音轨）
      → 择优（有音轨 > 像素数）→ 8MB 分块续传整文件 → 原地解密前 128KB
      → 校验（ffprobe 有音轨；时长 vs video_play_len ±5s）→ 归档 + 写 index.json
```

records.jsonl 是 addon→orchestrator 的唯一 IPC 通道，schema 由 probe.js v3 决定：嵌套对象（spec/hdr_spec/hls_spec/codec_info/media_cdn_info）已 JSON.stringify 成字符串（v2 曾打成 "[object Object]" 丢失变体清单，这是教训）。改探针时保持该约定。

## 必须遵守的技术事实（违反会复现 spike 期的解密失败）

1. **配对规则**：encfilekey 是逻辑文件 id，url_token 决定 CDN 给哪个变体。必须用 `media[i].url + media[i] 自己的 url_token` 配 `media[i].decode_key`；播放器选中的变体 token ≠ media[0] 的 key。
2. **加密**：ISAAC-64 XOR 流只覆盖每个文件前 131072 字节（`ENC_PREFIX`），其余明文；种子 = decode_key 的 uint64 值。`src/isaac64.py` 逐行移植自 nobiyou/wx_channel 的 Go 实现（减法型 Jenkins mix、移位常数 21/5/12/33、从 Seed[255] 倒序消费），已与官方 WASM 字节级对拍。嗅探前缀取 12MB（`SNIFF`）是因为实测 moov 最大 9.4MB。
3. **media[0] 是自带音轨的完整 MP4**（当前拿到 720p），无需 ffmpeg 合流；1080p 变体在 `spec` 字段里。变体择优在 orchestrator 嗅探阶段做，不在探针里做。
4. **下载 URL 有效期约 2 天**（url_valid_duration=172800s）→ 捕获当次必须当场下载。直播回放无 decode_key → 跳过。
5. **续传安全**：半成品 `下载中/*.mp4.meta` 记 `{key,total}`；残留文件 key 或 total 不符必须弃用重下（防不同变体混拼）。

## 防断网（改动任何代理/进程逻辑前先读这段）

历史上发生过 mitmdump 后台进程被系统回收导致用户断网约 7 小时。现有四层保护，新改动不得削弱：

1. orchestrator 内 supervisor 线程：mitmdump 崩溃自动重启，超过 5 次设 dead_reason 安全退出
2. orchestrator 内 watchdog 线程：端口 8899 连续 30s 无监听 → 安全退出
3. 外置 `src/watchdog.ps1`（bat 在 python 之前启动、独立最小化窗口）：同样条件直接关系统代理——主程序死了它也活着
4. `每周下载.bat` 在 orchestrator 退出后无条件再关一次代理

`ProxySession.__exit__` 与 `main` 的 finally 都会 `set_proxy("off")`，删改这些路径需极其谨慎。

## 安全边界

- 只对 channels.weixin.qq.com 的 HTML 响应剥 CSP 并注入探针；其余流量纯透传，不解密、不记录、不存媒体分片。
- 视频下载走直连：`http_get` 用空 ProxyHandler 显式绕过系统代理，不经过 mitmproxy。
- `records.jsonl` / `src/capture_log.jsonl` / `归档/index.json` 含真实 url_token 与 decode_key，不要外发。

## Windows / 编码约定

- `.bat` 与 `.ps1` 保持 ASCII-only（PS 5.1 无 BOM 按 GBK 解析）；bat 里不要加 chcp（已知 cmd 偏移 bug，`每周下载.bat` 顶部注释有说明）。orchestrator 输出中文：真控制台走 WriteConsoleW，重定向时 reconfigure 为 UTF-8。
- 路径含中文与空格（项目根目录名即中文）；subprocess 一律传 list 参数 + 绝对路径。
- 系统代理开关走 `src/set_proxy.ps1`（HKCU 注册表 + InternetSetOption 通知 WinINET 刷新），用户级、无需管理员。

## 归档与去重

- `归档/index.json` 按对象 id 记录已归档条目（file/title/分辨率/decode_key/archived_at），是去重依据，勿删。
- 同对象发现更高清变体（像素 > 已归档 ×1.05）→ 原地替换同名文件升级。
- 归档名日期 = createtime 的北京时间（UTC+8），序号 = 同日第几条。
- 自动收摊条件：20 分钟无新记录且无下载（`IDLE_EXIT`）/ 运行满 45 分钟（`HARD_EXIT`）。
