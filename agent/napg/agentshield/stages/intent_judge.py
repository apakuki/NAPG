"""Stage 1 — Intent Judge.

A second Anthropic call, independent of the reasoning layer, that reviews
the proposed action and returns one of three verdicts via tool-use:

- `agree` — passes Stage 1.
- `disagree` — fails closed with the judge's reason.
- `abstain` — fails closed; uncertainty is not consent.

The judge is told the action, rationale, supporting breaches, and the
key transaction fields (destination, value). It is instructed to look
for inconsistency between rationale and action, value-vs-rationale
mismatch, and obvious red flags. The system prompt is marked for
ephemeral prompt caching; the per-call user message is uncached.

This is a structurally independent second opinion — it shares the
model family but lives in its own call with its own prompt + tool
schema. A successful prompt-injection on the reasoner does not also
poison the judge.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from anthropic import Anthropic

from napg.agentshield.pipeline import StageResult, TxIntent

DEFAULT_JUDGE_MODEL = "claude-opus-4-7"
DEFAULT_JUDGE_MAX_TOKENS = 512

JUDGE_SYSTEM_PROMPT = """You are AgentShield's Intent Judge — an independent \
review of a proposed onchain action.

A reasoning agent has decided to take an action and supplied a rationale. \
Your role is to verify the action is consistent with the rationale and with \
sound risk management. You are independent: you do NOT defer to the agent.

Return one of three verdicts via the `submit_verdict` tool:

- `agree` — the proposed action matches the rationale, the rationale is \
coherent, and there are no obvious red flags.
- `disagree` — the rationale does not justify the action, or the rationale \
is incoherent, or there is a clear red flag (destination unrelated to a \
configured safe address, value beyond what the rationale describes, \
mismatch between supporting_breaches and the rationale text, etc.).
- `abstain` — the input is ambiguous or you cannot reach a confident \
verdict. AgentShield treats abstain as fail-closed; only `agree` passes.

Red flags to look for:
- The action is `migrate_to_safe` but the rationale describes calm or \
green status. Inconsistency between action and rationale is always a \
red flag.
- The rationale references breaches not present in the \
`supporting_breaches` list, or vice-versa.
- The destination address does not look like the configured safe contract.
- The value is orders of magnitude beyond what the rationale describes \
(e.g., the rationale says "migrate dust" but the value is multiple ETH).

Return concisely. Your verdict and reason land in the audit log."""

VERDICT_TOOL: dict[str, Any] = {
    "name": "submit_verdict",
    "description": "Submit a judge verdict on the proposed action.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["agree", "disagree", "abstain"],
                "description": "The judge's verdict on whether to allow this action.",
            },
            "reason": {
                "type": "string",
                "description": "One-paragraph explanation referencing intent fields by name.",
            },
        },
        "required": ["verdict", "reason"],
    },
}


def build_intent_judge_stage(
    *,
    api_key: str,
    client: Anthropic | None = None,
    model: str = DEFAULT_JUDGE_MODEL,
    max_tokens: int = DEFAULT_JUDGE_MAX_TOKENS,
) -> Callable[[TxIntent], StageResult]:
    """Return a Stage 1 callable bound to an Anthropic client.

    `client` is injectable so tests run against a mocked SDK without
    network calls. The default constructs a fresh `Anthropic(api_key=...)`.
    """
    if not api_key:
        raise ValueError("Anthropic API key is required for Intent Judge")
    api = client if client is not None else Anthropic(api_key=api_key)

    def _stage(intent: TxIntent) -> StageResult:
        response = api.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": JUDGE_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[VERDICT_TOOL],
            tool_choice={"type": "tool", "name": "submit_verdict"},
            messages=[{"role": "user", "content": _render_user_message(intent)}],
        )
        tool_input = _extract_verdict(response)
        verdict = tool_input["verdict"]
        reason = tool_input.get("reason", "")
        if verdict == "agree":
            return StageResult(
                stage="intent_judge",
                passed=True,
                reason=reason,
                details={"verdict": "agree", "model": getattr(response, "model", model)},
            )
        return StageResult(
            stage="intent_judge",
            passed=False,
            reason=f"judge {verdict}: {reason}",
            details={"verdict": verdict, "model": getattr(response, "model", model)},
        )

    return _stage


def _render_user_message(intent: TxIntent) -> str:
    payload = {
        "action": intent.action,
        "from_address": intent.from_address,
        "to_address": intent.to_address,
        "value_wei": intent.value_wei,
        "data": intent.data,
        "rationale": intent.rationale,
        "supporting_breaches": list(intent.supporting_breaches),
    }
    return (
        "The reasoning agent proposes the following action. Review and call "
        "submit_verdict.\n\n```json\n" + json.dumps(payload, sort_keys=True, indent=2) + "\n```"
    )


def _extract_verdict(response: Any) -> dict[str, Any]:
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "submit_verdict"
        ):
            return dict(block.input)
    raise RuntimeError("Intent Judge response did not include a submit_verdict tool_use block")


__all__ = [
    "DEFAULT_JUDGE_MAX_TOKENS",
    "DEFAULT_JUDGE_MODEL",
    "JUDGE_SYSTEM_PROMPT",
    "VERDICT_TOOL",
    "build_intent_judge_stage",
]
