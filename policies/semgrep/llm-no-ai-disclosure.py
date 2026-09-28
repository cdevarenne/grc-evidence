from rest_framework.response import Response


def summarize(client, request):
    out = client.messages.create(model="m", max_tokens=10, timeout=5, messages=[])
    # ruleid: llm-no-ai-disclosure
    return Response({"summary": out.content[0].text})


def disclosed(client, request):
    out = client.messages.create(model="m", max_tokens=10, timeout=5, messages=[])
    # ok: llm-no-ai-disclosure
    return Response({"summary": out.content[0].text, "ai_generated": True})


def no_model(request):
    # ok: llm-no-ai-disclosure
    return Response({"summary": "static"})
