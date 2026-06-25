# ADR 0008 — Compute: ECS Fargate over EC2 or Kubernetes
 
**Date:** 2026-05

## Status

Accepted

## Context

The application consists of two long-running web services (FastAPI backend, Dash frontend) and one pre-deployment one-shot task (Liquibase migrations). A compute platform was needed to run these containers in AWS.

Options evaluated:

- **EC2 with ECS** — requires managing instance types, AMI updates, autoscaling groups, and SSH key rotation
- **Amazon EKS (Kubernetes)** — powerful but introduces significant operational complexity: node groups, control plane upgrades, Helm charts, and Kubernetes RBAC on top of AWS IAM
- **ECS Fargate** — serverless container execution; no instances to manage; pay per task-second

The workload is modest: two stateless web services with low traffic variability and an occasional one-shot migration task. There is no need for advanced scheduling, multi-tenant isolation, or custom node configuration.

## Decision

Use ECS Fargate with Graviton (ARM64) tasks. One ECS cluster per environment. Both services are defined as ECS services with ALB target group integration. The Liquibase migration runs as an ECS `run-task` one-shot call before each deployment.

## Consequences

- No EC2 instances to patch, rotate, or right-size
- Fargate scales tasks independently — the backend and frontend can be scaled without affecting each other
- Graviton (ARM64) tasks cost approximately 20% less than equivalent x86 Fargate tasks
- The `linux/arm64` Docker images must be built with Docker Buildx multi-platform support in CI
- ECS service logs go directly to CloudWatch Logs without a logging agent
- If workload grows significantly, migrating from ECS to EKS is possible but non-trivial
