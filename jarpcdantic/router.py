import inspect
from inspect import _empty
from typing import Any, OrderedDict, Type

from pydantic import BaseModel, create_model

from jarpcdantic import AsyncJarpcClient, JarpcClient, JarpcDispatcher


class JarpcClientRouter:
    def __init__(
        self,
        prefix: str | None = None,
        client: AsyncJarpcClient | JarpcClient | None = None,
        is_absolute_prefix: bool = False,
    ):
        self._client: AsyncJarpcClient | JarpcClient | None = client
        self._prefix: str | None = prefix
        self._is_absolute_prefix: bool = is_absolute_prefix
        self._method_map: dict = {}

        self._decorate_methods()

    def _decorate_methods(self, is_nested: bool = False):
        for attr_name, attr_value in self.__class__.__dict__.items():
            if attr_name.startswith("_") or isinstance(attr_value, property):
                continue

            if isinstance(attr_value, JarpcClientRouter):
                self._proceed_nested_router(attr_name, attr_value)

            if (
                not is_nested
                and not attr_name.startswith("_")
                and hasattr(attr_value, "__annotations__")
                and "return" in attr_value.__annotations__
            ):
                self._proceed_endpoint(attr_name, attr_value)

    def _proceed_endpoint(self, endpoint_name, endpoint_method):
        attr_signature = inspect.signature(endpoint_method)
        ordered_parameters_signature = [
            (k, v) for k, v in attr_signature.parameters.items()
        ]
        clear_parameters = {
            k: v
            for k, v in attr_signature.parameters.items()
            if k not in ["self", "args", "kwargs"] and not k.startswith("_")
        }

        model: Type[BaseModel] | None = None

        if "_model" in attr_signature.parameters:
            model: Type[BaseModel] = attr_signature.parameters["_model"].default
        elif len(clear_parameters) == 1 and issubclass(
            clear_parameters[list(clear_parameters.keys())[0]].annotation, BaseModel
        ):
            parameter = clear_parameters[list(clear_parameters.keys())[0]]
            model = parameter.annotation if parameter.annotation is not _empty else None
        elif len(clear_parameters) >= 1:
            model = create_model(
                "DynamicModel",
                **{
                    k: (
                        Any if v.annotation is _empty else v.annotation,
                        ... if v.default is _empty else v.default,
                    )
                    for k, v in clear_parameters.items()
                },
            )

        wrapped_attr = self._wrap(self, endpoint_name, model, attr_signature.parameters)
        wrapped_attr.__annotations__ = endpoint_method.__annotations__

        self._method_map[endpoint_name] = wrapped_attr
        setattr(self, endpoint_name, wrapped_attr)

    def _proceed_nested_router(
        self, attr_router_name, nested_router: "JarpcClientRouter"
    ) -> None:
        if nested_router._prefix is None:
            nested_router._prefix = attr_router_name

        if nested_router._is_absolute_prefix:
            return

        if self._prefix is None:
            prefix = ""
        else:
            prefix = self._prefix

        if not nested_router._prefix.startswith(prefix):
            nested_router._prefix = (
                prefix
                + ("." if prefix and nested_router._prefix else "")
                + nested_router._prefix
            )

        if nested_router._client is None and self._client is not None:
            nested_router._client = self._client

        nested_router._decorate_methods(is_nested=True)

    @staticmethod
    def _wrap(
        self,
        method: str,
        model: Type[BaseModel] | None,
        attr_signature_parameters: OrderedDict,
    ):
        async def wrapped(*args, **kwargs):
            service_kwargs = {k: v for k, v in kwargs.items() if k.startswith("_")}
            clear_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_")}

            if model is not None:
                args_with_default = {
                    k: v.default for k, v in attr_signature_parameters.items()
                }
                for index, value in enumerate(args):
                    args_with_default[
                        list(attr_signature_parameters.items())[index + 1][0]
                    ] = value
                if issubclass(model, BaseModel):
                    params = model(**(args_with_default | clear_kwargs))
                else:
                    params = {
                        k: v
                        for k, v in (args_with_default | clear_kwargs).items()
                        if v is not _empty
                    }
            else:
                params = {}

            if self._client is not None:
                response = await self._client(
                    method=self._prefix + ("." if self._prefix else "") + method,
                    params=params,
                    **service_kwargs,
                )
                return response
            else:
                print("client is None, call", self._prefix + "." + method, params)

        def __str__(*args, **kwargs) -> str:
            return self._prefix + "." + method

        wrapped.__str__ = __str__
        wrapped.__repr__ = __str__

        return wrapped
