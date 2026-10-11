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
DB_NAME="nyctlc_bootcamp"
MASTER_USERNAME="postgres"
MASTER_PASSWORD="DataEngHub2050!"
CLUSTER_ID="${PREFIX}-aurora-cluster"
INSTANCE_ID="${PREFIX}-aurora-instance"
SG_NAME="${PREFIX}-aurora-sg"
SUBNET_GROUP_NAME="${PREFIX}-subnet-group"
LOG_FILE="${PREFIX}-nyctlc-setup-$(date '+%Y%m%d-%H%M%S').log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

cleanup_on_error() {
    log "ERROR: Setup failed. Starting cleanup..."
    aws rds delete-db-instance --db-instance-identifier ${INSTANCE_ID} \
        --skip-final-snapshot 2>/dev/null && log "Deleted instance" || true
    aws rds wait db-instance-deleted --db-instance-identifier ${INSTANCE_ID} 2>/dev/null || true
    aws rds delete-db-cluster --db-cluster-identifier ${CLUSTER_ID} \
        --skip-final-snapshot 2>/dev/null && log "Deleted cluster" || true
    aws rds wait db-cluster-deleted --db-cluster-identifier ${CLUSTER_ID} 2>/dev/null || true
    aws rds delete-db-subnet-group --db-subnet-group-name ${SUBNET_GROUP_NAME} 2>/dev/null || true
    SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
    if [ "$SG_ID" != "None" ] && [ -n "$SG_ID" ]; then
        aws ec2 delete-security-group --group-id ${SG_ID} 2>/dev/null || true
    fi
    log "Cleanup completed. Check log: ${LOG_FILE}"
    exit 1
}

trap cleanup_on_error ERR

log "Starting NYC TLC Database setup..."
log "Database: ${DB_NAME}"
log "Cluster: ${CLUSTER_ID}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log "AWS Account: ${ACCOUNT_ID}"

VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" \
    --query 'Vpcs[0].VpcId' --output text)
if [ "$VPC_ID" == "None" ] || [ -z "$VPC_ID" ]; then
    log "ERROR: No default VPC found"
    exit 1
fi
log "VPC: ${VPC_ID}"

log "Finding Aurora PostgreSQL version..."
PG_VERSION=$(aws rds describe-db-engine-versions \
    --engine aurora-postgresql \
    --query 'DBEngineVersions[?contains(SupportedEngineModes, `provisioned`)].EngineVersion' \
    --output text | tr '\t' '\n' | sort -V | tail -1)
log "Aurora PostgreSQL version: ${PG_VERSION}"


# --- Security Group ---
log "Creating security group: ${SG_NAME}"
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "")
if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name ${SG_NAME} \
        --description "Security group for ${PREFIX} Aurora cluster" \
        --vpc-id ${VPC_ID} \
        --query 'GroupId' --output text)
    aws ec2 authorize-security-group-ingress \
        --group-id ${SG_ID} \
        --protocol tcp \
        --port 5432 \
        --cidr 0.0.0.0/0
    log "Security group created: ${SG_ID}"
else
    log "Security group exists: ${SG_ID}"
fi

# --- DB Subnet Group ---
log "Creating DB subnet group: ${SUBNET_GROUP_NAME}"
if ! aws rds describe-db-subnet-groups --db-subnet-group-name ${SUBNET_GROUP_NAME} &>/dev/null; then
    SUBNET_IDS=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=${VPC_ID}" \
        --query 'Subnets[*].SubnetId' \
        --output json | python3 -c "import json,sys; ids=json.load(sys.stdin); print(' '.join(ids[:6]))")
    if [ -z "${SUBNET_IDS}" ]; then
        log "ERROR: No subnets found in VPC ${VPC_ID}"
        exit 1
    fi
    log "Using subnets: ${SUBNET_IDS}"
    aws rds create-db-subnet-group \
        --db-subnet-group-name ${SUBNET_GROUP_NAME} \
        --db-subnet-group-description "Subnet group for ${PREFIX} Aurora" \
        --subnet-ids ${SUBNET_IDS}
    log "Subnet group created"
else
    log "Subnet group exists"
fi

# --- Aurora Cluster ---
log "Creating Aurora cluster: ${CLUSTER_ID}"
if ! aws rds describe-db-clusters --db-cluster-identifier ${CLUSTER_ID} &>/dev/null; then
    aws rds create-db-cluster \
        --db-cluster-identifier ${CLUSTER_ID} \
        --engine aurora-postgresql \
        --engine-version ${PG_VERSION} \
        --master-username ${MASTER_USERNAME} \
        --master-user-password ${MASTER_PASSWORD} \
        --database-name ${DB_NAME} \
        --db-subnet-group-name ${SUBNET_GROUP_NAME} \
        --vpc-security-group-ids ${SG_ID} \
        --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=1.0 \
        --enable-http-endpoint
    log "Waiting for cluster (5-10 min)..."
    aws rds wait db-cluster-available --db-cluster-identifier ${CLUSTER_ID}
    log "Cluster available"
