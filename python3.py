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

LOG_FILE="mission-deh-hof-glue-athena-teardown-$(date +%Y%m%d-%H%M%S).log"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting Glue + Athena Lab Teardown"
log "=========================================="

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log "Account ID: $ACCOUNT_ID"

# Resource names
BUCKET_NAME="mission-deh-hof-bootcamp-$ACCOUNT_ID"
ROLE_NAME="mission-deh-hof-bootcamp-glue-role"
GLUE_DB_NAME="mission_deh_hof_bootcamp"

# --- Delete Glue Crawler (if exists) ---
log "Checking for Glue Crawler..."
CRAWLER_NAME="mission-deh-hof-bootcamp-hvfhv-crawler"
if aws glue get-crawler --name "$CRAWLER_NAME" 2>/dev/null; then
    log "Deleting Glue Crawler: $CRAWLER_NAME"
    aws glue delete-crawler --name "$CRAWLER_NAME" 2>/dev/null || true
    log "Crawler deleted"
else
    log "No crawler found, skipping"
fi

# --- Delete Glue Database ---
log "Deleting Glue database: $GLUE_DB_NAME"
aws glue delete-database --name "$GLUE_DB_NAME" 2>/dev/null \
    || log "Glue database not found, skipping"

# --- Delete S3 Bucket ---
log "Deleting S3 bucket: $BUCKET_NAME"
if aws s3 ls "s3://$BUCKET_NAME" 2>/dev/null; then
    aws s3 rb "s3://$BUCKET_NAME" --force
    log "S3 bucket deleted"
else
    log "S3 bucket not found, skipping"
fi

# --- Delete IAM Role ---
log "Cleaning up IAM role: $ROLE_NAME"
if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null > /dev/null; then
    # Detach managed policies
    aws iam detach-role-policy --role-name "$ROLE_NAME" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole" 2>/dev/null || true
    aws iam detach-role-policy --role-name "$ROLE_NAME" \
        --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" 2>/dev/null || true

    # Delete inline policies
    aws iam delete-role-policy --role-name "$ROLE_NAME" \
        --policy-name "AthenaFullAccessInline" 2>/dev/null || true

    # Delete the role
    aws iam delete-role --role-name "$ROLE_NAME"
    log "IAM role deleted"
else
    log "IAM role not found, skipping"
fi

log ""
log "================================================================================"
log "GLUE + ATHENA LAB TEARDOWN COMPLETE!"
log "================================================================================"
log "All resources deleted."
log "================================================================================"
