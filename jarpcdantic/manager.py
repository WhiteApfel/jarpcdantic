# -*- coding: utf-8 -*-
import asyncio
import inspect
import logging
from collections import deque
from typing import Any, Iterable, Optional, Callable, Awaitable, AsyncContextManager, Sequence

MiddlewareFunc = Callable[
    ["JarpcRequest", Callable[["JarpcRequest"], Awaitable[Optional["JarpcResponse"]]]],
    Awaitable[Optional["JarpcResponse"]]
]

from pydantic_core import ValidationError

from .context import meta_context_var
from .dispatcher import JarpcDispatcher
from .errors import JarpcError, JarpcInvalidParams, JarpcParseError, JarpcServerError
from .format import JarpcRequest, JarpcResponse
from .utils import convert_params_to_models, process_return_value

logger = logging.getLogger(__name__)


def get_args_representation(args: Iterable) -> str:
    """
    ['c', 'a', 'b'] -> "a, b, c"
    {'b',"a"} -> "a, b"
    """
    return ", ".join(sorted(args))


def prepare_context_params(method, request, context):
    """
    Подготавливает параметры контекста для вызова метода.
    """
    context_params = {}
    method_sig = inspect.signature(method)
    if "jarpc_request" in method_sig.parameters:
        context_params["jarpc_request"] = request
    if "_meta" in method_sig.parameters:
        context_params["_meta"] = request.meta or {}
    for param, value in context.items():
        if param in method_sig.parameters:
            context_params[param] = value
    return context_params, method_sig


def check_function_call(fun, kwargs: dict, context: dict) -> (bool, Optional[str]):
    """
    Check that `kwargs` match signature of `fun` given `context`.
    Positional arguments in call are not supported.

    Minimal valid argument set: positional args with no default + kw-only args with no default,
                                except for what is provided by context.
    Maximum valid argument set: all positional + all kw-only args IF no **varkw present,
                                except for what is provided by context.
    If **varkw is present, there is no upper limit.
    *varargs has no effect because there are no positional args in call.
    If fun is a method, args[0] is self. If fun is a callable object, we have to look at its __call__

    :returns (is_ok, explanation)
    """
    argspec = inspect.getfullargspec(fun)
    args_deque = deque(argspec.args)
    if inspect.ismethod(fun) or inspect.ismethod(fun.__call__):
        # skip self
        args_deque.popleft()
    allowed_args = set(args_deque)
    if argspec.defaults:
        # skip defaults
        for _ in argspec.defaults:
            args_deque.pop()
    required_args = set(args_deque)

    required = (
        (required_args | set(argspec.kwonlyargs))
        - (argspec.kwonlydefaults or {}).keys()
        - context.keys()
        - {"jarpc_request", "_meta"}
    )
    if required - kwargs.keys():
        return (
            False,
            f"Missing arguments: {get_args_representation(required - kwargs.keys())}",
        )

    if argspec.varkw is None:
        allowed = (
            (allowed_args | set(argspec.kwonlyargs))
            - context.keys()
            - {"jarpc_request", "_meta"}
        )
        if kwargs.keys() - allowed:
            return (
                False,
                (
                    "Unexpected arguments:"
                    f" {get_args_representation(kwargs.keys() - allowed)}"
                ),
            )
    else:
        # if **varkw is present, anything is considered allowed except for args from context
        restricted_intersection = kwargs.keys() & (context.keys() | {"jarpc_request", "_meta"})
        if restricted_intersection:
            return (
                False,
                (
                    "Unavailable arguments:"
                    f" {get_args_representation(restricted_intersection)}"
                ),
            )
    return True, None