else
    log "Cluster exists"
fi

ENDPOINT=$(aws rds describe-db-clusters --db-cluster-identifier ${CLUSTER_ID} \
    --query 'DBClusters[0].Endpoint' --output text)
log "Endpoint: ${ENDPOINT}"

# --- Aurora Instance ---
log "Creating Aurora instance: ${INSTANCE_ID}"
if ! aws rds describe-db-instances --db-instance-identifier ${INSTANCE_ID} &>/dev/null; then
    aws rds create-db-instance \
        --db-instance-identifier ${INSTANCE_ID} \
        --db-instance-class db.serverless \
        --engine aurora-postgresql \
        --db-cluster-identifier ${CLUSTER_ID} \
        --publicly-accessible
    log "Waiting for instance (5-10 min)..."
    aws rds wait db-instance-available --db-instance-identifier ${INSTANCE_ID}
    log "Instance available"
else
    log "Instance exists"
fi


# --- Create Schema and Load Data ---
log "Creating NYC TLC database schema and loading data..."

cat > /tmp/nyctlc-schema.sql << 'EOSQL'
-- ============================================================
-- NYC TLC Operational Database Schema
-- Simulates the transactional system behind NYC taxi trip data
-- ============================================================

-- Lookup: Vendors (TPEP/LPEP providers)
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id INTEGER PRIMARY KEY,
    vendor_name VARCHAR(100) NOT NULL
);

-- Lookup: Rate Codes
CREATE TABLE IF NOT EXISTS rate_codes (
    rate_code_id INTEGER PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);

-- Lookup: Payment Types
CREATE TABLE IF NOT EXISTS payment_types (
    payment_type_id INTEGER PRIMARY KEY,
    description VARCHAR(50) NOT NULL
);

-- Lookup: Taxi Zones
CREATE TABLE IF NOT EXISTS taxi_zones (
    location_id INTEGER PRIMARY KEY,
    borough VARCHAR(50) NOT NULL,
    zone VARCHAR(100) NOT NULL,
    service_zone VARCHAR(50) NOT NULL
);

-- Lookup: FHV/HVFHV Bases
CREATE TABLE IF NOT EXISTS bases (
    base_license_number VARCHAR(10) PRIMARY KEY,
    base_name VARCHAR(100) NOT NULL,
    app_company VARCHAR(50)
);

-- Yellow Taxi Trips
CREATE TABLE IF NOT EXISTS yellow_taxi_trips (
    trip_id SERIAL PRIMARY KEY,
    vendor_id INTEGER REFERENCES vendors(vendor_id),
    tpep_pickup_datetime TIMESTAMP NOT NULL,
    tpep_dropoff_datetime TIMESTAMP NOT NULL,
    passenger_count INTEGER,
    trip_distance DECIMAL(10,2),
    pu_location_id INTEGER REFERENCES taxi_zones(location_id),
    do_location_id INTEGER REFERENCES taxi_zones(location_id),
    rate_code_id INTEGER REFERENCES rate_codes(rate_code_id),
    store_and_fwd_flag CHAR(1),
    payment_type INTEGER REFERENCES payment_types(payment_type_id),
    fare_amount DECIMAL(10,2),
    extra DECIMAL(10,2),
    mta_tax DECIMAL(10,2),
    tip_amount DECIMAL(10,2),
    tolls_amount DECIMAL(10,2),
    improvement_surcharge DECIMAL(10,2),
    congestion_surcharge DECIMAL(10,2),
    total_amount DECIMAL(10,2)
);

-- Green Taxi Trips
CREATE TABLE IF NOT EXISTS green_taxi_trips (
    trip_id SERIAL PRIMARY KEY,
    vendor_id INTEGER REFERENCES vendors(vendor_id),
    lpep_pickup_datetime TIMESTAMP NOT NULL,
    lpep_dropoff_datetime TIMESTAMP NOT NULL,
    passenger_count INTEGER,
    trip_distance DECIMAL(10,2),
    pu_location_id INTEGER REFERENCES taxi_zones(location_id),
    do_location_id INTEGER REFERENCES taxi_zones(location_id),
    rate_code_id INTEGER REFERENCES rate_codes(rate_code_id),
    store_and_fwd_flag CHAR(1),
    payment_type INTEGER REFERENCES payment_types(payment_type_id),
    fare_amount DECIMAL(10,2),
    extra DECIMAL(10,2),
    mta_tax DECIMAL(10,2),
    tip_amount DECIMAL(10,2),
    tolls_amount DECIMAL(10,2),
    improvement_surcharge DECIMAL(10,2),
    congestion_surcharge DECIMAL(10,2),
    trip_type INTEGER,
    total_amount DECIMAL(10,2)
);

-- FHV Trips (standard for-hire vehicles)
CREATE TABLE IF NOT EXISTS fhv_trips (
    trip_id SERIAL PRIMARY KEY,
    dispatching_base_num VARCHAR(10) REFERENCES bases(base_license_number),
    pickup_datetime TIMESTAMP NOT NULL,
    dropoff_datetime TIMESTAMP,
    pu_location_id INTEGER REFERENCES taxi_zones(location_id),
    do_location_id INTEGER REFERENCES taxi_zones(location_id),
    sr_flag INTEGER
);

