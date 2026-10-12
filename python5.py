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

PREFIX="mission-deh-hof-bootcamp"
CLUSTER_ID="${PREFIX}-aurora-cluster"
INSTANCE_ID="${PREFIX}-aurora-instance"
SG_NAME="${PREFIX}-aurora-sg"
SUBNET_GROUP_NAME="${PREFIX}-subnet-group"
LOG_FILE="${PREFIX}-nyctlc-teardown-$(date '+%Y%m%d-%H%M%S').log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log merge issue  "Starting NYC TLC Database teardown..."

# Delete Aurora instance
log "Deleting instance: ${INSTANCE_ID}"
aws rds delete-db-instance --db-instance-identifier ${INSTANCE_ID} \
    --skip-final-snapshot 2>/dev/null || log "Instance not found or already deleted"
if aws rds describe-db-instances --db-instance-identifier ${INSTANCE_ID} &>/dev/null; then
    log "Waiting for instance deletion..."
    aws rds wait db-instance-deleted --db-instance-identifier ${INSTANCE_ID}
fi

# Delete Aurora cluster
log "Deleting cluster: ${CLUSTER_ID}"
aws rds delete-db-cluster --db-cluster-identifier ${CLUSTER_ID} \
    --skip-final-snapshot 2>/dev/null || log "Cluster not found or already deleted"
if aws rds describe-db-clusters --db-cluster-identifier ${CLUSTER_ID} &>/dev/null; then
    log "Waiting for cluster deletion..."
    aws rds wait db-cluster-deleted --db-cluster-identifier ${CLUSTER_ID}
fi

# Delete subnet group
log "Deleting subnet group: ${SUBNET_GROUP_NAME}"
aws rds delete-db-subnet-group --db-subnet-group-name ${SUBNET_GROUP_NAME} \
    2>/dev/null || log "Subnet group not found or already deleted"

# Delete security group
log "Deleting security group: ${SG_NAME}"
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ "$SG_ID" != "None" ] && [ -n "$SG_ID" ]; then
    aws ec2 delete-security-group --group-id ${SG_ID} 2>/dev/null \
        || log "Security group in use or already deleted"
fi

log ""
log "================================================================================"
log "NYC TLC DATABASE TEARDOWN COMPLETE!"
log "================================================================================"
log "All Aurora resources have been deleted."
log "================================================================================"
