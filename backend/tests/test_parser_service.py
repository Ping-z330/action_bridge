from types import SimpleNamespace

import app.services.parser_service as parser_service


def test_parse_transcript_extracts_decisions_and_actions() -> None:
    transcript = """
    讨论了本周上线风险和延期方案
    Decision: Beta 版本延期到周五
    Action: 前端更新落地页文案
    Next step: 产品经理确认用户通知时间
    """.strip()

    parsed = parser_service.parse_transcript("产品例会", transcript)

    assert parsed.summary == "讨论了本周上线风险和延期方案"
    assert "Decision: Beta 版本延期到周五" in parsed.decisions
    assert len(parsed.action_items) == 2
    assert parsed.action_items[0].title == "Action: 前端更新落地页文案"


def test_parse_transcript_falls_back_when_no_action_keywords() -> None:
    transcript = """
    本次会议同步了项目排期
    确认联调时间推迟一天
    请大家明早继续同步风险项
    """.strip()

    parsed = parser_service.parse_transcript("站会", transcript)

    assert parsed.summary == "本次会议同步了项目排期"
    assert len(parsed.decisions) == 1
    assert len(parsed.action_items) == 1
    assert parsed.action_items[0].title == "请大家明早继续同步风险项"


def test_parse_transcript_uses_openai_when_available(monkeypatch) -> None:
    class FakeResponses:
        @staticmethod
        def create(**kwargs):
            assert kwargs["model"] == "test-model"
            return SimpleNamespace(
                output_text=(
                    '{"summary":"确认本周上线计划","decisions":["本周五上线"],'
                    '"action_items":[{"title":"补充回归测试","owner_name":"测试同学","deadline":"周四","status":"pending"}]}'
                )
            )

    class FakeClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setattr(parser_service, "PARSER_PROVIDER", "openai")
    monkeypatch.setattr(parser_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(parser_service, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(parser_service, "OpenAI", FakeClient)

    parsed = parser_service.parse_transcript("周会", "原始记录")

    assert parsed.summary == "确认本周上线计划"
    assert parsed.decisions == ["本周五上线"]
    assert parsed.action_items[0].owner_name == "测试同学"


def test_parse_transcript_uses_deepseek_when_available(monkeypatch) -> None:
    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            assert kwargs["model"] == "deepseek-v4-flash"
            assert kwargs["response_format"] == {"type": "json_object"}
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"summary":"同步了发布安排","decisions":["周四冻结版本"],'
                                '"action_items":[{"title":"补充冒烟测试","owner_name":"QA","deadline":"周三","status":"pending"}]}'
                            )
                        )
                    )
                ]
            )

    class FakeClient:
        def __init__(self, api_key: str, base_url: str):
            assert api_key == "deepseek-test-key"
            assert base_url == "https://api.deepseek.com"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(parser_service, "PARSER_PROVIDER", "deepseek")
    monkeypatch.setattr(parser_service, "DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setattr(parser_service, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(parser_service, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(parser_service, "OpenAI", FakeClient)

    parsed = parser_service.parse_transcript("发布会", "原始记录")

    assert parsed.summary == "同步了发布安排"
    assert parsed.decisions == ["周四冻结版本"]
    assert parsed.action_items[0].title == "补充冒烟测试"


def test_parse_transcript_falls_back_when_openai_fails(monkeypatch) -> None:
    class FailingClient:
        def __init__(self, api_key: str):
            self.responses = self

        def create(self, **kwargs):
            raise RuntimeError("network error")

    monkeypatch.setattr(parser_service, "PARSER_PROVIDER", "openai")
    monkeypatch.setattr(parser_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(parser_service, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(parser_service, "OpenAI", FailingClient)

    parsed = parser_service.parse_transcript("周会", "讨论排期\nAction: 跟进上线准备")

    assert parsed.summary == "讨论排期"
    assert parsed.action_items[0].title == "Action: 跟进上线准备"
