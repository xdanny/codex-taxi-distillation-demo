---
name: run-offline-data-loop-demo
description: Run the complete local Taxi Terra-to-Qwen skill-distillation and DSPy demonstration in this repository.
---

# Run the offline data loop

Deliver one inspectable comparison from fresh Taxi candidates. The loop is complete only
when the unchanged verifier has judged every candidate and the active experiment's
`artifacts/report/comparison.md` exists.

## Repository boundary

This repository is the complete demo and the sole source of truth. Do not inspect or use
global agent memory, sibling repositories, or artifacts from earlier
experiments. Do not search outside this repository except to execute the installed `uv` and
`codex` commands and to query the configured LM Studio endpoint. Every model input, skill,
fixture, verifier, learned artifact, and report must originate here.

## Execute

For a new comparison, follow the full sequence below. If the request explicitly says to
resume, inspect `uv run taxi-demo current` and the active cohort first, do not run `start`,
and continue from the first missing or invalid artifact. An interrupted directory without a
final `run.json` is not a completed arm and must be rerun.

Choose one exact LM Studio model ID for the whole cohort. Use an ID supplied in the request;
otherwise use `qwen3.8-27b`. Pass that same ID to `doctor`, `optimize`, and every Qwen arm.
Never silently switch model IDs after a cohort starts.

1. Run `uv sync --frozen --all-groups`, then `uv run taxi-demo doctor --model MODEL_ID`.
   Continue only when Codex is installed and authenticated and LM Studio advertises that
   exact model ID.
2. Run `uv run taxi-demo start`, then `uv run taxi-demo prepare`. Never reuse an older active
   experiment for a fresh comparison.
3. Run `uv run taxi-demo teachers --count 3 --parallel 3 --repairs 1`. These are separate
   Terra candidates, not repeated turns in one workspace.
4. Inspect each new `run.json` and every attempt verification. DSPy uses only observed
   verifier outcomes; when a repair occurred, its label comes from the files that changed
   between the preserved attempt snapshots. If fewer than three candidates are accepted,
   run additional single Terra candidates with
   `uv run taxi-demo run terra --repairs 1`. Stop after two additional candidates and
   report the missing evidence if the minimum still does not exist. Do not manufacture evals.
5. Run `uv run taxi-demo run qwen-bare --model MODEL_ID --repairs 1` before creating either
   learned artifact.
6. Run `uv run taxi-demo optimize --model MODEL_ID --max-metric-calls 18`. Confirm that
   DSPy is `dspy.GEPA`,
   Terra is the reflection model, Qwen is the student, and source-run IDs do not cross the
   train/development/held-out split. Run
   `uv run taxi-demo run qwen-dspy --model MODEL_ID --repairs 1` before producing the
   distilled skill. A routing lift is not a product-completion claim.
7. Run `uv run taxi-demo distill`. Read the generated `SKILL.md`, evidence map, validation
   report, release checklist, and symptom-to-repair guide. Continue only when every
   procedure cites real files from at least two accepted source runs. The copied teacher
   evidence belongs in the experiment's separate provenance directory; it must not be
   mounted into a treatment candidate as part of the deployable skill. This establishes a
   testable skill, not transfer. Then run these arms under the same contract and verifier:
   - `uv run taxi-demo run qwen-skill --model MODEL_ID --repairs 1`
   - `uv run taxi-demo run qwen-both --model MODEL_ID --repairs 1`
8. Run `uv run taxi-demo report` and read both comparison files.

## Preserve the experiment

- Use only the active `.demo/experiments/<experiment-id>` cohort.
- Each candidate starts in a random temporary directory outside the repository, with only
  assigned inputs staged. Codex's standard workspace sandbox is not claimed as a
  machine-wide filesystem read-isolation proof against a deliberately probing model.
- Preserve failed attempts, raw JSONL, stderr, verifier findings, and repair lineage.
- Treat the exact model, provider, prompt, selected skill contents, token usage, and elapsed
  time as evidence; aliases and confidence are not evidence.
- Keep the requirement, frozen SQL, rubric, verifier, and dataset fixed across arms.
- Use the distilled skill only in `qwen-skill` and `qwen-both`. Execute the saved DSPy router
  on real verifier findings only in `qwen-dspy` and `qwen-both`.
- Count cost inputs from every attempt. Count accepted output only when the verifier passes.

## Completion report

State:

- how many Terra sources were accepted and used for learning;
- whether the distilled skill package passed validation;
- DSPy baseline and optimized held-out routing scores;
- completion, attempts, total tokens, tokens per accepted task, and elapsed time for every
  candidate arm;
- which economic inputs are still missing;
- the exact paths to the report, skill package, DSPy evidence, and each run.

Make no transfer, quality, or economic claim beyond the recorded comparison.
