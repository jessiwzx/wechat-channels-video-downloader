# 微信视频号视频下载（wechat-channels-video-downloader）

> 一个 Windows 上的个人小工具：打开你**自己微信里能看到**的视频号主页，刷一下，自动把新视频下载、解密、校验、归档到本地。
> 不用录屏、不用第三方下载站、不用手点。

## ⚠️ 免责声明（请先读）

本项目**仅供个人备份、学习与研究使用**。

- 它只作用于**你本人微信账号本来就能正常观看**的内容，不绕过任何账号权限、不做付费/私密内容获取。
- 请勿用于批量抓取、二次分发、商业用途或任何侵犯他人著作权/隐私权的场景，由此产生的一切后果由使用者自行承担。
- 视频版权归原作者所有。下载的文件请仅限自己观看，不要传播。
- 原理涉及对本地客户端自身流量的抓取与解密，可能违反平台《用户协议》，请自行评估风险。

## 它能做什么

- 监听微信 PC 端视频号页面，自动捕获视频清单（含多个清晰度变体）
- 自动挑选最优变体（有音轨优先 > 分辨率更高优先）
- 8MB 分块断点续传，下完自动解密、用 ffprobe 校验真实性（分辨率、音轨、时长）
- 按发布时间归档为 `归档/YYYY-MM-DD_序号.mp4`
- 同一视频后续拿到更高清版本时，自动升级替换
- 支持 `--dry` / `--offline` 离线试跑，不联网也能验证逻辑

## 工作原理

```
微信 PC 端 channels.weixin.qq.com 页面
   │
   ├─ src/capture_addon.py（mitmdump addon，:8899）
   │     剥离 CSP + 往页面 <head> 注入探针
   │
   ├─ src/probe.js（页内探针）
   │     hook WeixinJSBridge.invoke("finderH5ExtTransfer")
   │     解析 resp_json → 递归找 object_desc.media[]
   │     按对象 id 去重 → POST /__probe_sink
   │
   ├─ 落盘 records.jsonl（addon ↔ orchestrator 的唯一 IPC 通道）
   │
   └─ src/orchestrator.py
         增量 tail records.jsonl
         → 逐变体嗅探（Range 拉 12MB 前缀 → 解密 → ffprobe 探真实分辨率）
         → 择优 → 分块续传整文件 → 原地解密前 128KB
         → 校验（有音轨 + 时长误差 ±5s）→ 归档 → 写 index.json
```

### 两个关键点（不了解会踩坑）

1. **配对规则**：`encfilekey` 是逻辑文件 id，`url_token` 才决定 CDN 给你哪个清晰度变体。
   必须用 `media[i].url + media[i] 自己的 url_token` 去配 `media[i].decode_key`。
   播放器选中的变体 token ≠ `media[0]` 的 key —— 这是最容易导致解密失败的地方。
2. **加密范围**：ISAAC-64 XOR 密钥流**只覆盖每个文件的前 131072 字节**，其余是明文。
   种子 = `decode_key` 的 uint64 值。`src/isaac64.py` 是逐个移位常数（21/5/12/33）移植的
   实现，已与官方 WASM 做过字节级对拍。

## 目录结构

```
.
├── 每周下载.bat            # 用户入口：启动看门狗 + orchestrator，退出后强制关代理
├── 修复网络.bat            # 断网兜底：杀 mitmdump + 关系统代理 + 连通性检测
├── 使用说明.md             # 面向普通用户的手册
├── CLAUDE.md               # 面向开发者的架构说明与硬性技术约束
├── src/                    # 生产代码
│   ├── orchestrator.py     # 总控：代理生命周期 + 监听 + 嗅探 + 下载 + 归档
│   ├── capture_addon.py    # mitmdump addon：剥 CSP、注入探针、收记录
│   ├── probe.js            # 页内探针 v3
│   ├── isaac64.py          # ISAAC-64 密钥流（解密用）
│   ├── set_proxy.ps1       # 系统代理开关（HKCU 注册表 + WinINET 刷新）
│   ├── watchdog.ps1        # 外置看门狗：端口死了自动关代理
│   └── bin/                # ffmpeg.exe / ffprobe.exe（不入库，见下）
└── spike/                  # 早期取证实验（已冻结，仅作技术参考）
    └── SPIKE_REPORT.md     # 逆向结论汇总，想搞懂原理看这份
```

运行时才会生成、且**已被 `.gitignore` 排除**的：`归档/`（视频成品）、`下载中/`（临时分片）、
`records.jsonl`（含真实 url_token / decode_key）、`归档/index.json`（去重记录）。

> `spike/` 原始取证数据（2.8GB 的 flow 抓包、媒体分片、日志）不随仓库分发，只保留代码与结论报告。

## 快速开始

### 环境要求

- Windows（依赖注册表代理开关与 `WriteConsoleW`，未做跨平台适配）
- Python 3.12（`每周下载.bat` 优先找 `%LOCALAPPDATA%\Programs\Python\Python312`，找不到则用 PATH 里的 `python`）
- [mitmproxy](https://mitmproxy.org/)（`mitmdump` 需在 PATH 或 Python Scripts 目录）
- ffmpeg / ffprobe：**本仓库不含二进制**，请自行下载后放到 `src/bin/ffmpeg.exe` 与 `src/bin/ffprobe.exe`
- mitmproxy CA 证书需装进系统信任区（一次性）

### 使用

1. 双击 `每周下载.bat`，窗口显示「系统代理已开启」
2. 打开微信 → 视频号 → 进入目标主页 → 下拉刷新
3. 看到「发现视频记录」后它会自动完成嗅探→下载→解密→校验→归档
4. 下完按 `Ctrl+C` 或直接关窗口，代理会自动关闭

忘了关也没事：20 分钟无新记录自动收摊，最长 45 分钟强制收摊。

### 调试

```bash
python src/orchestrator.py --dry       # 不起代理，把现有 records.jsonl 处理一遍
python src/orchestrator.py --offline   # 不联网，只打印决策
```

## 安全设计（这几层是有事故教训的）

曾有 mitmdump 后台进程被系统回收、导致系统代理悬挂、断网约 7 小时的记录，因此有四层保护：

1. orchestrator 内 supervisor 线程：mitmdump 崩溃自动重启，超过 5 次安全退出
2. orchestrator 内 watchdog 线程：端口 8899 连续 30s 无监听 → 安全退出
3. 外置 `src/watchdog.ps1`：独立最小化窗口，主程序死了它还活着，同样条件直接关代理
4. `每周下载.bat` 在 orchestrator 退出后无条件再关一次代理

流量边界：只对 `channels.weixin.qq.com` 的 HTML 响应剥 CSP 并注入探针，其余流量纯透传、不解密、不落盘；
视频下载走直连（显式绕过系统代理），不经过 mitmproxy。

真断网了：双击 `修复网络.bat`。

## 已知限制

- 目前稳定拿到的是 720p 自包含 MP4（音画齐全）。1080p 变体在 `spec` 字段里，探针已完整记录，攒到样本后可升级
- 直播回放不支持（没有 `decode_key`）
- 下载链接有效期约 2 天（`url_valid_duration = 172800s`），所以必须捕获当次当场下载
- 只适配微信 PC 端页面结构；微信改版可能让探针失效

## 相关项目与致谢

- ISAAC-64 解密种子推导参考了 [nobiyou/wx_channel](https://github.com/nobiyou/wx_channel) 的 Go 实现
- 代理与注入基于 [mitmproxy](https://github.com/mitmproxy/mitmproxy)
