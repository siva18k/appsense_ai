#!/usr/bin/env bash
# Launch the single AppSense EC2 instance and start Docker Compose on it.
# Requires the deployer IAM policy in docs/aws-iam/appsense-sandbox-deployer-policy.json.
#
#   cp .env.sample .env    # then set LLM_API_KEY
#   SUBNET_ID=subnet-xxxx BUCKET=appsense-deploy ./deploy/ec2/deploy.sh
#
# BUCKET must start with appsense- so it matches the IAM policies.
# Re-running the script updates the app on the same instance.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
: "${SUBNET_ID:?Set SUBNET_ID to a public subnet id}"
: "${BUCKET:?Set BUCKET to an S3 bucket name starting with appsense-}"

if [[ "$BUCKET" != appsense-* ]]; then
  echo "BUCKET must start with appsense-" >&2
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Create $ROOT/.env from .env.sample and set LLM_API_KEY before deploying." >&2
  exit 1
fi

AWS_REGION="${AWS_REGION:-$(aws configure get region)}"
if [[ -z "$AWS_REGION" || "$AWS_REGION" == "None" ]]; then
  echo "Set AWS_REGION or configure a default AWS region." >&2
  exit 1
fi
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"

VPC_ID="$(aws ec2 describe-subnets --subnet-ids "$SUBNET_ID" --query "Subnets[0].VpcId" --output text)"
if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
  echo "Could not find a VPC for subnet $SUBNET_ID" >&2
  exit 1
fi

ALLOWED_CIDR="${ALLOWED_CIDR:-0.0.0.0/0}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.medium}"
STACK="${STACK:-appsense-ec2}"

if ! aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  echo "Creating s3://$BUCKET"
  python3 - "$BUCKET" "$AWS_REGION" <<'PY'
import datetime
import json
import os
import subprocess
import sys

bucket, region = sys.argv[1], sys.argv[2]
payload = {
    "Bucket": bucket,
    "Tagging": {
        "TagSet": [
            {"Key": "Name", "Value": "appsense"},
            {"Key": "Created Date", "Value": datetime.date.today().isoformat()},
            {"Key": "Division", "Value": os.environ.get("APPSENSE_TAG_DIVISION", "appsense")},
            {"Key": "Internal", "Value": "true"},
            {"Key": "Client Code", "Value": os.environ.get("APPSENSE_TAG_CLIENT_CODE", "internal")},
            {"Key": "Created By", "Value": os.environ.get("APPSENSE_TAG_CREATED_BY", "appsense-deploy")},
            {"Key": "Customer Name", "Value": os.environ.get("APPSENSE_TAG_CUSTOMER", "internal")},
            {"Key": "Project Name", "Value": "appsense"},
            {"Key": "Owner", "Value": os.environ.get("APPSENSE_TAG_OWNER", "appsense")},
        ]
    },
}
if region != "us-east-1":
    payload["CreateBucketConfiguration"] = {"LocationConstraint": region}
path = "/tmp/appsense-create-bucket.json"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
subprocess.check_call(["aws", "s3api", "create-bucket", "--cli-input-json", f"file://{path}"])
PY
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
fi

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --template-file "$ROOT/deploy/ec2/appsense-ec2.yaml" \
  --stack-name "$STACK" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    "VpcId=$VPC_ID" \
    "SubnetId=$SUBNET_ID" \
    "AllowedCidr=$ALLOWED_CIDR" \
    "InstanceType=$INSTANCE_TYPE"

INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"
PUBLIC_IP="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIp'].OutputValue" --output text)"

echo "Waiting for SSM on $INSTANCE_ID"
for _ in $(seq 1 60); do
  status="$(aws ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query "InstanceInformationList[0].PingStatus" --output text 2>/dev/null || true)"
  if [[ "$status" == "Online" ]]; then
    break
  fi
  sleep 10
done
if [[ "${status:-}" != "Online" ]]; then
  echo "Instance never registered with Systems Manager. Check the subnet has a route to the internet." >&2
  exit 1
fi

tar -C "$ROOT" -czf /tmp/appsense-src.tgz \
  --exclude data \
  --exclude .git \
  --exclude .env \
  --exclude node_modules \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude frontend/dist \
  .
aws s3 cp /tmp/appsense-src.tgz "s3://$BUCKET/appsense-src.tgz"
aws s3 cp "$ROOT/.env" "s3://$BUCKET/appsense.env"

python3 - "$BUCKET" "$AWS_REGION" <<'PY'
import json
import sys

bucket, region = sys.argv[1], sys.argv[2]
script = f"""
set -euxo pipefail
export AWS_DEFAULT_REGION={region}
mkdir -p /opt/appsense
aws s3 cp s3://{bucket}/appsense-src.tgz /tmp/appsense-src.tgz
tar -xzf /tmp/appsense-src.tgz -C /opt/appsense
aws s3 cp s3://{bucket}/appsense.env /opt/appsense/.env
chmod 600 /opt/appsense/.env
if grep -q '^FRONTEND_PORT=' /opt/appsense/.env; then
  sed -i 's/^FRONTEND_PORT=.*/FRONTEND_PORT=80/' /opt/appsense/.env
else
  echo 'FRONTEND_PORT=80' >> /opt/appsense/.env
fi
cd /opt/appsense
ready=0
i=0
while [ "$i" -lt 60 ]; do
  if docker compose version >/dev/null 2>&1; then
    ready=1
    break
  fi
  i=$((i+1))
  sleep 5
done
if [ "$ready" -ne 1 ]; then
  echo "docker compose is not installed yet" >&2
  exit 1
fi
docker compose up --build -d
"""
with open("/tmp/appsense-ssm-params.json", "w", encoding="utf-8") as handle:
    json.dump({"commands": [script]}, handle)
PY

COMMAND_ID="$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --timeout-seconds 1800 \
  --comment "Deploy AppSense" \
  --parameters file:///tmp/appsense-ssm-params.json \
  --query Command.CommandId --output text)"

echo "SSM command $COMMAND_ID"
for _ in $(seq 1 120); do
  invocation="$(aws ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" --output json 2>/dev/null || true)"
  state="$(python3 -c 'import json,sys
try:
    print(json.loads(sys.argv[1] or "{}").get("Status",""))
except Exception:
    print("")
' "$invocation")"
  case "$state" in
    Success)
      echo "AppSense is running at http://$PUBLIC_IP"
      exit 0
      ;;
    Failed|Cancelled|TimedOut)
      echo "$invocation" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("StandardErrorContent") or data.get("StandardOutputContent") or data)'
      exit 1
      ;;
  esac
  sleep 15
done

echo "Timed out waiting for the deploy command. Check SSM command $COMMAND_ID." >&2
exit 1
