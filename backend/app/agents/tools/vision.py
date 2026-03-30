"""LLM Vision tools for photo triage and analysis.

Uses the LLMRouter's VISION tier to analyze customer/crew photos.
No custom CV models needed — LLM vision APIs are accurate enough
for Phase 2 and generate training data for future fine-tuning.
"""

from langchain_core.tools import tool

from app.integrations.llm.router import LLMRequest, ModelTier, llm_router


@tool
async def analyze_roof_photo(
    image_url: str,
    context: str = "",
    tenant_id: str | None = None,
) -> dict:
    """Analyze a roof/siding photo using LLM vision.

    Identifies: roof type, visible damage, approximate condition,
    whether the image is usable for estimation purposes.

    Args:
        image_url: URL of the photo (S3 or Twilio media URL).
        context: Additional context about what to look for.
        tenant_id: For cost tracking.

    Returns:
        Dict with analysis results: roof_visible, condition, damage_notes,
        estimated_squares, usable_for_estimate, confidence.
    """
    system_prompt = (
        "You are an expert roofing and siding inspector analyzing a property photo. "
        "Provide a structured assessment. Be conservative with estimates — "
        "it's better to flag uncertainty than give a false precise number.\n\n"
        "Analyze and return the following in your response:\n"
        "1. roof_visible: Is a roof clearly visible? (yes/no)\n"
        "2. siding_visible: Is siding clearly visible? (yes/no)\n"
        "3. roof_type: Identified roof type (asphalt shingle, metal, tile, flat, unknown)\n"
        "4. apparent_condition: good/fair/poor/damaged/unknown\n"
        "5. visible_damage: List any visible damage (missing shingles, sagging, staining, etc.)\n"
        "6. estimated_stories: Number of stories visible (1, 2, 3, unknown)\n"
        "7. estimated_complexity: simple/moderate/complex/very_complex/unknown\n"
        "8. usable_for_estimate: Can this photo support a preliminary estimate? (yes/no)\n"
        "9. confidence: Your confidence in this assessment (0.0 to 1.0)\n"
        "10. notes: Any additional observations\n\n"
        "Respond in a structured format with each field on its own line as 'field: value'."
    )

    if context:
        system_prompt += f"\n\nAdditional context: {context}"

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please analyze this property photo."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            tier=ModelTier.VISION,
            max_tokens=800,
            tenant_id=tenant_id,
        )
    )

    # Parse structured response into dict
    analysis = _parse_vision_response(response.content)
    analysis["model_used"] = response.model
    analysis["tokens_used"] = response.input_tokens + response.output_tokens
    return analysis


@tool
async def analyze_progress_photo(
    image_url: str,
    milestone_name: str,
    expected_work: str,
    tenant_id: str | None = None,
) -> dict:
    """Analyze a crew progress photo against expected milestone work.

    Used by QC flows to verify work completion before milestone sign-off.

    Args:
        image_url: URL of the progress photo.
        milestone_name: What milestone this photo is for (e.g., 'Tear-off complete').
        expected_work: Description of what should be visible if complete.
        tenant_id: For cost tracking.

    Returns:
        Dict with: milestone_appears_complete, issues_found, confidence, recommendation.
    """
    system_prompt = (
        "You are a roofing/siding QC inspector reviewing a progress photo.\n\n"
        f"Milestone: {milestone_name}\n"
        f"Expected work: {expected_work}\n\n"
        "Assess:\n"
        "1. milestone_appears_complete: Does the photo show the expected work is done? (yes/no/unclear)\n"
        "2. issues_found: List any visible quality issues (gaps, misalignment, debris, etc.)\n"
        "3. confidence: Your confidence in this assessment (0.0 to 1.0)\n"
        "4. recommendation: approve / flag_for_review / reject\n"
        "5. notes: Additional observations\n\n"
        "Be conservative — flag for review if uncertain rather than approving."
    )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please review this progress photo."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            tier=ModelTier.VISION,
            max_tokens=600,
            tenant_id=tenant_id,
        )
    )

    analysis = _parse_vision_response(response.content)
    analysis["milestone_name"] = milestone_name
    return analysis


def _parse_vision_response(content: str) -> dict:
    """Parse a structured 'field: value' response into a dict."""
    result: dict = {}
    for line in content.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            # Try to parse booleans and numbers
            if value.lower() in ("yes", "true"):
                result[key] = True
            elif value.lower() in ("no", "false"):
                result[key] = False
            else:
                try:
                    result[key] = float(value)
                except ValueError:
                    result[key] = value
    return result
