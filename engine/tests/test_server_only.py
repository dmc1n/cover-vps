"""Server-only settings (ADR-123): the AI's hosts and the spending caps cannot be changed by a
model, a trial override, a family preset or a learned rule, and a key never leaves for a host
that is not its provider's own."""

import json
from pathlib import Path

import pytest
from coverengine import ai, learned
from coverengine.errors import CoverError
from coverengine.params import Registry
from coverengine.params.registry import ParamError, parse_set, resolve_model

SERVER_KEYS = (
    "ai.base_url",
    "ai.vision_base_url",
    "spend.budget_eur_month",
    "spend.hard_stop",
    "suggest.visitor_eur_day",
    "suggest.per_hour",
    # the agent API's limits (ADR-135)
    "limits.agent_per_hour",
    "limits.agent_anon_per_day",
    "limits.agent_key_per_day",
    "limits.agent_key_photos_per_day",
    "limits.agent_key_eur_day",
    "limits.agent_link_hours",
)


def test_the_marked_keys_are_server_only() -> None:
    reg = Registry.load()
    for key in SERVER_KEYS:
        assert reg.specs[key].server_only, key
    assert not reg.specs["hull.clearance_mm"].server_only


@pytest.mark.parametrize("layer", ["preset", "model", "trial"])
def test_no_override_layer_may_set_them(layer: str) -> None:
    reg = Registry.load()
    for key, value in (("ai.base_url", "https://evil.example"), ("spend.hard_stop", False)):
        with pytest.raises(ParamError, match="server only"):
            reg.resolve(**{layer: {key: value}})
    # nested trees too (a CoverDefinition's parameters)
    with pytest.raises(ParamError):
        reg.resolve(**{layer: {"spend": {"budget_eur_month": 1e9}}})


def test_the_program_itself_may() -> None:
    eff = Registry.load().resolve(server={"spend.budget_eur_month": 3})
    assert eff["spend.budget_eur_month"] == 3 and eff.source("spend.budget_eur_month") == "server"


def test_cli_set_and_model_file_are_refused(tmp_path: Path) -> None:
    trial = parse_set(["ai.base_url=https://evil.example"])
    with pytest.raises(ParamError):
        Registry.load().resolve(trial=trial)
    (tmp_path / "cover.json").write_text(
        json.dumps({"parameters": {"ai": {"vision_base_url": "https://evil.example"}}})
    )
    with pytest.raises(ParamError):
        resolve_model(tmp_path)


def test_learned_rule_cannot_set_a_server_key(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    d = tmp_path / "learning" / "rules"
    d.mkdir(parents=True)
    (d / "table.yaml").write_text("ai:\n  base_url: https://evil.example\n")
    model = tmp_path / "m"
    model.mkdir()
    (model / "cover.json").write_text(json.dumps({"family": "table"}))
    assert learned.rules("table")  # the file is read ...
    with pytest.raises(ParamError):  # ... but cannot change a server-only key
        resolve_model(model)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/v1",
        "http://api.deepseek.com",
        "https://api.deepseek.com.evil.example",
        "https://user@api.deepseek.com",
        "https://api.deepseek.com:8443",
        "https://generativelanguage.googleapis.com/v1beta/openai",  # gemini's, not deepseek's
    ],
)
def test_key_only_to_its_own_provider(url: str) -> None:
    with pytest.raises(CoverError, match="not sent"):
        ai.chat_url("deepseek", url)


def test_the_defaults_are_allowed() -> None:
    reg = Registry.load()
    assert ai.chat_url(
        str(reg.specs["ai.provider"].default), str(reg.specs["ai.base_url"].default)
    ).endswith("/chat/completions")
    assert ai.chat_url(str(reg.specs["ai.vision_provider"].default),
                       str(reg.specs["ai.vision_base_url"].default)).startswith(
        "https://generativelanguage.googleapis.com/")  # fmt: skip


def test_ask_refuses_before_sending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sent: list[object] = []
    monkeypatch.setattr(ai.urllib.request, "urlopen", lambda *a, **k: sent.append(a))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    from coverengine import spend

    monkeypatch.setattr(spend, "guard", lambda p: None)
    eff = Registry.load().resolve(server={"ai.base_url": "https://evil.example"})
    with pytest.raises(CoverError):
        ai.ask(eff, "s", "u")
    assert not sent
