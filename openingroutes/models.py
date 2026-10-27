from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain import safe_url


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    event: str = Field(min_length=1, max_length=160)
    match: str = Field(min_length=1, max_length=160)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    url: str = Field(max_length=1000)
    verified: bool = False
    reviewer: str = Field(default="", max_length=100)

    @field_validator("url")
    @classmethod
    def check_url(cls, value):
        if not value.startswith("https://") or not safe_url(value):
            raise ValueError("A valid HTTPS match source is required")
        return value


class Teaching(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="", max_length=200)
    area: str = Field(default="", max_length=100)
    purpose: str = Field(default="", max_length=2000)
    prerequisites: str = Field(default="", max_length=2000)
    stance: str = Field(default="", max_length=2000)
    aim: str = Field(default="", max_length=2000)
    operation: str = Field(default="", max_length=2000)
    timing: str = Field(default="", max_length=2000)
    effect: str = Field(default="", max_length=2000)
    coordination: str = Field(default="", max_length=2000)
    failures: str = Field(default="", max_length=2000)
    counterplay: str = Field(default="", max_length=2000)
    stance_image: str = Field(default="", max_length=1000)
    aim_image: str = Field(default="", max_length=1000)
    pro_video: str = Field(default="", max_length=1000)
    recreation_video: str = Field(default="", max_length=1000)
    reproduction: Literal["pending", "failed", "verified"] = "pending"
    verified_by: str = Field(default="", max_length=100)
    verified_on: str = Field(default="", max_length=30)
    map_version: str = Field(default="", max_length=100)
    video_offset: float = Field(default=0, ge=0, le=86400)
    status: Literal["draft", "review", "published", "withdrawn"] = "draft"

    @field_validator("stance_image", "aim_image", "pro_video", "recreation_video")
    @classmethod
    def check_media(cls, value):
        if value and not safe_url(value):
            raise ValueError("Use an HTTPS URL or an imported media asset")
        return value
