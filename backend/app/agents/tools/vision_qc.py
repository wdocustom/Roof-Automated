"""Advanced Vision QC — spec-based comparison and data collection.

Phase 4: Compares progress photos against EagleView/spec data for more
accurate QC assessments. Also collects structured data from photos to
build training datasets for future fine-tuning.

Key capabilities:
  - Compare photo against measurement specs (facet count, pitch, area)
  - Grade shingle alignment, flashing quality, drip edge installation
  - Collect structured annotations for ML training pipeline
  - Generate customer-facing QC summary reports
"""

from dataclasses import dataclass, field

from langchain_core.tools import tool

from app.integrations.llm.router import LLMRequest, ModelTier, llm_router


@dataclass
class QCComparison:
    """Result of comparing a progress photo against measurement specs."""

    photo_url: str = ""
    milestone: str = ""
    spec_match_score: float = 0.0  # 0.0 to 1.0 — how well photo matches specs
    issues: list[str] = field(default_factory=list)
    annotations: dict = field(default_factory=dict)  # Structured data for ML
    recommendation: str = ""  # approve / flag_for_review / reject
    confidence: float = 0.0
    details: str = ""


@tool
async def compare_photo_to_spec(
    image_url: str,
    milestone_name: str,
    measurement: dict | None = None,
    tenant_id: str | None = None,
) -> dict:
    """Compare a progress photo against measurement specifications.

    Uses vision to verify that installed work matches the property's
    measurement data (e.g., correct number of facets, proper flashing
    at valleys, drip edge along eaves).

    Args:
        image_url: URL of the progress photo.
        milestone_name: Current milestone being verified.
        measurement: Dict with spec data (from PropertyMeasurement).
        tenant_id: For cost tracking.

    Returns:
        Dict with spec_match_score, issues, annotations, recommendation.
    """
    spec_context = ""
    if measurement:
        spec_lines = []
        if measurement.get("total_roof_sqft"):
            spec_lines.append(f"Total roof area: {measurement['total_roof_sqft']} sqft")
        if measurement.get("num_facets"):
            spec_lines.append(f"Number of roof facets: {measurement['num_facets']}")
        if measurement.get("predominant_pitch"):
            spec_lines.append(f"Predominant pitch: {measurement['predominant_pitch']}")
        if measurement.get("ridge_length_ft"):
            spec_lines.append(f"Ridge length: {measurement['ridge_length_ft']} ft")
        if measurement.get("valley_length_ft"):
            spec_lines.append(f"Valley length: {measurement['valley_length_ft']} ft")
        if measurement.get("eave_length_ft"):
            spec_lines.append(f"Eave length: {measurement['eave_length_ft']} ft")
        if measurement.get("flashing_length_ft"):
            spec_lines.append(f"Flashing length: {measurement['flashing_length_ft']} ft")
        spec_context = "\n".join(spec_lines)

    system_prompt = (
        "You are an expert roofing QC inspector comparing a progress photo against "
        "property measurement specifications.\n\n"
        f"Milestone: {milestone_name}\n"
    )

    if spec_context:
        system_prompt += f"\nProperty Specifications:\n{spec_context}\n"

    system_prompt += (
        "\nAssess the following and respond with each field on its own line as 'field: value':\n"
        "1. spec_match_score: How well does the visible work match the specs? (0.0 to 1.0)\n"
        "2. facets_visible: How many distinct roof facets/sections are visible?\n"
        "3. ridge_cap_quality: Quality of ridge cap installation (good/fair/poor/not_visible)\n"
        "4. flashing_quality: Quality of visible flashing (good/fair/poor/not_visible)\n"
        "5. drip_edge_visible: Is drip edge properly installed? (yes/no/not_visible)\n"
        "6. shingle_alignment: Are shingles properly aligned? (good/fair/poor/not_visible)\n"
        "7. debris_present: Is construction debris visible? (yes/no)\n"
        "8. issues: List any specific issues (comma-separated)\n"
        "9. recommendation: approve / flag_for_review / reject\n"
        "10. confidence: Your confidence in this assessment (0.0 to 1.0)\n"
        "11. notes: Additional observations\n\n"
        "Be conservative — flag for review if uncertain rather than approving."
    )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Compare this progress photo against the specs."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            tier=ModelTier.VISION,
            max_tokens=800,
            tenant_id=tenant_id,
        )
    )

    from app.agents.tools.vision import _parse_vision_response

    analysis = _parse_vision_response(response.content)

    # Build structured annotations for ML training
    annotations = {
        "milestone": milestone_name,
        "facets_visible": analysis.get("facets_visible"),
        "ridge_cap_quality": analysis.get("ridge_cap_quality"),
        "flashing_quality": analysis.get("flashing_quality"),
        "drip_edge_visible": analysis.get("drip_edge_visible"),
        "shingle_alignment": analysis.get("shingle_alignment"),
        "debris_present": analysis.get("debris_present"),
    }

    analysis["annotations"] = annotations
    analysis["has_measurement_specs"] = bool(measurement)
    return analysis


