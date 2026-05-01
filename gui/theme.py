# 暗色游戏风格主题常量

COLORS = {
    # 背景层次 (从深到浅)
    "bg_dark": "#0f0f1a",  # 窗口最底层
    "bg_primary": "#1a1a2e",  # 卡片背景
    "bg_secondary": "#16213e",  # 次级面板
    "bg_input": "#0f3460",  # 输入框内部
    "bg_card": "#1e1e36",  # 卡片背景（略亮于 primary）
    # 主题色
    "accent": "#00adb5",
    "accent_hover": "#00c9d4",
    "accent_dim": "#007a80",  # 暗化 accent，用于未激活滑块轨道
    # 状态色
    "success": "#00e676",
    "error": "#ff5252",
    "warning": "#ffc107",
    "btn_send_flash": "#00e676",
    # 文字
    "text_primary": "#e0e0e0",
    "text_secondary": "#9e9e9e",
    "text_dim": "#616161",
    # 边框 / 装饰
    "border": "#2a2a4a",
    "border_light": "#3a3a5a",  # 卡片边框（稍亮）
    "divider": "#2a2a4a",  # 分隔线
}

FONTS = {
    "title": ("Microsoft YaHei UI", 16, "bold"),
    "subtitle": ("Microsoft YaHei UI", 11, "bold"),
    "body": ("Microsoft YaHei UI", 12),
    "small": ("Microsoft YaHei UI", 10),
    "mono": ("Consolas", 11),
}

ICONS = {
    "send": "\u25b6",  # ▶ 发送
}

WINDOW = {
    "default_geometry": "500x780",
    "min_width": 420,
    "min_height": 600,
    "title": "TTS Soundpad",
}
