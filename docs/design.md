# GA4GH Analytics Dashboard: Design Document

* Project Title: GA4GH Analytics Dashboard
* Project Maintainers:
  * GA4GH Technical Team
    * Dashrath Chauhan (dashrath.chauhan@ga4gh.org)
    * Chen Chen (chen.chen@ga4gh.org)
    * Jeremy Adams (jeremy.adams@ga4gh.org)
    * Jimmy Payyappilly (jimmy.payyappilly@ga4gh.org)

## Overview
Analytics are important for standards organisations like GA4GH as it helps to make data-driven The GA4GH Analytics Dashboard is a one-stop resource for understanding the real-world impact of GA4GH standards, policy frameworks, and products. Drawing on data from GitHub, PyPI, and EuropePMC, it tracks how GA4GH's work has been adopted, cited, and built upon across the genomics community.

Whether you're a Work Stream contributor looking to understand how your efforts are landing, a product lead shaping the next development cycle, or a stakeholder making the case for genomic data sharing — this dashboard gives you the evidence to do it. Explore trends, spot implementation gaps, and see over a decade of open science translated into data.

Sources (will expand):
    GitHub
    PyPI
    EuropePMC

# Scope & Requirements

## Goals

# Architecture & System Design

## System Overview

The GA4GH Analytics Dashboard is a two-service web application deployed on AWS using ECS Fargate. It consists of a Python/FastAPI backend that ingests and serves data from GitHub, PyPI, and EuropePMC, and a Python/Dash frontend that visualises that data for stakeholders. Both services run as Docker containers defined in their respective repositories and are provisioned through CloudFormation templates.

Infrastructure is managed entirely through AWS CloudFormation. Database schema migrations are managed through Liquibase, which runs as a one-shot Fargate task before each backend deployment.

---

## Infrastructure Components

### Virtual Private Cloud (VPC)

- A dedicated VPC provides network isolation for all resources.

---

### Relational Database — Amazon RDS (PostgreSQL 17)

- A single Amazon RDS PostgreSQL 17 instance provides persistent storage for all application data. It is provisioned by the CloudFormation database stack and sits in the **private subnets**, unreachable from the internet.

