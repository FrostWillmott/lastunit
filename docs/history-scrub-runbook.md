# History scrub runbook

How `agent-sessions/` was removed from git history on 2026-10-07, and how to
replay the remaining steps. The directory held session exports containing a
local home path and an employer name, so it was scrubbed rather than kept.

## What the leak actually was

- The tag `submission-2026-09-14` was **local-only** — it was never pushed to
  `origin` (`git ls-remote --tags origin` was empty). Deleting it changed
  nothing public.
- The real public exposure was two things:
  1. `agent-sessions/` blobs in `origin/main`'s git history (committed in
     September, removed from the tree on 2026-10-01, but still reachable via
     `git log`/`git checkout`).
  2. 28 GitHub PR head refs (`refs/pull/*/head`), which still reach the blobs
     and can only be removed by deleting those PRs (or GitHub Support).

## Part A — Push the already-rewritten local `main`

The local repository is already scrubbed: `main` = `dbc33c2`, `origin/main`
still at `ca302d5`.

1. **Relax the branch rules** (GitHub → repo `Settings` → the ruleset protecting
   `main`; the push error links to `…/rules?ref=refs/heads/main`). Uncheck
   "Require a pull request before merging" and "Block force pushes"; uncheck the
   required status checks too if they would block a history rewrite.

2. **Push:**
   ```bash
   git push --force-with-lease origin main
   ```
   If the lease is stale, `git fetch origin && git push --force-with-lease origin main`.

3. **Confirm CI is green** — the repo's rule is that a push is not done until the
   run is green and no job is missing:
   ```bash
   gh run list --branch main --limit 5
   ```

4. **Re-arm the rules** exactly as they were.

## Part B — Full replay from a clean clone

```bash
git clone git@github.com:FrostWillmott/lastunit.git lastunit-scrub
cd lastunit-scrub

# 1. Drop the (local-only) tag
git tag -d submission-2026-09-14

# 2. Strip agent-sessions from ALL history
git filter-repo --path agent-sessions --invert-paths --force
#    (--force: the clone isn't "fresh" in filter-repo's sense; it also
#     removes the origin remote on success)

# 3. Re-point commit SHAs the rewrite invalidated
#    - docs/handover.md: "first commit is `efdaea8`" -> new `git rev-list --max-parents=0 HEAD`
#    - docs/history/code-audit-2026-09-12.md: add a "pre-scrub SHAs" note
#    - DECISIONS.md: add a dated entry noting SHAs were re-assigned
#    (see commits d22f524 and dbc33c2 for the exact wording)

# 4. Verify the scrub is real
git rev-list --all --objects | grep -c 'agent-sessions/'   # must print 0

# 5. Re-add the remote and push (after relaxing the rules, per Part A)
git remote add origin git@github.com:FrostWillmott/lastunit.git
git push --force-with-lease origin main
```

## Gotchas

1. `git filter-repo` refuses on a non-fresh repo — `--force` is required.
2. It removes the `origin` remote on success — re-add it before pushing.
3. It rewrites *every* commit SHA, not just the ones touching `agent-sessions/`,
   so the SHAs cited in docs (`efdaea8`, `2dae4ad`, ~15 in the code audit) all
   break and need re-pointing or a "pre-scrub" note.
4. Branch protection blocks the whole push — the `remote rejected` error is a
   rules violation, not something git can fix.

## Residue that no git command reaches

The 28 PR head refs still hold the blobs. Delete those PRs (GitHub UI,
`gh pr close` + delete, or GitHub Support for a hard purge). Until then the leak
is reduced, not gone: a reader can still
`git fetch origin refs/pull/22/head` and recover the files.
