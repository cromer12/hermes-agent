from agent.conversation_loop import (
    _fallback_confirmation_action,
    _fallback_confirmation_message,
)


def test_fallback_confirmation_accepts_only_explicit_local_continuation():
    assert _fallback_confirmation_action("continue on Tiiny") == "continue"
    assert _fallback_confirmation_action("YES, continue locally") == "continue"
    assert _fallback_confirmation_action("wait for cloud") == "wait"
    assert _fallback_confirmation_action("no") == "wait"
    assert _fallback_confirmation_action("continue") is None
    assert _fallback_confirmation_action("finish the deployment") is None


def test_fallback_pause_message_names_target_and_data_boundary():
    text = _fallback_confirmation_message({
        "provider": "custom:tiiny",
        "model": "Qwen/Qwen3.6-35B-A3B",
    })

    assert "paused" in text.lower()
    assert "before sending" in text.lower()
    assert "conversation context" in text.lower()
    assert "reasoning state" in text.lower()
    assert "continue on Tiiny" in text
    assert "wait for cloud" in text
    assert "Qwen/Qwen3.6-35B-A3B" in text
