from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Any


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProject(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class SelectProject(StrictModel):
    id: str


class CreateEntity(StrictModel):
    kind: Literal["asset", "sequence", "scene", "shot"]
    title: str
    parent_id: str | None = None
    description: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class UpdateEntity(StrictModel):
    revision: int = Field(ge=1, strict=True)
    changes: dict[str, Any]


class Revision(StrictModel):
    revision: int = Field(ge=1, strict=True)
