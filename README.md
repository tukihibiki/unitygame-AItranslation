# Hanhua — Unity Mono 游戏日语 LLM 实时翻译

通过 AI 大语言模型将 Unity Mono 游戏中的日语文本实时翻译为中文。本地 Ollama 模型优先，云端 DeepSeek API 兜底，零配置注入。

## 特性

- **双 AI 引擎** — 本地 Ollama（qwen3:0.6b，零费用）→ 云端 DeepSeek API（兜底）
- **自适应 Token** — 根据文本长度动态调整 token 预算，300+len×2
- **自动注入** — 选择游戏 `.exe` 自动部署 CustomTranslate.dll + Config.ini
- **SQLite 缓存** — 翻译一次永久缓存，命中时 <5ms 即时显示
- **自动检测 Unity Mono** — 扫描目录批量识别游戏
- **双击启动** — 双击游戏列表自动启动翻译引擎 + 游戏
- **翻译历史** — 实时显示原文/译文/AI/耗时

## 架构

```
游戏 (AutoTranslator) → HTTP POST → 翻译服务 (Python)
                                       ├── 缓存 SQLite (命中 <5ms)
                                       ├── 本地 Ollama (~1s, 零费用)
                                       └── 云端 DeepSeek (~1s, 极低费用)
                                              ↓
                                         返回中文 → 游戏 UI
```

## 环境要求

- Windows 10/11
- Python 3.11+
- [Ollama](https://ollama.com)（可选，用于本地翻译）
- DeepSeek API Key（可选，用于云端翻译）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置模板
copy config.example.yaml config.yaml

# 3. 编辑 config.yaml，填入 API Key
#    （本地 Ollama 无需 API Key，可直接使用）

# 4. 启动 GUI
python run_gui.py
```

## 配置

```yaml
# config.yaml
server:
  port: 56443

llm:                          # 云端 AI
  enabled: true
  provider: deepseek
  api_key: YOUR_API_KEY       # 替换为你的 Key
  model: deepseek-v4-flash
  temperature: 0.1

ollama:                       # 本地 AI
  enabled: true
  base_url: http://127.0.0.1:11434
  model: qwen3:0.6b
  timeout: 10
```

## 使用流程

1. 打开 GUI → 配置 API Key（或只勾选本地 AI）
2. 点击"启动"翻译引擎
3. 切换到"游戏管理" → 选择游戏 `.exe` → 添加
4. 双击游戏列表中的游戏（或右键 → 启动游戏）
5. 游戏内日语文本自动翻译为中文

## 为新游戏注入

添加游戏时自动检测并部署翻译组件到 `Managed/Translators/` 目录。

如果游戏未安装 XUnity.AutoTranslator，需先用 ReiPatcher 或 BepInEx 注入基础框架，再添加到此工具。

## GUI 界面

```
┌─ AI 配置 & 服务 ─────────────────────────────────────┐
│ [x] 本地 AI  [qwen3:0.6b] [检测]         ← 优先     │
│ [x] 云端 AI  [DeepSeek] Key:[••••]        ← 兜底     │
│ 模型:[deepseek-v4-flash] Temp:[0.1] 端口:[56443]      │
│                              [保存全部配置]            │
│ 翻译引擎: ● 运行中 PID 12345  [启动] [停止] [重启]      │
│ 统计: 本地AI:12 云端AI:3 缓存:3400 费用:$0.00005       │
│ 实时日志: おはよう → 早上好  (local, 1044ms)          │
├─ 游戏管理 ────────────────────────────────────────────┤
│ 启动程序: [选择.exe] [选择...] [添加游戏]              │
│ [自动扫描目录...]                                      │
│ ┌─ 已添加游戏 ────┐  ┌─ 翻译历史 ─────────── [刷新] ┐ │
│ │ IedeMusune 已注入│  │ 18:28 local こんにちは→你好  │ │
│ └─────────────────┘  └──────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

## 项目结构

```
hanhua/
├── run_gui.py              # GUI 入口
├── config.example.yaml     # 配置模板
├── requirements.txt        # Python 依赖
├── CustomTranslateEndpoint.cs  # XUnity.AutoTranslator 插件源码
├── gui/
│   └── main_window.py      # tkinter GUI
└── translator/
    ├── main.py             # aiohttp HTTP 服务器
    ├── llm_client.py       # 混合翻译客户端 (Ollama + DeepSeek)
    ├── llm_prompts.py      # AI 提示词
    ├── cache.py            # SQLite 缓存
    ├── language_detect.py  # 日/中语言检测
    ├── protocols.py        # XUnity CustomTranslate 协议
    ├── translation_pipeline.py  # 翻译管线
    ├── debounce.py         # 去抖队列
    ├── cache_warmer.py     # 字符串扫描工具
    └── config.py           # 配置加载
```

## License

MIT