-- HVFHV Trips (High Volume: Uber, Lyft)
CREATE TABLE IF NOT EXISTS hvfhv_trips (
    trip_id SERIAL PRIMARY KEY,
    hvfhs_license_num VARCHAR(10) NOT NULL,
    dispatching_base_num VARCHAR(10) REFERENCES bases(base_license_number),
    originating_base_num VARCHAR(10),
    request_datetime TIMESTAMP,
    on_scene_datetime TIMESTAMP,
    pickup_datetime TIMESTAMP NOT NULL,
    dropoff_datetime TIMESTAMP NOT NULL,
    pu_location_id INTEGER REFERENCES taxi_zones(location_id),
    do_location_id INTEGER REFERENCES taxi_zones(location_id),
    trip_miles DECIMAL(10,2),
    trip_time INTEGER,
    base_passenger_fare DECIMAL(10,2),
    tolls DECIMAL(10,2),
    bcf DECIMAL(10,2),
    sales_tax DECIMAL(10,2),
    congestion_surcharge DECIMAL(10,2),
    tips DECIMAL(10,2),
    driver_pay DECIMAL(10,2),
    shared_request_flag CHAR(1),
    shared_match_flag CHAR(1),
    access_a_ride_flag CHAR(1),
    wav_request_flag CHAR(1),
    wav_match_flag CHAR(1)
);
EOSQL

PGPASSWORD=${MASTER_PASSWORD} psql -h ${ENDPOINT} -U ${MASTER_USERNAME} -d ${DB_NAME} \
    -f /tmp/nyctlc-schema.sql 2>&1 | tee -a "${LOG_FILE}"

log "Schema created. Loading lookup data..."


cat > /tmp/nyctlc-lookups.sql << 'EOSQL'
-- Vendors
INSERT INTO vendors (vendor_id, vendor_name) VALUES
(1, 'Creative Mobile Technologies, LLC'),
(2, 'VeriFone Inc.');

-- Rate Codes
INSERT INTO rate_codes (rate_code_id, description) VALUES
(1, 'Standard rate'),
(2, 'JFK'),
(3, 'Newark'),
(4, 'Nassau or Westchester'),
(5, 'Negotiated fare'),
(6, 'Group ride');

-- Payment Types
INSERT INTO payment_types (payment_type_id, description) VALUES
(1, 'Credit card'),
(2, 'Cash'),
(3, 'No charge'),
(4, 'Dispute'),
(5, 'Unknown'),
(6, 'Voided trip');

-- Taxi Zones (subset of key zones)
INSERT INTO taxi_zones (location_id, borough, zone, service_zone) VALUES
(1, 'EWR', 'Newark Airport', 'EWR'),
(4, 'Manhattan', 'Alphabet City', 'Yellow Zone'),
(7, 'Queens', 'Astoria', 'Boro Zone'),
(12, 'Manhattan', 'Battery Park', 'Yellow Zone'),
(13, 'Manhattan', 'Battery Park City', 'Yellow Zone'),
(24, 'Manhattan', 'Bloomingdale', 'Yellow Zone'),
(41, 'Manhattan', 'Central Harlem', 'Boro Zone'),
(43, 'Manhattan', 'Central Park', 'Yellow Zone'),
(45, 'Manhattan', 'Chinatown', 'Yellow Zone'),
(48, 'Manhattan', 'Clinton East', 'Yellow Zone'),
(68, 'Manhattan', 'East Chelsea', 'Yellow Zone'),
(79, 'Manhattan', 'East Village', 'Yellow Zone'),
(87, 'Manhattan', 'Financial District North', 'Yellow Zone'),
(90, 'Manhattan', 'Flatiron', 'Yellow Zone'),
(100, 'Manhattan', 'Garment District', 'Yellow Zone'),
(107, 'Manhattan', 'Gramercy', 'Yellow Zone'),
(113, 'Manhattan', 'Greenwich Village North', 'Yellow Zone'),
(114, 'Manhattan', 'Greenwich Village South', 'Yellow Zone'),
(125, 'Manhattan', 'Hudson Sq', 'Yellow Zone'),
(132, 'Queens', 'JFK Airport', 'Airports'),
(138, 'Queens', 'LaGuardia Airport', 'Airports'),
(140, 'Manhattan', 'Lenox Hill East', 'Yellow Zone'),
(141, 'Manhattan', 'Lenox Hill West', 'Yellow Zone'),
(142, 'Manhattan', 'Lincoln Square East', 'Yellow Zone'),
(143, 'Manhattan', 'Lincoln Square West', 'Yellow Zone'),
(148, 'Manhattan', 'Lower East Side', 'Yellow Zone'),
(158, 'Manhattan', 'Meatpacking/West Village West', 'Yellow Zone'),
(161, 'Manhattan', 'Midtown Center', 'Yellow Zone'),
(162, 'Manhattan', 'Midtown East', 'Yellow Zone'),
(163, 'Manhattan', 'Midtown North', 'Yellow Zone'),
(164, 'Manhattan', 'Midtown South', 'Yellow Zone'),
(170, 'Manhattan', 'Murray Hill', 'Yellow Zone'),
(186, 'Manhattan', 'Penn Station/Madison Sq West', 'Yellow Zone'),
(209, 'Manhattan', 'Seaport', 'Yellow Zone'),
(211, 'Manhattan', 'SoHo', 'Yellow Zone'),
(224, 'Manhattan', 'Stuy Town/Peter Cooper Village', 'Yellow Zone'),
(229, 'Manhattan', 'Sutton Place/Turtle Bay North', 'Yellow Zone'),
(230, 'Manhattan', 'Times Sq/Theatre District', 'Yellow Zone'),
(231, 'Manhattan', 'TriBeCa/Civic Center', 'Yellow Zone'),
(234, 'Manhattan', 'Union Sq', 'Yellow Zone'),
(236, 'Manhattan', 'Upper East Side North', 'Yellow Zone'),
(237, 'Manhattan', 'Upper East Side South', 'Yellow Zone'),
(238, 'Manhattan', 'Upper West Side North', 'Yellow Zone'),
(239, 'Manhattan', 'Upper West Side South', 'Yellow Zone'),
(246, 'Manhattan', 'West Chelsea/Hudson Yards', 'Yellow Zone'),
(249, 'Manhattan', 'West Village', 'Yellow Zone'),
(261, 'Manhattan', 'World Trade Center', 'Yellow Zone'),
(262, 'Manhattan', 'Yorkville East', 'Yellow Zone'),
(263, 'Manhattan', 'Yorkville West', 'Yellow Zone'),
(264, 'Unknown', 'N/A', 'N/A'),
(265, 'N/A', 'Outside of NYC', 'N/A');

