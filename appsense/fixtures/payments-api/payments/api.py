"""Fake Payments API surface for AppSense testing."""

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Payments API", version="2.4.1")


class AuthRequest(BaseModel):
    merchant_id: str
    amount_cents: int
    currency: str = "USD"
    card_token: str


class AuthResponse(BaseModel):
    auth_id: str
    status: str
    processor: str = "northstar"


@app.get("/health")
def health():
    return {"ok": True, "service": "payments-api", "region": "us-east-1"}


@app.post("/v1/authorizations", response_model=AuthResponse)
def authorize(body: AuthRequest, x_request_id: str | None = Header(default=None)):
    if body.amount_cents > 250_000:
        raise HTTPException(status_code=402, detail="amount_exceeds_merchant_limit")
    if not body.card_token.startswith("tok_"):
        raise HTTPException(status_code=400, detail="invalid_card_token")
    return AuthResponse(auth_id="auth_demo_88421", status="approved")


@app.post("/v1/captures/{auth_id}")
def capture(auth_id: str):
    if auth_id == "auth_expired":
        raise HTTPException(status_code=409, detail="authorization_expired")
    return {"auth_id": auth_id, "status": "captured"}


@app.get("/v1/settlements/{batch_id}")
def settlement(batch_id: str):
    return {
        "batch_id": batch_id,
        "status": "posted",
        "item_count": 1842,
        "failed": 3,
    }