@tool
async def generate_qc_summary(
    photo_analyses: list[dict],
    milestone_name: str,
    measurement: dict | None = None,
    tenant_id: str | None = None,
) -> dict:
    """Generate a customer-facing QC summary from multiple photo analyses.

    Aggregates individual photo analyses into a single milestone QC report
    suitable for sharing with the homeowner.

    Args:
        photo_analyses: List of results from compare_photo_to_spec.
        milestone_name: The milestone being reported on.
        measurement: Optional spec data for context.
        tenant_id: For cost tracking.

    Returns:
        Dict with summary, overall_grade, issues, customer_message.
    """
    if not photo_analyses:
        return {
            "summary": "No photos available for QC review.",
            "overall_grade": "incomplete",
            "issues": ["No progress photos submitted"],
            "customer_message": "",
        }

    # Aggregate scores
    scores = [
        a.get("spec_match_score", 0)
        for a in photo_analyses
        if isinstance(a.get("spec_match_score"), (int, float))
    ]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    all_issues = []
    for a in photo_analyses:
        issues = a.get("issues", "")
        if isinstance(issues, str) and issues and issues.lower() not in ("none", "n/a"):
            all_issues.extend(i.strip() for i in issues.split(",") if i.strip())
        elif isinstance(issues, list):
            all_issues.extend(issues)

    recommendations = [a.get("recommendation", "flag_for_review") for a in photo_analyses]

    # Determine overall grade
    if all(r == "approve" for r in recommendations) and avg_score >= 0.8:
        overall_grade = "pass"
    elif any(r == "reject" for r in recommendations):
        overall_grade = "fail"
    else:
        overall_grade = "review_needed"

    # Generate customer message
    analysis_summary = "\n".join(
        f"  Photo {i + 1}: score={a.get('spec_match_score', 'N/A')}, recommendation={a.get('recommendation', 'N/A')}"
        for i, a in enumerate(photo_analyses)
    )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write professional, friendly QC status updates for homeowners about their "
                        "roofing/siding project. Be concise (2-3 sentences). If there are issues, "
                        "mention them reassuringly. Never use overly technical jargon."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Milestone: {milestone_name}\n"
                        f"Overall grade: {overall_grade}\n"
                        f"Issues found: {', '.join(all_issues) if all_issues else 'None'}\n"
                        f"Photo analyses:\n{analysis_summary}"
                    ),
                },
            ],
            tier=ModelTier.FAST,
            max_tokens=200,
            tenant_id=tenant_id,
        )
    )

    return {
        "summary": response.content,
        "overall_grade": overall_grade,
        "avg_score": round(avg_score, 2),
        "issues": all_issues,
        "customer_message": response.content,
        "photo_count": len(photo_analyses),
        "recommendation_counts": {
            "approve": recommendations.count("approve"),
            "flag_for_review": recommendations.count("flag_for_review"),
            "reject": recommendations.count("reject"),
        },
    }
