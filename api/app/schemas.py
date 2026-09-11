from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class DestinationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    platform: str = Field(default="custom", max_length=50)
    rtmp_url: str = Field(min_length=6)
    stream_key: str = Field(min_length=1)


class PlaylistCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    media_ids: list[str] = Field(min_length=1)


class StreamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    destination_id: str
    media_id: str | None = None
    playlist_id: str | None = None
    loop: bool = True
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def validate_source(self):
        if bool(self.media_id) == bool(self.playlist_id):
            raise ValueError("Choose exactly one source: media_id or playlist_id")
        return self
