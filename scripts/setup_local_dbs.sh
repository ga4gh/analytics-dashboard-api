#!/usr/bin/env bash
# setup_local_dbs.sh
#
# Sets up two local PostgreSQL databases for curation and provenance development:
#
#   analytics_staging_local  — mirrors the staging RDS instance (schema + data)
#   analytics_prod_local     — same schema + data, with all existing pmc_articles
#                              stamped as system-approved (production baseline)
#
# Prerequisites:
#   - PostgreSQL running locally (macOS: brew install postgresql)
#   - psql and pg_dump available in PATH
#   - VPN or network access to the staging RDS host
#
# Usage:
#   export DB_PASS="your_staging_db_password"
#   bash scripts/setup_local_dbs.sh
#
# To connect in DBeaver or psql:
#   Host: localhost | Port: 5432 | Username: <your-os-username> | No password
#   Database: analytics_staging_local  OR  analytics_prod_local

set -e

DB_HOST="analytics-dashboard-staging-base-database-verhcap8spla.c0q4keadjybw.us-east-2.rds.amazonaws.com"
DB_PORT="5432"
DB_NAME="analytics_dashboard_staging_db"
DB_USER="analytics_dashboard_staging_user"

SCHEMA_DUMP="/tmp/staging_schema.sql"
DATA_DUMP="/tmp/staging_data.sql"

if [ -z "$DB_PASS" ]; then
  echo "Error: DB_PASS environment variable is not set."
  echo "Run: export DB_PASS='your_staging_db_password'"
  exit 1
fi

echo ">>> Dropping existing local databases (if any)..."
psql template1 -c "DROP DATABASE IF EXISTS analytics_staging_local;"
psql template1 -c "DROP DATABASE IF EXISTS analytics_prod_local;"

echo ">>> Creating local databases..."
psql template1 -c "CREATE DATABASE analytics_staging_local;"
psql template1 -c "CREATE DATABASE analytics_prod_local;"

echo ">>> Dumping schema from staging RDS..."
PGSSLMODE=require PGPASSWORD=$DB_PASS pg_dump \
  -h $DB_HOST -p $DB_PORT \
  -U $DB_USER \
  -d $DB_NAME \
  --schema-only --no-owner --no-acl \
  --exclude-table=databasechangelog \
  --exclude-table=databasechangeloglock \
  -f $SCHEMA_DUMP

echo ">>> Dumping data from staging RDS..."
PGSSLMODE=require PGPASSWORD=$DB_PASS pg_dump \
  -h $DB_HOST -p $DB_PORT \
  -U $DB_USER \
  -d $DB_NAME \
  --data-only --no-owner \
  --exclude-table=databasechangelog \
  --exclude-table=databasechangeloglock \
  -f $DATA_DUMP

echo ">>> Loading schema into both local databases..."
psql analytics_staging_local -f $SCHEMA_DUMP
psql analytics_prod_local -f $SCHEMA_DUMP

echo ">>> Loading data into both local databases..."
psql analytics_staging_local -c "SET session_replication_role = replica;" -f $DATA_DUMP
psql analytics_prod_local -c "SET session_replication_role = replica;" -f $DATA_DUMP

echo ">>> Deduplicating prod — keeping latest row per article..."
# The staging ingestion pipeline re-inserts all records on every run, creating
# duplicate rows per article (one per ingestion run). Production must hold
# exactly one curated row per article (the latest ingestion_id wins).
psql analytics_prod_local -c "
  DELETE FROM pmc_articles
  WHERE id NOT IN (
    SELECT DISTINCT ON (pm_id) id
    FROM pmc_articles
    ORDER BY pm_id, ingestion_id DESC
  );
"

echo ">>> Stamping prod as system-approved baseline..."
psql analytics_prod_local -c "
  ALTER TABLE pmc_articles
    ADD COLUMN IF NOT EXISTS approved_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

  UPDATE pmc_articles
  SET approved_by = 'system',
      approved_at = created_at
  WHERE approved_by IS NULL;
"

echo ">>> Verifying row counts..."
echo ""
echo "--- analytics_staging_local ---"
psql analytics_staging_local -c "
  SELECT 'pmc_articles'    AS table_name, COUNT(*) AS rows FROM pmc_articles
  UNION ALL SELECT 'pmc_authors',  COUNT(*) FROM pmc_authors
  UNION ALL SELECT 'citations',    COUNT(*) FROM citations
  UNION ALL SELECT 'grants',       COUNT(*) FROM grants
  UNION ALL SELECT 'ingestion',    COUNT(*) FROM ingestion;
"

echo ""
echo "--- analytics_prod_local ---"
psql analytics_prod_local -c "
  SELECT 'pmc_articles'    AS table_name, COUNT(*) AS rows FROM pmc_articles
  UNION ALL SELECT 'pmc_authors',  COUNT(*) FROM pmc_authors
  UNION ALL SELECT 'citations',    COUNT(*) FROM citations
  UNION ALL SELECT 'grants',       COUNT(*) FROM grants
  UNION ALL SELECT 'ingestion',    COUNT(*) FROM ingestion;
"

echo ""
echo "--- prod approved check ---"
psql analytics_prod_local -c "
  SELECT
    COUNT(*)                                    AS total,
    COUNT(approved_by)                          AS stamped,
    COUNT(*) FILTER (WHERE approved_by IS NULL) AS unstamped
  FROM pmc_articles;
"

echo ""
echo "Done. Both local databases are ready for curation development."
