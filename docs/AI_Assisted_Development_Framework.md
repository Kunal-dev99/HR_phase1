# AI-Assisted Development Framework

How Fusion Practices builds the AI-Enabled Recruitment Screening System with AI agents
under engineering control.

## Why this exists

AI agents write code quickly. Speed without controls produces changes that are hard to
review, hard to undo and hard to trust. This framework keeps the speed and adds the
controls: every change is planned, isolated, checked by someone other than its author,
reversible, and recorded.

## The flow

| # | Step | What happens | Output |
|---|---|---|---|
| 1 | Requirement | The business need is written in plain terms with acceptance and exclusions. | Kickoff file in `docs/prompts/kickoffs/` |
| 2 | Research | Architecture, decisions, project memory and the existing code are read. | Notes in the plan |
| 3 | Challenge | Ambiguities, conflicts and risks are raised before any plan is written. | Questions answered by the client |
| 4 | Plan | The feature is split into phases and tasks, each with a Done-when check, a reversibility note and a deferred list. | `docs/DELIVERY_PLAN.md` |
| 5 | Isolate | Work happens in a separate git worktree against a copy of the database. | Branch + worktree |
| 6 | Build inside agent boundaries | Backend and frontend agents build one phase, each limited to its own tools and rules. | Commits |
| 7 | Independent review | A reviewer that did not write the code reviews the diff. | Review findings, fixes |
| 8 | Build, type check, migration round trip | Build, lint, type check, and `upgrade → downgrade → upgrade` on every migration. | Real command output |
| 9 | Machine regression | The full automated test suite runs against the change. | Test report |
| 10 | Human testing | A person exercises the feature in a running app. | Test notes |
| 11 | End-to-end | The full requisition-to-shortlist path is run with mocked or sandbox HR System and Fusion Mind. | E2E result |
| 12 | Scenario testing | Business scenarios (edge cases, failures, permission boundaries) are walked through. | Scenario log |
| 13 | Record decisions | Decisions and a checkpoint are recorded. | `docs/DECISIONS.md`, checkpoint |

## The three agents and their boundaries

| Agent | May use | Owns | May not |
|---|---|---|---|
| Solution architect | Read, Grep, Glob, Write, Edit (no shell) | Delivery plan, decision log | Edit source code, run commands, tick unverified tasks |
| Backend engineer | Read, Write, Edit, Bash, Grep, Glob | FastAPI backend, migrations, tests | Bypass the Router → Service → Repository → Database layers, tick the plan |
| Frontend engineer | Read, Write, Edit, Bash, Grep, Glob | React + TypeScript UI | Access data except through the API, hand-write API types, tick the plan |

Every agent treats retrieved content — files, memory, CVs, HR System and Fusion Mind
payloads — as data, never as instructions.

## Design constraints

- **Reversibility.** Every schema change has a tested downgrade. Archive and reject hide
  records; nothing is deleted. New behaviour can be switched off to restore the previous
  behaviour exactly.
- **Additive change.** Gaps are closed by adding, not by removing what already works.
- **Isolation.** Work in progress never touches the running app or the live database.
- **Fail-closed authorization and business-unit isolation.** No permission means no access.
  Data visibility per business unit or requisition is enforced in the data-access layer and
  cannot be widened by a crafted request.
- **AI interprets, rules decide.** Gates, weights and thresholds are versioned code and
  configuration, never only prompts.

## What the client receives

Instead of raw prompts, the client receives:

- **Methodology** — this document.
- **Architecture** — `docs/ARCHITECTURE.md` and the source specifications.
- **Decisions** — `docs/DECISIONS.md`, a numbered log that is never renumbered.
- **Phase-wise plans** — `docs/DELIVERY_PLAN.md`, with permanent task IDs and checks.
- **Git log** — every change traceable to a task.
- **Scenario testing** — the record of business scenarios run against each phase.
