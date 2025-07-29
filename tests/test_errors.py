# -*- coding: utf-8 -*-
import pytest

from jarpcdantic import (
    JarpcError,
    JarpcExternalServiceUnavailable,
    JarpcForbidden,
    JarpcUnauthorized,
    JarpcUnknownError,
    JarpcValidationError,
    jarpcdantic_exceptions,
)


@pytest.mark.parametrize(
    "code, error_class, data",
    [
        (1000, JarpcUnauthorized, "test1"),
        (1001, JarpcForbidden, "test2"),
        (2000, JarpcValidationError, "test3"),
        (3000, JarpcExternalServiceUnavailable, "test3"),
        (9999, JarpcUnknownError, "test4"),
    ],
)
def test_raise_exception(code, error_class, data):
    with pytest.raises(error_class) as e:
        jarpcdantic_exceptions.raise_exception(code=code, data=data)

    assert e.value.error == data
    assert e.value.code == code
    assert e.value.message == error_class.message


@pytest.mark.parametrize(
    "code, error_class, message, data",
    [
        (9999, JarpcUnknownError, "test1", "testst"),
        (9999, JarpcUnknownError, "test2", {}),
        (9999, JarpcUnknownError, "test3", ()),
        (9999, JarpcUnknownError, "test4", None),
    ],
)
def test_raise_exception_unknown_error(code, error_class, data, message):
    with pytest.raises(error_class) as e:
        jarpcdantic_exceptions.raise_exception(code=code, data=data, message=message)

    assert e.value.error == data
    assert e.value.code == code
    assert e.value.message == message


def test_as_dict_method():
    with pytest.raises(JarpcError) as e:
        jarpcdantic_exceptions.raise_exception(
            code=4444, data="test_as_dict_method", message="test exception"
        )

    assert e.value.as_dict() == {
        "code": 4444,
        "error": "test_as_dict_method",
        "message": "test exception",
    }
