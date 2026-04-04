"""Contract endpoints — generate, send, view, and sign contracts.

Two types of endpoints:
1. Authenticated (for the contractor): generate, send, list contracts
2. Public (for the customer): view and sign via token (no auth needed)
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.contract import Contract

logger = logging.getLogger(__name__)

router = APIRouter(tags=["contracts"])


# ─── Authenticated endpoints (contractor) ─────────────────────────


class GenerateContractRequest(BaseModel):
    project_id: str
    contract_amount: float | None = None


class ContractResponse(BaseModel):
    contract_id: str
    token: str
    status: str
    contract_amount: float
    sign_url: str | None = None


@router.post("/projects/{project_id}/generate-contract", response_model=ContractResponse)
async def generate_contract(
    project_id: uuid.UUID,
    request: Request,
    data: GenerateContractRequest | None = None,
    company_id: str = Depends(get_company_id),
):
    """Generate a contract for a project. Returns the signing token and URL."""
    from app.services.contract_service import generate_contract as gen

    try:
        result = await gen(
            company_id=company_id,
            project_id=str(project_id),
            contract_amount=data.contract_amount if data else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Contract generation failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(e))

    # Build signing URL from the frontend origin
    frontend_url = request.headers.get("origin") or str(request.base_url).rstrip("/")
    sign_url = f"{frontend_url}/sign/{result['token']}"

    return ContractResponse(
        contract_id=result["contract_id"],
        token=result["token"],
        status=result["status"],
        contract_amount=result["contract_amount"],
        sign_url=sign_url,
    )


@router.post("/contracts/{contract_id}/send")
async def send_contract(
    contract_id: uuid.UUID,
    request: Request,
    company_id: str = Depends(get_company_id),
):
    """Send the contract signing link to the customer via SMS."""
    from app.services.contract_service import send_contract_sms

    # Build base URL from request
    base_url = str(request.base_url).rstrip("/")
    # In production, use the frontend URL
    frontend_url = request.headers.get("origin") or base_url

    try:
        sid = await send_contract_sms(
            company_id=company_id,
            contract_id=str(contract_id),
            base_url=frontend_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Contract send failed for %s", contract_id)
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "sent", "twilio_sid": sid}


@router.get("/projects/{project_id}/contracts")
async def list_project_contracts(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """List all contracts for a project."""
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Contract)
            .where(Contract.project_id == project_id)
            .order_by(Contract.created_at.desc())
        )
        contracts = result.scalars().all()

    return [
        {
            "contract_id": str(c.id),
            "token": c.token,
            "status": c.status.value,
            "contract_amount": c.contract_amount,
            "signer_name": c.signer_name,
            "signed_at": c.signed_at.isoformat() if c.signed_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in contracts
    ]


# ─── Public endpoints (customer — no auth) ────────────────────────


@router.get("/public/contracts/{token}")
async def view_contract(token: str):
    """Public endpoint: view a contract by its signing token. No auth needed."""
    from app.services.contract_service import get_contract_by_token

    data = await get_contract_by_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Contract not found")

    return data


class SignRequest(BaseModel):
    signer_name: str


@router.post("/public/contracts/{token}/sign")
async def sign_contract_endpoint(
    token: str,
    data: SignRequest,
    request: Request,
):
    """Public endpoint: sign a contract. Records name, IP, and timestamp."""
    from app.services.contract_service import sign_contract

    # Get client IP
    signer_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        signer_ip = forwarded.split(",")[0].strip()

    try:
        result = await sign_contract(
            token=token,
            signer_name=data.signer_name.strip(),
            signer_ip=signer_ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result
