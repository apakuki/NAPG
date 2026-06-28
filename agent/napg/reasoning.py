"""Reasoning layer — Anthropic SDK direct, prompt-cached system block, tool-use
for structured decisions.

Inputs: a `ReasoningInputs` bundle (heartbeat + optional Aerodrome / Morpho
probes + the breach evaluator's verdict). Output: a `Decision` carrying intent,
rationale, confidence, supporting breaches, plus the model identifier and the
cache-usage stats returned by the API.

Prompt caching strategy:
- The system block (NAPG's role + decision criteria + the tool schema is
  served via `tools=`) is marked `cache_control={"type": "ephemeral"}`. It is
  stable across calls so cache hits accumulate quickly.
- The user message carries the per-tick state JSON and is uncached.

Audit integration: when an `AuditLog` is passed in, every `decide()` call
writes one `decision` row. The Anthropic API key is *never* part of that row;
the audit-log test suite enforces this.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from anthropic import Anthropic
from pydantic import BaseModel, ConfigDict, Field

from napg.audit import AuditLog
from napg.monitor.aerodrome import LiquidityProbe
from napg.monitor.morpho import MorphoPoll
from napg.monitor.rpc import HeartbeatResult
from napg.policy.breaches import Breach

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_MAX_TOKENS = 1024

Intent = Literal["hold", "migrate_to_safe", "pause_for_investigation"]


SYSTEM_PROMPT = """You are NAPG (NetAssure Protocol Guardian), an autonomous \
Protocol Service Assurance agent for the Coinbase Base ecosystem.

# Role and operating envelope

NAPG provides NOC-level reliability assurance for decentralised protocols on \
Base (Ethereum L2, OP Stack). It heartbeats RPC nodes, monitors sequencer \
latency and liquidity-pool health, watches lending-market utilisation, and \
decides whether to autonomously migrate funds to a pre-defined safe contract \
when service-level guarantees degrade.

You are the decision layer. The probes have already executed and the \
threshold evaluator has already produced any Service Level Breach records. \
Your only job is to choose the next action and write a clear rationale a \
compliance reviewer can audit months later.

# The three intents

- `hold` — no autonomous action. Use when protocol state sits within \
acceptable bounds: no breaches, or only transient noise that does not \
threaten the surfaces NAPG is assuring.
- `migrate_to_safe` — move agent-controlled funds to the pre-defined safe \
contract. Use when the breach pattern indicates real degradation. This is \
the highest-cost action; it locks the agent out of the affected surface \
until a human un-pauses it.
- `pause_for_investigation` — suspend autonomous action without moving \
funds. Use when the signal is ambiguous or borderline and a human review \
would meaningfully change the call. Better than `migrate_to_safe` when the \
cost of a false-positive migration outweighs the risk of waiting.

# Decision matrix

Apply these rules in order. The first matching rule wins.

1. **No breaches**: `hold`.

2. **Any `reorg_is_breach`**: `migrate_to_safe`. Chain integrity is the floor \
under every other guarantee. A reorg means transactions you thought were \
settled may have been un-settled. There is no safe assumption to operate \
under while this is true.

3. **`peg_deviation_bps_max` breach where the actual deviation exceeds 100 \
bps**: `migrate_to_safe`. The stablecoin assurance surface is the headline \
product; a 1% peg drop is no longer a tail event you ride out.

4. **`peg_deviation_bps_max` breach below 100 bps actual, with no \
corroborating breach**: `pause_for_investigation`. The system flagged \
something but it is not severe enough on its own to justify the migration \
cost.

5. **`liquidity_required` breach (0x reports no liquidity available)**: \
`migrate_to_safe`. NAPG cannot assure a surface that has no tradeable depth.

6. **Two or more simultaneous breaches across distinct sources** (e.g. \
heartbeat + Aerodrome, or heartbeat + Morpho): `migrate_to_safe`. \
Coincident failures across unrelated surfaces almost always mean a deeper \
incident in flight.

7. **Single non-reorg, non-100-bps breach** on lending utilisation, market \
staleness, latency, or block age, with no other signal: \
`pause_for_investigation`. Worth human eyes but not worth the migration.

8. **Anything that does not cleanly fit the rules above**: \
`pause_for_investigation`. Default to caution.

# Rationale quality

A good rationale:
- Cites the exact rule name(s) that fired (e.g. `reorg_is_breach`, \
`peg_deviation_bps_max`).
- References the observed numeric values from the input where relevant \
(latency in ms, deviation in bps, utilisation in bps, staleness in seconds).
- Explains which decision matrix rule applied and why.
- Is concise — one to three sentences. Reviewers read these in bulk; \
preamble and hedging hurt scannability.

A bad rationale invents state that was not in the input, hand-waves with \
phrases like "appears concerning" without numbers, or restates the rule \
text verbatim instead of explaining why it matters here.

# Confidence calibration

`confidence` is on [0, 1]. Use it honestly:
- 0.95+: the matrix rule applies cleanly and the input is unambiguous.
- 0.75-0.95: the matrix rule applies but at least one input value is near \
a threshold or partially redacted.
- 0.50-0.75: borderline match; the matrix says one thing but a small change \
in input would flip the decision. Often pairs with `pause_for_investigation`.
- Below 0.50: do not submit a decision in this range. Choose \
`pause_for_investigation` and explain in the rationale why the call is \
under-determined.

