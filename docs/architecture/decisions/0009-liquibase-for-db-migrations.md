# ADR 0009 — Database Migrations: Liquibase

**Date:** 2026-05

## Context

The PostgreSQL schema must evolve as the application adds tables, columns, indexes, and constraints. Changes need to be:

- Version-controlled alongside application code
- Applied in a deterministic order
- Idempotent — safe to run multiple times without side effects
- Tracked — the database should know which changesets have already been applied

The initial infrastructure used Terraform to provision the RDS instance but had no mechanism for managing the schema after initial creation.

Options evaluated:

- **Flyway** — Java-based, uses numbered SQL files; simpler than Liquibase but less expressive
- **Liquibase** — XML/SQL/YAML changesets; tracks applied changes in `DATABASECHANGELOG`; supports rollback; has an official Docker image

## Decision

Use Liquibase with an XML changelog (`liquibase/dbchangelog.xml`). All schema changes are defined as changesets in this file. A dedicated Docker image (`analytics-dashboard-liquibase`) is built from `liquibase/Dockerfile` and pushed to ECR alongside the application image.

On each deployment, a one-shot ECS Fargate task runs this image with `DATABASE_URL` from Secrets Manager. The deployment pipeline waits for the task to exit with code 0 before updating the ECS application services.

## Consequences

- Schema changes are peer-reviewed through the same pull request process as application code
- The `DATABASECHANGELOG` table in PostgreSQL provides a full audit trail of applied migrations
- Adding a migration never requires code changes outside `dbchangelog.xml`
- Rollback is supported at the changeset level via `<rollback>` blocks (must be authored explicitly)
- The migration image must be rebuilt and pushed on any change to `dbchangelog.xml` or the Liquibase base image