-- Bases (FHV/HVFHV)
INSERT INTO bases (base_license_number, base_name, app_company) VALUES
('B02512', 'Uber NYC', 'Uber'),
('B02764', 'Uber NYC II', 'Uber'),
('B02617', 'Lyft Inc', 'Lyft'),
('B02682', 'Via Transportation', 'Via'),
('B02395', 'Carmel Car & Limo', NULL),
('B02404', 'Dial 7 Car Service', NULL),
('B02510', 'Skyline NY Inc', NULL);
EOSQL

PGPASSWORD=${MASTER_PASSWORD} psql -h ${ENDPOINT} -U ${MASTER_USERNAME} -d ${DB_NAME} \
    -f /tmp/nyctlc-lookups.sql 2>&1 | tee -a "${LOG_FILE}"

log "Lookups loaded. Inserting yellow taxi trips..."


cat > /tmp/nyctlc-yellow.sql << 'EOSQL'
INSERT INTO yellow_taxi_trips (vendor_id, tpep_pickup_datetime, tpep_dropoff_datetime, passenger_count, trip_distance, pu_location_id, do_location_id, rate_code_id, store_and_fwd_flag, payment_type, fare_amount, extra, mta_tax, tip_amount, tolls_amount, improvement_surcharge, congestion_surcharge, total_amount) VALUES
(1, '2024-01-15 08:22:00', '2024-01-15 08:38:00', 1, 2.10, 161, 237, 1, 'N', 1, 12.50, 1.00, 0.50, 3.25, 0.00, 0.30, 2.50, 20.05),
(2, '2024-01-15 09:05:00', '2024-01-15 09:22:00', 2, 3.40, 236, 170, 1, 'N', 1, 17.00, 0.00, 0.50, 4.10, 0.00, 0.30, 2.50, 24.40),
(1, '2024-01-15 07:45:00', '2024-01-15 08:32:00', 1, 17.80, 138, 161, 2, 'N', 1, 52.00, 1.25, 0.50, 11.50, 6.55, 0.30, 2.50, 74.60),
(2, '2024-01-15 12:10:00', '2024-01-15 12:25:00', 1, 1.50, 234, 249, 1, 'N', 2, 10.00, 0.00, 0.50, 0.00, 0.00, 0.30, 2.50, 13.30),
(1, '2024-01-15 14:30:00', '2024-01-15 14:48:00', 3, 2.80, 163, 107, 1, 'N', 1, 14.50, 0.00, 0.50, 3.00, 0.00, 0.30, 2.50, 20.80),
(2, '2024-01-15 18:05:00', '2024-01-15 18:45:00', 1, 11.20, 161, 132, 2, 'N', 1, 52.00, 1.00, 0.50, 13.00, 6.55, 0.30, 2.50, 75.85),
(1, '2024-01-15 19:30:00', '2024-01-15 19:42:00', 2, 1.80, 230, 164, 1, 'N', 1, 10.50, 1.00, 0.50, 2.50, 0.00, 0.30, 2.50, 17.30),
(2, '2024-01-15 22:15:00', '2024-01-15 22:28:00', 1, 2.30, 79, 113, 1, 'N', 2, 11.50, 0.50, 0.50, 0.00, 0.00, 0.30, 2.50, 15.30),
(1, '2024-01-16 06:50:00', '2024-01-16 07:05:00', 1, 1.90, 140, 262, 1, 'N', 1, 11.00, 0.00, 0.50, 2.80, 0.00, 0.30, 2.50, 17.10),
(2, '2024-01-16 08:00:00', '2024-01-16 08:35:00', 1, 5.60, 239, 87, 1, 'N', 1, 26.00, 1.00, 0.50, 6.00, 0.00, 0.30, 2.50, 36.30),
(1, '2024-01-16 10:20:00', '2024-01-16 10:32:00', 2, 1.20, 100, 186, 1, 'N', 2, 8.50, 0.00, 0.50, 0.00, 0.00, 0.30, 2.50, 11.80),
(2, '2024-01-16 11:45:00', '2024-01-16 12:10:00', 1, 4.10, 211, 142, 1, 'N', 1, 19.50, 0.00, 0.50, 4.50, 0.00, 0.30, 2.50, 27.30),
(1, '2024-01-16 13:00:00', '2024-01-16 13:08:00', 1, 0.80, 90, 234, 1, 'N', 1, 6.50, 0.00, 0.50, 1.50, 0.00, 0.30, 2.50, 11.30),
(2, '2024-01-16 15:30:00', '2024-01-16 16:20:00', 2, 18.50, 132, 230, 2, 'N', 1, 52.00, 0.00, 0.50, 15.00, 6.55, 0.30, 2.50, 76.85),
(1, '2024-01-16 17:00:00', '2024-01-16 17:25:00', 1, 3.20, 162, 236, 1, 'N', 1, 16.00, 1.00, 0.50, 4.00, 0.00, 0.30, 2.50, 24.30),
(2, '2024-01-16 20:10:00', '2024-01-16 20:22:00', 4, 1.60, 143, 238, 1, 'N', 2, 9.50, 0.50, 0.50, 0.00, 0.00, 0.30, 2.50, 13.30),
(1, '2024-01-17 07:15:00', '2024-01-17 07:30:00', 1, 2.00, 237, 161, 1, 'N', 1, 11.50, 1.00, 0.50, 3.00, 0.00, 0.30, 2.50, 18.80),
(2, '2024-01-17 09:40:00', '2024-01-17 09:55:00', 1, 1.70, 170, 162, 1, 'Y', 1, 10.50, 0.00, 0.50, 2.50, 0.00, 0.30, 2.50, 16.30),
(1, '2024-01-17 16:20:00', '2024-01-17 16:50:00', 2, 4.50, 163, 1, 3, 'N', 1, 35.00, 1.00, 0.50, 8.00, 16.50, 0.30, 2.50, 63.80),
(2, '2024-01-17 23:00:00', '2024-01-17 23:18:00', 1, 3.10, 114, 68, 1, 'N', 2, 14.50, 0.50, 0.50, 0.00, 0.00, 0.30, 2.50, 18.30);
EOSQL