class JarpcManager:
    def __init__(
        self,
        dispatcher: JarpcDispatcher,
        context: dict[str, Any] = None,
        run_sync_in_thread: bool = True,
        middlewares: Iterable[MiddlewareFunc] = None,
        limiters: Sequence[AsyncContextManager] = None,
    ):
        self.dispatcher: JarpcDispatcher = dispatcher
        self.context: dict[str, Any] = (
            context or dict()
        )  # per-manager context cannot contain jarpc_request
        self.run_sync_in_thread: bool = run_sync_in_thread
        self._background_tasks: set[asyncio.Task] = set()
        self.middlewares: list[MiddlewareFunc] = list(middlewares) if middlewares else []
        self.limiters: Sequence[AsyncContextManager] = limiters or []
        self._middleware_stack = self._build_middleware_stack()

    def middleware(self, func: MiddlewareFunc) -> MiddlewareFunc:
        """Decorator to add a middleware function."""
        self.middlewares.append(func)
        self._middleware_stack = self._build_middleware_stack()
        return func

    def _build_middleware_stack(self) -> Callable[["JarpcRequest"], Awaitable[Optional["JarpcResponse"]]]:
        next_call = self._endpoint_handler
        for middleware in reversed(self.middlewares):
            next_call = self._wrap_middleware(middleware, next_call)
        return next_call

    def _wrap_middleware(
        self, 
        middleware: MiddlewareFunc, 
        next_call: Callable[["JarpcRequest"], Awaitable[Optional["JarpcResponse"]]]
    ) -> Callable[["JarpcRequest"], Awaitable[Optional["JarpcResponse"]]]:
        async def wrapped(request: JarpcRequest) -> Optional[JarpcResponse]:
            return await middleware(request, next_call)
        return wrapped

    async def handle(self, request: str) -> str | None:
        response: JarpcResponse = await self.get_response(request)
        return response.model_dump_json() if response else None

    async def get_response(self, request_string: str) -> JarpcResponse | None:
        request_id: str | None = None
        context_token = None
        rsvp = True

        try:
            request = self._parse_request_or_raise(request_string)
            request_id = request.id
            rsvp = request.rsvp
            context_token = meta_context_var.set(request.meta)

            return await self._middleware_stack(request)

        except asyncio.CancelledError:
            raise

        except JarpcError as e:
            logger.debug(e, exc_info=True)
            return JarpcResponse(request_id=request_id, error=e.as_dict()) if rsvp else None

        except Exception as e:
            logger.exception(e)
            return JarpcResponse(
                request_id=request_id,
                error=JarpcServerError(e).as_dict()
            ) if rsvp else None

        finally:
            if context_token is not None:
                meta_context_var.reset(context_token)

    async def _endpoint_handler(self, request: JarpcRequest) -> JarpcResponse | None:
        if request.expired:
            logger.warning(f"Request arrived too late: {request}")
            return None

        method = self.dispatcher[request.method]

        if not request.rsvp:
            task = asyncio.create_task(self._run_method(method, request))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return None

        result = await self._execute_request_method(method, request)

        if request.expired:
            logger.warning(f"Request took too long to complete: {request}")
            return None

        return JarpcResponse(request_id=request.id, result=result)

    def _parse_request_or_raise(self, request_string: str) -> JarpcRequest:
        try:
            return JarpcRequest.model_validate_json(request_string)
        except ValidationError:
            raise JarpcParseError()

    async def _execute_request_method(self, method, request: JarpcRequest) -> Any:
        try:
            from contextlib import AsyncExitStack
            async with AsyncExitStack() as stack:
                for limiter in self.limiters:
                    await stack.enter_async_context(limiter)
                return await self._call_method(method, request)
        except TypeError:
            is_call_ok, explanation = check_function_call(
                method, request.params, self.context
            )
            if is_call_ok:
                raise
            logger.debug(f"Wrong signature in call to {request.method}: {explanation}")
            raise JarpcInvalidParams(explanation)

    async def _call_method(self, method, request: JarpcRequest) -> Any:
        context_params, method_sig = prepare_context_params(method, request, self.context)
        converted_params = convert_params_to_models(request.params, method_sig)

        if any(key in converted_params for key in context_params):
            raise TypeError("Cannot mix context and non-context parameters")

        final_params = {**converted_params, **context_params}
        
        is_async = inspect.iscoroutinefunction(method) or (
            hasattr(method, "__call__") and inspect.iscoroutinefunction(method.__call__)
        )

        if is_async:
            result = await method(**final_params)
        elif self.run_sync_in_thread:
            result = await asyncio.to_thread(method, **final_params)
        else:
            result = method(**final_params)

        return process_return_value(method_sig.return_annotation, result)

    async def _run_method(self, method: Callable, request: JarpcRequest) -> None:
        """Runs the method asynchronously for background tasks."""
        try:
            from contextlib import AsyncExitStack
            async with AsyncExitStack() as stack:
                for limiter in self.limiters:
                    await stack.enter_async_context(limiter)
                await self._call_method(method, request)
        except Exception as e:
            logger.exception(f"Unhandled exception in background task for method {request.method}: {e}")

    async def shutdown(self):
        if self._background_tasks:
            logger.info(f"Shutting down: waiting for {len(self._background_tasks)} RSVP=False tasks to complete...")
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            logger.info("All background tasks completed. Shutdown complete.")
        else:
            logger.info("No background tasks. Shutdown complete.")

