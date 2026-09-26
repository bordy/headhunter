import os

import anthropic

_client = None

# Server-side refusal fallback: if the primary model declines a request, the API
# re-runs it on a substitute model inside the same call instead of just stopping.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Only needed if your API key isn't scoped to a workspace (the API will tell you).
        workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        _client = anthropic.Anthropic(default_headers=headers)
    return _client


def _cached_system(system_text: str):
    """A system prompt block marked for prompt caching.

    Used when the same system text (e.g. a resume) is reused across many
    calls in a loop, so only the first call pays full input-token cost.
    """
    return [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]


def _check_stop(response) -> None:
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model declined the request: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Response hit max_tokens before finishing - raise max_tokens for this call.")


def _text_of(response) -> str:
    # With web search, the answer is split into several text blocks around citations.
    return "".join(b.text for b in response.content if b.type == "text")


def generate_text(
    model: str,
    system_text: str,
    user_content: str,
    max_tokens: int = 16000,
    effort: str = "medium",
    web_search_max_uses: int = 0,
) -> str:
    """Free-form Markdown output. Pass web_search_max_uses > 0 to let Claude search the web."""
    client = get_client()
    tools = [{**WEB_SEARCH_TOOL, "max_uses": web_search_max_uses}] if web_search_max_uses else []
    messages = [{"role": "user", "content": user_content}]

    # Long server-tool turns can pause; resume by sending the paused turn back.
    for _ in range(5):
        response = client.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_cached_system(system_text),
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=messages,
            tools=tools,
            betas=[_FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    else:
        raise RuntimeError("Turn still paused after 5 continuations.")

    _check_stop(response)
    return _text_of(response)


def parse_structured(
    model: str,
    system_text: str,
    user_content: str,
    output_model,
    max_tokens: int = 16000,
    effort: str = "medium",
):
    client = get_client()
    response = client.beta.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=_cached_system(system_text),
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user_content}],
        output_format=output_model,
        betas=[_FALLBACK_BETA],
        fallbacks="default",
    )
    _check_stop(response)
    return response.parsed_output
