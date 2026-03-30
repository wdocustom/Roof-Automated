"""Tests for the LLM Vision tools."""

from app.agents.tools.vision import _parse_vision_response


class TestParseVisionResponse:
    def test_parses_structured_output(self):
        content = (
            "roof_visible: yes\n"
            "siding_visible: no\n"
            "roof_type: asphalt shingle\n"
            "apparent_condition: fair\n"
            "visible_damage: Missing shingles near ridge, some curling\n"
            "estimated_stories: 2\n"
            "estimated_complexity: moderate\n"
            "usable_for_estimate: yes\n"
            "confidence: 0.75\n"
            "notes: Appears to be a 15-20 year old architectural shingle roof"
        )

        result = _parse_vision_response(content)

        assert result["roof_visible"] is True
        assert result["siding_visible"] is False
        assert result["roof_type"] == "asphalt shingle"
        assert result["apparent_condition"] == "fair"
        assert result["estimated_stories"] == 2.0
        assert result["confidence"] == 0.75
        assert result["usable_for_estimate"] is True

    def test_handles_missing_fields(self):
        content = "roof_visible: yes\nconfidence: 0.5"
        result = _parse_vision_response(content)
        assert result["roof_visible"] is True
        assert result["confidence"] == 0.5
        assert "apparent_condition" not in result

    def test_handles_empty_input(self):
        result = _parse_vision_response("")
        assert result == {}
