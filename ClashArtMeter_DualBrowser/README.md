# Clash Art Meter · Edge + Chrome 双浏览器版（v2）

适用于 **Clash for Windows / Clash Verge Rev / Mihomo** 的 Windows 桌面悬浮窗，按域名筛选 ChatGPT 流量，并尽可能将 **Edge** 和 **Chrome** 的 ChatGPT 连接分别累计。保留「开始作图 → 结束并保存」会话、上/下行实时速度、历史记录和迷你置顶模式。

![双浏览器悬浮窗界面（模拟测试数据）](preview.png)

**重要：这是估算工具，不是浏览器 DevTools 精确流量计费工具。**

- 从本机 Clash/Mihomo 的只读 `/connections` API 获取活跃连接快照，每秒采样；仅统计符合域名的连接。
- 尝试利用 Clash 提供的 `process` / `processPath` 区分 `chrome.exe`、`msedge.exe`。经典 Clash for Windows 无进程信息时，Windows 上还会尝试通过本机已建立的 TCP 连接的源端口识别浏览器进程。
- 无法识别归属的 ChatGPT 域名连接显示为 **「未识别浏览器」**，不会强行算入 Edge 或 Chrome。三栏合计就是本次 **可观测到的匹配流量**。
- **不是**浏览器标签页级监控：同域名的普通聊天、图片生成、上传图片和其他 OpenAI 请求会一并计入；IP-only、未匹配的 CDN、经过直连未进入 Clash 的请求不会计入；极短连接、关闭前最后的字节、采样间隔可能漏算。
- 这是代理核心观测到的字节数，不包含机场倍率/加密开销等，不能等同实际套餐计费量。

## 1. 最简单的 Windows 使用步骤

1. 解压整个 ZIP，进入 **`ClashArtMeter_DualBrowser`** 文件夹。**不要在压缩包内部直接运行。**
2. 确保 Clash for Windows 已启动，且 ChatGPT 浏览器请求实际通过 Clash。
3. 已安装 Python 3.11+ 的电脑，直接双击 **`start_windows.bat`**。它会在项目文件夹运行程序，不必手动输入 `cd` 或 `py app.py`。也可以打开本文件夹的 CMD，执行 `py app.py`。
4. 如果没安装 Python，可将项目上传 GitHub 并用 Actions 构建 Windows EXE，见下文。
5. 点击悬浮窗右上角 **⚙**；API 地址填写你在原版中已经连通的地址，例如 `http://127.0.0.1:61311`（**示例端口，不保证重启后仍是此端口**）；API Secret 继续使用原来的值。
6. **统计范围选「Edge + Chrome 的 ChatGPT」**，域名保持默认，点击「保存并连接」。
7. 两个浏览器同时作图前，点击「开始作图」；完成后点击「结束并保存」。右键悬浮窗可看历史记录。

**升级不需要重新查 Secret。** 软件仍使用 `%LOCALAPPDATA%\ClashArtMeter\settings.json` 和 `history.sqlite3`：v1 的端口、Secret 和历史记录会原样保留；旧设置第一次升级时自动切换到新的双浏览器模式。建议先退出旧版，**不要同时运行两个版本**。首次升级不会删除旧记录。

## 2. 如何判断是否真的分开了？

悬浮窗四项数字说明：

| 指标 | 含义 |
| --- | --- |
| 本次作图合计 | 本时段内匹配 ChatGPT 域名的连接字节增量（估算） |
| Edge · ChatGPT | 有明确 Edge 进程归属的匹配流量 |
| Chrome · ChatGPT | 有明确 Chrome 进程归属的匹配流量 |
| 未识别浏览器 | 域名匹配，但是没有足够的证据判断哪个浏览器发起 |
| 总速 ↓ / ↑ | 当前符合域名筛选的每秒字节增量，**不是**全部 Clash 速度 |

在 Edge/Chrome 打开 `chatgpt.com`，加载页面并下载图片，观察两个数值。如果「未识别浏览器」明显增加，但 Edge/Chrome 一直是 0，说明当前 CFW 的进程元数据及 Windows TCP 归属不能充分识别你的连接；**程序不会伪造两浏览器数据**。仍可使用三栏合计做估算统计。

默认域名：

```text
chatgpt.com, openai.com, oaiusercontent.com, oaistatic.com
```

