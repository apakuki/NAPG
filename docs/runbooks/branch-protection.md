# Branch protection on `main`

Status as of 2026-06-02: **decided, pending GitHub Pro upgrade.**

`main` has had no server-side protection since the Phase 0 deferral
(2026-05-17) — direct push allowed, history rewritable. The revisit
trigger fired when a second collaborator with push access landed
(`[removed]`, confirmed to be [removed]). With more than one person able
to push, "solo-dev mode" no longer justifies the deferral, so we are
enabling a protection ruleset.

## Why a ruleset and not classic branch protection

This repo is **private on the Free plan**. Both classic branch
protection and rulesets return HTTP 403:

> Upgrade to GitHub Pro or make this repository public to enable this
> feature.

Decision (2026-06-02): **upgrade `apakuki` to GitHub Pro** (~$4/mo) and
keep the repo private, rather than make it public before launch. Pro
unlocks rulesets on private repos.

## Prerequisite (manual, owner-only)

Upgrade the account at <https://github.com/settings/billing> ->
**Plans** -> GitHub Pro. The `gh` CLI cannot change billing. Confirm:

```bash
gh api user --jq '.plan.name'        # expect: "pro"
gh api repos/apakuki/NAPG/rulesets   # expect: [] (200), not 403
```

## Apply the ruleset

Once Pro is active:

```bash
gh api -X POST repos/apakuki/NAPG/rulesets \
  --input docs/runbooks/main-protection-ruleset.json
```

The payload (`main-protection-ruleset.json`) enforces, on the default
branch (`~DEFAULT_BRANCH` = `main`):

- **No direct push** — changes must land via pull request.
- **>=1 approving review** before merge, stale approvals dismissed on a
  new push.
- **Required status checks** (branch must be up to date first):
  `agent (python)`, `frontend (next.js)`, `security scans` — the three
  jobs from `.github/workflows/ci.yml`.
- **No force-push** (`non_fast_forward`) and **no branch deletion**.
- **No bypass actors** — the rules apply to the owner too.

## Operational caveat: self-approval

GitHub does not let you approve your own pull request. With
`required_approving_review_count: 1` and two collaborators, every PR
Samuel opens needs [removed]'s approval and vice versa. For a two-person
project that is the intended check. If it proves too heavy, two knobs:

- Add an emergency owner bypass: append to `bypass_actors`
  `{ "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" }`
  (RepositoryRole id 5 = Admin), which lets an admin merge without the
  review while still routing through a PR.
- Or drop `required_approving_review_count` to `0` to keep the PR + CI
  gate without a human review requirement.

Apply edits by `PUT`ting the updated JSON to
`repos/apakuki/NAPG/rulesets/{id}`.

## Verify

```bash
# Ruleset is active:
gh api repos/apakuki/NAPG/rulesets --jq '.[] | {name, enforcement, id}'

# Direct push is now refused (run on a throwaway commit):
git push origin main      # expect: rejected, "Changes must be made through a pull request"
```

## Teardown

```bash
RID=$(gh api repos/apakuki/NAPG/rulesets --jq '.[] | select(.name=="protect-main") | .id')
gh api -X DELETE repos/apakuki/NAPG/rulesets/$RID
```
