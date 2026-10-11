# mission-deh-hof-lyft-pipeline-codebase

This repository contains the infrastructure setup and teardown scripts for the **NYC TLC / Lyft data pipeline** bootcamp project. It provisions all AWS resources needed to simulate a real-world ride-share data ingestion pipeline.

---

## Branch Strategy

| Branch | Purpose |
|---|---|
| `master` | Stable / production-ready code |
| `develop` | Ongoing development |
| `lyft-pipeline-ingestion` | Active feature branch — current infrastructure scripts |

---

## What This Codebase Does

These scripts run in **AWS CloudShell (us-east-1)** and set up a self-contained data environment inside your own AWS account. No cross-account access is needed. All data is seeded directly from the scripts.

```
CloudShell
    │
    ├── Setup scripts create:
    │     ├── S3 bucket          (raw data + Athena results)
    │     ├── IAM Role           (Glue + Athena permissions)
    │     ├── Aurora PostgreSQL  (source database with NYC TLC data)
    │     └── Glue-ready folders in S3
    │
    └── Teardown scripts delete all of the above cleanly
```

---

## Repository Structure

```
mission-deh-hof-lyft-pipeline-codebase/
│
├── python2.py              # Glue + Athena infrastructure SETUP
├── python3.py              # Glue + Athena infrastructure TEARDOWN
├── python4.py              # NYC TLC Aurora DB SETUP + data seed
├── python5.py              # NYC TLC Aurora DB TEARDOWN
│
├── cloudformation/
│   └── cloudforamtioncode  # CloudFormation template (in progress)
│
└── README.md
```

> **Note:** `python2.py` – `python5.py` are Bash scripts saved with a `.py` extension. They start with `#!/bin/bash` and must be run with `bash`, not `python`.

---

## Scripts — What Each One Does

### `python2.py` — Glue + Athena Setup
- Creates S3 bucket: `mission-deh-hof-bootcamp-<ACCOUNT_ID>`
- Creates S3 folders: `raw/hvfhv/` and `athena-results/`
- Creates IAM Role: `mission-deh-hof-bootcamp-glue-role`
- Attaches policies: `AWSGlueServiceRole`, `AmazonS3FullAccess`, Athena inline policy
- Has rollback/cleanup on failure via `trap`

### `python3.py` — Glue + Athena Teardown
- Deletes Glue Crawler: `mission-deh-hof-bootcamp-hvfhv-crawler`
- Deletes Glue Database: `mission_deh_hof_bootcamp`
- Deletes S3 bucket and all contents
- Detaches policies and deletes IAM role

### `python4.py` — NYC TLC Aurora DB Setup
- Creates Security Group (port 5432)
- Creates DB Subnet Group
- Creates Aurora PostgreSQL Serverless v2 cluster + instance
- Creates 9 tables: `vendors`, `rate_codes`, `payment_types`, `taxi_zones`, `bases`, `yellow_taxi_trips`, `green_taxi_trips`, `fhv_trips`, `hvfhv_trips`
- Seeds each table with realistic NYC TLC sample data (20 rows per trip table)

### `python5.py` — NYC TLC Aurora DB Teardown
- Deletes Aurora instance and cluster
- Deletes DB subnet group
- Deletes security group

---

## AWS Resources Created

| Resource | Name | Service |
|---|---|---|
| S3 Bucket | `mission-deh-hof-bootcamp-<ACCOUNT_ID>` | S3 |
| IAM Role | `mission-deh-hof-bootcamp-glue-role` | IAM |
| Aurora Cluster | `mission-deh-hof-bootcamp-aurora-cluster` | RDS |
| Aurora Instance | `mission-deh-hof-bootcamp-aurora-instance` | RDS |
| Security Group | `mission-deh-hof-bootcamp-aurora-sg` | EC2/VPC |
| DB Subnet Group | `mission-deh-hof-bootcamp-subnet-group` | RDS |

---

## How to Run

> **Prerequisite:** Must be run from **AWS CloudShell in us-east-1**. Scripts will exit with an error if run from any other region.

```bash
# 1. Setup Glue + Athena infrastructure
bash python2.py

# 2. Setup Aurora DB + load NYC TLC data
bash python4.py

# --- when done, to clean up ---

# 3. Teardown Aurora DB
bash python5.py

# 4. Teardown Glue + Athena infrastructure
bash python3.py
```

---

## Pipeline Architecture (Big Picture)

```
Aurora PostgreSQL (source)
        │
        ▼
  Glue ETL Job  ──→  S3 raw/hvfhv/  (parquet)
                              │
                              ▼
                      Glue Crawler  ──→  Glue Data Catalog
                                                 │
                                                 ▼
                                           Amazon Athena
                                           (query results → S3 athena-results/)
```

The scripts in this repo provision **the foundation layer** (S3, IAM, Aurora). The Glue ETL job scripts and CloudFormation templates are the next phase of development.

---

## What's Coming Next

- [ ] Glue PySpark ETL job script (reads Aurora → writes S3 parquet)
- [ ] CloudFormation template for full stack deployment (`cloudformation/cloudforamtioncode`)
- [ ] Step Functions workflow for orchestration
- [ ] Lambda trigger for event-driven ingestion
