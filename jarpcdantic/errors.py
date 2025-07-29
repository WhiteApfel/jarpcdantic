# -*- coding: utf-8 -*-
"""
JARPC exception classes.

Modelled after JSON-RPC 2.0 errors.

"""
from typing import Any, Type, TypeVar

from pydantic import BaseModel, Field

_T = TypeVar("_T", bound=Type["JarpcError"])


class JarpcErrorModel(BaseModel):
    """Pydantic model for JARPC errors."""

    code: int | None
    message: str | None
    error: dict[str, Any] | str | None = Field(
        default_factory=dict, description="Additional error data"
    )

    def __init__(self, code: int, message: str, data: dict[str, Any] | Any = None):
        """Format the message dynamically using data values."""
        data = data or {}
        if not isinstance(data, dict):
            data = data
            formatted_message = message
        else:
            formatted_message = message.format(**data) if message else None
        super().__init__(code=code, message=formatted_message, error=data)

    class Config:
        from_attributes = True


class JarpcError(Exception):
    """Base JARPC exception"""

    code: int = None
    message: str = None
    error: Any | None= None
    _data: JarpcErrorModel = None

    def __init__(self, data: Any = None, **kwargs: Any):
        if isinstance(data, Exception):
            self.error= f"{data.__class__.__name__}: {data}"
        elif not isinstance(data, dict):
            self.error = data
        else:
            combined_data = {**(data or {}), **kwargs}
            self.error = combined_data
        self._data = JarpcErrorModel(
            code=self.code,
            message=self.message,
            data=self.error,
        )

    def __str__(self) -> str:
        return f"{self.code} {self.message}"

    def as_dict(self) -> dict[str, Any]:
        """Convert the error to a Pydantic-serialized dictionary."""
        return self._data.model_dump()


class JarpcUnknownError(JarpcError):
    """Unknown error: unknown exception code"""

    def __init__(self, code, message, data):
        self.code = code
        self.message = message
        super().__init__(data=data)


class ExceptionManager:
    """Global manager for handling JARPC exceptions."""

    def __init__(self) -> None:
        self._exceptions: dict[int, Type[JarpcError]] = {}

    def add(self, exception_class: _T) -> _T:
        """
        Registers a custom exception.

        Can be used as a decorator:
        @exception_manager.add
        class MyError(JarpcError):
            code = 1000
            message = "Custom error"
        """
        if not issubclass(exception_class, JarpcError):
            raise TypeError(
                f"{exception_class.__name__} must be a subclass of JarpcError"
            )
        if not hasattr(exception_class, "code") or not isinstance(
            exception_class.code, int
        ):
            raise ValueError(
                f"{exception_class.__name__} must define an integer 'code' attribute"
            )

        self._exceptions[exception_class.code] = exception_class
        return exception_class  # Allows usage as a decorator

    def get(self, code: int) -> Type[JarpcError] | None:
        """Retrieves an exception class by its error code."""
        return self._exceptions.get(code)

    def raise_exception(
        self, code: int, data: str | None = None, message: str | None = None
    ) -> None:
        """
        Creates and raises an exception based on the provided code.
        If the code is unrecognized, raises `JarpcUnknownError`.
        """
        exception_class = self.get(code) or JarpcUnknownError
        raise exception_class(
            code=code, message=message or exception_class.message, data=data
        )

    def list_registered_exceptions(self) -> list[int]:
        """Returns a list of registered exception codes."""
        return list(self._exceptions.keys())


# Global instance
jarpcdantic_exceptions = ExceptionManager()


@jarpcdantic_exceptions.add
class JarpcParseError(JarpcError):
    """Parse Error: invalid JSON format."""

    code = -32700
    message = "Parse error"


@jarpcdantic_exceptions.add
class JarpcInvalidRequest(JarpcError):
    """Invalid Request: the JSON object is not a JARPC 1.0 request."""

    code = -32600
    message = "Invalid Request"


@jarpcdantic_exceptions.add
class JarpcMethodNotFound(JarpcError):
    """Method not found: method with requested name does not exist."""

    code = -32601
    
    message = "Method not found"
    
    def __init__(self, method: str, declared_methods: list[str]):
        super().__init__(data={"method": method, "declared_methods": declared_methods})


@jarpcdantic_exceptions.add
class JarpcInvalidParams(JarpcError):
    """Invalid params: invalid method call."""

    code = -32602
    message = "Invalid params"


@jarpcdantic_exceptions.add
class JarpcInternalError(JarpcError):
    """Internal error: internal JARPC error."""

    code = -32603
    message = "Internal error"


@jarpcdantic_exceptions.add
class JarpcTimeout(JarpcError):
    """Timeout: request could not be completed in time."""

    code = -32604
    message = "Timeout"


@jarpcdantic_exceptions.add
class JarpcServerError(JarpcError):
    """Server error: server could not complete the request."""

    code = -32000
    message = "Server error"


# Should be thrown in dispatch methods.

# 1xxx - Access errors


@jarpcdantic_exceptions.add
class JarpcUnauthorized(JarpcError):
    """Unauthorized: Similar to JarpcForbidden, but specifically for use when authentication is required and
    has failed or has not yet been provided."""

    code = 1000
    message = "Unauthorized"


@jarpcdantic_exceptions.add
class JarpcForbidden(JarpcError):
    """Forbidden: The request was valid, but the server is refusing action.
    The user might not have the necessary permissions for a resource, or may need an account of some sort.
    """

    code = 1001
    message = "Forbidden"


# 2xxx - invalid arguments


@jarpcdantic_exceptions.add
class JarpcValidationError(JarpcError):
    """ValidationError: error validating input parameters"""

    code = 2000
    message = "Validation error"


# 3xxx - integration errors


@jarpcdantic_exceptions.add
class JarpcExternalServiceUnavailable(JarpcError):
    """ExternalServiceUnavailable: ошибка запроса удаленной системы"""

    code = 3000
    message = "External service unavailable"
