"""EagleView API client stub — interface defined, implementation pending commercial contract.

This module defines the interface that the platform uses for property measurements.
In Phase 1, this returns mock/manual data. Once the EagleView commercial contract
is in place, swap the implementation to hit the real API.
"""

from dataclasses import dataclass


@dataclass
class PropertyMeasurement:
    """Standardized property measurement data."""

    address: str
    total_roof_sqft: float | None = None
    total_roof_squares: float | None = None  # 1 square = 100 sqft
    roof_pitch: str | None = None
    roof_facets: int | None = None
    siding_sqft: float | None = None
    perimeter_linear_ft: float | None = None
    stories: int | None = None
    source: str = "manual"  # "manual", "eagleview", "hover"
    report_id: str | None = None
    raw_data: dict | None = None


class PropertyMeasurementProvider:
    """Abstract interface for property measurement providers."""

    async def get_measurements(self, address: str) -> PropertyMeasurement:
        """Fetch measurements for a property address.

        Override this for EagleView, Hover, or other providers.
        """
        # Phase 1: Return empty measurement for manual entry
        return PropertyMeasurement(address=address, source="manual")


class EagleViewProvider(PropertyMeasurementProvider):
    """EagleView API integration (stub — requires commercial contract)."""

    def __init__(self, api_key: str = "", api_url: str = ""):
        self.api_key = api_key
        self.api_url = api_url

    async def get_measurements(self, address: str) -> PropertyMeasurement:
        # TODO: Implement once EagleView contract is active
        # Will call EagleView API, parse response, return standardized data
        raise NotImplementedError("EagleView integration pending commercial contract")


# Default provider — manual entry for Phase 1
measurement_provider = PropertyMeasurementProvider()
