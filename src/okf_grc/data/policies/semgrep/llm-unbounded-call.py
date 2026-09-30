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