# Hard rules

- Never invent state that is not present in the input payload.
- Never reference values absent from the input (e.g. "the previous tick \
showed X" when only the current tick is provided).
- Always call the `submit_decision` tool with all four required fields.
- `supporting_breaches` must list the actual `rule` field of each breach \
that drove the decision. Empty when `intent` is `hold`.
- A `pause_for_investigation` is a real product action — it stops the \
agent. Do not use it as a "soft no". Use it when human review is the right \
next step.

# What is NOT your job

You are not picking which fund-migration path to execute, computing gas, \
or signing transactions. The AgentShield validation layer (later phase) \
takes your intent and decides whether the actual transaction is safe to \
sign. Your job ends at the intent + rationale. Trust the downstream gates."""


DECISION_TOOL: dict[str, Any] = {
    "name": "submit_decision",
    "description": (
        "Submit NAPG's autonomous decision after evaluating the current protocol-state "
        "payload. Use the `intent` field for the action, `rationale` for the why, "
        "`confidence` to flag uncertainty, and `supporting_breaches` to list the "
        "breach rules that drove the decision."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["hold", "migrate_to_safe", "pause_for_investigation"],
                "description": "The action the agent intends to take.",
            },
            "rationale": {
                "type": "string",
                "description": (
                    "Brief explanation of why this intent was chosen. Must "
                    "reference specific observed values or breach rule names."
                ),
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Model's confidence in the decision, on [0, 1].",
            },
            "supporting_breaches": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Rule names of breaches that drove this decision. Empty when intent is `hold`."
                ),
            },
        },
        "required": ["intent", "rationale", "confidence", "supporting_breaches"],
    },
}


class CacheMetadata(BaseModel):
    """Anthropic usage stats relevant to prompt caching."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)


class Decision(BaseModel):
    """One reasoning outcome — JSON-safe, audit-log-ready."""

    model_config = ConfigDict(frozen=True)

    intent: Intent
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_breaches: tuple[str, ...]
    model: str
    cache_metadata: CacheMetadata


class ReasoningInputs(BaseModel):
    """The state bundle handed to the reasoner each cycle."""

    model_config = ConfigDict(frozen=True)

    heartbeat: HeartbeatResult | None = None
    liquidity: LiquidityProbe | None = None
    morpho: MorphoPoll | None = None
    breaches: tuple[Breach, ...] = ()


class Reasoner:
    """Wraps the Anthropic SDK call + optional audit-log persistence.

    Inject `client=` to mock in tests. The constructor never embeds the
    API key in the instance dict beyond what the SDK already holds.
    """

    def __init__(
        self,
        api_key: str,
        client: Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        audit_log: AuditLog | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic API key is required (set ANTHROPIC_API_KEY in .env)")
        self._client = client if client is not None else Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._audit_log = audit_log

    def decide(self, inputs: ReasoningInputs) -> Decision:
        user_content = _render_user_message(inputs)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[DECISION_TOOL],
            tool_choice={"type": "tool", "name": "submit_decision"},
            messages=[{"role": "user", "content": user_content}],
        )

        tool_input = _extract_tool_input(response)
        cache_metadata = _extract_cache_metadata(response)
        decision = Decision(
            intent=tool_input["intent"],
            rationale=tool_input["rationale"],
            confidence=float(tool_input["confidence"]),
            supporting_breaches=tuple(tool_input.get("supporting_breaches", ())),
            model=getattr(response, "model", self._model),
            cache_metadata=cache_metadata,
        )

        if self._audit_log is not None:
            self._audit_log.record(
                "decision",
                json.loads(decision.model_dump_json()),
            )

        return decision


def _render_user_message(inputs: ReasoningInputs) -> str:
    """Serialize the input bundle to a JSON document the model can read.

    Frozen pydantic models round-trip cleanly through `model_dump_json`; we
    decode once so the final payload is a single embedded JSON object rather
    than nested strings.
    """
    payload = {
        "heartbeat": json.loads(inputs.heartbeat.model_dump_json())
        if inputs.heartbeat is not None
        else None,
        "liquidity": json.loads(inputs.liquidity.model_dump_json())
        if inputs.liquidity is not None
        else None,
        "morpho": json.loads(inputs.morpho.model_dump_json())
        if inputs.morpho is not None
        else None,
        "breaches": [json.loads(b.model_dump_json()) for b in inputs.breaches],
    }
    return (
        "Current protocol state follows. Decide the next action and call "
        "submit_decision.\n\n```json\n" + json.dumps(payload, sort_keys=True, indent=2) + "\n```"
    )


def _extract_tool_input(response: Any) -> dict[str, Any]:
    """Pull the `submit_decision` tool's input dict out of the response."""
    for block in response.content:
        is_tool_use = getattr(block, "type", None) == "tool_use"
        is_submit = getattr(block, "name", None) == "submit_decision"
        if is_tool_use and is_submit:
            return dict(block.input)
    raise RuntimeError("Anthropic response did not include a submit_decision tool_use block")


def _extract_cache_metadata(response: Any) -> CacheMetadata:
    usage = response.usage
    return CacheMetadata(
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
    )


__all__ = [
    "DECISION_TOOL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MODEL",
    "SYSTEM_PROMPT",
    "CacheMetadata",
    "Decision",
    "Reasoner",
    "ReasoningInputs",
]
