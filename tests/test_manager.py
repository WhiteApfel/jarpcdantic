# -*- coding: utf-8 -*-
import asyncio
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from jarpcdantic import JarpcDispatcher, JarpcManager, JarpcRequest
from jarpcdantic.manager import check_function_call


class TestCheckFunctionCall:
    @pytest.mark.parametrize("context", [{}, {"app": "some app", "db": "db"}])
    @pytest.mark.parametrize(
        "func, params, expected",
        [
            (lambda a, b: ..., dict(a=1, b=2), (True, None)),
            (
                lambda a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, c=3, x=0, y=1),
                (True, None),
            ),
            (lambda a, b, c=0, *, x, y=1, **kw: ..., dict(a=1, b=2, x=0), (True, None)),
            (
                lambda a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0, foo="bar"),
                (True, None),
            ),
            (lambda a, b: ..., dict(a=1, b=2, c=3), (False, "Unexpected arguments: c")),
            (lambda a, b: ..., dict(a=1), (False, "Missing arguments: b")),
            (lambda a, b: ..., dict(), (False, "Missing arguments: a, b")),
            (
                lambda a, b, c=0, *, x, y=1: ...,
                dict(a=1, b=2, c=3, x=0, y=1, z=2),
                (False, "Unexpected arguments: z"),
            ),
            (
                lambda a, b, c=0, *, x, y=1: ...,
                dict(a=1, x=0),
                (False, "Missing arguments: b"),
            ),
            (
                lambda a, b, c=0, *, x, y=1: ...,
                dict(a=1, b=2),
                (False, "Missing arguments: x"),
            ),
        ],
    )
    def test_no_context_effect(self, func, params, context, expected):
        assert check_function_call(func, params, context) == expected

    @pytest.mark.parametrize(
        "func, params, expected",
        [
            (lambda jarpc_request, app, a, b: ..., dict(a=1, b=2), (True, None)),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, c=3, x=0, y=1),
                (True, None),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0),
                (True, None),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0, foo="bar"),
                (True, None),
            ),
            (
                lambda jarpc_request, app, a, b: ...,
                dict(a=1, b=2, c=3),
                (False, "Unexpected arguments: c"),
            ),
            (
                lambda jarpc_request, app, a, b: ...,
                dict(a=1),
                (False, "Missing arguments: b"),
            ),
            (
                lambda jarpc_request, app, a, b: ...,
                dict(),
                (False, "Missing arguments: a, b"),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1: ...,
                dict(a=1, b=2, c=3, x=0, y=1, z=2),
                (False, "Unexpected arguments: z"),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1: ...,
                dict(a=1, x=0),
                (False, "Missing arguments: b"),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1: ...,
                dict(a=1, b=2),
                (False, "Missing arguments: x"),
            ),
            (lambda a, b, app="default", *, x: ..., dict(a=1, b=2, x=0), (True, None)),
            (
                lambda a, b, app="default", *, x: ...,
                dict(a=1, b=2, x=0, app="evil app"),
                (False, "Unexpected arguments: app"),
            ),
            (
                lambda jarpc_request, a, b, *, x: ...,
                dict(a=1, b=2, x=0, jarpc_request="evil request"),
                (False, "Unexpected arguments: jarpc_request"),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, c=3, x=0, y=1),
                (True, None),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0),
                (True, None),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0, foo="bar"),
                (True, None),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0, jarpc_request="evil"),
                (False, "Unavailable arguments: jarpc_request"),
            ),
            (
                lambda jarpc_request, app, a, b, c=0, *, x, y=1, **kw: ...,
                dict(a=1, b=2, x=0, app="evil"),
                (False, "Unavailable arguments: app"),
            ),
        ],
    )
    def test_with_context(self, func, params, expected):
        assert (
            check_function_call(func, params, {"app": "some app", "db": "db"})
            == expected
        )

    @pytest.mark.parametrize(
        "params, expected",
        [
            (dict(a=1, b=2), (True, None)),
            (dict(a=1, b=2, c=3), (False, "Unexpected arguments: c")),
            (dict(self=0, a=1, b=2), (False, "Unexpected arguments: self")),
            (dict(a=1), (False, "Missing arguments: b")),
            (dict(), (False, "Missing arguments: a, b")),
        ],
    )
    def test_method(self, params, expected):
        class SomeMethod:
            def run(self, app, a, b): ...

        assert (
            check_function_call(
                SomeMethod().run, params, {"app": "some app", "db": "db"}
            )
            == expected
        )

    @pytest.mark.parametrize(
        "params, expected",
        [
            (dict(a=1, b=2), (True, None)),
            (dict(a=1, b=2, c=3), (False, "Unexpected arguments: c")),
            (dict(a=1), (False, "Missing arguments: b")),
            (dict(), (False, "Missing arguments: a, b")),
        ],
    )
    def test_static_method(self, params, expected):
        class SomeMethod:
            @staticmethod
            def run(app, a, b): ...

        assert (
            check_function_call(
                SomeMethod().run, params, {"app": "some app", "db": "db"}
            )
            == expected
        )

    @pytest.mark.parametrize(
        "params, expected",
        [
            (dict(a=1, b=2), (True, None)),
            (dict(a=1, b=2, c=3), (False, "Unexpected arguments: c")),
            (dict(self=0, a=1, b=2), (False, "Unexpected arguments: self")),
            (dict(a=1), (False, "Missing arguments: b")),
            (dict(), (False, "Missing arguments: a, b")),
        ],
    )
    def test_object_no_context(self, params, expected):
        class SomeMethod:
            def __call__(self, a, b): ...

        assert check_function_call(SomeMethod(), params, {}) == expected

    @pytest.mark.parametrize(
        "params, expected",
        [
            (dict(a=1, b=2, c=3, x=0, y=1), (True, None)),
            (dict(a=1, b=2, x=0), (True, None)),
            (dict(a=1, b=2, x=0, foo="bar"), (False, "Unexpected arguments: foo")),
            (dict(a=1, b=2, c=3, x=0, y=1, z=2), (False, "Unexpected arguments: z")),
            (dict(self=0, a=1, b=2, x=0), (False, "Unexpected arguments: self")),
            (dict(a=1, x=0), (False, "Missing arguments: b")),
            (dict(a=1, b=2), (False, "Missing arguments: x")),
        ],
    )
    def test_object_with_context(self, params, expected):
        class SomeMethod:
            def __call__(self, jarpc_request, app, a, b, c=0, *, x, y=1): ...

        assert (
            check_function_call(SomeMethod(), params, {"app": "some app", "db": "db"})
            == expected
        )