域名匹配为完整域名/子域名，不是简单的字符串包含。例如 `evilchatgpt.com` 不会被计入。可以根据真实网络连接增删域名，**不要把所有 CDN 都当成 ChatGPT 的专用流量**。

## 3. 不同统计模式

- **Edge + Chrome 的 ChatGPT（默认）**：只统计筛选域名，尝试按浏览器归属，未识别单独显示。
- **指定域名**：只计入符合域名的连接，不分浏览器。
- **全部 Clash 流量**：内核全局累计计数器（包含其他软件、TikTok、其他网页的 Clash 流量）。
- **指定程序**：按 API 中的进程名筛选；可能不完整。

两种筛选模式的速度均由过滤后的连接字节增量计算，不使用整体 Clash 网速冒充过滤网速。历史按会话存储，每个历史条目也能看到 Edge、Chrome、未识别、上传、下载及总量。

## 4. 创建 GitHub 仓库并生成 EXE

把解压后 `ClashArtMeter_DualBrowser` **文件夹里面的内容**上传到新 GitHub 仓库根目录（包含隐藏的 `.github/workflows`）。

1. GitHub → New repository → 创建仓库。
2. **Add file → Upload files**：上传项目里的全部源码及目录，提交到 `main`。
3. 进入 **Actions → Build Windows EXE → Run workflow**。
4. 构建完成后进入该次运行的 **Artifacts**，下载 `ClashArtMeter-DualBrowser-Windows-x64`。
5. 解压得到 **`ClashArtMeterDual.exe`**，双击使用即可。EXE 不要求安装 Python。

该 EXE 使用 GitHub 的 Windows 构建环境自动生成，**本工作环境无法实际验证原生 Windows EXE**。新生成的无签名 EXE 可能触发 SmartScreen 提示，请仅在确认项目源码及构建来源可信后使用。

本机也可运行 `scripts\build_windows.bat`，生成 `dist\ClashArtMeterDual.exe`。

## 5. Clash for Windows 连接 API

1. 确认本地控制器的地址（**不是 7890/7897 代理端口**）。
2. 如果访问 `http://127.0.0.1:你的端口/version` 返回 `{"message":"Unauthorized"}`，说明该端口已响应、但需 API Secret。找到本机 Clash 配置中 `secret:` 的值，填入软件设置；**不要分享 Secret、订阅地址或敏感配置**。
3. 如果开启了随机控制端口，CFW 重启后端口可能改变；以当前软件显示的 API 地址为准，必要时重新检查。
4. 程序只接收 `http://127.0.0.1:端口`、`http://localhost:端口`、`http://[::1]:端口` 形式的本机控制器地址。不要开放外部控制器到公网。

## 6. 隐私和安全

- 只读访问本地 `/connections` 接口；不会修改 Clash 配置、节点或代理路由，也不会读取浏览器 Cookie、登录凭证、聊天正文或图片内容。
- Windows TCP 后备归属只读取本机 TCP 连接表及进程可执行文件名（如果可读）。
- 本地设置、Secret 及历史数据库保存在 `%LOCALAPPDATA%\ClashArtMeter\`，**不会包含在 GitHub 源码 ZIP 中**。
- **Secret 保存在本机 settings.json 中（明文）**，注意本机安全，不要上传、分享该文件。所有统计都仅存本机 SQLite，无在线云同步。

## 7. 开发和测试

```powershell
py -m unittest discover -s tests -v
py app.py
```

纯 Python 标准库（Tkinter + SQLite + ctypes）；需要 Windows EXE 时用 PyInstaller 打包。包含 13 项自动化测试及 Windows GitHub Actions 构建流程。

## 代码结构

```text
app.py                          启动入口
start_windows.bat               Windows 双击启动源码
clash_meter/core.py             过滤、双浏览器归属、流量增量/速度
clash_meter/winports.py         Windows TCP 端口→浏览器进程后备归属
clash_meter/monitor.py          本地 Clash API 请求 + 每秒采样
clash_meter/config.py           配置验证及兼容升级
clash_meter/storage.py          SQLite 历史与旧数据迁移
clash_meter/ui.py               桌面悬浮窗、设置和历史
.github/workflows/              GitHub Windows 自动构建
scripts/build_windows.bat       Windows 本地打包
resources/                      图标
```

License: MIT.
