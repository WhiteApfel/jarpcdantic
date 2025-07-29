# -*- coding: utf-8 -*-
import time
import uuid
from typing import Any, Awaitable, Callable, Type

from pydantic import ValidationError

from .context import meta_context_var
from .errors import (
    JarpcError,
    JarpcInvalidRequest,
    JarpcServerError,
    jarpcdantic_exceptions,
)
from .format import JarpcRequest, JarpcResponse, RequestT, ResponseT


class JarpcClient:
    """
    JARPC Client implementation.

    To make RPC it requires transport.
    Transport gets JARPC request as string, JarpcRequest-object and kwargs given with client call.
    If rsvp is True, transport must return JARPC response string, otherwise transport may not return any result.
    Transport's exceptions will be overwritten with `JarpcServerError` unless they are `JarpcError` subclasses.

    Example of usage with python "requests" library:
    ```
    def requests_transport(request_string, request, timeout=60.0):
        try:
            return requests.post(url='https://kitchen.org/jsonrpc', data=request_string, timeout=timeout)
        except Timeout:
            raise JarpcTimeout

    kitchen = JarpcClient(transport=requests_transport)
    salad = kitchen(method='cook_salad', params=dict(name='Caesar'), request_id='1', timeout=15)
    ```

    You can also define transport as class:
    ```
    class RequestsTransport:
        def __init__(self, url, headers=None):
            self.url = url
            self.headers = headers or {}
        def __call__(self, request_string, request, timeout=60.0):
            try:
                return requests.post(url=self.url, headers=self.headers, data=request_string, timeout=timeout)
            except Timeout:
                raise JarpcTimeout

    transport = RequestsTransport(url='https://kitchen.org/jsonrpc', headers={'Content-Type': 'application/json'})
    kitchen = JarpcClient(transport)
    salad = kitchen(method='cook_salad', params=dict(name='Caesar'), request_id='1', timeout=15)
    ```

    If you don't need to pass JARPC meta params and transport kwargs, you can use method-like calling syntax:
    ```
    salad = kitchen.cook_salad(name='Caesar')
    ```
    """

    def __init__(
        self,
        # transport: Callable[[str, JarpcRequest, **kwargs], Union[str, None]]
        transport: Callable[
            [str, JarpcRequest, Any | None], Awaitable[str | None] | str | None
        ],
        default_ttl: float | None = None,
        default_rpc_ttl: float | None = None,
        default_notification_ttl: float | None = None,
    ):
        """
        :param transport: callable to send request
        :param default_ttl: float time interval while calling still actual
        :param default_rpc_ttl: default_ttl for rsvp=True calls (if None default_ttl will be used)
        :param default_notification_ttl: default_ttl for rsvp=False calls (if None default_ttl will be used)
        """
        self._transport = transport
        self._default_rpc_ttl = default_rpc_ttl or default_ttl
        self._default_notification_ttl = default_notification_ttl or default_ttl

    def __getattr__(self, method_name: str) -> Callable[..., Any]:
        """Allows calling `client.some_method(**params)` instead of `client("some_method", ...)`."""

        def wrapped(**params):
            return self.simple_call(method_name=method_name, params=params)

        return wrapped

    def simple_call(self, method_name: str, **params) -> Any:
        """Alias for `self.__call__`."""
        return self(method_name=method_name, params=params)

    def __call__(
        self,
        method_name: str,
        params: RequestT,
        ts: float | None = None,
        ttl: float | None = None,
        request_id: str | None = None,
        rsvp: bool = True,
        durable: bool = False,
        **transport_kwargs
    ) -> JarpcResponse:
        """Makes a synchronous JARPC request."""
        request = self._prepare_request(
            method_name, params, ts, ttl, request_id, rsvp, durable
        )
        request_string = request.model_dump_json()

        try:
            response_string = self._transport(
                request_string, request, **transport_kwargs
            )

        # Allow only JarpcError and its subclasses to be raised
        except JarpcError:
            raise
        except Exception as e:
            # Unexpected exception
            raise JarpcServerError(e)

        return self._parse_response(response_string, rsvp)

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
                jarpcdantic_exceptions.raise_exception(
                    code=error.get("code"),
                    data=error.get("data"),
                    message=error.get("message"),
                )
        return None


class AsyncJarpcClient(JarpcClient):
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

    kitchen = AsyncJarpcClient(transport=aiohttp_transport)
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
        kitchen = AsyncJarpcClient(transport=transport)
        salad = await kitchen(method='cook_salad', params=dict(name='Caesar'), request_id='1', timeout=15)
    ```

    If you don't need to pass JARPC meta params and transport kwargs, you can use method-like calling syntax:
    ```
    salad = await kitchen.cook_salad(name='Caesar')
    ```
    """

    async def __call__(
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
        generic_response_type: Type[ResponseT] = Any,
        **transport_kwargs
    ) -> ResponseT:
        combined_meta = (meta_context_var.get({}) or {}) | (meta or {})

        request: JarpcRequest[generic_request_type] = self._prepare_request(
            method_name, params, ts, ttl, request_id, rsvp, durable, combined_meta
        )
        request_string = request.model_dump_json(exclude_unset=True)

        try:
            response_string = await self._transport(
                request_string, request, **transport_kwargs
            )
        except JarpcError:
            raise
        except Exception as e:
            raise JarpcServerError(e)

        return self._parse_response(response_string, rsvp, generic_response_type)
