# Handover note

A guide for the reviewer: the seven points of "What we expect from you"
([`docs/acceptance.md`](acceptance.md#what-we-expect-from-you)) in order, each
with a link into the repository. This is not a retelling of the README: the
content lives in the files this page links to; here is only the route to them.

## 1. Link to the repository

<https://github.com/FrostWillmott/lastunit>

## 2. What it was built with: which model, which tool, and why

[`README.md` → "Tools and models"](../README.md#tools-and-models). The tool is
Claude Code (CLI); the same section, in the "Why Claude Code" paragraph, says
why it was chosen and why the harness around it is not ported to another tool.
The work was deliberately split across three models in separate sessions, and
the same section says why: a mistake has to survive a different model in a
different session before it reaches the repository. Both audits found defects
that the implementer's own review had passed.

In the decision log: [`DECISIONS.md`](../DECISIONS.md) → "Claude Code as the
tool, and why the harness is not ported" (2026-09-13). One model did not run
through Anthropic: `ANTHROPIC_BASE_URL` points the same harness at
`api.deepseek.com/anthropic`, so no second tool was needed for it.

## 3. Prompts, a decision log or an export of the agent session

- [`agent-sessions/`](https://github.com/FrostWillmott/lastunit/tree/submission-2026-09-14/agent-sessions)
  — session exports: a full `.jsonl` and a short `.md` for each. They are kept
  under the tag `submission-2026-09-14`; removed from `main` on 2026-10-01.
- [`agent-sessions/README.md`](https://github.com/FrostWillmott/lastunit/blob/submission-2026-09-14/agent-sessions/README.md)
  — what did **not** go in and why (forks and continuations of the same work)
  and what was cut before submission (dead local secrets, the test accounts'
  password). Read it before comparing the number of exports with the number of
  sessions.
- [`DECISIONS.md`](../DECISIONS.md) — the decision log: why things are built
  this way and not another. Dated entries, newest first.

## 4. The course of the work over time

- `git log --format='%ad %s' --date=iso` — the timestamp of every commit. The
  work took five days, 10–14 September 2026; the first commit is `efdaea8`,
  2026-09-10 09:59 +0300.
- [`DECISIONS.md`](../DECISIONS.md) — each decision is dated and sits in the
  same change as the code, not added after the fact.
- [`agent-sessions/`](https://github.com/FrostWillmott/lastunit/tree/submission-2026-09-14/agent-sessions)
  — dates in the file names.
- [`docs/plan.md` → "Stages and commits"](plan.md#stages-and-commits) — the
  sequence of commits planned in advance, to compare the plan with the actual
  history.

## 5. Project description: how to deploy it and what state it is in

- **Deploy.** ["Prerequisites"](../README.md#prerequisites) — what to install,
  with versions; ["Run locally"](../README.md#run-locally) — the commands from
  clone to a working app; ["Configuration"](../README.md#configuration) —
  environment variables; ["Testing"](../README.md#testing) — how to run the
  checks.
- **State.** ["State"](../README.md#state) — the table "Expected behaviour
  bullet → proving test → status", including what is not proven. Next to it:
  [`docs/verification-2026-09-12.md`](verification-2026-09-12.md) — a run of
  the assembled app in a browser, separate from the tests, and two independent
  reviews — [`docs/plan-audit-2026-09-10.md`](plan-audit-2026-09-10.md) and
  [`docs/code-audit-2026-09-12.md`](code-audit-2026-09-12.md).

## 6. What would come in the next round

[`README.md` → "Next steps"](../README.md#next-steps) — what did not fit into
the scope and why.

## 7. The template it was built on

[`README.md` → "Tools and models"](../README.md#tools-and-models), first
paragraph. The scaffold is the Claude Code skill
[`.claude/skills/workflow-scaffolding/SKILL.md`](../.claude/skills/workflow-scaffolding/SKILL.md);
it lives in the repository, so what it provides is visible. What the
repository held before the first application commit is listed in
[`docs/plan.md` → "Context"](plan.md#context): tooling, CI, agent rules, an
empty `FastAPI()` and a Vue stub with a single `/api/health` request. The
frontend skeleton itself is mine, but generated with `create-vite`
(`npm create vite`); no one else's templates or ready-made solutions underlie
it.
