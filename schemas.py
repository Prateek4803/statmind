from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

class CapabilityRequest(BaseModel):
    data: List[float] = Field(..., min_length=2, description="Raw measurement data. Must have at least 2 points.")
    usl: Optional[float] = Field(None, description="Upper Specification Limit")
    lsl: Optional[float] = Field(None, description="Lower Specification Limit")
    target: Optional[float] = Field(None, description="Nominal Target")
    subgroup_size: int = Field(1, ge=1, description="Size of subgroups. Must be >= 1")

    @model_validator(mode='after')
    def check_spec_limits(self):
        if self.usl is None and self.lsl is None:
            raise ValueError("At least one specification limit (USL or LSL) must be provided.")
        if self.usl is not None and self.lsl is not None and self.usl <= self.lsl:
            raise ValueError("USL must be strictly greater than LSL.")
        return self

class SPCRequest(BaseModel):
    data: List[float] = Field(..., min_length=2)
    chart_type: str = Field(..., pattern="^(Xbar-R|Xbar-S|I-MR)$")
    subgroup_size: int = Field(1, ge=1)

class MESStreamPayload(BaseModel):
    machine_id: str = Field(..., min_length=1)
    parameter: str = Field(..., min_length=1)
    value: float
    timestamp: Optional[str] = None