# Treasury policy

Status: **policy defined now; enforcement is Group F / Phase 5.** Written
2026-06-28. An external review made the case — correctly — that treasury
concentration is an *architecture* input, not a later feature: it changes the
migration, outage, rescue, and dependency assumptions the whole system is built
on. So the limits are stated now even though the agent holds only testnet dust
today and the enforcement code lands with Group F.

## The question that sets everything

Not "how much yield?" but **"what is the maximum acceptable permanent loss?"**
Yield is never free — it stacks smart-contract, protocol, governance, depeg, and
regulatory risk. The treasury policy is written in terms of acceptable loss and
concentration, and yield is whatever is left after those constraints.

## Limits (launch)

| Parameter | Launch value | Rationale |
|---|---|---|
| `max_acceptable_permanent_loss` | **5% of treasury** | The line past which the position is wound down regardless of yield. A stated number, not a vibe. |
| `max_single_issuer_exposure` | **100% (USDC) at launch, with eyes open** | Driven by the 24h Base-outage assumption (below). Revisit before any material balance. |
| `max_single_protocol_exposure` | **40%** | No single DeFi venue (Aerodrome, Morpho, etc.) holds more than 40% once funds are deployed beyond bare USDC. |
| `max_stablecoin_exposure` | **60%** | If/when non-stable assets enter, cap stable concentration too. |
| `min_liquid_reserve` | **enough to cover one full migration + gas** | The rescue must always be fundable. |

These are deliberately conservative and meant to be tightened, not loosened.

## The Base-outage linkage (locked 2026-06-28)

Maximum acceptable Base outage = **24h** (see
[runbooks/infra-outage.md](runbooks/infra-outage.md)). That assumption is what
makes 100% on-Base USDC acceptable *for launch*: if Base is down, the treasury is
frozen but not lost, and a day is tolerable. The dependency chain to watch:

```
max_acceptable_Base_outage  drives  max_single_issuer / on-chain concentration
        24h (launch)         ->     100% on-Base USDC acceptable
        tighten to 6-72h?    ->     need cross-chain / off-chain reserves
```

If the outage tolerance ever tightens, this table changes *first*, then the
deployment strategy follows. Do not change one without the other.

## Concentration reality to disclose

CDP (signing) + Base (chain) + USDC (asset) are all Coinbase/Circle-adjacent.
This is inherent to "building on Base" and a deliberate product choice, but it
means a single-ecosystem incident is correlated across signing, settlement, and
treasury. State this in any risk disclosure rather than pretending the three are
independent.

## Enforcement (Group F / Phase 5)

- A treasury-state poller + a `treasury_concentration_bps` breach when a limit is
  exceeded (same rules-engine + audit-log pattern as every other breach).
- Migration / rebalance actions respect `min_liquid_reserve` and the per-protocol
  caps.
- Reviewed in writing at the Phase 5 mainnet gate alongside the AgentShield
  mainnet policy.

Related: [dependency-register.md](dependency-register.md),
[runbooks/emergency-migration.md](runbooks/emergency-migration.md).
