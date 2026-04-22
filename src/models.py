from pydantic import BaseModel
from typing import List, Optional


class PropertyInput(BaseModel):
    property_id: str
    address: str
    city: str
    zip_code: str
    property_type: str          # "Wohnung" | "Haus" | "Gewerbe"
    size_sqm: float
    rooms: float
    purchase_price: Optional[float] = None
    monthly_rent: Optional[float] = None
    year_built: Optional[int] = None
    energy_class: Optional[str] = None
    features: List[str] = []
    notes: Optional[str] = None  # agent notes, not published


class JobResult(BaseModel):
    job_id: str
    timestamp: str
    status: str                  # "pending" | "approved" | "rejected"
    property_id: str
    expose_text: str
    hallucination_detected: bool
    hallucination_details: str   # empty string if none
    created_by: Optional[str] = None   # username of the generating agent
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
