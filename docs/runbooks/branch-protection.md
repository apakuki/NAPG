# Branch protection on `main`

Status: **not currently enabled — solo-dev mode.** A protection ruleset
was briefly active on `main` (enabled 2026-06-02 via GitHub Pro) and then
removed when the project returned to a single maintainer. With one
person on the repo, a required-review gate is unsatisfiable (you cannot
approve your own PR), so `main` is back to direct push and workstation
hygiene is the active control, consistent with the Phase 0 accepted
risk. The steps below are retained so protection can be re-enabled
quickly if another collaborator ever joins.

## Why a ruleset and not classic branch protection

This repo is **private on the Free plan**. Both classic branch
protection and rulesets return HTTP 403 unless the account is on GitHub
Pro (or the repo is made public):

> Upgrade to GitHub Pro or make this repository public to enable this
> feature.

`apakuki` was upgraded to GitHub Pro on 2026-06-02, which unlocks
rulesets on private repos; Pro remains active even though the ruleset
has since been removed.

## Re-enable: apply the ruleset

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

GitHub does not let you approve your own pull request. The
`>=1 approving review` rule therefore only works with two or more
collaborators; with a single maintainer it blocks every merge. If
re-enabling solo, either drop `required_approving_review_count` to `0`
(keep the PR + CI gate without a human review requirement) or add an
admin bypass:

- Append to `bypass_actors`:
  `{ "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" }`
  (RepositoryRole id 5 = Admin), which lets an admin merge without the
  review while still routing through a PR.

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
