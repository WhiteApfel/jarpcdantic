# -*- coding: utf-8 -*-
import json
from unittest import mock

import pytest
from freezegun import freeze_time

from jarpcdantic import (
    AsyncJarpcClient,
    JarpcClient,
    JarpcRequest,
    JarpcServerError,
    JarpcTimeout,
    JarpcValidationError,
)


class TestJarpcClient:
    @pytest.mark.parametrize("is_async", [False, True])
    @freeze_time("2012-01-14")
    def test_prepare_request(self, is_async):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(transport=None)

        with mock.patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = "example-uuid"
            request = jarpc_client._prepare_request(
                method="test_method", params={"a": 1}
            )

        assert request.model_dump() == {
            "method": "test_method",
            "params": {"a": 1},
            "id": "example-uuid",
            "version": "1.0",
            "ts": 1326499200.0,
            "ttl": None,
            "rsvp": True,
        }

    @pytest.mark.parametrize(
        "rsvp, ttl, default_ttl, default_rpc_ttl, default_notification_ttl,"
        " expected_ttl",
        [
            (True, None, None, None, None, None),
            (False, None, None, None, None, None),
            (True, 10.0, None, None, None, 10.0),
            (False, 10.0, None, None, None, 10.0),
            (True, None, 10.0, None, None, 10.0),
            (False, None, 10.0, None, None, 10.0),
            (True, 30.0, 10.0, None, None, 30.0),
            (False, 30.0, 10.0, None, None, 30.0),
            (True, None, None, 10.0, 20.0, 10.0),
            (False, None, None, 10.0, 20.0, 20.0),
            (True, None, 30.0, 10.0, 20.0, 10.0),
            (False, None, 30.0, 10.0, 20.0, 20.0),
            (True, 30.0, None, 10.0, 20.0, 30.0),
            (False, 30.0, None, 10.0, 20.0, 30.0),
            (True, 40.0, 30.0, 10.0, 20.0, 40.0),
            (False, 40.0, 30.0, 10.0, 20.0, 40.0),
        ],
    )
    @pytest.mark.parametrize("is_async", [False, True])
    @freeze_time("2012-01-14")
    def test_prepare_request_default_ttl(
        self,
        is_async,
        rsvp,
        ttl,
        default_ttl,
        default_rpc_ttl,
        default_notification_ttl,
        expected_ttl,
    ):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(
            transport=None,
            default_ttl=default_ttl,
            default_rpc_ttl=default_rpc_ttl,
            default_notification_ttl=default_notification_ttl,
        )

        with mock.patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = "example-uuid"
            request = jarpc_client._prepare_request(
                method="test_method", params={"a": 1}, ttl=ttl, rsvp=rsvp
            )

        assert request.model_dump() == {
            "method": "test_method",
            "params": {"a": 1},
            "id": "example-uuid",
            "version": "1.0",
            "ts": 1326499200.0,
            "ttl": expected_ttl,
            "rsvp": rsvp,
        }

    @pytest.mark.parametrize("is_async", [False, True])
    @freeze_time("2012-01-14")
    def test_prepare_request_durable(self, is_async):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(
            transport=None,
            default_ttl=1.0,
            default_rpc_ttl=2.0,
            default_notification_ttl=3.0,
        )

        with mock.patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = "example-uuid"
            request = jarpc_client._prepare_request(
                method="test_method", params={"a": 1}, ttl=4.0, durable=True
            )

        assert request.model_dump() == {
            "method": "test_method",
            "params": {"a": 1},
            "id": "example-uuid",
            "version": "1.0",
            "ts": 1326499200.0,
            "ttl": None,
            "rsvp": True,
        }

    @pytest.mark.parametrize("is_async", [False, True])
    def test_parse_response_no_rsvp(self, is_async):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(transport=None)
        assert jarpc_client._parse_response(response_string="", rsvp=False) is None

    @pytest.mark.parametrize("is_async", [False, True])
    def test_parse_response_ok(self, is_async):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(transport=None)
        result = {
            "result": "some result",
            "request_id": "123-456-788",
            "id": "123-456-789",
        }
        assert (
            jarpc_client._parse_response(response_string=json.dumps(result), rsvp=True)
            == result["result"]
        )

    @pytest.mark.parametrize("is_async", [False, True])
    def test_parse_response_error(self, is_async):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(transport=None)
        error = {
            "error": {"code": 2000, "message": "Validation error", "data": "some data"},
            "request_id": "123-456-788",
            "id": "123-456-789",
        }
        with pytest.raises(JarpcValidationError) as e:
            jarpc_client._parse_response(response_string=json.dumps(error), rsvp=True)
        assert e.value.code == error["error"]["code"]
        assert e.value.message == error["error"]["message"]
        assert e.value.data == error["error"]["data"]

    @pytest.mark.parametrize("is_async", [False, True])
    def test_parse_response_invalid_json(self, is_async):
        client = AsyncJarpcClient if is_async else JarpcClient
        jarpc_client = client(transport=None)

        with pytest.raises(JarpcServerError):
            jarpc_client._parse_response(response_string="", rsvp=True)

    @pytest.mark.parametrize("is_async", [False, True])
    @pytest.mark.asyncio
    @freeze_time("2012-01-14")
    async def test_call(self, is_async):
        request_id = "123-456-788"
        response = {
            "result": "some result",
            "request_id": request_id,
            "id": "123-456-789",
        }
        transport = lambda *args, **kwargs: json.dumps(response)
        jarpc_client = JarpcClient(transport=transport)

        call_kwargs = dict(
            method="method", params={"param1": 1}, id=request_id, extra_kwarg=1
        )
        call_result = jarpc_client(**call_kwargs)
        assert call_result == response["result"]

    @pytest.mark.parametrize("is_async", [False, True])
    @pytest.mark.asyncio
    @freeze_time("2012-01-14")
    async def test_call_simple_syntax(self, is_async):
        response = {
            "result": "some result",
            "request_id": "no check",
            "id": "123-456-789",
        }

        transport = lambda *args, **kwargs: json.dumps(response)
        jarpc_client = JarpcClient(transport=transport)

        call_result = jarpc_client.method(param1=1)

        assert call_result == response["result"]
