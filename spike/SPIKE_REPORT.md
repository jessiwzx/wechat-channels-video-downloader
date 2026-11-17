# Spike 结论报告：视频号视频自动获取 — 解密链路验证

日期：2026-08-17　状态：**全线打通，成品已产出**

## 结论

端到端链路 100% 验证成功：**mitmproxy 注入探针 → 抓取 feed 数据（url + url_token + decode_key）→ Range 下载 → Python ISAAC-64 解密前 128KB → 完整可播放 MP4**。

成品：
- `归档/2025-08-23_1.mp4` — 长视频 1:59:14，720p，h264+aac（自带音轨）
- `归档/2024-12-08_1.mp4` — 短视频 9:42（意外捞到的另一条，验证了管线通用性）

## 核心技术事实（生产版必须遵守）

1. **配对规则（本次最大发现）**：`encfilekey` 是逻辑文件 id，`url_token` 决定 CDN 给哪个变体。
   必须用 **`media[i].url + media[i] 自己的 url_token`** 配 `media[i].decode_key`。
   播放器选中的变体 token ≠ media[0] 的 key（这就是前期解密失败的根因）。

2. **media[0] 是自带音轨的完整 MP4**：直接下载即成品，**无需** ffmpeg 合流。
   分离音轨（hy=SZ 文件）只是播放器 MSE 流式架构用的，下载管线不需要。
   注意：media[0] 实际拿到的是 720p 变体；1080p 变体在 `spec` 数组里（探针 v2 把嵌套对象
   打成了 "[object Object]"，生产版要用 JSON.stringify 修复才能拿到高清变体 url）。

3. **加密细节**：ISAAC-64 XOR 流覆盖**每个文件的前 131072 字节**（128KB），其余明文。
   种子 = `decode_key` 的 uint64 十进制串。密钥流取法与官方 WASM
   （`WxIsaac64`，decrypt-video-core 1.3.0）字节级一致（已用 Node 跑官方 WASM 对拍验证）。
   Python 实现：`spike/isaac64.py`（含 Bob Jenkins 官方测试向量自检）。

4. **数据通道**：桌面微信 视频号 页面壳 `/web/pages/feed|profile`（每次打开 200 新取），
   数据走 `WeixinJSBridge.invoke("finderH5ExtTransfer", ...)` → `resp.jsapi_resp.resp_json`
   → `object.object_desc.media[]`。关键字段：url、url_token（顶层、完整不截断）、
   decode_key、file_size、md5sum、video_play_len；对象级：createtime（归档日期用）、
   nickname、object_nonce_id。URL 有效期 `url_valid_duration` = 172800s（2 天）。

5. **下载**：finder.video.qq.com 支持 HTTP Range（206），8MB 分块续传实测 ~10MB/s，
   1.7GB 约 3 分钟。重试 + 续传已验证。

6. **直播回放没有 decode_key（为空）**——直播内容流式加密不同，本期不做。

## 安全面

- 仅解密 *.qq.com / *.qpic.cn / *.wechat.com（config.yaml allow_hosts 白名单），其余流量透传不动
- 系统代理异常自愈：supervisor（mitmdump 崩溃自动重启×5）+ watchdog（8899 端口死 30s → 自动关代理）
- `代理关闭.bat` 兜底随时可用；mitm CA 证书可随时移除
- **事故复盘**：曾发生一次 mitmdump 后台进程被系统回收导致断网 ~7 小时未察觉。已用上述双层自愈修复，
  生产版必须内置同样机制且把状态写到用户可见的日志窗口

## 生产版待办（下一步）

1. 探针修复：嵌套对象（spec/hdr_spec/hls_spec/media_cdn_info）用 JSON.stringify 全量保留 → 支持 1080p
2. 抓取 addon 自动化：检测到新视频 → 自动下载+解密 → `归档/YYYY-MM-DD_序号.mp4`
   （序号按同日第几条；日期取 createtime 本地时区）
3. `每周下载.bat` 一键流程：开代理 → 等用户刷目标主页 → 自动抓新 → 关代理
   （supervisor/watchdog 内置，窗口里显示进度）
4. `修复网络.bat` 保留；md5sum 校验落地；文档

## 关键文件

- `spike/full_pipeline.py` — 收集→下载→解密 全流程（生产版蓝本）
- `spike/isaac64.py` — ISAAC-64 精确移植（Go 原版语义）
- `spike/probe.js` v2 — 页内探针（addon 注入）
- `spike/capture5_addon.py` — mitmdump addon（CSP 剥离 + 注入 + /__probe_sink 收集）
- `spike/run_wasm.js` — 官方 WASM 对拍工具（ground truth）
- `spike/supervisor.ps1` / `watchdog.ps1` — 自愈层
- `spike/download/` — 解密后成品 + meta.json（大体积取证数据不入库，见 README）
