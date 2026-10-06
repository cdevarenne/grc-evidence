def call(client, prompt):
    # ruleid: llm-unbounded-call
    client.messages.create(model="m", messages=prompt)
    # ruleid: llm-unbounded-call
    client.messages.create(model="m", max_tokens=100, messages=prompt)
    # ruleid: llm-unbounded-call
    client.messages.create(model="m", timeout=30, messages=prompt)
    # ok: llm-unbounded-call
    client.messages.create(model="m", max_tokens=100, timeout=30, messages=prompt)
    # ok: llm-unbounded-call
    client.messages.create(timeout=30, model="m", messages=prompt, max_tokens=100)


def langchain_models():
    # ruleid: llm-unbounded-call
    ChatGoogleGenerativeAI(model="m")
    # ruleid: llm-unbounded-call
    ChatGoogleGenerativeAI(model="m", timeout=30)
    # ruleid: llm-unbounded-call
    ChatOpenAI(model="m", max_tokens=100)
    # ok: llm-unbounded-call
    ChatGoogleGenerativeAI(model="m", max_output_tokens=256, timeout=30)
    # ok: llm-unbounded-call
    ChatAnthropic(timeout=30, model="m", max_tokens=100)
    # ok: llm-unbounded-call
    ChatPromptTemplate.from_messages([("human", "{q}")])
