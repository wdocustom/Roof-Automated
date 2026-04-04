"""SOW (Scope of Work) generator — AI-powered structured scope of work.

Uses Gemma 4 to produce a detailed, itemized scope of work from project data.
Every project through every funnel (SMS lead, manual create, referral) gets
the same professional, standardized SOW format.

The SOW is stored as JSON on the project and rendered into the contract HTML.
Future: fine-tune Gemma 4 on approved SOWs for per-contractor voice.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_tenant_session
from app.integrations.llm.router import LLMRequest, ModelTier, llm_router
from app.models.company import Company
from app.models.project import Project

logger = logging.getLogger(__name__)

# ─── SOW JSON Schema (what we ask the LLM to produce) ──────────

SOW_JSON_SCHEMA = """{
  "project_summary": "<2-3 sentence overview of the project>",
  "line_items": [
    {
      "category": "<tear_off|underlayment|shingles|flashing|ridge|gutters|siding|cleanup|other>",
      "description": "<what will be done>",
      "materials": "<specific materials/brands>",
      "quantity": "<amount with units>"
    }
  ],
  "exclusions": ["<things NOT included in this scope>"],
  "assumptions": ["<conditions assumed to be true>"],
  "warranty_terms": "<warranty description>",
  "estimated_duration": "<e.g. 2-3 days weather permitting>"
}"""


# ─── SOW generation prompt by project type ──────────────────────

ROOFING_CONTEXT = """
Standard roofing scope categories (include all that apply):
- tear_off: Remove existing roofing materials, inspect decking
- decking_repair: Replace damaged/rotted decking (if discovered)
- underlayment: Ice/water shield at eaves + synthetic underlayment
- drip_edge: Install aluminum drip edge at eaves and rakes
- flashing: Step flashing, counter flashing, valley metal, pipe boots
- shingles: Install architectural shingles with proper nailing pattern
- ridge: Ridge cap shingles, ridge vent installation
- cleanup: Magnetic nail sweep, debris removal, yard inspection

Standard exclusions: interior drywall/paint, landscaping replacement, structural framing, permits (unless specified), gutter work (unless combo).
Standard assumptions: No more than 10% decking replacement, standard pitch accessible by ladders, disposal included.
"""

SIDING_CONTEXT = """
Standard siding scope categories:
- removal: Remove existing siding and dispose
- house_wrap: Install/repair house wrap or moisture barrier
- insulation: Rigid foam insulation board (if included)
- siding: Install vinyl/fiber cement siding panels
- trim: J-channel, corners, window/door trim, soffits
- cleanup: Debris removal, yard inspection

Standard exclusions: window replacement, painting (unless fiber cement), electrical/plumbing penetrations.
"""

GUTTER_CONTEXT = """
Standard gutter scope categories:
- removal: Remove existing gutters and downspouts
- gutters: Install seamless aluminum gutters (typically 5" K-style)
- downspouts: Install downspouts with extensions
- hangers: Hidden hanger system every 24"
- accessories: End caps, miters, outlets, splash blocks
- cleanup: Debris removal

Standard exclusions: underground drainage, soffit/fascia repair, gutter guards (unless specified).
"""


async def generate_sow(company_id: str, project_id: str) -> dict:
    """Generate a structured SOW for a project using Gemma 4.

    Returns the SOW as a dict and saves it to project.sow_json.
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

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()

    # ─── Build context from project data ────────────────────────
    project_type = project.project_type.value
    combo_details = []
    if project.combo_details:
        try:
            combo_details = json.loads(project.combo_details)
        except json.JSONDecodeError:
            pass

    # Determine which domain contexts to include
    domain_context = ""
    service_types = combo_details if combo_details else [project_type]
    for svc in service_types:
        if "roof" in svc:
            domain_context += ROOFING_CONTEXT
        if "siding" in svc:
            domain_context += SIDING_CONTEXT
        if "gutter" in svc:
            domain_context += GUTTER_CONTEXT

    if not domain_context:
        domain_context = ROOFING_CONTEXT  # Default

    # Build project details
    project_details = f"Project type: {project_type.replace('_', ' ').title()}\n"
    if combo_details:
        project_details += f"Services included: {', '.join(s.replace('_', ' ').title() for s in combo_details)}\n"
    project_details += f"Property: {project.property_address}, {project.property_city}, {project.property_state} {project.property_zip}\n"
    if project.estimated_sqft:
        project_details += f"Estimated area: {project.estimated_sqft:,.0f} sq ft\n"
    if project.contract_amount:
        project_details += f"Contract amount: ${project.contract_amount:,.2f}\n"
    elif project.estimate_low and project.estimate_high:
        project_details += f"Estimate range: ${project.estimate_low:,.2f} - ${project.estimate_high:,.2f}\n"
    if project.description:
        project_details += f"Notes/description: {project.description}\n"

    company_name = company.name if company else "Contractor"

    # ─── Call Gemma 4 for structured SOW ────────────────────────
    system_prompt = (
        f"You are a professional scope of work generator for {company_name}, "
        f"an exterior contracting company. Generate a detailed, itemized scope of work "
        f"for the following project.\n\n"
        f"DOMAIN KNOWLEDGE:\n{domain_context}\n\n"
        f"PROJECT DETAILS:\n{project_details}\n\n"
        f"Generate a comprehensive, professional SOW as JSON matching this exact schema:\n"
        f"{SOW_JSON_SCHEMA}\n\n"
        f"Requirements:\n"
        f"- Include ALL relevant line items for the project type(s)\n"
        f"- Use specific materials from the project description if mentioned\n"
        f"- Be specific about quantities (use sqft, linear ft, squares, etc.)\n"
        f"- Include realistic exclusions and assumptions\n"
        f"- Warranty should mention both workmanship (5 years) and manufacturer material warranty\n"
        f"- Duration should be realistic for the project size\n"
        f"- Respond with ONLY valid JSON, no other text"
    )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate the scope of work."},
            ],
            tier=ModelTier.SOW,
            temperature=0.2,
            max_tokens=1500,
            tenant_id=company_id,
            response_format={"type": "json_object"},
        )
    )

    # Parse the JSON response
    sow_data = response.json()
    if not sow_data:
        # Fallback: try to extract JSON from text response
        try:
            # Find JSON in the response
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            sow_data = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            logger.error("Failed to parse SOW response as JSON: %s", response.content[:200])
            raise ValueError("SOW generation failed — could not parse LLM response")

    # Validate required fields
    if "line_items" not in sow_data or not sow_data["line_items"]:
        raise ValueError("SOW generation produced no line items")

    # ─── Save to project ────────────────────────────────────────
    sow_json_str = json.dumps(sow_data)

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        proj = result.scalar_one()
        proj.sow_json = sow_json_str
        await session.flush()

    logger.info(
        "SOW generated for project %s: %d line items, model=%s",
        project_id,
        len(sow_data["line_items"]),
        response.model,
    )

    return {
        "project_id": project_id,
        "sow": sow_data,
        "model": response.model,
        "tokens": response.input_tokens + response.output_tokens,
    }


