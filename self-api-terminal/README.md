# 自用 API 终端

> 一个 Windows 桌面端的 OpenAI 兼容聊天客户端：原生 Qt 窗口、进程内直连 API、数据全部留在本机。

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.12-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-TBD-lightgrey)

`#desktop` `#llm` `#openai-compatible` `#pyside6` `#llama-cpp` `#local-first`

<!-- 发布前把上面 License 换成你选的协议，并把下面的 OWNER/REPO 换成真实仓库路径 -->
<!-- ![stars](https://img.shields.io/github/stars/OWNER/REPO?style=social) -->

**中文** | [English](#english)

---

## 目录

- [它是什么](#它是什么)
- [界面](#界面)
- [功能](#功能)
- [快速开始](#快速开始)
- [连接哪些服务](#连接哪些服务)
- [使用技巧](#使用技巧)
- [数据与隐私](#数据与隐私)
- [技术栈与结构](#技术栈与结构)
- [开发](#开发)
- [路线图](#路线图)
- [已知限制](#已知限制)
- [常见问题](#常见问题)
- [License](#license)

---

## 它是什么

一个「自己用的」聊天客户端。最早是一个单文件网页（浏览器里跑），后来改成原生桌面程序：

- **不套浏览器外壳**：PySide6 画的界面，不是 Electron / WebView
- **进程内直连**：请求由程序自己发出，没有 CORS、没有本地反向代理，看到 `Origin` 就 403 的本地服务也能用
- **本地优先**：配置、聊天记录、附件都在 `%LOCALAPPDATA%`，不经过任何第三方
- **面向本地模型**：会读 llama.cpp 的 `/props` 自动拿上下文长度，超限前先提醒你清理历史

## 界面

![界面截图](docs/screenshot.png)

## 功能

### 对话

| | |
|---|---|
| 流式输出 | 边生成边渲染，可随时停止，已收到的内容保留 |
| 推理过程 | 识别 `reasoning_content` / `reasoning` / `thinking`，折叠显示，可开关 |
| 工具调用 | 内置计算器、当前时间、抓网页；最多 5 轮，防死循环 |
| Markdown | 标题、粗斜体、删除线、行内代码、代码高亮、引用、表格、链接、列表 |
| 消息操作 | 复制、复制代码、朗读、重新生成、继续（并回原回答）、右键编辑重发 / 删除及之后 |
| 统计 | 每条回答显示 `用时 · 字数 · 字/秒` |

### 输入

- **图片**：选择 / 拖拽 / `Ctrl+V` 粘贴，缩略图 + 点开看大图
- **文本文件**：代码、md、json、csv、日志直接内联
- **PDF / Word**：pypdf / python-docx 抽文本
- **语音输入**：Windows 听写引擎（需麦克风 + 语言包）
- **技能库**：一段系统提示词存成标签，点一下套在下一句上

### 会话与配置

- 多话题：新建、搜索（标题 **和正文**）、重命名、置顶、删除、导出 Markdown / JSON
- 多套 API 配置：预设 DeepSeek / OpenAI / Moonshot / 智谱 / 通义 / Groq / OpenRouter / Ollama，可拉取模型列表、测试连接
- 每话题独立系统提示词；全局系统提示词；温度 / top_p / max_tokens（含「精确 / 平衡 / 发散」三档预设）

### 上下文管理

顶栏 `27.9k/16k · 170%` 是按字数估算的占用 / 上限：

- ≥85% 变黄，≥100% 变红
- **点它**可以：删掉最早的消息 / 新建话题 / 清空 / 改上限
- 发送前超限会先问要不要自动裁剪到 70%
- 上限默认自动读 llama.cpp `/props` 的 `n_ctx`

### 还能干这些

- **运行网页**：回答里的 HTML/SVG 代码块一键内嵌预览（QtWebEngine），也可转系统浏览器
- **朗读**：Windows SAPI 语音，逐条朗读或自动朗读
- **模型对比**：一句话问两个模型，左右并排流式回答
- **画图**：调 `/images/generations`，结果插入对话
- **自定义工具**：任意 HTTP 接口包成函数给模型调用
- **插件**：`plugins/*.py` 里 `register(reg)` 就能加 Python 工具
- **备份**：全量 JSON 导出 / 导入

## 快速开始

### 用打包好的版本

1. 下载 `自用API终端-绿色版.zip` 并解压
2. 双击 `自用API终端.exe`（整个文件夹要一起留下，`_internal` 是运行时）
3. 首次启动会弹「API 设置」：选预设或填 Base URL、API Key、模型名，点「测试连接」

> exe 未签名，可能被 Smart App Control 或杀软拦；被拦就用下面的源码方式跑。

### 用源码

```powershell
git clone <this-repo>
cd hermes-native
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install PySide6 pypdf python-docx
.\.venv\Scripts\python.exe app.py
```

## 连接哪些服务

任何 OpenAI 兼容的 `/chat/completions` 都行：

| 类型 | 例子 | 备注 |
|---|---|---|
| 云 API | `https://api.deepseek.com/v1` | 填 Key |
| 本地 llama.cpp | `http://127.0.0.1:8080/v1` | 自动读 `/props` 的 `n_ctx` |
| Ollama | `http://localhost:11434/v1` | Key 随便填 |
| 中转 / 自建 | 任意兼容网关 | 无 CORS 限制 |

## 使用技巧

| 快捷键 | 作用 |
|---|---|
| `Enter` / `Shift+Enter` | 发送 / 换行 |
| `Ctrl+K` | 新建话题 |
| `Ctrl+B` | 收起/展开侧边栏 |
| `Ctrl+O` | 选择附件 |
| `Ctrl+,` | API 设置 |
| `Ctrl+Shift+S` | 停止生成 / 停止朗读 |

输入框支持 `/` 指令：`/new` `/clear` `/stop` `/regen` `/cont` `/sys` `/skills` `/params` `/image` `/compare` `/export` `/help`

- **滚动锁定**：生成时往上翻不会被拽回底部，顶栏 `⤓` 会变成 `⤓●`
- **上下文满了**：换新话题，或点顶栏那个百分比清理历史——超限请求会让本地模型极慢甚至失败

## 数据与隐私

```
%LOCALAPPDATA%\SelfApiTerminal\
├─ store.json   配置（含 API Key，明文）、话题、参数
├─ media\       附件图片
├─ plugins\     插件
└─ crash.log    崩溃与异常记录
```

- 没有遥测、没有云端同步、不主动联网（只连你配置的 API）
- **API Key 是明文存储**——这是本机自用程序的取舍；共享电脑上请注意
- 想搬走就拷整个目录，或用「导出备份」

## 技术栈与结构

Python 3.11 + PySide6(Qt6) + 标准库 `http.client` 手写 SSE 解析，PyInstaller 打包。

```
app.py        主窗口、消息气泡、会话、设置
api.py        OpenAI 兼容接口：流式、工具回合、模型列表、/props、画图
store.py      config/话题/参数的 JSON 存储
workers.py    QThread 封装（聊天流、一次性任务、线程回收）
dialogs.py    技能库、参数、自定义工具、模型对比、画图
widgets.py    附件条、图片查看、网页预览
media.py      附件落盘、data URL、PDF/Word 抽取
md_render.py  Markdown → Qt 富文本
tts.py        朗读      voice.py  语音输入
plugins.py    插件加载   theme.py  深色样式
```

## 开发

```powershell
# 本地假模型（支持流式、工具回合、图片）
.\.venv\Scripts\python.exe fake_model.py 18899

# 测试
.\.venv\Scripts\python.exe ui_check.py          # 界面构造（38 项）
.\.venv\Scripts\python.exe test_render.py       # Markdown 渲染（含真实历史全量）
.\.venv\Scripts\python.exe test_features.py     # 表格/工具/插件/PDF/参数
.\.venv\Scripts\python.exe test_crash.py        # 流式中切话题、关窗口
.\.venv\Scripts\python.exe test_stress_chat.py  # 连发 5 轮 + 重生成 + 继续
.\.venv\Scripts\python.exe test_settings.py     # 测试连接遇到不回话的服务器
.\.venv\Scripts\python.exe smoke.py shot.png    # 发一条消息并截图

# 打包
powershell -ExecutionPolicy Bypass -File .\build.ps1            # 目录版（推荐）
powershell -ExecutionPolicy Bypass -File .\build.ps1 -OneFile   # 单文件（%TEMP% 需可写）

# 打包后自检
.\dist\自用API终端\自用API终端.exe --selftest
.\dist\自用API终端\自用API终端.exe --selftest-preview
```

## 路线图

- [ ] **消息分支**：重新生成保留旧版本、可左右切换。需要先把流式从「QThread 发信号」换成
      「Python 线程 + 队列 + 主线程轮询」，否则多路流会踩线程生命周期
- [ ] 单实例保护（现在两个实例会互相覆盖 `store.json`）
- [ ] 代码签名 / 免安装更新
- [ ] 主题（浅色）
- [ ] macOS / Linux 适配

## 已知限制

- 只有 Windows（打包脚本、语音、快捷键都按 Windows 写的）
- 单实例：同时开两个，后关的会覆盖 `store.json`
- 未签名 exe，可能被 Smart App Control 拦
- 工具调用最多 5 轮
- 朗读 / 语音输入依赖系统语音组件，中文识别包默认没装
- 上下文占用是**估算**（字数 ÷ 1.6），不是真实 token 数

## 常见问题

**Q：闪退怎么办？**
先看 `%LOCALAPPDATA%\SelfApiTerminal\crash.log`。若事件查看器里是
`shiboken6.abi3.dll` + `0xc0000005`，可用 `⋯ → 网页预览用系统浏览器` 或环境变量
`SELFAPI_NO_WEBENGINE=1` 排除内嵌浏览器的影响，再把日志发出来。

**Q：回答说到一半就停了？**
大概率上下文满了（顶栏变红）。点那个百分比清理历史，或换个新话题。

**Q：「运行 HTML」打不开？**
预览用的是 QtWebEngine；某些环境下起不来会自动提示，可改用「在浏览器打开」，
或在 `⋯` 里打开「网页预览用系统浏览器」。

**Q：为什么不是单文件 exe？**
单文件启动要解压到 `%TEMP%`，在使用者机器上这一步可能被策略挡住；目录版免解压，更稳。

## License

TBD —— 发布前请指定协议（MIT / Apache-2.0 / 私有）。

---

## English

A native Windows chat client for any OpenAI-compatible API (including local llama.cpp / Ollama),
built with PySide6 — no Electron, no embedded browser shell, no local proxy.

- **Local-first**: config, chats and attachments live in `%LOCALAPPDATA%\SelfApiTerminal`
- **Direct HTTP**: requests are made in-process, so servers that reject cross-origin calls still work
- **Context-aware**: reads `n_ctx` from llama.cpp `/props` and warns before you overflow it
- Feature set: streaming, reasoning blocks, tool calls, markdown + code highlight, image/file/PDF/Word
  attachments, HTML preview, TTS, voice input, skills, per-conversation system prompt, model comparison,
  image generation, custom HTTP tools, Python plugins, backup/restore

```powershell
# run from source
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install PySide6 pypdf python-docx
.\.venv\Scripts\python.exe app.py
```

License: TBD.
