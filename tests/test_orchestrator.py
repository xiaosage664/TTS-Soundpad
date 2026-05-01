from app.orchestrator import Orchestrator, SpeakStatus


class DummyEngine:
    def __init__(self, result_path: str = "out.mp3"):
        self.result_path = result_path
        self.calls = []

    def synthesize(self, text, voice, **params):
        self.calls.append((text, voice, params))
        return self.result_path

    def list_voices(self):
        return [{"Name": "dummy"}]


class DummySoundpad:
    def __init__(self):
        self.play_calls = []
        self.stop_calls = 0

    def play_tts_file(self, file_path, speakers=False, mic=True):
        self.play_calls.append((file_path, speakers, mic))
        return 123

    def stop_sound(self):
        self.stop_calls += 1

    def is_running(self):
        return True


class DummyRoot:
    def after(self, _delay, callback):
        callback()


class DummyBridge:
    def __init__(self):
        self.root = DummyRoot()

    def submit(self, coro, on_success=None, on_error=None):
        if isinstance(coro, Exception):
            if on_error:
                on_error(coro)
            return
        if on_success:
            on_success(coro)


class DummyConfig:
    def __init__(self):
        self.values = {
            "engine": "edge",
            "voice": "v1",
            "max_text_length": 10,
            "rate": "+0%",
            "pitch": "+0Hz",
            "play_on_speakers": False,
            "play_on_mic": True,
        }
        self.recent = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def add_recent_text(self, text):
        self.recent.append(text)


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        if self.target:
            self.target()


def test_speak_rejects_empty_text():
    orchestrator = Orchestrator(
        tts=DummyEngine(),
        minimax=DummyEngine(),
        soundpad=DummySoundpad(),
        bridge=DummyBridge(),
        config=DummyConfig(),
    )
    statuses = []
    orchestrator.speak("   ", "v1", lambda s, m: statuses.append((s, m)))
    assert statuses == [(SpeakStatus.ERROR, "请输入文字")]


def test_speak_rejects_too_long_text():
    config = DummyConfig()
    config.values["max_text_length"] = 3
    orchestrator = Orchestrator(
        tts=DummyEngine(),
        minimax=DummyEngine(),
        soundpad=DummySoundpad(),
        bridge=DummyBridge(),
        config=config,
    )
    statuses = []
    orchestrator.speak("hello", "v1", lambda s, m: statuses.append((s, m)))
    assert statuses == [(SpeakStatus.ERROR, "文本超过 3 字限制")]


def test_speak_success_path_updates_history_and_recent(monkeypatch):
    monkeypatch.setattr("app.orchestrator.threading.Thread", ImmediateThread)
    edge = DummyEngine(result_path="generated.mp3")
    soundpad = DummySoundpad()
    config = DummyConfig()
    orchestrator = Orchestrator(
        tts=edge,
        minimax=DummyEngine(),
        soundpad=soundpad,
        bridge=DummyBridge(),
        config=config,
    )

    statuses = []
    orchestrator.speak("hello", "v1", lambda s, m: statuses.append((s, m)))

    assert statuses[0] == (SpeakStatus.GENERATING, "正在生成语音...")
    assert statuses[1] == (SpeakStatus.SENDING, "正在发送到 Soundpad...")
    assert statuses[2] == (SpeakStatus.PLAYING, "播放中")
    assert soundpad.play_calls == [("generated.mp3", False, True)]
    assert config.recent == ["hello"]
    assert orchestrator.get_latest_history().text == "hello"
    assert orchestrator.is_busy is False


def test_speak_calls_error_when_engine_fails():
    class ErrorBridge(DummyBridge):
        def submit(self, coro, on_success=None, on_error=None):
            if on_error:
                on_error(RuntimeError("boom"))

    orchestrator = Orchestrator(
        tts=DummyEngine(),
        minimax=DummyEngine(),
        soundpad=DummySoundpad(),
        bridge=ErrorBridge(),
        config=DummyConfig(),
    )
    statuses = []
    orchestrator.speak("ok", "v1", lambda s, m: statuses.append((s, m)))
    assert statuses[-1] == (SpeakStatus.ERROR, "boom")
    assert orchestrator.is_busy is False
