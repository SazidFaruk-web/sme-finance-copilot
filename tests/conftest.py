"""Shared pytest setup: isolate every test session in a temp data dir with a fixed key."""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="smecopilot-test-")
os.environ["APP_ENV"] = "test"
os.environ["DATA_DIR"] = _TMP
os.environ["LLM_PROFILE"] = "rules-offline"
os.environ["LOCAL_ONLY_MODE"] = "false"
# Test-only Fernet key (not a secret; generated for this repository's tests).
os.environ["FIELD_ENCRYPTION_KEY"] = "q2Vt0b2dJ3m8u0cA8n7f1yV3oZx9lS5eT4rW6pQ1hKs="
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
          "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):
    os.environ.pop(k, None)