PGPASSWORD=${MASTER_PASSWORD} psql -h ${ENDPOINT} -U ${MASTER_USERNAME} -d ${DB_NAME} \
    -f /tmp/nyctlc-yellow.sql 2>&1 | tee -a "${LOG_FILE}"

log "Yellow trips loaded. Inserting green taxi trips..."


cat > /tmp/nyctlc-green.sql << 'EOSQL'
INSERT INTO green_taxi_trips (vendor_id, lpep_pickup_datetime, lpep_dropoff_datetime, passenger_count, trip_distance, pu_location_id, do_location_id, rate_code_id, store_and_fwd_flag, payment_type, fare_amount, extra, mta_tax, tip_amount, tolls_amount, improvement_surcharge, congestion_surcharge, trip_type, total_amount) VALUES
(2, '2024-01-15 07:30:00', '2024-01-15 07:52:00', 1, 3.80, 7, 138, 1, 'N', 1, 18.50, 0.00, 0.50, 4.20, 0.00, 0.30, 0.00, 1, 23.50),
(1, '2024-01-15 09:10:00', '2024-01-15 09:28:00', 2, 2.50, 41, 43, 1, 'N', 2, 13.00, 0.00, 0.50, 0.00, 0.00, 0.30, 0.00, 1, 13.80),
(2, '2024-01-15 11:00:00', '2024-01-15 11:15:00', 1, 1.90, 7, 7, 1, 'N', 1, 10.50, 0.00, 0.50, 2.50, 0.00, 0.30, 0.00, 1, 13.80),
(1, '2024-01-15 14:20:00', '2024-01-15 14:40:00', 1, 3.20, 41, 48, 1, 'N', 1, 15.00, 0.00, 0.50, 3.50, 0.00, 0.30, 2.50, 1, 21.80),
(2, '2024-01-15 17:45:00', '2024-01-15 18:05:00', 3, 2.80, 7, 79, 1, 'N', 2, 14.00, 1.00, 0.50, 0.00, 0.00, 0.30, 2.50, 1, 18.30),
(1, '2024-01-16 06:30:00', '2024-01-16 06:55:00', 1, 4.50, 7, 132, 1, 'N', 1, 21.00, 0.00, 0.50, 5.00, 0.00, 0.30, 0.00, 1, 26.80),
(2, '2024-01-16 08:45:00', '2024-01-16 09:00:00', 1, 1.60, 41, 41, 1, 'N', 2, 9.50, 0.00, 0.50, 0.00, 0.00, 0.30, 0.00, 1, 10.30),
(1, '2024-01-16 12:30:00', '2024-01-16 12:50:00', 2, 3.00, 7, 113, 1, 'N', 1, 15.50, 0.00, 0.50, 3.80, 0.00, 0.30, 2.50, 1, 22.60),
(2, '2024-01-16 16:00:00', '2024-01-16 16:30:00', 1, 5.20, 41, 161, 1, 'N', 1, 23.00, 1.00, 0.50, 5.50, 0.00, 0.30, 2.50, 1, 32.80),
(1, '2024-01-16 19:15:00', '2024-01-16 19:30:00', 1, 2.10, 7, 7, 1, 'N', 2, 11.00, 0.50, 0.50, 0.00, 0.00, 0.30, 0.00, 1, 12.30),
(2, '2024-01-17 07:00:00', '2024-01-17 07:25:00', 1, 4.00, 41, 163, 1, 'N', 1, 19.00, 0.00, 0.50, 4.50, 0.00, 0.30, 2.50, 1, 26.80),
(1, '2024-01-17 10:30:00', '2024-01-17 10:42:00', 2, 1.40, 7, 7, 1, 'N', 1, 8.50, 0.00, 0.50, 2.00, 0.00, 0.30, 0.00, 1, 11.30),
(2, '2024-01-17 13:15:00', '2024-01-17 13:35:00', 1, 3.10, 41, 234, 1, 'N', 2, 15.00, 0.00, 0.50, 0.00, 0.00, 0.30, 2.50, 1, 18.30),
(1, '2024-01-17 15:50:00', '2024-01-17 16:20:00', 1, 5.80, 7, 132, 1, 'N', 1, 25.00, 1.00, 0.50, 6.00, 0.00, 0.30, 0.00, 1, 32.80),
(2, '2024-01-17 18:30:00', '2024-01-17 18:45:00', 1, 2.20, 41, 79, 1, 'N', 1, 12.00, 1.00, 0.50, 3.00, 0.00, 0.30, 2.50, 1, 19.30),
(1, '2024-01-18 08:00:00', '2024-01-18 08:20:00', 2, 3.50, 7, 161, 1, 'N', 2, 16.50, 0.00, 0.50, 0.00, 0.00, 0.30, 2.50, 1, 19.80),
(2, '2024-01-18 11:30:00', '2024-01-18 11:42:00', 1, 1.30, 41, 43, 1, 'N', 1, 8.00, 0.00, 0.50, 2.00, 0.00, 0.30, 0.00, 1, 10.80),
(1, '2024-01-18 14:00:00', '2024-01-18 14:25:00', 1, 4.20, 7, 230, 1, 'N', 1, 20.00, 0.00, 0.50, 4.80, 0.00, 0.30, 2.50, 1, 28.10),
(2, '2024-01-18 17:30:00', '2024-01-18 17:50:00', 3, 3.00, 41, 162, 1, 'N', 2, 15.00, 1.00, 0.50, 0.00, 0.00, 0.30, 2.50, 1, 19.30),
(1, '2024-01-18 21:00:00', '2024-01-18 21:12:00', 1, 1.80, 7, 7, 1, 'N', 1, 10.00, 0.50, 0.50, 2.50, 0.00, 0.30, 0.00, 1, 13.80);
EOSQL

