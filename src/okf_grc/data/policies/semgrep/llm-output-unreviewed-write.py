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
