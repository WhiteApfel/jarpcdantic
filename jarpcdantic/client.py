# -*- coding: utf-8 -*-
import time
import uuid
from typing import Any, Awaitable, Callable, Type, Iterable, Optional

ClientMiddlewareFunc = Callable[
    ["JarpcRequest", Callable[["JarpcRequest"], Awaitable[Any]]],
    Awaitable[Any]
]

from pydantic import ValidationError

from .context import meta_context_var
from .errors import (
    ExceptionManager,
    JarpcError,
    JarpcInvalidRequest,
    JarpcServerError,
    jarpcdantic_exceptions,
)
from .format import JarpcRequest, JarpcResponse, RequestT, ResponseT


class JarpcClient:
    """
    Asynchronous JARPC Client implementation.

    To make RPC it requires async transport.
    Transport gets JARPC request as string, JarpcRequest-object and kwargs given with client call.
    If rsvp is True, transport must return JARPC response string, otherwise transport may not return any result.
    Transport's exceptions will be overwritten with `JarpcServerError` unless they are `JarpcError` subclasses.

    Example of usage with python "aiohttp" library:
    ```
    async def aiohttp_transport(request_string, request, timeout=60.0):
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(url='https://kitchen.org/jsonrpc', data=request_string, timeout=timeout)
                return await response.text()
        except TimeoutError:
            raise JarpcTimeout

    kitchen = JarpcClient(transport=aiohttp_transport)
    salad = await kitchen(method='cook_salad', params=dict(name='Caesar'), request_id='1', timeout=15)
    ```

    You can also define transport as class:
    ```
    class AiohttpTransport:
        def __init__(self, session, url, headers=None):
            self.session = session
            self.url = url
            self.headers = headers or {}
        async def __call__(self, request_string, request, timeout=60.0):
            try:
                response = await session.post(url=self.url, headers=self.headers, data=request_string, timeout=timeout)
                return await response.text()
            except TimeoutError:
                raise JarpcTimeout

    async with aiohttp.ClientSession() as session:
        transport = AiohttpTransport(session=session, url='https://kitchen.org/jsonrpc',
                                     headers={'Content-Type': 'application/json'})
        kitchen = JarpcClient(transport=transport)
        salad = await kitchen(method='cook_salad', params=dict(name='Caesar'), request_id='1', timeout=15)
    ```

    If you don't need to pass JARPC meta params and transport kwargs, you can use method-like calling syntax:
    ```
    salad = await kitchen.cook_salad(name='Caesar')
    ```
    """

    def __init__(
        self,
        transport: Callable[[str, "JarpcRequest", Any | None], Awaitable[str | None]],
        default_ttl: float | None = None,
        default_rpc_ttl: float | None = None,
        default_notification_ttl: float | None = None,
        exception_manager: ExceptionManager | None = None,
        middlewares: Iterable[ClientMiddlewareFunc] = None,
    ):
        self._transport = transport
        self._default_rpc_ttl = default_rpc_ttl or default_ttl
        self._default_notification_ttl = default_notification_ttl or default_ttl
        self.exception_manager = exception_manager or jarpcdantic_exceptions
        self.middlewares: list[ClientMiddlewareFunc] = list(middlewares) if middlewares else []
        self._middleware_stack = self._build_middleware_stack()

    def middleware(self, func: ClientMiddlewareFunc) -> ClientMiddlewareFunc:
        """Decorator to add a middleware function."""
        self.middlewares.append(func)
        self._middleware_stack = self._build_middleware_stack()
        return func

    def _build_middleware_stack(self) -> Callable[["JarpcRequest", Callable], Awaitable[Any]]:
        async def base_call(req: JarpcRequest, endpoint_handler: Callable) -> Any:
            return await endpoint_handler(req)
            
        stack = base_call
        for mw in reversed(self.middlewares):
            def wrap(m: ClientMiddlewareFunc, n: Callable):
                async def wrapped(req: JarpcRequest, handler: Callable) -> Any:
                    async def call_next(r: JarpcRequest) -> Any:
                        return await n(r, handler)
                    return await m(req, call_next)
                return wrapped
            stack = wrap(mw, stack)
            
        return stack

    async def __call__(
        self,
        method_name: str,
        params: Any,
        ts: float | None = None,
        ttl: float | None = None,
        request_id: str | None = None,
        rsvp: bool = True,
        durable: bool = False,
        meta: dict[str, Any] = None,
        generic_request_type: type = Any,
        generic_response_type: type = Any,
        **transport_kwargs
    ):
        combined_meta = (meta_context_var.get({}) or {}) | (meta or {})
        request: JarpcRequest = self._prepare_request(
            method_name, params, ts, ttl, request_id, rsvp, durable, combined_meta
        )
        
        async def _endpoint_handler(req: JarpcRequest) -> JarpcResponse | None:
            request_string = req.model_dump_json(exclude_unset=True)
            try:
                response_string = await self._transport(
                    request_string, req, **transport_kwargs
                )
            except JarpcError:
                raise
            except Exception as e:
                raise JarpcServerError(e)
            return self._parse_response(response_string, req.rsvp, generic_response_type)

        return await self._middleware_stack(request, _endpoint_handler)

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        async def method_wrapper(*args, **kwargs) -> Any:
            service_keys = {"ts", "ttl", "request_id", "rsvp", "durable", "meta"}
            service_kwargs = {k: kwargs.pop(k) for k in list(kwargs.keys()) if k in service_keys}
            return await self(method_name=name, params=kwargs, **service_kwargs)

        return method_wrapper

    def simple_call(self, method_name: str, **params) -> Any:
        """Alias for `self.__call__`."""
        return self(method_name=method_name, params=params)

    def _prepare_request(
        self,
        method_name: str,
        params: RequestT,
        ts: float | None = None,
        ttl: float | None = None,
        request_id: str | None = None,
        rsvp: bool = True,
        durable: bool = False,
        meta: dict[str, Any] = None,
        generic_request_type: Type[RequestT] = Any,
    ) -> JarpcRequest[RequestT]:
        """Creates a JARPC request object."""
        if durable:
            ttl = None
        else:
            # If request is not durable, use default ttl
            # If default ttl is not set, use default_rpc_ttl for rsvp=True
            # and default_notification_ttl for rsvp=False
            default_ttl = (
                self._default_rpc_ttl if rsvp else self._default_notification_ttl
            )
            ttl = default_ttl if ttl is None else ttl

        context_meta = meta_context_var.get({})
        combined_meta = context_meta | (meta or {})

        try:
            request = JarpcRequest[generic_request_type](
                method=method_name,
                params=params,
                ts=time.time() if ts is None else ts,
                ttl=ttl,
                id=str(uuid.uuid4()) if request_id is None else request_id,
                rsvp=rsvp,
                meta=combined_meta,
            )
        except ValidationError as e:
            raise JarpcInvalidRequest(e) from e

        return request

    def _parse_response(
        self,
        response_string: str,
        rsvp: bool,
        generic_response_type: Type[ResponseT] = Any,
    ) -> ResponseT | None:
        """Parse response and either return result or raise JARPC error."""
        if rsvp:
            try:
                response = JarpcResponse[generic_response_type].model_validate_json(
                    response_string
                )
            except ValidationError as e:
                raise JarpcServerError(e) from e
            if response.success:
                return response.result
            else:
                error = response.error
                self.exception_manager.raise_exception(
                    code=error.get("code"),
                    data=error.get("error") or error.get("data"),
                    message=error.get("message"),
                )
        return None
