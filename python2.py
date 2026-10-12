#!/bin/bash
# Copyright © Sachin Chandrashekhar - Data Engineering Hub. All Rights Reserved.
#
# This code is provided as part of a paid training program.
# Unauthorized copying, distribution, or
# publication of this code—either in whole or in part—
# is strictly prohibited.
#
# This code may NOT be:
# - Uploaded to public repositories (GitHub, GitLab, etc.)
# - Shared with third parties
# - Used for commercial purposes
#
# Licensed for personal educational use only.
#
# If this code is found on a public repository or distributed without
# authorization, please notify: legal@dataengineeringhub.in
# =========================================================
# REGION CHECK — Must run in us-east-1 (CloudShell)
# =========================================================
CURRENT_REGION="${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo "")}"

if [ "$CURRENT_REGION" != "us-east-1" ] && [ -n "$CURRENT_REGION" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    ❌ WRONG REGION!                         ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║                                                            ║"
    echo "║  This script MUST be run from us-east-1 (N. Virginia).     ║"
    echo "║                                                            ║"
    echo "║  Your current region: ${CURRENT_REGION}                    ║"
    echo "║                                                            ║"
    echo "║  HOW TO FIX:                                               ║"
    echo "║  1. Open AWS Console                                       ║"
    echo "║  2. Top-right corner → click region dropdown               ║"
    echo "║  3. Select US East (N. Virginia) us-east-1                 ║"
    echo "║  4. Open CloudShell again from us-east-1                   ║"
    echo "║  5. Re-run this script                                     ║"
    echo "║                                                            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    exit 1
fi



set -e
export AWS_PAGER=""

LOG_FILE="mission-deh-hof-glue-athena-setup-$(date +%Y%m%d-%H%M%S).log"
CREATED_RESOURCES=()

log() {
    echo merge conflict "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cleanup_on_failure() {
    log "ERROR: Setup failed. Rolling back..."

    if [[ " ${CREATED_RESOURCES[@]} " =~ " S3_BUCKET " ]]; then
        log "Deleting S3 bucket: $BUCKET_NAME"
        aws s3 rb "s3://$BUCKET_NAME" --force 2>/dev/null || true
    fi

    if [[ " ${CREATED_RESOURCES[@]} " =~ " IAM_ROLE " ]]; then
        log "Detaching policies and deleting role: $ROLE_NAME"
        aws iam detach-role-policy --role-name "$ROLE_NAME" \
            --policy-arn "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole" 2>/dev/null || true
        aws iam detach-role-policy --role-name "$ROLE_NAME" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" 2>/dev/null || true
        aws iam delete-role-policy --role-name "$ROLE_NAME" \
            --policy-name "AthenaFullAccessInline" 2>/dev/null || true
        aws iam delete-role --role-name "$ROLE_NAME" 2>/dev/null || true
    fi

    log "Rollback completed. Check log: $LOG_FILE"
    exit 1
}

trap cleanup_on_failure ERR

log "=========================================="
log "Starting Glue + Athena Lab Setup"
log "=========================================="

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log "Account ID: $ACCOUNT_ID"

# Resource names
BUCKET_NAME="mission-deh-hof-bootcamp-$ACCOUNT_ID"
ROLE_NAME="mission-deh-hof-bootcamp-glue-role"


# --- Create S3 Bucket ---
log "Creating S3 bucket: $BUCKET_NAME"
if aws s3 ls "s3://$BUCKET_NAME" 2>/dev/null; then
    log "Bucket already exists, skipping"
else
    aws s3 mb "s3://$BUCKET_NAME" --region us-east-1
    CREATED_RESOURCES+=("S3_BUCKET")
    log "S3 bucket created"
fi

# Create folder structure
log "Creating folder structure in S3..."
aws s3api put-object --bucket "$BUCKET_NAME" --key "raw/hvfhv/" --content-length 0
aws s3api put-object --bucket "$BUCKET_NAME" --key "athena-results/" --content-length 0
log "Folders created: raw/hvfhv/, athena-results/"


# --- Create IAM Role for Glue ---
log "Creating IAM role: $ROLE_NAME"

cat > /tmp/glue-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "glue.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null > /dev/null; then
    log "Role already exists, skipping creation"
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "file:///tmp/glue-trust-policy.json" > /dev/null
    CREATED_RESOURCES+=("IAM_ROLE")
    log "IAM role created"
fi

# Attach managed policies
log "Attaching policies to role..."
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole" 2>/dev/null || true
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" 2>/dev/null || true
log "Attached: AWSGlueServiceRole, AmazonS3FullAccess"

# Add inline policy for Athena access
log "Adding Athena inline policy..."
cat > /tmp/athena-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:StopQueryExecution",
        "athena:GetWorkGroup"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetPartitions"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "AthenaFullAccessInline" \
    --policy-document "file:///tmp/athena-policy.json" 2>/dev/null || true
log "Athena inline policy added"

# Cleanup temp files
rm -f /tmp/glue-trust-policy.json /tmp/athena-policy.json


log ""
log "================================================================================"
log "GLUE + ATHENA LAB SETUP COMPLETE!"
log "================================================================================"
log ""
log "Resources created:"
log "  S3 Bucket:  s3://$BUCKET_NAME"
log "  IAM Role:   $ROLE_NAME"
log ""
log "S3 folder structure:"
log "  s3://$BUCKET_NAME/raw/hvfhv/       <-- upload HVFHV parquet file here"
log "  s3://$BUCKET_NAME/athena-results/   <-- Athena query results location"
log ""
log "Next steps:"
log "  1. Download HVFHV parquet from NYC TLC portal to your laptop:"
log "     https://d37ci6vzurychx.cloudfront.net/trip-data/fhvhv_tripdata_2024-01.parquet"
log "  2. Upload it to S3 via console: s3://$BUCKET_NAME/raw/hvfhv/"
log "  3. Create a Glue database manually in the Glue Data Catalog"
log "  4. Create and run a Glue Crawler pointing at s3://$BUCKET_NAME/raw/hvfhv/"
log "  5. Open Athena, set results to s3://$BUCKET_NAME/athena-results/"
log "  6. Query the crawled table"
log ""
log "To teardown: ~/mission-deh-hof-bootcamp-mission-1/mission-deh-hof-glue-athena-teardown.sh"
log "================================================================================"