PGPASSWORD=${MASTER_PASSWORD} psql -h ${ENDPOINT} -U ${MASTER_USERNAME} -d ${DB_NAME} \
    -f /tmp/nyctlc-green.sql 2>&1 | tee -a "${LOG_FILE}"

log "Green trips loaded. Inserting FHV trips..."


cat > /tmp/nyctlc-fhv.sql << 'EOSQL'
INSERT INTO fhv_trips (dispatching_base_num, pickup_datetime, dropoff_datetime, pu_location_id, do_location_id, sr_flag) VALUES
('B02395', '2024-01-15 06:00:00', '2024-01-15 06:25:00', 132, 161, NULL),
('B02404', '2024-01-15 07:30:00', '2024-01-15 07:50:00', 236, 170, NULL),
('B02510', '2024-01-15 08:45:00', '2024-01-15 09:10:00', 79, 87, NULL),
('B02395', '2024-01-15 10:00:00', '2024-01-15 10:20:00', 161, 230, NULL),
('B02404', '2024-01-15 11:30:00', '2024-01-15 11:55:00', 138, 163, NULL),
('B02510', '2024-01-15 13:00:00', '2024-01-15 13:15:00', 107, 90, NULL),
('B02395', '2024-01-15 14:30:00', '2024-01-15 14:50:00', 234, 142, NULL),
('B02404', '2024-01-15 16:00:00', '2024-01-15 16:35:00', 161, 132, NULL),
('B02510', '2024-01-15 18:00:00', '2024-01-15 18:20:00', 230, 237, NULL),
('B02395', '2024-01-15 20:00:00', '2024-01-15 20:30:00', 163, 1, NULL),
('B02404', '2024-01-16 07:00:00', '2024-01-16 07:20:00', 7, 138, NULL),
('B02510', '2024-01-16 09:00:00', '2024-01-16 09:25:00', 41, 161, NULL),
('B02395', '2024-01-16 11:00:00', '2024-01-16 11:15:00', 170, 162, NULL),
('B02404', '2024-01-16 13:30:00', '2024-01-16 13:50:00', 236, 239, NULL),
('B02510', '2024-01-16 15:00:00', '2024-01-16 15:30:00', 79, 132, NULL),
('B02395', '2024-01-16 17:30:00', '2024-01-16 17:55:00', 161, 236, 1),
('B02404', '2024-01-16 19:00:00', '2024-01-16 19:20:00', 143, 238, NULL),
('B02510', '2024-01-17 08:00:00', '2024-01-17 08:30:00', 132, 163, NULL),
('B02395', '2024-01-17 12:00:00', '2024-01-17 12:18:00', 237, 140, NULL),
('B02404', '2024-01-17 16:00:00', '2024-01-17 16:25:00', 230, 87, NULL);
EOSQL

