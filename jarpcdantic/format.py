# -*- coding: utf-8 -*-
import time
import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


class JarpcRequest(BaseModel, Generic[RequestT]):
    """JARPC request model."""

    version: str = "1.0"
    method: str
    params: RequestT
    ts: float = Field(default_factory=time.time)
    ttl: float | None = None
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rsvp: bool = True
    meta: dict[str, Any] | None = None

    def __repr__(self):
        return (
            f"<JarpcRequest version {self.version}, method {self.method}, params"
            f" {self.params}, ts {self.ts}, ttl {self.ttl}, id {self.id}, rsvp"
            f" {self.rsvp}, meta {self.meta}>"
        )

    @property
    def expired(self) -> bool:
        """Returns True if the request has expired based on TTL."""
        if self.ttl is None:
            return False
        return time.time() > self.ts + self.ttl


class JarpcResponse(BaseModel, Generic[ResponseT]):
    """JARPC response model."""

    result: ResponseT | None = None
    error: Any | None = None
    request_id: str | None = None
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    meta: dict[str, Any] | None = None

    def __repr__(self):
        return (
            f"<JarpcResponse id {self.id} result {self.result}, error {self.error},"
            f" request_id {self.request_id}, meta {self.meta}>"
        )

    @property
    def success(self) -> bool:
        """Returns True if there was no error in the response."""
        return self.error is None
