import json
import math
from decimal import Decimal, DecimalException, ROUND_CEILING


def cost_upper_bound(request, model, observed=None):
    """Reserve one token per serialized UTF-8 byte plus rounded chat overhead.

    Non-text inputs and missing output ceilings cannot be bounded this way.
    """
    prices = [model.get("input_price"), model.get("output_price")]
    if any(type(p) not in (int, float) or not math.isfinite(p) or p < 0 for p in prices):
        return {}
    limits = [request[k] for k in ("max_tokens", "max_completion_tokens") if k in request]
    if not limits:
        limits = [model.get("max_output_tokens")]
    choices = request.get("n", 1)
    if any(type(n) is not int or n <= 0 for n in [*limits, choices]):
        return {}
    messages = request.get("messages")
    if not isinstance(messages, list):
        return {}
    for message in messages:
        if not isinstance(message, dict):
            return {}
        content = message.get("content")
        if isinstance(content, list):
            if any(not isinstance(p, dict) or p.get("type") != "text" or not isinstance(p.get("text"), str) for p in content):
                return {}
        elif not isinstance(content, (str, type(None))):
            return {}
    size = len(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    prompt = ((size + 64 * len(messages) + 256 + 1023) // 1024) * 1024
    prompt, output = prompt * choices, max(limits) * choices
    observed = observed or {}
    prompt = max(prompt, observed.get("prompt_tokens") or 0)
    output = max(output, observed.get("completion_tokens") or 0)
    try:
        amount = Decimal(prompt) * Decimal(str(prices[0])) + Decimal(output) * Decimal(str(prices[1]))
        bound = float(amount.quantize(Decimal("0.000000001"), rounding=ROUND_CEILING))
    except (DecimalException, OverflowError, ValueError):
        return {}
    if not math.isfinite(bound):
        return {}
    return {"cost_upper_bound_usd": bound, "cost_basis": "upper_bound",
            "prompt_tokens_upper_bound": prompt, "completion_tokens_upper_bound": output}