**Database schema migrations** are managed by [Liquibase](https://www.liquibase.org/). On each deployment, a one-shot ECS Fargate task runs the `analytics-dashboard-liquibase` container, which applies any pending changesets from `liquibase/dbchangelog.xml` against the target database before the backend service is updated.

---

### Container Registry — Amazon ECR

Two ECR repositories store all Docker images built by CI:

| Repository | Image | Built from |
|---|---|---|
| `analytics-dashboard` | FastAPI backend | `analytics-dashboard/Dockerfile` |
| `analytics-dashboard-liquibase` | Liquibase migration runner | `analytics-dashboard/liquibase/Dockerfile` |
| `analytics-dashboard-ui` | Dash frontend | `analytics-dashboard-ui/Dockerfile` |

Images are built for the `linux/arm64` platform (Graviton) to match the Fargate task architecture. Each CI run tags images with the git describe output, `latest`, and the environment name (`staging` or `prod`).

---

### Compute — Amazon ECS (Fargate)

An ECS cluster runs both application services as serverless Fargate tasks. No EC2 instances are managed. The CloudFormation ECS stack provisions:

**Cluster**
- One ECS cluster per environment (`analytics-staging` / `analytics-prod`)
- Platform: `FARGATE` with Graviton (`ARM64`) CPU architecture

**Backend Service — `analytics-dashboard`**
- Container: `analytics-dashboard` image from ECR

**Frontend Service — `analytics-dashboard-ui`**
- Container: `analytics-dashboard-ui` image from ECR

**Liquibase Migration Task (pre-deployment)**
- Container: `analytics-dashboard-liquibase` image from ECR
- Runs as a one-shot `run-task` call (not a long-running service)

---

### Application Load Balancer (ALB)

A single internet-facing Application Load Balancer sits in the **public subnets** and routes traffic to the ECS services in the private subnets. The CloudFormation ALB stack provisions:

---

### Logging — Amazon CloudWatch Logs

All ECS task output (stdout/stderr) is routed to CloudWatch Logs via the `awslogs` log driver. Log groups:

- `/ecs/analytics-dashboard/{env}` — backend logs
- `/ecs/analytics-dashboard-ui/{env}` — frontend logs
- `/ecs/analytics-liquibase/{env}` — migration task logs

Log retention: 30 days (staging), 90 days (production).
---

## CI/CD Pipeline(Work in progress - currently its a manual process and no production instance yet, will be implementing it soon)

Deployments will be fully automated through GitHub Actions. Pushing to a branch triggers the corresponding environment pipeline.

```
git push → develop                    git push → main
       │                                     │
       ▼                                     ▼
┌─────────────────┐               ┌──────────────────────┐
│  CI (ci.yml)    │               │  Manual approval     │
│  Lint, type     │               │  gate (GitHub        │
│  check, tests   │               │  Environments)       │
└────────┬────────┘               └──────────┬───────────┘
         │                                   │
         ▼                                   ▼
┌─────────────────────────────────────────────────────────┐
│  Build & Push (ECR)                                     │
│  - analytics-dashboard:staging / :prod                  │
│  - analytics-dashboard-liquibase:staging / :prod        │
│  - analytics-dashboard-ui:staging / :prod               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Deploy CloudFormation stacks                           │
│  aws cloudformation deploy --stack analytics-*-{env}    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Run Liquibase migrations                               │
│  aws ecs run-task (one-shot Fargate task)               │
│  Waits for exit code 0 before proceeding                │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Update ECS services                                    │
│  aws ecs update-service --force-new-deployment          │
│  Backend → analytics-dashboard                          │
│  Frontend → analytics-dashboard-ui                      │
└─────────────────────────────────────────────────────────┘
```

---

## Database Schema

See [schema-tables.md](schema-tables.md) and [er-diagram.md](er-diagram.md) for the full schema.

The database is versioned and migrated through Liquibase using `liquibase/dbchangelog.xml`. Each deployment runs the migration task before any application containers are updated, ensuring schema and application code are always in sync.

---

## API / Interface Design

### Backend (`analytics-dashboard`) — FastAPI, port 8000

The backend exposes a REST API consumed by the frontend. Key router modules:

| Router | Base path | Responsibility |
|---|---|---|
| `health.py` | `/health` | Liveness probe for ALB and ECS health checks |
| `github.py` | `/github` | GitHub repository metrics, contributor data |
| `pypi.py`   | `/pypi`   | PyPI package download statistics and version history |
| `epmc.py`   | `/epmc`   | EuropePMC article, author, citation, and grant data |
| `pubmed.py` | `/pubmed` | PubMed article supplementary data |

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc`.

### Frontend (`analytics-dashboard-ui`) — Plotly Dash, port 8050

The frontend is a Plotly Dash single-page application served via Gunicorn (2 workers). It connects to the backend API to fetch data and renders interactive visualisations for:

- GitHub repository adoption trends
- PyPI download statistics and package usage
- EuropePMC citation and publication analytics
- Cross-source GA4GH impact overview

---

# Design Decisions

Key architectural decisions are recorded as Architecture Decision Records (ADRs) in [`docs/architecture/decisions/`](architecture/decisions/). Each record captures the context, the decision made, and its consequences.

### Record Architecture Decisions
[`0001-record-architecture-decisions.md`](architecture/decisions/0001-record-architecture-decisions.md)

### Formalise Setup Instructions and API Information in Notebooks
[`0002-formalise-the-setup-instructions-and-api-information-in-all-notebooks.md`](architecture/decisions/0002-formalise-the-setup-instructions-and-api-information-in-all-notebooks.md)

### Review EuropePMC and Decide Architecture for Data
[`0003-review-europe-pmc-and-decide-architecture-for-data.md`](architecture/decisions/0003-review-europe-pmc-and-decide-architecture-for-data.md)

### PMC Integration as Data Source After v0.2
[`0004-pmc-integration-as-data-source-after-v0-2.md`](architecture/decisions/0004-pmc-integration-as-data-source-after-v0-2.md)

### PubMed Data Cleanup
[`0005-pubmed-data-cleanup.md`](architecture/decisions/0005-pubmed-data-cleanup.md)

### Python ORM
[`0006-python-orm.md`](architecture/decisions/0006-python-orm.md)

### Infrastructure as Code — CloudFormation over Terraform
[`0007-cloudformation-over-terraform.md`](architecture/decisions/0007-cloudformation-over-terraform.md)

### Compute — ECS Fargate over EC2 or Kubernetes
[`0008-ecs-fargate-for-compute.md`](architecture/decisions/0008-ecs-fargate-for-compute.md)

### Database Migrations — Liquibase
[`0009-liquibase-for-db-migrations.md`](architecture/decisions/0009-liquibase-for-db-migrations.md)

### Audit Strategy — Unified Audit Log Table
[`0010-unified-audit-log.md`](architecture/decisions/0010-unified-audit-log.md)

### Data Provenance — EuropePMC Ingestion Versioning
[`0011-epmc-data-provenance.md`](architecture/decisions/0011-epmc-data-provenance.md)

### Remove PubMed in Favour of EuropePMC
[`0012-remove-pubmed-in-favour-of-europepmc.md`](architecture/decisions/0012-remove-pubmed-in-favour-of-europepmc.md)