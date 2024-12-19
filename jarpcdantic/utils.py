import inspect
import traceback
from collections.abc import Iterable, Mapping
from types import UnionType
from typing import get_origin, get_args, Union, Type, Any

from pydantic import BaseModel, ValidationError

from jarpcdantic import JarpcParseError


def convert_dict_to_model(dict_data: dict, target_model: Type[BaseModel]):
    return target_model.model_validate(dict_data)


def convert_instance_to_another_model(
    instance: BaseModel, target_model: Type[BaseModel]
):
    return target_model.model_validate(instance, from_attributes=True)


def convert_to_pydantic_model(source: dict | BaseModel, target_model: Type[BaseModel]):
    if isinstance(source, dict):
        return convert_dict_to_model(source, target_model)
    elif isinstance(source, BaseModel):
        return convert_instance_to_another_model(source, target_model)
    else:
        raise JarpcParseError(
            f"Cannot convert {type(source)} to {target_model.__name__}"
        )


def convert_single_value(value: Any, target_type: Type) -> Any:
    if inspect.isclass(target_type) and issubclass(target_type, BaseModel):
        return convert_to_pydantic_model(value, target_type)
    try:
        return target_type(value)
    except (ValueError, TypeError):
        raise JarpcParseError(f"Cannot convert value {value} to {target_type}")


def convert_iterable(value: Any, target_type: Type) -> Any:
    item_type = get_args(target_type)[0]
    origin = get_origin(target_type)
    iterable = (convert_value_to_type(item, item_type) for item in value)
    return origin(iterable)


def convert_mapping(value: Any, target_type: Type) -> Any:
    key_type, value_type = get_args(target_type)
    return {
        convert_value_to_type(k, key_type): convert_value_to_type(v, value_type)
        for k, v in value.items()
    }


def convert_union(value: Any, target_type: Type) -> Any:
    for arg in get_args(target_type):
        if arg is type(None):
            if value is None:
                return None
        else:
            try:
                return convert_value_to_type(value, arg)
            except (ValidationError, JarpcParseError, TypeError, AttributeError):
                continue
    raise JarpcParseError(f"Cannot convert value {value} to any of {target_type}")


def convert_value_to_type(value: Any, target_type: Type) -> Any:
    """
    Универсальная функция для преобразования значения в указанный тип.
    Поддерживает Pydantic модели, контейнеры с моделями и Union.
    """
    origin = get_origin(target_type)

    if origin is None:
        return convert_single_value(value, target_type)
    elif issubclass(origin, Iterable) and not isinstance(value, str):
        return convert_iterable(value, target_type)
    elif origin in {dict, Mapping}:
        return convert_mapping(value, target_type)
    elif origin in (Union, UnionType):
        return convert_union(value, target_type)
    else:
        raise JarpcParseError(f"Unknown type {target_type}")


def convert_params_to_models(params, method_sig):
    """
    Converts parameters from dict to types specified in the method signature.
    """
    converted_params = {}
    for param_name, param_value in params.items():
        param_type = method_sig.parameters.get(
            param_name, inspect.Parameter.empty
        ).annotation
        if param_type is not inspect.Parameter.empty:
            try:
                converted_params[param_name] = convert_value_to_type(
                    param_value, param_type
                )
            except ValidationError as e:
                raise JarpcParseError(
                    f"Invalid parameter '{param_name}' for type {param_type}: {e}"
                )
        else:
            converted_params[param_name] = param_value
    return converted_params


def process_return_value(return_annotation, result):
    if return_annotation is not inspect.Signature.empty:
        try:
            return convert_value_to_type(result, return_annotation)
        except ValidationError as e:
            raise JarpcParseError(
                f"Failed to process return value {result} to type {return_annotation}: {e}"
            )
    return result
