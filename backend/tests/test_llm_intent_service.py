"""Old llm_intent_service tests — function has been removed.

The LLM intent detection was replaced by ReAct Function Calling in graph.py.
"""

import pytest


@pytest.mark.skip(reason="Old llm_intent_service removed; replaced by ReAct Function Calling in graph.py")
def test_intent_from_payload_legacy() -> None:
    pass
