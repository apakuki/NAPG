# Manual test procedures — Phase 0 (Scaffolding)

Verify the repo, agent, frontend, scripts, and CI all run green on a clean machine. Run on macOS, Linux, or Windows (WSL) — call out the OS in the result notes if it matters.

Prerequisites: `git`, `uv`, `node` 20+, `npm`, ability to clone from the repo origin. No `.env` keys are needed for Phase 0.

---

## 0.1 — Fresh-clone install timing

**Goal:** confirm a new user can clone -> install -> run in under 10 minutes.

**Steps:**
```bash
cd /tmp
time git clone https://github.com/apakuki/NAPG.git napg-fresh
cd napg-fresh/agent && time uv sync
cd ../frontend && time npm install
```

**Expected:**
- [x] Clone completes successfully.
- [x] `uv sync` reports "Resolved N packages" with no errors; `.venv/` created.
- [x] `npm install` reports "added N packages" with no errors.
- [x] Total wall time under 10 minutes on a reasonable connection.

**Failure modes:**
- `uv sync` complains about Python version -> `uv python install 3.12`.
- `npm install` peer-dep errors -> confirm `node --version` is 20+.
- Network timeouts -> retry; if persistent, check corporate proxy.

**Result notes:** 2026-05-17 (macOS 24.5.0, M-series, warm uv + npm caches): git clone 1.7s, `uv sync` 0.9s (75 packages resolved), `npm install` 5.4s (added ~376 packages). Total ~8s. Comfortably under the 10-minute budget; first-time-ever runs on a cold machine will be slower but still well within budget.

---

## 0.2 — Agent unit tests and lint

**Goal:** the agent toolchain runs green with no source code yet beyond the smoke test.

