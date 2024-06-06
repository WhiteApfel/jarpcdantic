# -*- coding: utf-8 -*-
import json
import time
import uuid
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

from .errors import JarpcInvalidRequest, JarpcParseError, JarpcServerError

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


def json_dumps(data):
    """Default JSON serialiser."""
    return json.dumps(data, ensure_ascii=False)


def json_loads(data):
    """Default JSON deserialiser."""
    return json.loads(data)


class JarpcRequest(BaseModel, Generic[RequestT]):
    version: str = "1.0"
    method: str
    params: RequestT
    ts: float = Field(default_factory=time.time)
    ttl: float | None = None
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rsvp: bool = True

    def __repr__(self):
        return (
            f"<JarpcRequest version {self.version}, method {self.method}, params"
            f" {self.params}, ts {self.ts}, ttl {self.ttl}, id {self.id}, rsvp"
            f" {self.rsvp}>"
        )

    @property
    def expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() > self.ts + self.ttl

    #         except (TypeError, json.JSONDecodeError) as e:
    #             raise JarpcParseError(e) from e


class JarpcResponse(BaseModel, Generic[ResponseT]):
    result: ResponseT | None = None
    error: Any | None = None
    request_id: str | None = None
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def __repr__(self):
        return (
            f"<JarpcResponse id {self.id} result {self.result}, error {self.error},"
            f" request_id {self.request_id}>"
        )

    @property
    def success(self) -> bool:
        return self.error is None
