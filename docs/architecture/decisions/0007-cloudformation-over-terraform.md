# ADR 0007 — Infrastructure as Code: CloudFormation over Terraform

**Date:** 2026-05

## Context

The project needs a repeatable, automated way to provision and update AWS infrastructure (VPC, RDS, ECS cluster, ALB, IAM roles, Secrets Manager). Two options were evaluated:

- **HashiCorp Terraform** — was already partially in use for staging RDS provisioning (`terraform/staging/rds/`)
- **AWS CloudFormation** — AWS-native IaC, no external toolchain

The Terraform setup required:
- An S3 bucket and DynamoDB table for remote state
- Terraform CLI installed in CI runners
- Separate AWS credentials scoped to state bucket access
- `terraform plan` output parsed to extract resource values (e.g. RDS endpoint)

These added operational overhead without meaningful benefit for a two-service deployment.

## Decision

Use AWS CloudFormation for all infrastructure. Templates are committed to `infrastructure/cloudformation/` and deployed via `aws cloudformation deploy` in GitHub Actions. The existing `terraform/staging/rds/` directory is not used for new infrastructure.

## Consequences

- No external state backend — CloudFormation state is managed natively by AWS and visible in the Console
- Stack outputs (RDS endpoint, subnet IDs, security group IDs) are shared between stacks using CloudFormation exports
- All infrastructure changes are recorded as CloudFormation events with timestamps and user attribution
- Rollback is handled natively by CloudFormation on stack update failure
- The team no longer needs to install or version the Terraform CLI
