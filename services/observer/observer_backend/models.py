"""Pydantic response models."""

from pydantic import BaseModel


class Scenario(BaseModel):
    name: str
    description: str


class LabStatus(BaseModel):
    scenarios: list[Scenario]
    routers: list[str]


class RouterMetadata(BaseModel):
    name: str
    asn: int
    role: str
    networks: list[str]
    peers: list[str]


class LinkMetadata(BaseModel):
    ipv4_subnet: str


class TopologyModel(BaseModel):
    lab_name: str
    description: str
    routers: list[RouterMetadata]
    links: dict[str, LinkMetadata]
