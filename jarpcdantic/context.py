from contextvars import ContextVar
from typing import Any

meta_context_var: ContextVar[dict[str, Any]] = ContextVar("meta", default={})