@pytest.mark.asyncio
class TestGetResponse:
    basic_request = {
        "method": "method",
        "params": {"param": "value"},
        "request_id": "1",
        "version": "1.0",
        "ts": float(1 << 31),
        "ttl": 1.0,
        "rsvp": True,
    }

    async def test_no_method(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        response = await manager.get_response(json.dumps(self.basic_request))
        assert response is not None
        assert response.result is None
        assert response.error == {
            "code": -32601,
            "message": "Method not found",
            "error": {
                "method": "method",
                "declared_methods": [],
            },
        }

    @pytest.mark.parametrize(
        "params, explanation",
        [
            (dict(a=1, b=2, c=3, x=0, y=1, z=2), "Unexpected arguments: z"),
            (dict(a=1, x=0), "Missing arguments: b"),
            (dict(a=1, b=2), "Missing arguments: x"),
        ],
    )
    async def test_invalid_params(self, params, explanation):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        dispatcher.add_rpc_method(lambda a, b, c=0, *, x, y=1: ..., "method")

        request = deepcopy(self.basic_request)
        request["params"] = params
        response = await manager.get_response(json.dumps(request))
        
        assert response is not None
        assert response.result is None
        assert response.error == {
            "code": -32602,
            "message": "Invalid params",
            "error": explanation,
        }

    async def test_handle_result_ok(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        @dispatcher.rpc_method
        def method(jarpc_request, param):
            return "42"

        response = await manager.handle(json.dumps(self.basic_request))

        assert json.loads(response)["result"] == "42"

    async def test_handle_result_none(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        @dispatcher.rpc_method
        def method(jarpc_request, param):
            return None

        request_data = deepcopy(self.basic_request)
        request_data["ts"] = 1.0

        response = await manager.handle(json.dumps(request_data))

        assert response is None

    async def test_invalid_request_json_parse_error(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        request = "some invalid json"
        response = await manager.get_response(request)
        
        error = response.error
        assert error["message"] == "Parse error"

    # TODO: Fix test
    # @pytest.mark.parametrize("is_async", [False, True])
    # async def test_invalid_request_no_params(self, is_async):
    #     dispatcher = JarpcDispatcher()
    #     manager = (
    #         AsyncJarpcManager(dispatcher) if is_async else JarpcManager(dispatcher)
    #     )
    #     request = deepcopy(self.basic_request)
    #     request.pop("params")
    #     if is_async:
    #         response = await manager.get_response(json.dumps(request))
    #     else:
    #         response = manager.get_response(json.dumps(request))
    #     error = response.error
    #     assert error["message"] == "Invalid Request"
    #     assert error["data"] == 'Missing required field "params"'

    async def test_invalid_rpc_method(self):
        """Test rpc_method TypeError"""
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        @dispatcher.rpc_method
        def method(jarpc_request, param):
            return "2" + 2

        response = await manager.get_response(json.dumps(self.basic_request))
        error = response.error
        assert error["message"] == "Server error"

    async def test_invalid_rpc_method_rsvp_false(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        request = deepcopy(self.basic_request)
        request["rsvp"] = False

        @dispatcher.rpc_method
        def method(jarpc_request, param):
            return "2" + 2

        response = await manager.get_response(json.dumps(request))
        assert response is None

    async def test_rpc_method_time_out(self, caplog):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        request = deepcopy(self.basic_request)
        request["ts"] = datetime.now(tz=timezone.utc).timestamp()
        request["ttl"] = 1.0

        @dispatcher.rpc_method
        def method(jarpc_request, param):
            import time

            time.sleep(1)

        response = await manager.get_response(json.dumps(request))

        caplog.set_level(logging.WARNING)

        assert response is None
        assert "Request took too long to complete" in caplog.text

    async def test_sync(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        @dispatcher.rpc_method
        def method(param):
            assert param == "value"
            return "return value"

        response = await manager.get_response(json.dumps(self.basic_request))
        assert response is not None
        assert response.result == "return value"

    async def test_async(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        @dispatcher.rpc_method
        async def method(param):
            assert param == "value"
            return "return value"

        response = await manager.get_response(json.dumps(self.basic_request))
        assert response is not None
        assert response.result == "return value"

    async def test_task_cancellation(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)

        @dispatcher.rpc_method
        async def method(param):
            await asyncio.sleep(10)

        task = asyncio.ensure_future(
            manager.get_response(json.dumps(self.basic_request))
        )
        await asyncio.sleep(0.1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
class TestCallMethod:
    basic_request_kwargs = {
        "method": "method",
        "params": {"param": "value"},
        "request_id": "1",
        "ts": float(1 << 31),
        "ttl": 1.0,
        "rsvp": True,
    }

    @pytest.mark.parametrize(
        "params",
        [
            dict(a=1, b=2, c=3, x=0, y=1),
            dict(a=1, b=2, x=0),
            dict(a=1, b=2, x=0, y=1, z=2, abc="def"),
        ],
    )
    async def test_no_context(self, params):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        request_data = deepcopy(self.basic_request_kwargs)
        request_data["params"] = params
        request = JarpcRequest(**request_data)

        @dispatcher.rpc_method
        def method(a, b, c=0, *, x, y=1, **kw):
            return "return value"

        result = await manager._call_method(method, request)
        assert result == "return value"

    async def test_async(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        request_data = deepcopy(self.basic_request_kwargs)
        request = JarpcRequest(**request_data)

        @dispatcher.rpc_method
        async def method(jarpc_request, param):
            return "return value"

        result = await manager._call_method(method, request)
        assert result == "return value"

    async def test_context(self):
        context = {"app": "some app"}
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher, context)
        request = JarpcRequest(**self.basic_request_kwargs)

        @dispatcher.rpc_method
        def method(app, param):
            assert app == "some app"
            assert param == "value"
            return "return value"

        result = await manager._call_method(method, request)
        assert result == "return value"

    async def test_request(self):
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher)
        request = JarpcRequest(**self.basic_request_kwargs)

        @dispatcher.rpc_method
        def method(jarpc_request, param):
            assert jarpc_request is request
            assert param == "value"
            return "return value"

        result = await manager._call_method(method, request)
        assert result == "return value"

    async def test_context_conflict(self):
        context = {"app": "some app"}
        dispatcher = JarpcDispatcher()
        manager = JarpcManager(dispatcher, context)
        request_data = deepcopy(self.basic_request_kwargs)
        request_data["params"] = {"app": "my app", "param": "value"}
        request = JarpcRequest(**request_data)

        @dispatcher.rpc_method
        def method(app, param):
            assert False

        with pytest.raises(TypeError):
            await manager._call_method(method, request)
