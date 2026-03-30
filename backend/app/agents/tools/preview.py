"""Customer Preview — before/after composite generation via text.

Phase 4: Generates text-based property preview descriptions that can be
sent via SMS. For visual composites, delegates to an external image
generation service or pre-built templates.

Key capabilities:
  - Generate property assessment summary from measurement data
  - Create before/after text descriptions for customer SMS
  - Prepare data for visual composite generation (future: image API)
  - Format measurement highlights for customer consumption
"""

from langchain_core.tools import tool

from app.integrations.eagleview.client import PropertyMeasurement
from app.integrations.llm.router import LLMRequest, ModelTier, llm_router


@tool
async def generate_property_summary(
    measurement: dict,
    project_type: str = "roof_replacement",
    tenant_id: str | None = None,
) -> dict:
    """Generate a customer-friendly property summary from measurement data.

    Creates a text summary suitable for SMS that highlights key property
    measurements and what the scope of work involves.

    Args:
        measurement: Dict of PropertyMeasurement fields.
        project_type: Type of project for context.
        tenant_id: For cost tracking.

    Returns:
        Dict with summary text, key highlights, and SMS-formatted message.
    """
    highlights = []
    if measurement.get("total_roof_sqft"):
        highlights.append(f"Roof area: {measurement['total_roof_sqft']:,.0f} sq ft")
    if measurement.get("num_facets"):
        highlights.append(f"Roof sections: {measurement['num_facets']}")
    if measurement.get("predominant_pitch"):
        highlights.append(f"Roof pitch: {measurement['predominant_pitch']}")
    if measurement.get("stories"):
        highlights.append(f"Stories: {measurement['stories']}")
    if measurement.get("eave_length_ft"):
        highlights.append(f"Eave length: {measurement['eave_length_ft']:.0f} ft")

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write concise, friendly property assessment summaries for homeowners "
                        "considering a roofing or siding project. Use plain language. Keep it to "
                        "3-4 sentences. Mention key measurements naturally. Be professional but warm."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Project type: {project_type.replace('_', ' ').title()}\n"
                        f"Property measurements:\n" + "\n".join(f"  - {h}" for h in highlights)
                    ),
                },
            ],
            tier=ModelTier.FAST,
            max_tokens=200,
            tenant_id=tenant_id,
        )
    )

    # Format for SMS (160 char segments)
    sms_message = _format_preview_sms(measurement, project_type, response.content)

    return {
        "summary": response.content,
        "highlights": highlights,
        "sms_message": sms_message,
        "measurement_source": measurement.get("source", "manual"),
    }


@tool
async def generate_scope_preview(
    measurement: dict,
    estimate_low: float = 0.0,
    estimate_high: float = 0.0,
    project_type: str = "roof_replacement",
    tenant_id: str | None = None,
) -> dict:
    """Generate a scope-of-work preview for the customer.

    Combines measurement data with estimate range to create a clear
    picture of what the project entails.

    Args:
        measurement: Dict of PropertyMeasurement fields.
        estimate_low: Low end of estimate range.
        estimate_high: High end of estimate range.
        project_type: Type of project.
        tenant_id: For cost tracking.

    Returns:
        Dict with scope description, material list, and SMS message.
    """
    scope_items = _build_scope_items(measurement, project_type)

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write clear, professional scope-of-work previews for homeowners. "
                        "Explain what will happen during the project in plain language. "
                        "Keep it to 4-5 sentences. Include the estimate range if provided. "
                        "End with a reassuring note about quality."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Project: {project_type.replace('_', ' ').title()}\n"
                        f"Scope items:\n" + "\n".join(f"  - {s}" for s in scope_items) + "\n"
                        + (f"Estimate range: ${estimate_low:,.0f} - ${estimate_high:,.0f}" if estimate_low else "")
                    ),
                },
            ],
            tier=ModelTier.FAST,
            max_tokens=300,
            tenant_id=tenant_id,
        )
    )

    return {
        "scope_description": response.content,
        "scope_items": scope_items,
        "estimate_range": (
            f"${estimate_low:,.0f} - ${estimate_high:,.0f}" if estimate_low else "Pending"
        ),
        "sms_message": response.content,
    }


def _format_preview_sms(
    measurement: dict, project_type: str, summary: str
) -> str:
    """Format a property preview for SMS delivery."""
    lines = [f"Your {project_type.replace('_', ' ').title()} Project"]
    lines.append("")
    lines.append(summary)
    lines.append("")

    if measurement.get("total_roof_sqft"):
        lines.append(f"Roof: {measurement['total_roof_sqft']:,.0f} sq ft")
    if measurement.get("num_facets"):
        lines.append(f"Sections: {measurement['num_facets']}")
    if measurement.get("predominant_pitch"):
        lines.append(f"Pitch: {measurement['predominant_pitch']}")

    lines.append("")
    lines.append("Reply with any questions!")

    return "\n".join(lines)


def _build_scope_items(measurement: dict, project_type: str) -> list[str]:
    """Build a list of scope items based on project type and measurements."""
    items = []

    if "roof" in project_type:
        items.append("Remove existing roofing materials")
        items.append("Inspect and repair decking as needed")
        items.append("Install ice & water shield at eaves and valleys")
        items.append("Install synthetic underlayment")
        items.append("Install new architectural shingles")

        if measurement.get("ridge_length_ft"):
            items.append(
                f"Install ridge vent (~{measurement['ridge_length_ft']:.0f} ft)"
            )
        if measurement.get("flashing_length_ft"):
            items.append(
                f"Install/replace flashing (~{measurement['flashing_length_ft']:.0f} ft)"
            )
        if measurement.get("drip_edge_length_ft"):
            items.append(
                f"Install drip edge (~{measurement['drip_edge_length_ft']:.0f} ft)"
            )

        items.append("Clean up all debris and magnetic nail sweep")
        items.append("Final inspection and walkthrough")

    elif "siding" in project_type:
        items.append("Remove existing siding")
        items.append("Inspect and repair sheathing as needed")
        items.append("Install house wrap / moisture barrier")
        items.append("Install new siding panels")
        items.append("Install trim and corner pieces")
        items.append("Caulk and seal all joints")
        items.append("Final inspection and cleanup")

    return items
