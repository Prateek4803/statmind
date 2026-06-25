"""StatMind AI explainer — grounded, provider-swappable LLM explanations.

The LLM advises; it never recomputes or contradicts the verified engine. The
grounding layer (grounding.py) bounds what the model can say; the provider layer
(provider.py) makes hosted-vs-local a config switch. See explain_result().
"""
from .grounding import build_messages, build_grounding
from .provider import get_provider, ExplainResult


def explain_result(analysis_type: str, result: dict, user_question: str = None,
                   *, max_tokens: int = 600) -> ExplainResult:
    """Produce a grounded explanation of a computed analysis result.

    Returns ExplainResult(ok=False, ...) if the analysis type isn't supported or
    the provider isn't configured — callers should handle that gracefully (e.g.
    hide the explainer button) rather than erroring.
    """
    messages = build_messages(analysis_type, result, user_question)
    if messages is None:
        return ExplainResult(False, error=f"Explainer not available for '{analysis_type}'.")
    return get_provider().complete(messages, max_tokens=max_tokens)
