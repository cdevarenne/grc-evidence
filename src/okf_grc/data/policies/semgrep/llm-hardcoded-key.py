import os

# ruleid: llm-hardcoded-key
ANTHROPIC_API_KEY = "placeholder-not-a-real-key"
# ruleid: llm-hardcoded-key
OPENAI_API_KEY = ""
# ok: llm-hardcoded-key
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
# ok: llm-hardcoded-key
API_KEY_HEADER = "x-api-key"
