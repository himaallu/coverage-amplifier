TASK: Implement the data layer per docs/PRD.md §6 exactly.

Create SQLAlchemy 2.0 models for kits, assets, claims, verification_runs,
llm_calls with the exact columns and enums in the PRD (claims.verdict defaults
to 'pending'). Alembic migration. /healthz upgraded to check the DB connection.
LLMClient interface (abstract class only — no provider implementation yet).

TDD first: model round-trip tests (create kit → assets → claims → read back),
healthz returns {status:"ok", db:"ok"} against the Supabase connection string
from env; a second test proves healthz reports db:"down" gracefully when the
connection string is invalid.
Done when: all tests green, migration runs against Supabase, CI green.

Dependency justification: alembic==1.14.0 provides schema versioning and database migrations for SQLAlchemy 2.0 against Supabase Postgres.