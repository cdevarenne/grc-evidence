# INTENTIONALLY VULNERABLE — DO NOT DEPLOY. Never run; it exists to be scanned.
# Seeds AI-1, AI-3, AI-4 and AI-6 (see app/SEEDED.yaml).
import logging

import anthropic
from rest_framework.decorators import api_view
from rest_framework.response import Response

from widgets.models import Widget

from .settings import ANTHROPIC_API_KEY, ASSISTANT_MODEL

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@api_view(["POST"])
def summarize(request):
    widget = Widget.objects.get(pk=request.data["widget_id"])
    prompt = f"Summarize this widget for a customer:\n{widget.description}\n{request.data.get('note', '')}"
    logger.info("assistant prompt: %s", prompt)
    completion = client.messages.create(
        model=ASSISTANT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return Response({"widget": widget.pk, "summary": completion.content[0].text})


@api_view(["POST"])
def rewrite_description(request):
    widget = Widget.objects.get(pk=request.data["widget_id"])
    completion = client.messages.create(
        model=ASSISTANT_MODEL,
        max_tokens=512,
        timeout=30,
        messages=[{"role": "user", "content": f"Rewrite: {widget.description}"}],
    )
    widget.description = completion.content[0].text
    widget.save()
    return Response({"widget": widget.pk, "ai_generated": True})
