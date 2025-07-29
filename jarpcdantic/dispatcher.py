# -*- coding: utf-8 -*-
from typing import Callable, TypeVar

from .errors import JarpcMethodNotFound

_T = TypeVar("_T", bound=Callable)


class JarpcDispatcher:
    """Mapping for API methods. Effectively a dictionary wrapper."""

    def __init__(self, method_map: dict[str, Callable] = None):
        if not isinstance(method_map, (dict, type(None))):
            raise TypeError("method_map must be a dictionary or None")
        self.method_map: dict[str, Callable] = method_map or dict()

    def __getitem__(self, method_name: str) -> Callable:
        try:
            return self.method_map[method_name]
        except KeyError as e:
            raise JarpcMethodNotFound(
                method=method_name, declared_methods=list(self.method_map.keys())
            ) from e

    def rpc_method(self, method_function: _T) -> _T:
        """Decorator: adds `method_function` as RPC method."""
        self.method_map[method_function.__name__] = method_function
        return method_function

    def declare_method(self, method_name: str | None = None):
        """Decorator: adds `method_function` as RPC method."""

        def decorated(method_function: _T) -> _T:
            self.method_map[
                (method_name.__str__() if method_name else None)
                or method_function.__name__
            ] = method_function
            return method_function

        return decorated

    def add_rpc_method(self, method_function: Callable, method_name: str | None = None):
        """Adds `method_function` as RPC method.
        If `method_name` is not None, it is used as method name.
        """
        self.method_map[method_name or method_function.__name__] = method_function

    def update(self, dispatcher: "JarpcDispatcher", override: bool = False):
        """Merges another dispatcher into this one. Can override existing methods."""
        if not isinstance(dispatcher, JarpcDispatcher):
            raise TypeError("dispatcher must be an instance of JarpcDispatcher")
        for method_name, method in dispatcher.method_map.items():
            if override or method_name not in self.method_map:
                self.method_map[method_name] = method
