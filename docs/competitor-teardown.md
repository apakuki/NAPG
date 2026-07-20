# Competitor teardown (W8, 2026-07-20)

Purpose: decide NAPG's positioning before buyer conversations. One question drives
it — given who already exists, what does NAPG credibly own? The honest answer
reshapes the pitch and the roadmap.

## The landscape

| Player | What they do well | Who they sell to | Chains | The seam they leave |
|---|---|---|---|---|
| **Hypernative** | Real-time detection across 300+ risk types; automated onchain response bound to detection (pause / pre-staged exit / pre-tx block). 99.5% hack detection, <0.001% FP, $3B saved, $100B+ protected. | Enterprises, exchanges, large protocols, institutional custody (Bitwise, Fordefi, Utila). Six-figure contracts. | 75+ | Protects the **protocol's own contracts** and enterprise custody. Not embedded in Base's consumer/mini-app surface; not priced for sub-enterprise. |
| **Hexagate (Chainalysis)** | ML threat detection + automated actions (pause, block, withdraw); >98% detected pre-exploit. Acquired by Chainalysis (~$60M) — now bundled with compliance/remediation. Customers incl. Coinbase, Consensys. | Protocols, exchanges, chains/foundations, enterprises. Enterprise sales motion. | 75+ | Same protocol-defends-itself model, now inside a compliance giant. Heavy, top-down; nothing for the individual position-holder. |
| **BlockSec Phalcon** | Mempool-stage attack detection + **automatic block** via gas-bidding front-run; 200+ attack signatures; ~$20M rescued. Has an LP-side "auto-withdraw on hack" feature. | Primarily protocol teams; some LP protection. | Multi-chain | LP auto-withdraw exists but is secondary to the protocol-team GTM; not Base-native, not an operational-assurance service. |
| **Forta** | Sequencer-layer firewall (FORTRESS neural net), sub-block tx prevention for rollups; decentralized audit trail on Forta Chain. Live on Celo, Ink; RaaS integrations. | **Chains / rollups** (infrastructure buyer), not end-users. | Rollup-level | Sells to the chain, not the depositor or DAO. No position-level product; not on Base's sequencer. |
| **OpenZeppelin Defender** | Monitor + Autotasks + Relayer + Incident-Response scenarios (manual or auto-triggered). The reference managed-response toolkit. | Protocol teams / devs. | Multi-chain | **Shutting down July 1, 2026** (pivot to open-source Relayers/Monitor). Its managed-service customers now need a home. |
| **DeFiLlama** | Free, read-only analytics: TVL, yields, liquidations, oracle TVS across 7000+ protocols / 500+ chains; open API. | Everyone (free). | 500+ | Data baseline, not protection. No alerting-as-a-service, no action, no per-position assurance. Use it as a feed, not a rival. |

## What the data forces us to admit

1. **"Autonomous protection on threat" is not a NAPG moat.** Hypernative, Hexagate,
   and BlockSec already do detect-then-act at scale, multichain, better-funded, with
   detection track records (99.5% / >98% pre-exploit) NAPG cannot match on labeled
   attack data. Do **not** position on "detect the novel exploit faster" or "we pause
   contracts" — that is a losing fight against incumbents' core competency.
2. **Every serious incumbent defends the protocol's own contracts.** The buyer is the
   protocol team pausing its own code, or an enterprise custody desk. The **depositor /
   LP / DAO treasurer with exposure across protocols they do not control** is
   under-served — BlockSec's LP auto-withdraw is the only nod to it, and it is secondary.
3. **The incumbents are enterprise-priced and enterprise-shaped.** Six-figure contracts,
   top-down sales. Small-to-mid DAOs and emerging funds that hold real money sit below
   that line with no good option. (Retail stays out of scope — confirmed low WTP.)
4. **OZ Defender's July 2026 shutdown is a live wedge.** A known managed-response
   product just left the market weeks ago. Its customers are actively re-homing — a
   timely discovery target.
5. **No incumbent is Base-native.** None is embedded in the Base App mini-app surface,
   Basenames/SIWF, CDP MPC wallet, sponsored gas, Builder Code, or x402 agent-to-agent
   payments. That integration depth is not something a multichain enterprise vendor will
   build for one L2.

## Positioning decision

NAPG does not win on detection. It wins on the seams the incumbents structurally leave.
Position on the **intersection** of four things — no single one is defensible alone, the
combination is:

1. **Position-holder-side, not protocol-side.** Protect the depositor / LP / DAO
   treasury's exposure *across* protocols they do not own. This is the clearest open
   lane and the opposite of the incumbents' protocol-defends-itself model.
2. **Base-native depth and distribution.** Lean into everything a multichain vendor
   won't: Base App mini-app discovery, Basenames/SIWF, CDP MPC wallet + sponsored gas,
   Builder Code rewards, x402. Distribution *is* the moat here, not the algorithm.
3. **Operational assurance, not a detection feed.** Sell the thing Samuel is uniquely
   credible on — NOC-grade runbooks, incident response, permanent audit trail, SLA
   thinking — as a managed *service assurance* layer. This is a trust/GTM wedge, not a
   tech claim, and it is where OZ Defender's orphaned customers could land.
4. **Sub-enterprise price tier.** Serve small/mid DAO treasurers and emerging funds
   priced out of Hypernative/Hexagate contracts.

## Consequences for the pitch and roadmap

- **Pitch:** "We protect *your* position across the protocols you're exposed to on Base,
  with a documented playbook and an audit trail you can hand to your board" — not "we
  detect exploits." Lead with the depositor/treasurer's fear of loss, not the pipeline.
- **Wedge product (ties to W8):** high-signal, position-level alerts + a manual
  safe-migration playbook. Autonomous migration stays sequenced after trust (and after
  the W9 custody/regulatory question), because it is where incumbents are strongest and
  the liability is highest — not a place to fight on day one.
- **Do not claim** best-in-class threat ML or multichain coverage. Lean on Tenderly
  simulation + AgentShield policy + Base-native depth instead.
- **Discovery targets (W8):** small/mid DAO treasurers, emerging Base-focused funds, and
  OZ Defender's re-homing customers. Test whether position-holder-side + Base-native +
  operational-assurance clears a paid-pilot bar with >=5 of them.

## References

- Hypernative — hypernative.io (platform, automated incident response, $100B/75+ chains)
- Hexagate / Chainalysis acquisition — chainalysis.com/blog/chainalysis-hexagate-announcement; decrypt.co/297729
- BlockSec Phalcon — blocksec.com/phalcon/security (mempool blocking, LP auto-withdraw)
- Forta Firewall — forta.org/firewall; docs.forta.network (sequencer-layer, rollup buyer)
- OpenZeppelin Defender — docs.openzeppelin.com/defender (shutdown 2026-07-01)
- DeFiLlama — defillama.com (free read-only analytics baseline)