**Steps:**
```bash
cd agent
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

**Expected:**
- [x] `pytest` reports `1 passed`.
- [x] `ruff check` reports `All checks passed!`.
- [x] `ruff format --check` reports `1 file already formatted` (or similar).

**Failure modes:**
- `ModuleNotFoundError: napg` -> `uv sync --reinstall`.
- Ruff format diff -> `uv run ruff format .`, commit.

**Result notes:** 2026-05-17 (macOS 24.5.0, Python 3.13.9): `1 passed in 0.01s`; ruff `All checks passed!`; format `4 files already formatted`.

---

## 0.3 — Frontend lint, unit tests, build

**Goal:** the frontend toolchain runs green with the placeholder landing page.

**Steps:**
```bash
cd frontend
npm run lint
npm run test
npm run build
```

**Expected:**
- [x] `npm run lint` exits 0 with no errors.
- [x] `npm run test` reports `Tests  1 passed (1)`.
- [x] `npm run build` reports `Compiled successfully` and generates static pages.

**Failure modes:**
- Build complains about missing module -> `rm -rf .next node_modules && npm install && npm run build`.
- Vitest can't find `@/*` paths -> check `vitest.config.ts` alias matches `tsconfig.json` `paths`.

**Result notes:** 2026-05-17 (Next.js 16.2.6, Node 26): lint clean; vitest `1 passed`; build `Compiled successfully in 1805ms`, 4 static pages generated (`/`, `/_not-found`).

---

## 0.4 — Dev server smoke test

**Goal:** the Next.js landing page actually renders.

**Steps:**
```bash
cd frontend
npm run dev
# in another terminal:
curl -sS http://localhost:3000 | grep -i "NetAssure Protocol Guardian"
```

Then open `http://localhost:3000` in a browser.

**Expected:**
- [x] Dev server starts and reports "Ready" within ~5 seconds.
- [x] `curl` returns at least one line containing "NetAssure Protocol Guardian".
- [ ] Browser shows the title, the tagline, and the "Phase 0 — scaffolding" line. _(curl confirmed; browser visual not exercised in this run)_
- [ ] Browser devtools console shows no errors. _(deferred — needs a human at a browser)_

**Stop:** `Ctrl+C` in the dev-server terminal.

**Failure modes:**
- Port 3000 in use -> `PORT=3001 npm run dev`, retry on the new port.
- Page renders default Next.js content -> stale build, `rm -rf .next` and retry.

**Result notes:** 2026-05-17: server ready, `curl` returned 1 line matching "NetAssure Protocol Guardian".

---

## 0.5 — `scripts/start.sh` requires `.env`

**Goal:** start script correctly refuses to run without an `.env` file.

**Steps:**
```bash
# from repo root, no .env present
./scripts/start.sh
```

**Expected:**
- [x] Script exits non-zero with the message `missing .env — copy .env.example and fill in keys`.

**Failure modes:**
- Script runs anyway -> the guard is broken; check the `if [ ! -f .env ]` block in `scripts/start.sh`.

**Result notes:** 2026-05-17: exit=1 with the expected message.

---

## 0.6 — Secrets handling

**Goal:** confirm `.env` cannot be accidentally committed and `.env.example` documents every required key.

**Steps:**
```bash
cd /tmp/napg-fresh   # or your working copy
cp .env.example .env
echo "FAKE_SECRET=should_never_be_committed" >> .env
git status
git check-ignore -v .env
```

**Expected:**
- [x] `git status` does not list `.env` as untracked or modified.
- [x] `git check-ignore -v .env` prints a line referencing `.gitignore`.
- [x] `.env.example` contains entries for: `ANTHROPIC_API_KEY`, `CDP_API_KEY_NAME`, `CDP_API_KEY_PRIVATE_KEY`, `CDP_WALLET_ID`, `BASE_RPC_URL`, `BASE_SEPOLIA_RPC_URL`, `TENDERLY_*`, `ZEROX_API_KEY`, `NEYNAR_API_KEY`, `FARCASTER_SIGNER_UUID`, `NAPG_NETWORK`, `NAPG_AUDIT_DB`.

**Cleanup:**
```bash
rm .env
```

**Failure modes:**
- `.env` appears in `git status` -> `.gitignore` not picking it up; check the file is at repo root and the pattern matches.

**Result notes:** 2026-05-17: `.env` did not appear in `git status`; `git check-ignore -v .env` returned `.gitignore:44:.env`. All required keys present in `.env.example`.

---

## 0.7 — CI green on push

**Goal:** GitHub Actions runs both pipelines and they pass.

**Steps:**
- Push the current branch (or open a draft PR).
- Visit the Actions tab on GitHub.

**Expected:**
- [x] A workflow run named "CI" appears within ~30 seconds.
- [x] All three jobs (`agent (python)`, `frontend (next.js)`, `security scans`) report green.
- [x] Total run time under 5 minutes.

**Failure modes:**
- `uv` step fails -> ensure `astral-sh/setup-uv@v3` is reachable; check the workflow file for typos.
- `npm ci` fails on lockfile -> regenerate `package-lock.json` locally with `npm install`, commit.
- Tests pass locally but fail in CI -> usually a Node or Python version mismatch; pin in the workflow.

**Result notes:** 2026-05-17, commit `b90ef89`: CI run 25976499120 all three jobs green (agent, frontend, security scans).

---

## 0.8 — Repo hygiene

**Goal:** the committed tree contains nothing it shouldn't.

**Steps:**
```bash
git ls-files | grep -E '(node_modules|\.venv|\.env$|\.next/|audit\.db)' || echo "clean"
git log -1 --stat
```

**Expected:**
- [x] First command prints `clean`.
- [x] Last-commit stat shows only source, config, and lockfiles; no large binary blobs.

**Failure modes:**
- Forbidden paths appear -> `git rm --cached <path>`, commit; update `.gitignore` if missing.

**Result notes:** 2026-05-17: `clean`; last commit `333f818` (PLAN.md + manual-tests docs only).

---

## Sign-off checklist

- [ ] All procedures above completed (or skipped with a documented reason).
- [ ] Any deviations recorded in result notes.
- [ ] Security baseline for Phase 0 in [PLAN.md](../../PLAN.md) reviewed and checked.
- [ ] User has signed off in chat or in a commit message.
