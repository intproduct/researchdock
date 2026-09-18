"""Research metadata only; source code and working files remain on devices."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField
from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models import get_datetime_utc

Stage = Literal["exploring", "active", "writing", "paused", "archived"]
Comparison = Literal["synced", "ahead", "behind", "diverged", "unknown", "unrelated"]


class Project(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=2000)
    stage: str = Field(default="exploring", max_length=20)
    status_note: str = Field(default="", max_length=10000)
    next_step: str = Field(default="", max_length=2000)
    revision: int = 1
    created_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    stage: Stage = "exploring"
    next_step: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()


class ProjectUpdate(ProjectCreate):
    status_note: str = Field(default="", max_length=10000)
    revision: int = Field(ge=1)


class Device(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(max_length=120)
    platform: str = Field(max_length=80)
    token_hash: str = Field(unique=True, max_length=64)
    revoked: bool = False
    last_seen: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=80)


class DevicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    platform: str
    revoked: bool
    last_seen: datetime | None
    created_at: datetime


class WorkingCopy(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("device_id", "local_path", name="uq_device_path"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(
        foreign_key="project.id", ondelete="CASCADE", index=True
    )
    device_id: uuid.UUID = Field(
        foreign_key="device.id", ondelete="CASCADE", index=True
    )
    local_path: str = Field(max_length=2048)
    sequence: int = 0
    branch: str | None = Field(default=None, max_length=512)
    head: str | None = Field(default=None, max_length=64)
    upstream: str | None = Field(default=None, max_length=512)
    remote_url: str | None = Field(default=None, max_length=2048)
    dirty: bool = False
    changed_files: int = 0
    untracked_files: int = 0
    ahead: int | None = None
    behind: int | None = None
    comparison: str = Field(default="unknown", max_length=20)
    reason: str = Field(default="尚未扫描", max_length=500)
    observed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    received_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class CopyCreate(BaseModel):
    project_id: uuid.UUID
    local_path: str = Field(min_length=1, max_length=2048)


class Observation(BaseModel):
    sequence: int = Field(ge=1)
    observed_at: datetime
    branch: str | None = Field(default=None, max_length=512)
    head: str | None = PydanticField(
        default=None, pattern=r"^(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$"
    )
    upstream: str | None = Field(default=None, max_length=512)
    remote_url: str | None = Field(default=None, max_length=2048)
    dirty: bool = False
    changed_files: int = Field(default=0, ge=0)
    untracked_files: int = Field(default=0, ge=0)
    ahead: int | None = Field(default=None, ge=0)
    behind: int | None = Field(default=None, ge=0)
    comparison: Comparison = "unknown"
    reason: str = Field(default="", max_length=500)

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must include timezone")
        return value
