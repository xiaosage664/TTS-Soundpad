# TTS Soundpad

将文字转语音 (TTS) 无缝集成到 [Soundpad](https://leppsoft.com/soundpad/) 的桌面工具。输入文字，一键生成语音并通过 Soundpad 播放到游戏语音频道中。

## 功能特性

- **双引擎 TTS** — 免费 Edge TTS + 商用 MiniMax，一键切换
- **多角色语音** — Edge 支持 8 种中文语音（含方言），MiniMax 支持 30+ 系统音色
- **语速/音调调节** — 滑块实时调节，所见即所得
- **Soundpad 集成** — 自动将生成的音频发送到 Soundpad 并播放到麦克风
- **悬浮输入框** — 可拖拽、置顶的悬浮窗口，游戏内快速输入
- **历史记录** — 查看和重放历史语音，一键复用
- **常用短语** — 预设常用语，右键增删，一键发送
- **本地预听** — 发送前本地试听效果

## 快速开始

### 方式一：直接下载 (推荐)

1. 从 [Releases](https://github.com/xiaosage664/TTS-Soundpad/releases) 下载最新的 `TTS_Soundpad.exe`
2. 确保 [Soundpad](https://leppsoft.com/soundpad/) 已安装并运行
3. 双击运行 `TTS_Soundpad.exe`

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/xiaosage664/TTS-Soundpad.git
cd TTS-Soundpad

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

## TTS 引擎

### Edge TTS（默认，免费）

启动即用，无需任何配置。基于微软 Edge 浏览器内置的在线 TTS 服务。

**可用语音：** 晓晓、晓伊、云健、云希、云夏、云扬、晓北（东北话）、晓妮（陕西话）共 8 种。

### MiniMax（商用，需 API Key）

MiniMax 提供更丰富、更自然的音色，适合追求高品质语音的用户。

#### 获取 API Key

1. 访问 [MiniMax 开放平台](https://platform.minimaxi.com/) 注册账号
2. 进入 **账户管理 → API Keys** 创建密钥
3. 复制 API Key

#### 配置方法

1. 打开 TTS Soundpad，点击顶部的 **引擎切换** 选择「MiniMax」
2. 在 **API Key** 输入框中粘贴密钥
3. 点击 **验证** 按钮确认 Key 有效
4. 在 **语音** 下拉框选择喜欢的音色
5. 调节**语速**（0.5~2.0）、**音量**（0~10）、**音调**（-12~+12）

> 💡 **提示：** API Key 会通过本地加密存储（DPAPI）保存，下次启动无需重新输入。建议在游戏外先验证和试听，找到最佳参数组合。

#### 费用说明

MiniMax 按字符计费，具体价格请参考 [MiniMax 官方定价](https://platform.minimaxi.com/document/Price)。新用户通常有免费额度。

## 系统要求

- Windows 10 / 11
- [Soundpad](https://leppsoft.com/soundpad/)（需已安装并运行）
- 网络连接（用于 Edge TTS / MiniMax 语音合成）

## 项目结构

```
TTS-Soundpad/
├── main.py              # 程序入口
├── app/
│   ├── __init__.py      # 异常层级定义
│   ├── async_bridge.py  # 异步桥接 (后台线程运行 asyncio)
│   ├── audio_player.py  # 本地音频预听播放
│   ├── config_manager.py# 配置管理
│   ├── minimax_engine.py# MiniMax TTS 引擎
│   ├── orchestrator.py  # 业务协调器（双引擎调度）
│   ├── soundpad.py      # Soundpad Named Pipe 通信
│   └── tts_engine.py    # Edge TTS 语音合成
├── gui/
│   ├── floating_input.py# 悬浮输入窗口
│   ├── main_window.py   # 主窗口
│   ├── theme.py         # 主题配色和字体
│   └── widgets.py       # 自定义 UI 组件
├── requirements.txt
├── TTS_Soundpad.spec    # PyInstaller 打包配置
└── LICENSE
```

## 打包为 exe

```bash
pip install pyinstaller
pyinstaller TTS_Soundpad.spec
```

生成的可执行文件位于 `dist/TTS_Soundpad.exe`。

## 开发与质量检查

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
python -m pytest -q

# 代码检查
python -m ruff check app gui tests main.py
python -m black --check app gui tests main.py

# 本地自动化提交检查（首次）
python -m pre_commit install
python -m pre_commit run --all-files
```

## 故障排查与发布

- 常见问题排查：[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)
- 发布前检查清单：[`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
