# Acceptance rubric

Accept a candidate only when all of these are true:

- an outside verifier reran dbt and every model/test result passed;
- all five required tables exist in `serving.duckdb`;
- accepted and quarantined rows match the validity rules and reason precedence;
- the two metric tables match independent aggregations from the staged source;
- every required table has a readable Parquet export with the same row count;
- all frozen Analyst SQL statements execute against the serving database;
- staged inputs, requirements, SQL, and skills still match the pre-run receipt.

Model confidence is not evidence. The supplied verifier and the query results define
acceptance.
