from __future__ import annotations

import os

# Groq OpenAI-compatible endpoint
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
GROQ_API_KEY_ENV = "GROQ_API_KEY"

# Retry policy for transient infrastructure failures
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY_SEC = 0.5
