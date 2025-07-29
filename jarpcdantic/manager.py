# -*- coding: utf-8 -*-
import inspect
import logging
from asyncio import CancelledError, TaskGroup
from collections import deque
from typing import Any, Iterable, Optional

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
        - {"jarpc_request"}
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
            - {"jarpc_request"}
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
        restricted_intersection = kwargs.keys() & (context.keys() | {"jarpc_request"})
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
    ):
        self.dispatcher: JarpcDispatcher = dispatcher
        self.context: dict[str, Any] = (
            context or dict()
        )  # per-manager context cannot contain jarpc_request
        self.task_group: TaskGroup = TaskGroup()

    async def handle(self, request: str) -> str | None:
        response: JarpcResponse = await self.get_response(request)
        return response.model_dump_json() if response else None

    async def get_response(self, request_string: str) -> JarpcResponse | None:
        request_id: str | None = None
        context_token = None
        rsvp = True

        try:
            request = self._parse_request_or_raise(request_string)

            if request.expired:
                logger.warning(f"Request arrived too late: {request}")
                return None

            request_id = request.id
            rsvp = request.rsvp
            context_token = meta_context_var.set(request.meta)
            method = self.dispatcher[request.method]

            if not request.rsvp:
                self.task_group.create_task(self._run_method(method, request))
                return None

            result = await self._execute_request_method(method, request)

            if request.expired:
                logger.warning(f"Request took too long to complete: {request}")
                return None

            return JarpcResponse(request_id=request_id, result=result)

        except CancelledError:
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
            if context_token:
                meta_context_var.reset(context_token)

    def _parse_request_or_raise(self, request_string: str) -> JarpcRequest:
        try:
            return JarpcRequest.model_validate_json(request_string)
        except ValidationError:
            raise JarpcParseError()

    async def _execute_request_method(self, method, request: JarpcRequest) -> Any:
        try:
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
        result = method(**final_params)

        if inspect.isawaitable(result):
            result = await result

        return process_return_value(method_sig.return_annotation, result)

    async def _run_method(self, method, request: JarpcRequest):
        try:
            await self._call_method(method, request)
        except Exception as e:
            logger.exception(f"RSVP=False method {request.method} failed: {e}")

    async def shutdown(self):
        logger.info("Shutting down: waiting for all RSVP=False tasks to complete...")
        await self.task_group.__aexit__(None, None, None)
        logger.info("All tasks completed. Shutdown complete.")

