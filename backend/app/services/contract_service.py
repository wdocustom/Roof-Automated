"""Contract generation and signing service.

Generates a mobile-first HTML contract from project data, sends it via SMS,
and handles the signing flow. No third-party e-sign service needed.

Legally binding under ESIGN Act (15 U.S.C. 7001) and UETA:
- Customer consents to electronic signature by tapping "Sign"
- Intent to sign captured via typed name + explicit button
- Record preserved: signer name, IP, timestamp, full HTML snapshot
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_tenant_session
from app.integrations.stripe.payments import build_payment_schedule
from app.models.company import Company
from app.models.contract import Contract, ContractStatus
from app.models.project import Project, ProjectStatus
from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_contract(
    company_id: str,
    project_id: str,
    contract_amount: float | None = None,
) -> dict:
    """Generate a contract for a project and return the signing URL.

    If contract_amount is not provided, uses the project's estimate midpoint.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.customer))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        customer = project.customer
        if not customer:
            raise ValueError("Project has no customer")

        # Get company details for contract header
        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()
        if not company:
            raise ValueError("Company not found")

        # Determine contract amount
        amount = contract_amount
        if not amount:
            if project.contract_amount:
                amount = project.contract_amount
            elif project.estimate_low and project.estimate_high:
                # Use midpoint of estimate range
                amount = round((project.estimate_low + project.estimate_high) / 2, 2)
            else:
                raise ValueError("No contract amount or estimate available")

        # Build payment schedule (50/40/10 split)
        milestones = [
            {"name": "Deposit (upon signing)"},
            {"name": "Substantial completion"},
            {"name": "Final walkthrough & approval"},
        ]
        schedule = build_payment_schedule(amount, milestones)
        schedule_json = json.dumps(schedule)

        # Build contract HTML
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        html = _build_contract_html(
            company_name=company.name,
            company_phone=company.phone or "",
            company_license=f"{company.contractor_license_state or ''} #{company.contractor_license_number or ''}".strip(),
            company_address=f"{company.address or ''}, {company.city or ''}, {company.state or ''} {company.zip_code or ''}".strip(", "),
            customer_name=customer_name,
            customer_phone=customer.phone or "",
            customer_email=customer.email or "",
            property_address=project.property_address,
            property_city=project.property_city,
            property_state=project.property_state,
            property_zip=project.property_zip,
            project_type=project.project_type.value.replace("_", " ").title(),
            contract_amount=amount,
            payment_schedule=schedule,
            description=project.description or "",
        )

        # Create contract record
        contract = Contract(
            company_id=company_id,
            project_id=project.id,
            customer_id=customer.id,
            status=ContractStatus.DRAFT,
            html_content=html,
            contract_amount=amount,
            payment_schedule_json=schedule_json,
            company_name=company.name,
            company_phone=company.phone,
            company_license=company.contractor_license_number,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        session.add(contract)
        await session.flush()

        # Update project
        project.contract_amount = amount
        project.status = ProjectStatus.CONTRACT_SENT
        await session.flush()

        return {
            "contract_id": str(contract.id),
            "token": contract.token,
            "contract_amount": amount,
            "status": "draft",
        }


async def send_contract_sms(
    company_id: str,
    contract_id: str,
    base_url: str,
) -> str:
    """Send the signing link to the customer via SMS. Returns Twilio SID."""
    from app.integrations.twilio.sms import send_sms

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Contract)
            .options(selectinload(Contract.customer), selectinload(Contract.project))
            .where(Contract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise ValueError("Contract not found")

        # Get company Twilio number
        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()
        from_phone = company.twilio_phone_number if company else None
        if not from_phone:
            raise ValueError("No Twilio phone configured")

        customer = contract.customer
        customer_name = f"{customer.first_name or ''}".strip() or "there"
        sign_url = f"{base_url}/sign/{contract.token}"

        sms_body = (
            f"Hi {customer_name}! Your contract from {contract.company_name} "
            f"is ready for ${contract.contract_amount:,.2f}.\n\n"
            f"Review & sign here: {sign_url}\n\n"
            f"Valid for 7 days. Questions? Reply to this text."
        )

        sid = await send_sms(to=customer.phone, from_=from_phone, body=sms_body)

        # Update status
        contract.status = ContractStatus.SENT
        await session.flush()

    return sid


async def get_contract_by_token(token: str) -> dict | None:
    """Get contract data by signing token. No auth required (public endpoint)."""
    from app.core.database import get_system_session

    async with get_system_session() as session:
        result = await session.execute(
            select(Contract).where(Contract.token == token)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            return None

        # Track views
        if not contract.first_viewed_at:
            contract.first_viewed_at = datetime.now(UTC)
            if contract.status == ContractStatus.SENT:
                contract.status = ContractStatus.VIEWED
        contract.view_count = (contract.view_count or 0) + 1
        await session.flush()

        # Check expiration
        is_expired = (
            contract.expires_at
            and datetime.now(UTC) > contract.expires_at.replace(tzinfo=UTC)
            and contract.status != ContractStatus.SIGNED
        )

        schedule = []
        if contract.payment_schedule_json:
            try:
                schedule = json.loads(contract.payment_schedule_json)
            except json.JSONDecodeError:
                pass

        return {
            "contract_id": str(contract.id),
            "token": contract.token,
            "status": contract.status.value if not is_expired else "expired",
            "html_content": contract.html_content,
            "contract_amount": contract.contract_amount,
            "payment_schedule": schedule,
            "company_name": contract.company_name,
            "company_phone": contract.company_phone,
            "company_license": contract.company_license,
            "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
            "signer_name": contract.signer_name,
            "is_expired": is_expired,
            "expires_at": contract.expires_at.isoformat() if contract.expires_at else None,
        }


async def sign_contract(token: str, signer_name: str, signer_ip: str) -> dict:
    """Record the customer's signature on a contract."""
    from app.core.database import get_system_session

    async with get_system_session() as session:
        result = await session.execute(
            select(Contract).where(Contract.token == token)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise ValueError("Contract not found")

        if contract.status == ContractStatus.SIGNED:
            return {
                "status": "already_signed",
                "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
            }

        if contract.status == ContractStatus.VOIDED:
            raise ValueError("This contract has been voided")

        if (
            contract.expires_at
            and datetime.now(UTC) > contract.expires_at.replace(tzinfo=UTC)
        ):
            contract.status = ContractStatus.EXPIRED
            await session.flush()
            raise ValueError("This contract has expired")

        # Record signature
        now = datetime.now(UTC)
        contract.signer_name = signer_name
        contract.signer_ip = signer_ip
        contract.signed_at = now
        contract.status = ContractStatus.SIGNED
        await session.flush()

        # Update project status
        company_id = contract.company_id

    # Update project in tenant context
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == contract.project_id)
        )
        project = result.scalar_one_or_none()
        if project:
            project.status = ProjectStatus.CONTRACT_SIGNED
            await session.flush()

    # Send confirmation SMS to customer
    try:
        from app.integrations.twilio.sms import send_sms

        async with get_system_session() as session:
            result = await session.execute(
                select(Contract)
                .options(selectinload(Contract.customer))
                .where(Contract.token == token)
            )
            contract = result.scalar_one()
            customer = contract.customer

            co_result = await session.execute(
                select(Company).where(Company.clerk_org_id == company_id)
            )
            company = co_result.scalar_one_or_none()
            from_phone = company.twilio_phone_number if company else None

            if from_phone and customer.phone:
                await send_sms(
                    to=customer.phone,
                    from_=from_phone,
                    body=(
                        f"Contract signed! Thank you, {signer_name}. "
                        f"Your project with {contract.company_name} is confirmed. "
                        f"We'll be in touch about next steps. "
                    ),
                )

            # Also notify the company owner
            if from_phone and company.phone:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                await send_sms(
                    to=company.phone,
                    from_=from_phone,
                    body=(
                        f"Contract signed by {customer_name} ({customer.phone}) "
                        f"for ${contract.contract_amount:,.2f}. "
                        f"Project is now active!"
                    ),
                )
    except Exception:
        logger.exception("Failed to send signing confirmation SMS")

    return {
        "status": "signed",
        "signed_at": now.isoformat(),
        "signer_name": signer_name,
    }


def _build_contract_html(
    company_name: str,
    company_phone: str,
    company_license: str,
    company_address: str,
    customer_name: str,
    customer_phone: str,
    customer_email: str,
    property_address: str,
    property_city: str,
    property_state: str,
    property_zip: str,
    project_type: str,
    contract_amount: float,
    payment_schedule: list[dict],
    description: str,
) -> str:
    """Build the contract HTML content.

    This is a clean, structured HTML document — NOT a template with CSS.
    The signing page wraps this content in the mobile-first UI.
    """
    full_address = f"{property_address}, {property_city}, {property_state} {property_zip}"
    today = datetime.now(UTC).strftime("%B %d, %Y")

    schedule_rows = ""
    for item in payment_schedule:
        schedule_rows += (
            f"<tr>"
            f"<td>{item['milestone']}</td>"
            f"<td>{item['percentage']}%</td>"
            f"<td>${item['amount']:,.2f}</td>"
            f"</tr>"
        )

    return f"""
<h2>Roofing & Exterior Services Contract</h2>
<p><strong>Date:</strong> {today}</p>

<h3>Parties</h3>
<p><strong>Contractor:</strong> {company_name}<br>
{f"License: {company_license}<br>" if company_license else ""}
{f"Phone: {company_phone}<br>" if company_phone else ""}
{f"Address: {company_address}" if company_address else ""}</p>

<p><strong>Property Owner:</strong> {customer_name}<br>
{f"Phone: {customer_phone}<br>" if customer_phone else ""}
{f"Email: {customer_email}" if customer_email else ""}</p>

<h3>Property</h3>
<p>{full_address}</p>

<h3>Scope of Work</h3>
<p><strong>Project Type:</strong> {project_type}</p>
{f"<p>{description}</p>" if description else ""}
<p>Contractor agrees to furnish all labor, materials, equipment, and supervision
necessary to complete the above-described work at the property address in a
professional and workmanlike manner, in accordance with applicable building codes
and manufacturer specifications.</p>

<h3>Contract Price</h3>
<p><strong>Total: ${contract_amount:,.2f}</strong></p>

<h3>Payment Schedule</h3>
<table>
<thead><tr><th>Milestone</th><th>%</th><th>Amount</th></tr></thead>
<tbody>{schedule_rows}</tbody>
</table>

<h3>Terms & Conditions</h3>
<ol>
<li><strong>Materials.</strong> All materials will be new, of good quality, and
installed per manufacturer specifications. Specific brands/models will be
confirmed before work begins.</li>

<li><strong>Timeline.</strong> Work will begin within 10 business days of signing
(weather permitting). Contractor will communicate any delays promptly via text.</li>

<li><strong>Permits.</strong> Contractor will obtain all required permits and
schedule all required inspections at Contractor's expense.</li>

<li><strong>Warranty.</strong> Contractor provides a 5-year workmanship warranty
from date of completion, in addition to manufacturer material warranties.</li>

<li><strong>Change Orders.</strong> Any changes to the scope of work must be
agreed in writing by both parties. Changes may affect the total price and timeline.</li>

<li><strong>Cleanup.</strong> Contractor will remove all debris and leave the
property in clean condition upon completion. Magnetic nail sweep included.</li>

<li><strong>Insurance.</strong> Contractor maintains general liability insurance
and workers' compensation coverage. Proof available upon request.</li>

<li><strong>Cancellation.</strong> Either party may cancel this contract within
3 business days of signing without penalty. After 3 days, cancellation may be
subject to charges for materials ordered or work completed.</li>

<li><strong>Dispute Resolution.</strong> Any disputes will first be addressed
through good-faith negotiation. If unresolved, disputes will be settled through
binding arbitration in the county where the property is located.</li>

<li><strong>Entire Agreement.</strong> This contract represents the entire
agreement between the parties. No verbal agreements or representations outside
this document are binding.</li>
</ol>

<h3>Electronic Signature Consent</h3>
<p>By signing below, you agree that your electronic signature is the legal
equivalent of your handwritten signature. You consent to conducting this
transaction electronically under the federal ESIGN Act (15 U.S.C. &sect; 7001)
and your state's Uniform Electronic Transactions Act (UETA).</p>
"""
