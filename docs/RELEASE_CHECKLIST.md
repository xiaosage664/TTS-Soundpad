# 发布检查清单

## 发布前回归

- [ ] Edge 引擎：输入文本可生成并播放。
- [ ] MiniMax 引擎：Key 验证通过，生成并播放正常。
- [ ] 本地预听功能正常。
- [ ] 历史记录与常用短语功能正常。
- [ ] 错误提示可读（网络异常、鉴权失败、Soundpad 未连接）。

## 构建与交付

- [ ] `python -m pytest -q` 全通过。
- [ ] `python -m ruff check app gui tests main.py` 全通过。
- [ ] `python -m black --check app gui tests main.py` 全通过。
- [ ] `pyinstaller TTS_Soundpad.spec` 成功。
- [ ] 产物 `dist/TTS_Soundpad.exe` 在干净环境可启动。

## 发布说明建议模板

- 变更摘要：本次新增/优化内容。
- 兼容性说明：配置迁移、已知限制。
- 回滚建议：如遇问题，回退到上一个 release 版本。
