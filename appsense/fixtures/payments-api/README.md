# Payments API

Internal card settlement and authorization service used by the merchant dashboard.

- Runtime: Python 3.12, FastAPI, Uvicorn
- Port: `8080` (health on `GET /health`)
- Datastores: Postgres `payments_prod`, Redis `payments-cache`
- Nightly batch: `settlement-worker` at 01:15 UTC

## Local run

```bash
make run
# or
uvicorn payments.api:app --host 0.0.0.0 --port 8080
```

## Support

On-call: Payments Platform (PagerDuty: `payments-api`).
Escalate 5xx > 2% for 10 minutes or settlement SLA miss > 15 minutes.
