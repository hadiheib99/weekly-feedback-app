# Development Process

- Tasks are GitHub issues and are completed one at a time.
- Read the acceptance criteria before starting a task and again before closing it.
- Commit work regularly.

GitHub issues are the canonical and only active backlog. `_docs/tasks.md` records the original decomposition but does not override an issue.

## Roles

- PM — grooms a task before anyone implements it and follows `_docs/team/pm.md`.
- Engineer — implements one groomed task and follows `_docs/team/software-engineer.md`.
- QA — checks completed work against its acceptance criteria and follows `_docs/team/qa-engineer.md`.

## Orchestrator

The main session is the orchestrator. It launches the PM, Engineer, and QA as separate agents; it does not groom, implement, or test the task itself.

## Lifecycle

1. Pick the next open GitHub issue.
2. The PM grooms it.
3. The Engineer implements it.
4. QA verifies it.
5. On `FAIL`, return to step 3 with the QA comment as input.
6. On `PASS`, the orchestrator closes the issue.
7. Repeat until the backlog is empty.

## Workflow rules

- Do not skip grooming.
- Process only one issue at a time unless the user explicitly requests parallel work.
- The Engineer does not close issues.
- QA does not fix code; QA only reports `PASS` or `FAIL`.
- The orchestrator closes an issue only after QA reports `PASS` for every acceptance criterion.
- If requirements conflict, record the conflict on the issue instead of guessing.
