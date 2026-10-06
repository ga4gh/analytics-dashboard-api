# GA4GH Analytics Dashboard

## Introduction
Analytics are important for standards organisations like GA4GH as it helps to make data-driven decisions. The GA4GH Analytics Dashboard is a one-stop resource for understanding the real-world impact of GA4GH standards, policy frameworks, and products. Drawing on data from GitHub, PyPI, and Europe PMC, it tracks how GA4GH's work has been adopted, cited, and built upon across the genomics community.

Whether you're a Work Stream contributor looking to understand how your efforts are landing, a product lead shaping the next development cycle, or a stakeholder making the case for genomic data sharing, this dashboard gives you the evidence to do it. Explore trends, spot implementation gaps, and see over a decade of open science translated into data.


## Requirements
The dashboard ingests data from sources mentioned below, and draws out useful GA4GH-related analytics data from it such as publications, collaborators, software packages, countries with presence, etc. All the ingested data is curated and then creatively visualised for easy understanding of the impact. The data sources are selected based on parameters such as the quality and quantity of the data available, the importance of the data to GA4GH collaborators, and in executive decision making of future efforts. 

Data sources (will expand over time) 
* Europe PMC
* GitHub
* The Python Package Index (PyPI) 

The initial versions of the dashboard was based on Jupyter notebooks but to make it more accessible, the latest versions are web-based and available on the GA4GH domain. Regular ingestion of data from the sources ensure the analytics data and corresponding visualisations are up-to-date. 


## Architecture & System Design

### System Overview

The GA4GH Analytics Dashboard is a two-service web application deployed on GA4GH's cloud instance. AWS is the cloud provider and the deployments are managed through ECS Fargate. The dashboard application consists of a Python/FastAPI backend that ingests and serves data from the data sources, and a Python with [Plotly Dash](https://dash.plotly.com) frontend that visualises the data for community. Both services run as Docker containers defined in their respective repositories and are provisioned as well as managed through CloudFormation templates.



### Infrastructure Components

#### Virtual Private Cloud (VPC)

A dedicated VPC provides network isolation for all resources of the dashboard and ensures appropriate management controls.


#### Relational Database 

A single Amazon RDS (PostgreSQL) instance provides persistent storage for dashboard's data. As mentioned, the database stack is provisioned through CloudFormation templates and sits in the **private subnets** unreachable from the internet.

Database schema migrations are managed (versioned too) by [Liquibase](https://www.liquibase.org/). On each deployment, a one-time ECS Fargate task runs the `analytics-dashboard-liquibase` container, which applies any pending changesets from `liquibase/dbchangelog.xml` against the target database before the backend service is updated ensuring schema and application code are always in sync. 

See [schema-tables.md](schema-tables.md) and [er-diagram.md](er-diagram.md) for the full schema. 


#### Container Registry

AWS ECR is used for the dashboard's images. Two ECR repositories store all Docker images built by CI:

| Repository | Image | Built from |
|---|---|---|
| `analytics-dashboard` | FastAPI backend | `analytics-dashboard/Dockerfile` |
| `analytics-dashboard-liquibase` | Liquibase migration runner | `analytics-dashboard/liquibase/Dockerfile` |
| `analytics-dashboard-ui` | Dash frontend | `analytics-dashboard-ui/Dockerfile` |

Images are built for the `linux/arm64` platform (Graviton) to match the Fargate task architecture. Each CI run tags images with the git describe output, `latest`, and the environment name (`staging` or `prod`).



#### Compute 

An ECS cluster runs both application services as serverless Fargate tasks. No EC2 instances are managed. The CloudFormation ECS stack provisions:

* Cluster
  * One ECS cluster per environment (`analytics-staging` / `analytics-prod`)
  * Platform: `FARGATE` with Graviton (`ARM64`) CPU architecture

* Backend Service — `analytics-dashboard`
  * Container: `analytics-dashboard` image from ECR

* Frontend Service — `analytics-dashboard-ui`
  * Container: `analytics-dashboard-ui` image from ECR

* Liquibase Migration Task (pre-deployment)
  * Container: `analytics-dashboard-liquibase` image from ECR
  * Runs as a one-shot `run-task` call (not a long-running service)



#### Application Load Balancer (ALB)

A single internet-facing Application Load Balancer sits in the **public subnets** and routes traffic to the ECS services in the private subnets. The CloudFormation ALB stack provisions:



### Logging

All ECS task output (stdout/stderr) is routed to CloudWatch Logs via the `awslogs` log driver. Log groups:

- `/ecs/analytics-dashboard/{env}` — backend logs
- `/ecs/analytics-dashboard-ui/{env}` — frontend logs
- `/ecs/analytics-liquibase/{env}` — migration task logs

Log retention: 30 days (staging), 90 days (production).


### CI/CD Pipeline 
> [!WARNING]
> Work in progress - Currently, it's a manual process. Automated production instance will be implemented soon.

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




### API/Interface Design

#### Backend (`analytics-dashboard`) — FastAPI, port 8000

The backend exposes a REST API consumed by the frontend. Key router modules:

| Router | Base path | Responsibility |
|---|---|---|
| `health.py` | `/health` | Liveness probe for ALB and ECS health checks |
| `github.py` | `/github` | GitHub repository metrics, contributor data |
| `pypi.py`   | `/pypi`   | PyPI package download statistics and version history |
| `epmc.py`   | `/epmc`   | EuropePMC article, author, citation, and grant data |
| `pubmed.py` | `/pubmed` | PubMed article supplementary data |

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc`.

#### Frontend (`analytics-dashboard-ui`) — Plotly Dash, port 8050

The frontend is a Plotly Dash single-page application served via Gunicorn (2 workers). It connects to the backend API to fetch data and renders interactive visualisations for:

- GitHub repository adoption trends
- PyPI download statistics and package usage
- EuropePMC citation and publication analytics
- Cross-source GA4GH impact overview


## Design Decisions

Key architectural decisions are recorded as Architecture Decision Records (ADRs) in [`doc/architecture/decisions/`](architecture/decisions/). Each record captures the context, the decision made, and its consequences.


