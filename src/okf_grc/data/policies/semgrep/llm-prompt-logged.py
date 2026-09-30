import logging

logger = logging.getLogger(__name__)


def handler(prompt, completion, prompt_id, user_prompt):
    # ruleid: llm-prompt-logged
    logger.error("failed on %s", user_prompt)
    # ruleid: llm-prompt-logged
    logger.info("prompt: %s", prompt)
    # ruleid: llm-prompt-logged
    logger.debug("got %s", completion.content)
    # ruleid: llm-prompt-logged
    logging.warning(prompt)
    # ok: llm-prompt-logged
    logger.info("request %s done", prompt_id.hex)
    # ok: llm-prompt-logged
    logger.info("request done")
