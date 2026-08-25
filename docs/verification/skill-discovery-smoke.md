# Project-local skill discovery smoke test

On 2026-08-25, the installed `codex-cli 0.149.0-alpha.4.3` loaded the repository-local
`$run-offline-data-loop-demo` skill in a read-only, ephemeral call. No demo command or model
arm ran.

Command:

```bash
codex --ask-for-approval never exec --json --ephemeral --ignore-user-config \
  --model gpt-5.6-luna --sandbox read-only -C . \
  '$run-offline-data-loop-demo Do not execute commands or start any model arm. Read the \
  loaded project skill and state: the experiment-start command; what DSPy learns from; \
  how the optimized program is used on a real repair; the final report path; and the \
  remaining machine-wide read-isolation limitation.'
```

Codex returned thread `01a03ab4-f5ae-7263-809b-4033c59e330f` and identified:

- `uv run taxi-demo start`, followed by fixture preparation;
- DSPy learning from observed verifier outcomes and changed files between attempt snapshots;
- execution of the saved DSPy program on real Qwen repair findings;
- `.demo/experiments/<experiment-id>/artifacts/report/comparison.md`;
- random temporary candidate workspaces plus the explicit machine-wide read-isolation limit.

The final response was also written to `/tmp/codex-taxi-skill-smoke-final2.md` on the test
machine. That temporary file is not part of this repository.
