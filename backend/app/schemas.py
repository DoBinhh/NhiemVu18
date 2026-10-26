"""Pydantic models khớp 1-1 với object state.config bên frontend."""
from typing import Literal
from pydantic import BaseModel, Field


class DateRange(BaseModel):
    """Frontend gửi {from, to}, khớp alias vì 'from' là keyword của Python."""
    from_date: str = Field(alias="from")
    to: str

    class Config:
        populate_by_name = True


class CollectOptions(BaseModel):
    includeReplies: bool = True
    removeDuplicates: bool = True
    skipLinks: bool = True


class CollectRequest(BaseModel):
    group: str = "1"
    platform: str
    source: str
    dateRange: DateRange
    abbreviations: list[str] = Field(default_factory=list)
    matchMode: Literal["word", "part"] = "word"
    limit: int = 300
    sort: Literal["newest", "oldest", "likes"] = "newest"
    options: CollectOptions = Field(default_factory=CollectOptions)