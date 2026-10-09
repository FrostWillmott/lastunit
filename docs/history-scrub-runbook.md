# History scrub runbook

How `agent-sessions/` was removed from git history on 2026-10-07, and how to
replay the remaining steps. The directory held session exports containing a
local home path and an employer name, so it was scrubbed rather than kept.

## What the leak actually was

- The tag `submission-2026-09-14` and its GitHub release **were public**: both
  existed on GitHub and were deleted from the web UI on 2026-10-07, which is
  why `git ls-remote --tags origin` was already empty when the scrub ran.
  Anyone who fetched or downloaded the release before that may still hold a copy.
- The real public exposure was two things:
  1. `agent-sessions/` blobs in `origin/main`'s git history (committed in
     September, removed from the tree on 2026-10-01, but still reachable via
     `git log`/`git checkout`).
  2. 28 GitHub PR head refs (`refs/pull/*/head`), which still reach the blobs
     and only GitHub Support can remove (see the last section).

## Part A — Push the already-rewritten local `main`

Done on 2026-10-07: `origin/main` went from `ca302d5` to `faf0378` (the scrubbed
history plus two commits on top). The rules were switched off through the API
instead of the UI (`gh api -X PUT repos/FrostWillmott/lastunit/rulesets/23276082
-f enforcement=disabled`, then `=active`), and the ruleset was compared against a
saved copy afterwards. The first run after the push failed only in `audit`, on
advisories published that day; PR #29 fixed it and `main` was green at `2829bc2`.
The `main-clean` branch was deleted once it was part of `main`.

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

# 1. Drop the tag (already deleted on GitHub; a fresh clone may not have it)
git tag -d submission-2026-09-14 || true

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

PRs #1–#28 still hold the blobs through `refs/pull/<n>/head` (checked on
2026-10-07: #1–#28 reach `agent-sessions/`; #29 onwards were opened after the
rewrite and are clean). Until they are purged the leak is reduced, not
gone: anyone can `git fetch origin refs/pull/22/head` and recover the files.

An owner cannot remove these refs. GitHub has no way to delete a pull request,
in the UI or the API, and closing or merging one leaves `refs/pull/<n>/head` in
place; all 28 are already closed or merged. Only GitHub Support can delete the
PRs and garbage-collect the unreachable objects. Recreating the repository would
also work, but it loses every PR, the CodeQL and Actions history and the ruleset,
so it was rejected.

Status: filed on 2026-10-07 through GitHub's "Request pull request removals"
virtual agent (support.github.com/contact → Repositories; it created a ticket and
says it will report back once the PRs are removed). Do not use the "Deletions"
category on that form: it is for deleting or purging a whole repository.
Answers given to the agent: multiple PRs; `FrostWillmott/lastunit`; PRs 1–28;
sensitive data, already removed from history; rotation does not apply, because
the data is a home path and an employer name, not a credential. The reason
supplied:

> The leaked data is not a credential, so it cannot be rotated: the
> agent-sessions/ directory contained session exports with a local home path and
> an employer name. I removed it from all branch history with git filter-repo and
> force-pushed main on 2026-10-07 (old tip ca302d5, new tip faf0378), but PRs
> #1-#28 still reference the old commits via refs/pull/*/head, so the files remain
> fetchable. Please delete PRs #1-#28 and garbage-collect the unreachable objects.
> PRs #29 and later were created after the rewrite and should be kept.

Follow-up (ticket #4833169, 2026-10-09): before deleting anything, Support asked
for the full SHA of the commit that first introduced the sensitive data. They use
it to check that no other ref keeps the commit alive, because otherwise it would
survive garbage collection. We replied with `d723211d55501bd8bf729839f585db4e312020fc`
("docs: save the first agent session export and log"), the first commit in
`refs/pull/*/head` that adds a home path under `agent-sessions/`. Its parent
`efdaea8` adds only the directory's README. Neither commit is reachable from any
branch or tag. To find the commit again:

```bash
git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'
git log --reverse --format='%H %s' --glob='refs/remotes/origin/pr/*' -- agent-sessions/ | head -3
```

After Support confirms, check that no PR ref reaches the directory any more:

```bash
git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*' --prune
for ref in $(git for-each-ref --format='%(refname)' refs/remotes/origin/pr/); do
  [ "$(git rev-list --count "$ref" -- agent-sessions/)" -gt 0 ] && echo "LEAK $ref"
done   # no output = clean
```
