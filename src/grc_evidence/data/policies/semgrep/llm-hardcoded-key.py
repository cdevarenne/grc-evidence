import os

# ruleid: llm-hardcoded-key
ANTHROPIC_API_KEY = "placeholder-not-a-real-key"
# ruleid: llm-hardcoded-key
OPENAI_API_KEY = ""
# ok: llm-hardcoded-key
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
# ok: llm-hardcoded-key
API_KEY_HEADER = "x-api-key"
# ruleid: llm-hardcoded-key
llm = ChatGoogleGenerativeAI(model="m", google_api_key="placeholder-not-a-real-key")
# ruleid: llm-hardcoded-key
client = Anthropic(api_key="placeholder-not-a-real-key")
# ok: llm-hardcoded-key
llm = ChatGoogleGenerativeAI(model="m", google_api_key=os.environ["GOOGLE_API_KEY"])
# ok: llm-hardcoded-key
headers = dict(api_key_header="x-api-key")
