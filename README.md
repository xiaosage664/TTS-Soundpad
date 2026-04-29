# TTS Soundpad

将文字转语音 (TTS) 无缝集成到 [Soundpad](https://leppsoft.com/soundpad/) 的桌面工具。输入文字，一键生成语音并通过 Soundpad 播放到游戏语音频道中。

## 功能特性

- **文字转语音** — 基于 Edge TTS 引擎，支持多种语音角色和语速/语调调节
- **Soundpad 集成** — 自动将生成的音频发送到 Soundpad 并播放
- **悬浮输入框** — 便捷的悬浮窗口，快速输入并发送语音
- **历史记录** — 查看和重放历史语音
- **常用短语** — 一键发送预设短语

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

## 系统要求

- Windows 10 / 11
- [Soundpad](https://leppsoft.com/soundpad/)（需已安装并运行）
- 网络连接（用于 Edge TTS 语音合成）

## 项目结构

```
TTS-Soundpad/
├── main.py              # 程序入口
├── app/
│   ├── __init__.py      # 异常层级定义
│   ├── async_bridge.py  # 异步桥接 (后台线程运行 asyncio)
│   ├── audio_player.py  # 本地音频预听播放
│   ├── config_manager.py# 配置管理
│   ├── orchestrator.py  # 业务协调器
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

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
