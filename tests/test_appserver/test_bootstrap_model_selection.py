"""A cold worker must bootstrap with the task's model, not the old global active model."""

from pathlib import Path


def test_bootstrap_agent_forwards_task_model(monkeypatch, tmp_path):
    from appserver import bootstrap

    captured = {}

    class FakeAgent:
        pass

    class FakeSettings:
        @staticmethod
        def load_config():
            return {"language": "en"}

    class FakeI18n:
        @staticmethod
        def set_lang(_value):
            return None

    import sys
    import types

    fake_settings_module = types.SimpleNamespace(load_config=FakeSettings.load_config)
    fake_i18n_module = types.SimpleNamespace(i18n=FakeI18n())
    monkeypatch.setitem(sys.modules, "config.settings", fake_settings_module)
    monkeypatch.setitem(sys.modules, "utils.i18n", fake_i18n_module)

    class FakeAgentClass:
        def __init__(self, model_name=None):
            captured["model_name"] = model_name

    monkeypatch.setitem(sys.modules, "core.agent_v2", types.SimpleNamespace(AgentV2=FakeAgentClass))
    result = bootstrap.bootstrap_agent(
        stub=False,
        workspace_root=tmp_path,
        model_name="deepseek/deepseek-v4-flash",
    )

    assert isinstance(result, FakeAgentClass)
    assert captured["model_name"] == "deepseek/deepseek-v4-flash"
