# Liquibase Database Migrations

This directory contains the Liquibase changelog and Docker setup for managing schema migrations across staging and production databases.

---

## How it works

- `dbchangelog.xml` is the single source of truth for all schema changes
- The `Dockerfile` bakes the changelog into an image that runs `liquibase update` on startup
- The ECS migration task pulls this image and applies any pending changesets to the target database
- Liquibase is idempotent — it tracks which changesets have already run and skips them

---

## Making a schema change

### 1. Add a changeset to `dbchangelog.xml`

Always append at the bottom. Use a date-based ID. Never modify or delete existing changesets.

```xml
<!-- Brief description of what this changes and why -->
<changeSet author="dashrath" id="dc-YYYYMMDD-001">
    <addColumn tableName="some_table">
        <column name="new_column" type="varchar(255)">
            <constraints nullable="true"/>
        </column>
    </addColumn>
</changeSet>
```

**Never run `liquibase generate-changelog`** — it regenerates all changeset IDs and breaks tracking on existing databases.

### 2. Test locally

```bash
cd liquibase

liquibase \
  --changelog-file=dbchangelog.xml \
  --classpath=/Users/dashrath/postgresql.jar \
  --url=jdbc:postgresql://localhost:5432/analytics_staging_local \
  --username=dashrath \
  --password="" \
  update
```

Only your new changeset should run. All previous ones show as already applied.

### 3. Commit and push

```bash
git add liquibase/dbchangelog.xml
git commit -m "Add <column/table> to <table>"
git push
```

### 4. Rebuild and push the Docker image

The image bakes in `dbchangelog.xml` at build time — rebuild it every time the changelog changes.

```bash
cd liquibase

aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin 282236276875.dkr.ecr.us-east-2.amazonaws.com

docker build -t analytics-dashboard-liquibase .
docker tag analytics-dashboard-liquibase:latest \
  282236276875.dkr.ecr.us-east-2.amazonaws.com/analytics-dashboard-liquibase:latest
docker push \
  282236276875.dkr.ecr.us-east-2.amazonaws.com/analytics-dashboard-liquibase:latest
```

### 5. Run migration on staging

Always migrate staging before production.

```bash
aws ecs run-task \
  --cluster analytics-dashboard-staging-cluster \
  --task-definition analytics-dashboard-staging-liquibase \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0f26c31e6c9578717,subnet-00663ce89eb47404f,subnet-08b697026fc4502e5],securityGroups=[<staging-sg-id>],assignPublicIp=ENABLED}" \
  --region us-east-2
```

Check logs:

```bash
aws logs tail /analytics-dashboard/staging/backend --follow --region us-east-2
```

Confirm the task exited with code 0 before proceeding.

### 6. Run migration on production

```bash
aws ecs run-task \
  --cluster analytics-dashboard-production-cluster \
  --task-definition analytics-dashboard-production-liquibase \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0f26c31e6c9578717,subnet-00663ce89eb47404f,subnet-08b697026fc4502e5],securityGroups=[<prod-sg-id>],assignPublicIp=ENABLED}" \
  --region us-east-2
```

Check logs:

```bash
aws logs tail /analytics-dashboard/production/backend --follow --region us-east-2
```

---

## Verifying a database is up to date

### Check which changesets have been applied

```bash
psql "postgresql://<username>:<password>@<host>:5432/<dbname>?sslmode=require" \
  -c "SELECT id, author, dateexecuted FROM databasechangelog ORDER BY dateexecuted DESC LIMIT 15;"
```

The last row must be `dc-20260827-001`. If it stops before that, pending changesets need to be applied.

### Check for pending changesets (without applying them)

```bash
cd liquibase

LIQUIBASE_COMMAND_PASSWORD=<password> \
liquibase \
  --changelog-file=dbchangelog.xml \
  --classpath=/Users/dashrath/postgresql.jar \
  --url="jdbc:postgresql://<host>:5432/<dbname>?ssl=true&sslmode=require" \
  --username=<username> \
  status
```

Reports `0 change sets have not been applied` when fully up to date.

---

## Changeset ID convention

```
dc-YYYYMMDD-NNN
```

- `dc` — dashrath chauhan (author prefix)
- `YYYYMMDD` — date the changeset was written
- `NNN` — sequence number for that day (001, 002, …)

Examples: `dc-20260820-001`, `dc-20261102-001`

---

## Troubleshooting

### Migration task fails with "column already exists"

The image was built from a stale changelog. Rebuild and repush the Docker image (Step 4), then re-run the task.

### `liquibase update` tries to recreate existing tables

The changelog was regenerated at some point, causing changeset ID mismatches. Do not run `generate-changelog`. Run `changelogSync` to re-sync:

```bash
LIQUIBASE_COMMAND_PASSWORD=<password> \
liquibase \
  --changelog-file=dbchangelog.xml \
  --classpath=/Users/dashrath/postgresql.jar \
  --url="jdbc:postgresql://<host>:5432/<dbname>?ssl=true&sslmode=require" \
  --username=<username> \
  changelogSync
```

### Getting the database password

```bash
aws secretsmanager get-secret-value \
  --secret-id analytics-dashboard-<staging|production>-DBPassword \
  --version-stage AWSCURRENT \
  --region us-east-2 \
  --query 'SecretString' --output text
```
