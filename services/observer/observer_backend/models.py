"""Pydantic response models."""

from pydantic import BaseModel


class Scenario(BaseModel):
    name: str
    description: str


class LabStatus(BaseModel):
    scenarios: list[Scenario]
    routers: list[str]
