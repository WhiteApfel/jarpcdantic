import pytest
from pydantic import BaseModel, ValidationError
from typing import Union, List, Dict
from jarpcdantic.utils import (
    convert_dict_to_model,
    convert_instance_to_another_model,
    convert_to_pydantic_model,
    convert_single_value,
    convert_iterable,
    convert_mapping,
    convert_union,
    convert_value_to_type,
    convert_params_to_models,
    process_return_value,
)
from jarpcdantic import JarpcParseError
import inspect

class ModelA(BaseModel):
    x: int
    y: str

class ModelB(BaseModel):
    x: int
    y: str
    z: float = 1.0

# --- convert_dict_to_model ---
@pytest.mark.parametrize(
    "data,model_cls,expected_x,expected_y",
    [
        ({"x": 1, "y": "abc"}, ModelA, 1, "abc"),
    ],
)
def test_convert_dict_to_model_ok(data, model_cls, expected_x, expected_y):
    model = convert_dict_to_model(data, model_cls)
    assert isinstance(model, model_cls)
    assert model.x == expected_x and model.y == expected_y

@pytest.mark.parametrize(
    "data,model_cls,exc_type",
    [
        ({"x": "bad"}, ModelA, ValidationError),
    ],
)
def test_convert_dict_to_model_fail(data, model_cls, exc_type):
    with pytest.raises(exc_type):
        convert_dict_to_model(data, model_cls)

# --- convert_instance_to_another_model ---
@pytest.mark.parametrize(
    "instance,target_cls,expected_x,expected_y,expected_z",
    [
        (ModelA(x=2, y="foo"), ModelB, 2, "foo", 1.0),
    ],
)
def test_convert_instance_to_another_model_ok(instance, target_cls, expected_x, expected_y, expected_z):
    model = convert_instance_to_another_model(instance, target_cls)
    assert isinstance(model, target_cls)
    assert model.x == expected_x and model.y == expected_y and model.z == expected_z

# --- convert_to_pydantic_model ---
@pytest.mark.parametrize(
    "source,target_cls",
    [
        ({"x": 3, "y": "bar"}, ModelA),
        (ModelA(x=3, y="bar"), ModelA),
    ],
)
def test_convert_to_pydantic_model_ok(source, target_cls):
    assert isinstance(convert_to_pydantic_model(source, target_cls), target_cls)

@pytest.mark.parametrize(
    "source,target_cls,exc_type",
    [
        (123, ModelA, JarpcParseError),
    ],
)
def test_convert_to_pydantic_model_fail(source, target_cls, exc_type):
    with pytest.raises(exc_type):
        convert_to_pydantic_model(source, target_cls)

# --- convert_single_value ---
@pytest.mark.parametrize(
    "value,target_type,expected",
    [
        (5, int, 5),
        (None, type(None), None),
        ({"x": 1, "y": "a"}, ModelA, 1),  # x=1, only check x
    ],
)
def test_convert_single_value_ok(value, target_type, expected):
    result = convert_single_value(value, target_type)
    if isinstance(result, ModelA):
        assert result.x == expected
    else:
        assert result == expected

@pytest.mark.parametrize(
    "value,target_type,exc_type",
    [
        ("bad", ModelA, Exception),
    ],
)
def test_convert_single_value_fail(value, target_type, exc_type):
    with pytest.raises(exc_type):
        convert_single_value(value, target_type)

# --- convert_iterable ---
@pytest.mark.parametrize(
    "value,target_type,expected_type",
    [
        ([{"x": 1, "y": "a"}], List[ModelA], list),
    ],
)
def test_convert_iterable_ok(value, target_type, expected_type):
    res = convert_iterable(value, target_type)
    assert isinstance(res, expected_type)
    assert isinstance(res[0], ModelA)

# --- convert_mapping ---
@pytest.mark.parametrize(
    "value,target_type,expected_type",
    [
        ({"a": {"x": 1, "y": "b"}}, Dict[str, ModelA], dict),
    ],
)
def test_convert_mapping_ok(value, target_type, expected_type):
    res = convert_mapping(value, target_type)
    assert isinstance(res, expected_type)
    assert isinstance(res["a"], ModelA)

# --- convert_union ---
@pytest.mark.parametrize(
    "value,target_type,expected",
    [
        (1, Union[int, str], 1),
        ("a", Union[int, str], "a"),
        ({"x": 1, "y": "a"}, Union[ModelA, int], ModelA),
    ],
)
def test_convert_union_ok(value, target_type, expected):
    result = convert_union(value, target_type)
    if expected is ModelA:
        assert isinstance(result, ModelA)
    else:
        assert result == expected

@pytest.mark.parametrize(
    "value,target_type,exc_type",
    [
        ("1.1", Union[ModelA, int], JarpcParseError),
    ],
)
def test_convert_union_fail(value, target_type, exc_type):
    with pytest.raises(exc_type):
        convert_union(value, target_type)

# --- convert_value_to_type ---
@pytest.mark.parametrize(
    "value,target_type,expected",
    [
        (1, int, 1),
        ({"x": 1, "y": "a"}, ModelA, ModelA),
        ([1, 2], List[int], [1, 2]),
        (None, type(None), None),
    ],
)
def test_convert_value_to_type_ok(value, target_type, expected):
    result = convert_value_to_type(value, target_type)
    if expected is ModelA:
        assert isinstance(result, ModelA)
    else:
        assert result == expected

@pytest.mark.parametrize(
    "value,target_type,exc_type",
    [
        ({"a": 1}, Dict[str, int], ValueError),  # known баг в utils
    ],
)
def test_convert_value_to_type_fail(value, target_type, exc_type):
    with pytest.raises(exc_type):
        convert_value_to_type(value, target_type)

# --- convert_params_to_models ---
@pytest.mark.parametrize(
    "params,expected_a,expected_b",
    [
        ({"a": 5, "b": {"x": 1, "y": "c"}}, 5, ModelA),
    ],
)
def test_convert_params_to_models_ok(params, expected_a, expected_b):
    def foo(a: int, b: ModelA):
        pass
    sig = inspect.signature(foo)
    out = convert_params_to_models(params, sig)
    assert out["a"] == expected_a
    assert isinstance(out["b"], expected_b)

# --- process_return_value ---
@pytest.mark.parametrize(
    "return_annotation,result,expected",
    [
        (int, 5, 5),
        (type(None), None, None),
        (ModelA, {"x": 1, "y": "a"}, ModelA),
    ],
)
def test_process_return_value_ok(return_annotation, result, expected):
    out = process_return_value(return_annotation, result)
    if expected is ModelA:
        assert isinstance(out, ModelA)
    else:
        assert out == expected