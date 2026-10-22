# Architecture Decision Log

Each entry: ID, title, status, date, decision, reason. Standing rules (D-01…D-04) apply to
every feature unless a later decision names an exception and the reason for it.

---

## D-0 Project context manager

- **Status:** none installed, plan to add
- **Date:** 2026-10-22
- **Decision:** The Project Context System (PCS) is the intended durable memory for this
  project (append-only `.project-memory/events.jsonl` plus a searchable sqlite index).
- **Gap:** PCS was not available at bootstrap. It is not published on PyPI or npm, and no
  source repository or installer was supplied. `.project-memory/` is already gitignored so
  PCS can be dropped in without further changes.
- **Interim:** Checkpoints are written as markdown under `docs/checkpoints/` (committed) so
  they can be imported into PCS once it is installed.
- **Next:** Supply the PCS repo URL or package, install it next to the project, run its
  init, import `docs/checkpoints/*`, then mark this entry Accepted.

---

## D-01 Additive, never destructive

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** Close gaps by ADDING columns, tables, endpoints, pages and settings next to
  what already exists. Forward migrations are additive-only: no `DROP` (table, column,
  constraint, index) and no destructive `ALTER` in a forward migration.
- **Exceptions:** Allowed only when named in a decision entry here with the reason.

## D-02 Reversibility as a design constraint

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** Every schema change ships with a tested downgrade (upgrade → downgrade →
  upgrade round trip). Lifecycle actions (archive, withdraw, reject, expire) hide data;
  they never delete it. New behaviour ships behind a migration or a setting, so turning it
  off restores the previous behaviour exactly.

## D-03 Isolation of in-progress work

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** Every feature is built in a separate git worktree outside the running app
  folder, against a copy of the database, never against the live dev DB.

## D-04 Fail closed on authorization

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** A request with no matching permission is denied. Row scoping (by business
  unit, requisition, or tenant) runs as a repository-layer query filter derived from the
  authenticated principal. It can never be widened or bypassed by request parameters.

---

Never renumber existing IDs. New decisions are appended as D-05, D-06, …
