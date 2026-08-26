# Accepted Qwen build with the distilled Taxi skill

LM Studio model `qwen3.8-27b` produced this dbt project in run
`20260826-142447-qwen-skill-fe42bfa8`. Its candidate workspace mounted the dbt skill, the
DuckDB skill, and the distilled Taxi delivery skill. The unchanged outside verifier
accepted the candidate after one attempt.

- Generated dbt code: [`models/`](models/)
- Singular tests: [`tests/`](tests/)
- Macros: [`macros/`](macros/)
- Skills visible to the candidate: [`.codex/skills/`](.codex/skills/)
- Queryable release: `serving.duckdb`
- Parquet release: [`exports/`](exports/)
- Model inputs and Analyst rubric: [`model-inputs/`](model-inputs/)
- Source-run provenance and 1,000-row validation: [`evidence/`](evidence/)

From the repository root:

```bash
uv run taxi-demo inspect-example qwen-skill
uv run taxi-demo query-example qwen-skill 'show tables'
uv run taxi-demo query-example qwen-skill \
  'select reason, row_count from data_quality_summary order by row_count desc, reason'
```

To rerun this checked-in dbt project against its checked-in input:

```bash
cd examples/qwen-skill
uv run dbt build --profiles-dir .
```

Qwen originally produced this code against a 300-row fixture. The checked-in database and
exports were rebuilt and independently validated against the repository's 1,000-row
fixture. This example alone does not establish that the distilled skill caused the
accepted result or transfers to another dataset.