PGPASSWORD=${MASTER_PASSWORD} psql -h ${ENDPOINT} -U ${MASTER_USERNAME} -d ${DB_NAME} \
    -f /tmp/nyctlc-fhv.sql 2>&1 | tee -a "${LOG_FILE}"

log "FHV trips loaded. Inserting HVFHV trips..."


cat > /tmp/nyctlc-hvfhv.sql << 'EOSQL'
INSERT INTO hvfhv_trips (hvfhs_license_num, dispatching_base_num, originating_base_num, request_datetime, on_scene_datetime, pickup_datetime, dropoff_datetime, pu_location_id, do_location_id, trip_miles, trip_time, base_passenger_fare, tolls, bcf, sales_tax, congestion_surcharge, tips, driver_pay, shared_request_flag, shared_match_flag, access_a_ride_flag, wav_request_flag, wav_match_flag) VALUES
('HV0003', 'B02512', 'B02512', '2024-01-15 08:00:00', '2024-01-15 08:04:00', '2024-01-15 08:05:00', '2024-01-15 08:22:00', 161, 237, 2.10, 1020, 15.50, 0.00, 0.44, 1.38, 2.50, 3.20, 11.75, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-15 08:30:00', '2024-01-15 08:33:00', '2024-01-15 08:35:00', '2024-01-15 09:10:00', 132, 161, 11.80, 2100, 42.00, 6.55, 1.21, 3.73, 2.50, 8.50, 35.20, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02764', 'B02764', '2024-01-15 09:00:00', '2024-01-15 09:02:00', '2024-01-15 09:03:00', '2024-01-15 09:18:00', 236, 170, 1.80, 900, 12.00, 0.00, 0.34, 1.07, 2.50, 2.50, 9.10, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-15 10:15:00', '2024-01-15 10:18:00', '2024-01-15 10:20:00', '2024-01-15 10:35:00', 79, 234, 1.50, 900, 11.50, 0.00, 0.33, 1.02, 2.50, 0.00, 8.80, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02512', 'B02512', '2024-01-15 12:00:00', '2024-01-15 12:05:00', '2024-01-15 12:06:00', '2024-01-15 12:28:00', 163, 132, 10.50, 1320, 38.00, 6.55, 1.10, 3.38, 2.50, 7.00, 31.50, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-15 14:00:00', '2024-01-15 14:03:00', '2024-01-15 14:05:00', '2024-01-15 14:20:00', 230, 164, 1.20, 900, 10.50, 0.00, 0.30, 0.93, 2.50, 2.00, 8.00, 'Y', 'Y', ' ', 'N', 'N'),
('HV0003', 'B02764', 'B02764', '2024-01-15 16:30:00', '2024-01-15 16:33:00', '2024-01-15 16:35:00', '2024-01-15 17:05:00', 237, 132, 12.00, 1800, 45.00, 6.55, 1.30, 4.00, 2.50, 9.00, 37.50, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-15 18:00:00', '2024-01-15 18:02:00', '2024-01-15 18:03:00', '2024-01-15 18:15:00', 107, 90, 0.90, 720, 9.00, 0.00, 0.26, 0.80, 2.50, 1.80, 6.80, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02512', 'B02512', '2024-01-15 20:00:00', '2024-01-15 20:04:00', '2024-01-15 20:05:00', '2024-01-15 20:25:00', 142, 239, 2.50, 1200, 14.00, 0.00, 0.40, 1.24, 2.50, 3.00, 10.60, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-15 22:00:00', '2024-01-15 22:05:00', '2024-01-15 22:06:00', '2024-01-15 22:30:00', 161, 7, 4.20, 1440, 20.00, 0.00, 0.57, 1.78, 2.50, 4.00, 15.20, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02764', 'B02764', '2024-01-16 07:00:00', '2024-01-16 07:03:00', '2024-01-16 07:04:00', '2024-01-16 07:35:00', 138, 163, 9.50, 1860, 35.00, 0.00, 1.00, 3.11, 2.50, 7.50, 28.00, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-16 09:30:00', '2024-01-16 09:32:00', '2024-01-16 09:33:00', '2024-01-16 09:48:00', 234, 113, 1.30, 900, 11.00, 0.00, 0.31, 0.98, 2.50, 2.20, 8.30, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02512', 'B02512', '2024-01-16 11:00:00', '2024-01-16 11:02:00', '2024-01-16 11:03:00', '2024-01-16 11:20:00', 170, 236, 1.80, 1020, 12.50, 0.00, 0.36, 1.11, 2.50, 2.50, 9.50, 'Y', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-16 13:00:00', '2024-01-16 13:04:00', '2024-01-16 13:05:00', '2024-01-16 13:45:00', 163, 1, 15.00, 2400, 52.00, 16.50, 1.50, 4.62, 2.50, 10.00, 42.00, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02764', 'B02764', '2024-01-16 15:30:00', '2024-01-16 15:34:00', '2024-01-16 15:35:00', '2024-01-16 15:50:00', 79, 148, 1.10, 900, 10.00, 0.00, 0.29, 0.89, 2.50, 2.00, 7.60, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-16 17:00:00', '2024-01-16 17:02:00', '2024-01-16 17:03:00', '2024-01-16 17:22:00', 230, 107, 1.60, 1140, 13.00, 0.00, 0.37, 1.16, 2.50, 2.60, 9.90, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02512', 'B02512', '2024-01-16 19:00:00', '2024-01-16 19:03:00', '2024-01-16 19:04:00', '2024-01-16 19:18:00', 140, 262, 1.40, 840, 10.50, 0.00, 0.30, 0.93, 2.50, 0.00, 8.00, 'N', 'N', ' ', 'W', 'W'),
('HV0005', 'B02617', 'B02617', '2024-01-17 08:00:00', '2024-01-17 08:03:00', '2024-01-17 08:04:00', '2024-01-17 08:20:00', 162, 236, 1.90, 960, 13.00, 0.00, 0.37, 1.16, 2.50, 3.00, 9.90, 'N', 'N', ' ', 'N', 'N'),
('HV0003', 'B02764', 'B02764', '2024-01-17 12:00:00', '2024-01-17 12:02:00', '2024-01-17 12:03:00', '2024-01-17 12:35:00', 132, 230, 12.50, 1920, 46.00, 6.55, 1.33, 4.09, 2.50, 9.50, 38.00, 'N', 'N', ' ', 'N', 'N'),
('HV0005', 'B02617', 'B02617', '2024-01-17 18:00:00', '2024-01-17 18:04:00', '2024-01-17 18:05:00', '2024-01-17 18:22:00', 211, 249, 1.20, 1020, 11.00, 0.00, 0.31, 0.98, 2.50, 2.20, 8.30, 'N', 'N', ' ', 'N', 'N');
EOSQL

PGPASSWORD=${MASTER_PASSWORD} psql -h ${ENDPOINT} -U ${MASTER_USERNAME} -d ${DB_NAME} \
    -f /tmp/nyctlc-hvfhv.sql 2>&1 | tee -a "${LOG_FILE}"

log "HVFHV trips loaded."


# --- Cleanup temp files ---
rm -f /tmp/nyctlc-schema.sql /tmp/nyctlc-lookups.sql /tmp/nyctlc-yellow.sql \
      /tmp/nyctlc-green.sql /tmp/nyctlc-fhv.sql /tmp/nyctlc-hvfhv.sql

log ""
log "================================================================================"
log "NYC TLC DATABASE SETUP COMPLETE!"
log "================================================================================"
log "Cluster ID:  ${CLUSTER_ID}"
log "Instance ID: ${INSTANCE_ID}"
log "Endpoint:    ${ENDPOINT}"
log "Database:    ${DB_NAME}"
log "Username:    ${MASTER_USERNAME}"
log "Password:    ${MASTER_PASSWORD}"
log "Port:        5432"
log ""
log "Tables created:"
log "  - vendors (2 rows)"
log "  - rate_codes (6 rows)"
log "  - payment_types (6 rows)"
log "  - taxi_zones (50 zones)"
log "  - bases (7 rows)"
log "  - yellow_taxi_trips (20 rows)"
log "  - green_taxi_trips (20 rows)"
log "  - fhv_trips (20 rows)"
log "  - hvfhv_trips (20 rows)"
log ""
log "Query via RDS Query Editor v2 in the AWS Console."
log "To teardown: ~/mission-deh-hof-bootcamp-mission-1/mission-deh-hof-nyctlc-db-teardown.sh"
log "================================================================================"
