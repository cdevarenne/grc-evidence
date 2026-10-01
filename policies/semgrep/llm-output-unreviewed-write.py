def apply(widget, out, request):
    # ruleid: llm-output-unreviewed-write
    widget.description = out.content[0].text
    if request.data.get("human_reviewed"):
        # ok: llm-output-unreviewed-write
        widget.description = out.content[0].text
    if human_reviewed(widget):
        # ok: llm-output-unreviewed-write
        widget.name = out.content[0].text
    # ok: llm-output-unreviewed-write
    summary = out.content[0].text


def apply_langchain(record, llm, prompt, response):
    # ruleid: llm-output-unreviewed-write
    record.summary = llm.invoke(prompt).content
    reply = llm.invoke(prompt)
    # ruleid: llm-output-unreviewed-write
    record.summary = reply.content
    if record.human_reviewed:
        # ok: llm-output-unreviewed-write
        record.summary = reply.content
    # ok: llm-output-unreviewed-write
    record.body = response.content


async def apply_langchain_async(record, llm, prompt):
    # ruleid: llm-output-unreviewed-write
    record.summary = (await llm.ainvoke(prompt)).content
