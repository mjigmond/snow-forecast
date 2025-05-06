from typing import Literal, Self
from pydantic import BaseModel, Field, model_validator

from constants import *


class EmailSMTP(BaseModel):
    server: str = "smtp.gmail.com"
    user: str
    password: str


class Recipient(BaseModel):
    number: int = Field(gt=999999999, le=9999999999, description="Recipient's phone number")
    network: Literal["verizon", "at&t", "t-mobile"]


class ForecastFxx(BaseModel):
    fxx: int
    hours: int


class ModelStats(BaseModel):
    model: str
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    nan_reason: str | None = None


class ForecastResponse(BaseModel):
    name: str
    attime: str
    forecast: list[ModelStats]


class ForecastRequest(BaseModel):
    name: str
    attime: str
    models: list[str]
    lat: float | None = None
    lon: float | None = None
    geometry: str | None = None
    recipients: list[Recipient] | None = None

    @model_validator(mode="after")
    def check_input(self) -> Self:
        if self.lat and self.lon and self.geometry:
            raise ValueError("Either lat/lon or geometry must be provided, not both.")
        if (self.lat and not self.lon) or (self.lon and not self.lat):
            raise ValueError("Both lat and lon must be provided.")
        if not self.geometry and not self.lat and not self.lon:
            raise ValueError("One of lat/lon or geometry must be provided.")
        if set(self.models).intersection(set(VALID_MODELS)) != set(self.models):
            raise ValueError(f"Models must be from {VALID_MODELS}.")
        return self