def render_sow_html(sow_json: str | None) -> str:
    """Render a stored SOW JSON into HTML for the contract.

    Returns an HTML fragment to insert into the contract template.
    Falls back to a generic message if no SOW is available.
    """
    if not sow_json:
        return "<p><em>Scope of work to be detailed in a separate document.</em></p>"

    try:
        sow = json.loads(sow_json)
    except json.JSONDecodeError:
        return f"<p>{sow_json}</p>"

    html_parts = []

    # Project summary
    if sow.get("project_summary"):
        html_parts.append(f"<p>{sow['project_summary']}</p>")

    # Line items table
    items = sow.get("line_items", [])
    if items:
        html_parts.append(
            '<table style="width:100%;border-collapse:collapse;margin:12px 0;">'
            '<thead><tr style="background:#f8f8f8;border-bottom:2px solid #ddd;">'
            '<th style="text-align:left;padding:8px;font-size:13px;">Item</th>'
            '<th style="text-align:left;padding:8px;font-size:13px;">Description</th>'
            '<th style="text-align:left;padding:8px;font-size:13px;">Materials</th>'
            '<th style="text-align:left;padding:8px;font-size:13px;">Qty</th>'
            "</tr></thead><tbody>"
        )
        for i, item in enumerate(items):
            bg = 'style="background:#fafafa;"' if i % 2 else ""
            cat = item.get("category", "").replace("_", " ").title()
            desc = item.get("description", "")
            materials = item.get("materials", "-")
            qty = item.get("quantity", "-")
            html_parts.append(
                f"<tr {bg}>"
                f'<td style="padding:6px 8px;font-size:12px;font-weight:600;border-bottom:1px solid #eee;">{cat}</td>'
                f'<td style="padding:6px 8px;font-size:12px;border-bottom:1px solid #eee;">{desc}</td>'
                f'<td style="padding:6px 8px;font-size:12px;border-bottom:1px solid #eee;">{materials}</td>'
                f'<td style="padding:6px 8px;font-size:12px;border-bottom:1px solid #eee;">{qty}</td>'
                "</tr>"
            )
        html_parts.append("</tbody></table>")

    # Exclusions
    exclusions = sow.get("exclusions", [])
    if exclusions:
        html_parts.append('<p style="font-weight:600;margin-top:12px;font-size:13px;">Exclusions:</p><ul style="font-size:12px;margin:4px 0;">')
        for ex in exclusions:
            html_parts.append(f"<li>{ex}</li>")
        html_parts.append("</ul>")

    # Assumptions
    assumptions = sow.get("assumptions", [])
    if assumptions:
        html_parts.append('<p style="font-weight:600;margin-top:8px;font-size:13px;">Assumptions:</p><ul style="font-size:12px;margin:4px 0;">')
        for a in assumptions:
            html_parts.append(f"<li>{a}</li>")
        html_parts.append("</ul>")

    # Duration
    if sow.get("estimated_duration"):
        html_parts.append(
            f'<p style="font-size:12px;margin-top:8px;">'
            f'<strong>Estimated Duration:</strong> {sow["estimated_duration"]}</p>'
        )

    # Warranty
    if sow.get("warranty_terms"):
        html_parts.append(
            f'<p style="font-size:12px;margin-top:4px;">'
            f'<strong>Warranty:</strong> {sow["warranty_terms"]}</p>'
        )

    return "\n".join(html_parts)
