# W8 discovery target list (2026-07-20)

Purpose: the who and the how for W8 customer discovery. Built on the positioning
decided in [competitor-teardown.md](competitor-teardown.md) — NAPG protects the
**position holder** (depositor / LP / treasurer) across protocols they do not
control, Base-native, as an operational-assurance service, at a sub-enterprise
price. This list finds the people who live that pain.

Gate (from PLAN.md W8): >= 15 discovery conversations, >= 5 buyers committing
(LOI or paid pilot) before W5 mainnet-cutover effort scales. A no here redirects
W1-W7 rather than being discovered post-launch.

## Ideal customer profile

Someone who: (1) holds real money on Base in protocols they do not operate;
(2) has felt or fears a loss from a protocol they are merely *exposed* to (peg
drop, bad debt, oracle fail, liquidity flight); (3) is too small for a six-figure
Hypernative/Hexagate contract but too big to shrug off a loss; (4) already spends
time or money watching exposure manually. Disqualify: pure retail (<$50k, low
WTP), and protocol teams who only want to defend *their own* contract (that is the
incumbents' lane, not ours).

## Segments and candidate targets

Named orgs are **candidates to qualify, not confirmed leads** — verify current
Base activity and find a warm intro before outreach. Source live lists from
DeepDAO and [DefiLlama treasuries](https://defillama.com/treasuries).

**A. Small/mid DAO treasurers on Base (primary).** Hold treasury + LP + governance
tokens; one exploit in a protocol they are parked in costs real money; no security
budget for enterprise tools. Selection: $1M-$50M treasury, active governance,
Base exposure.
- Candidates: Moonwell, Aerodrome, Extra Finance, Overnight (USD+), Beefy (Base),
  Harvest — plus mid-size DAOs parking treasury in Base yield. (Seamless is
  winding down — deprioritize.)
- Concrete pain to open with: the Feb 2026 Moonwell cbETH liquidation incident
  that harmed 181 borrowers on Base. Ask treasurers if they would have wanted a
  heads-up on that exposure.

**B. Morpho / Base vault curators and risk managers (highest-signal).** They
manage other people's capital across protocols and *feel this pain daily* — their
whole job is exposure risk. Best interviews even if some end up partners or
competitors rather than buyers.
- Candidates: Gauntlet, Steakhouse Financial, Re7 Labs, Block Analitica, Karpatkey
  (DAO treasury manager). Galaxy just launched institutional Morpho vaults — a
  direct read on institutional risk framing on Base.
- Treat as insight + potential channel partners, not just prospects.

**C. Emerging Base-focused funds / onchain asset managers (sub-enterprise).**
Hold positions across Base DeFi; want monitoring/risk/reporting; priced out of
enterprise vendors. Selection: small-to-mid AUM, Base-native strategies.

**D. OpenZeppelin Defender re-homing customers (time-boxed wedge).** Defender shut
down 2026-07-01; its managed-response customers need a replacement *now*. Not all
are Base, but the Base-exposed ones are warm and urgent. Find them via the Defender
sunset threads, OZ forum, and Base builder channels.

**E. AI-agent / autonomous-trading platforms on Base.** Hold funds and run
strategies unattended — they understand and value autonomous safety, and speak
NAPG's language (agents, policy, audit). From the original W8 target set.

## How to reach them

- **Farcaster** — Samuel's own Base-native distribution; warm, on-platform, and the
  Cast loop (W7) doubles as a discovery funnel.
- **Governance forums** — Commonwealth / Discourse / Tally / Snapshot; treasurers
  post publicly, easy to reference a real proposal.
- **Base builder community** — Base Discord/Telegram, ecosystem calls, warm intros.
- **Curator/fund channels** — Gauntlet/Steakhouse/Karpatkey publish; engage on their
  public risk posts.
- **Sourcing** — DeepDAO (treasury size, governance activity), DefiLlama treasuries.

## Prioritization

1. **B (curators/risk managers)** first — richest insight, sharpens the pitch, may
   open channel partnerships.
2. **A (Base DAO treasurers)** — the primary buyer; run in parallel using the
   Moonwell incident as the opener.
3. **D (Defender refugees)** — time-boxed; hit while the migration is fresh.
4. **C, E** — after the pitch is sharpened by B/A.

## Interview script (loss-led; do not pitch)

Mom Test discipline: talk about their life, not your idea; ask about past behavior,
not hypotheticals; no "would you pay for X." Commitment is time/money/reputation,
not a compliment.

1. Walk me through where your treasury/positions sit on Base today. Which protocols?
2. Who watches that exposure? At 3am, on a weekend?
3. Tell me about the last time a protocol you were exposed to had a scare or a
   loss. What happened? How did you find out?
4. What did that cost you — dollars, hours, standing with your DAO/LPs?
5. What did you do about it afterward? What did you change?
6. How do you monitor exposure now — tools, dashboards, someone's job?
7. Do you pay for any monitoring, security, or risk service today? Which, how much?
   (Hypernative, Hexagate, Defender, BlockSec, custom?)
8. What did you look at when you last shopped for this, and why did you pick or
   reject it?
9. If exposure crossed a danger line, what should happen — an alert, a documented
   playbook you run, or an automatic exit? Who is allowed to pull that trigger?
10. Who signs off on a tool like this, and out of what budget?
11. What would have to be true for you to run a paid pilot in the next 60 days?
12. Close (only if real interest): would you commit to a paid pilot / sign an LOI?
    If not, what is missing? (A soft "looks cool" is a no — record it as one.)

## Tracking

Log every conversation. One row each; the honest status is the point.

| Org | Segment | Contact/channel | Date | Pain (real $/hrs?) | Pays today? | Trigger pref | Commit? | Notes |
|---|---|---|---|---|---|---|---|---|

Buyer signals: a specific past loss with a number; existing spend on monitoring;
a named budget owner; asks about pilot mechanics. Disqualifiers: only vague
interest; wants free; only wants to protect their own contract (send to Hypernative);
no money at stake.
