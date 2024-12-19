import inspect
from inspect import _empty, Signature, Parameter
from typing import Any, Type, Callable, Generator

from pydantic import BaseModel, create_model

from jarpcdantic import AsyncJarpcClient, JarpcClient
from jarpcdantic.utils import process_return_value


class JarpcClientRouter:
    def __init__(
        self,
        prefix: str | None = None,
        client: AsyncJarpcClient | JarpcClient | None = None,
        is_absolute_prefix: bool = False,
    ):
        """
       Initializes the JARPC client router.

       :param prefix: Optional prefix for the router.
       :type prefix: str
       :param client: Optional client instance (AsyncJarpcClient or JarpcClient).
       :type client: Union[AsyncJarpcClient, JarpcClient]
       :param is_absolute_prefix: Whether the prefix is absolute.
       :type is_absolute_prefix: bool
       """
        self._client: AsyncJarpcClient | JarpcClient | None = client
        self._prefix: str | None = prefix
        self._is_absolute_prefix: bool = is_absolute_prefix
        self._method_map: dict[str, Callable[..., Any]] = {}

        self._decorate_endpoints()

    def _filter_attributes(self) -> Generator[tuple[str, Any], None, None]:
        """
        Filters and yields non-private attributes of the class.

        :yield: Tuples of attribute names and values.
        """
        for attr_name, attr_value in self.__class__.__dict__.items():
            if attr_name.startswith("_") or isinstance(attr_value, property):
                continue
            yield attr_name, attr_value

    @staticmethod
    def _is_nested_router(attr_value: Any) -> bool:
        """
        Checks if the attribute is an instance of JarpcClientRouter.

        :param attr_value: Attribute value to check.
        :type attr_value: Any
        :return: True if the attribute is a nested router, False otherwise.
        """
        return isinstance(attr_value, JarpcClientRouter)

    @staticmethod
    def _is_not_processed_endpoint(attr_name: str, attr_value: Any, is_nested: bool) -> bool:
        """
        Checks if the attribute is not a processed endpoint.

        :param attr_name: Name of the attribute.
        :type attr_name: str
        :param attr_value: Value of the attribute.
        :type attr_value: Any
        :param is_nested: Whether the router is nested.
        :return: True if the attribute is an endpoint, False otherwise.
        """
        return (
            not is_nested
            and not attr_name.startswith("_")
            and hasattr(attr_value, "__annotations__")
            and "return" in attr_value.__annotations__
        )

    def _process_attributes(self, is_nested: bool = False) -> None:
        """
        Handles attributes, processing nested routers and endpoints.

        :param is_nested: Whether the router is nested.
        :type is_nested: bool
        """
        for attr_name, attr_value in self._filter_attributes():
            if self._is_nested_router(attr_value):
                self._proceed_nested_router(attr_name, attr_value)
            elif self._is_not_processed_endpoint(attr_name, attr_value, is_nested):
                self._proceed_endpoint(attr_name, attr_value)

    def _decorate_endpoints(self, is_nested: bool = False) -> None:
        """
        Decorates methods to handle attributes.

        :param is_nested: Whether the router is nested.
        :type is_nested: bool
        """
        self._process_attributes(is_nested)

    @staticmethod
    def _filter_parameters(attr_signature: Signature) -> dict[str, Parameter]:
        """
        Filters parameters to exclude 'self', 'args', 'kwargs', and private attributes.

        :param attr_signature: Signature of the attribute.
        :type attr_signature: Signature
        :return: Filtered parameters as a dictionary.
        """
        return  {
            k: v
            for k, v in attr_signature.parameters.items()
            if k not in ["self", "args", "kwargs"] and not k.startswith("_")
        }

    @staticmethod
    def _determine_request_model(filtered_parameters: dict[str, inspect.Parameter], attr_signature: Signature) -> Type[BaseModel] | None:
        """
        Determines the request model for the endpoint.

        :param filtered_parameters: Filtered parameters of the attribute.
        :type filtered_parameters: dict
        :param attr_signature: Signature of the attribute.
        :type attr_signature: Signature
        :return: Request model if applicable, None otherwise.
        """
        request_model: Type[BaseModel] | None = None

        if "_model" in attr_signature.parameters:
            request_model: Type[BaseModel] = attr_signature.parameters["_model"].default
        elif (
            len(filtered_parameters) == 1
            and isinstance(
                filtered_parameters[list(filtered_parameters.keys())[0]].annotation, type
            )
            and issubclass(
                filtered_parameters[list(filtered_parameters.keys())[0]].annotation, BaseModel
            )
        ):
            parameter = filtered_parameters[list(filtered_parameters.keys())[0]]
            request_model = (
                parameter.annotation if parameter.annotation is not _empty else None
            )
        elif len(filtered_parameters) >= 1:
            request_model = create_model(
                "DynamicModel",
                **{
                    k: (
                        Any if v.annotation is _empty else v.annotation,
                        ... if v.default is _empty else v.default,
                    )
                    for k, v in filtered_parameters.items()
                },
            )

        return request_model

    def _wrap_endpoint(self, endpoint_name: str, request_model: Type[BaseModel], endpoint_signature: Signature) -> Any:
        """
        Wraps an endpoint method to handle parameter validation and sending requests via the client.

        :param endpoint_name: Name of the endpoint.
        :type endpoint_name: str
        :param request_model: Request model used for validation, if applicable.
        :type request_model: Type[BaseModel]
        :param endpoint_signature: Signature of the original method.
        :type endpoint_signature: Signature
        :return: Wrapped function to be used as endpoint.
        """
        wrapped_attr = self._wrap(self, endpoint_name, request_model, endpoint_signature)
        wrapped_attr.__annotations__ = {
            param_name: param.annotation for param_name, param in endpoint_signature.parameters.items()
        }
        wrapped_attr.__annotations__['return'] = endpoint_signature.return_annotation
        return wrapped_attr

    def _proceed_endpoint(self, endpoint_name: str, endpoint_method: Any) -> None:
        """
        Processes an endpoint by wrapping it and adding it to the method map.

        :param endpoint_name: Name of the endpoint.
        :type endpoint_name: str
        :param endpoint_method: Original method of the endpoint.
        :type endpoint_method: Any
        """
        endpoint_signature = inspect.signature(endpoint_method)
        filtered_parameters = self._filter_parameters(endpoint_signature)
        request_model = self._determine_request_model(filtered_parameters, endpoint_signature)
        wrapped_endpoint = self._wrap_endpoint(endpoint_name, request_model, endpoint_signature)

        self._method_map[endpoint_name] = wrapped_endpoint
        setattr(self, endpoint_name, wrapped_endpoint)

    def _proceed_nested_router(
        self, attr_router_name: str, nested_router: "JarpcClientRouter"
    ) -> None:
        """
        Processes a nested router by setting prefixes, clients, and decorating its methods.

        :param attr_router_name: Name of the nested router attribute.
        :type attr_router_name: str
        :param nested_router: Instance of the nested router.
        :type nested_router: JarpcClientRouter
        """
        if nested_router._prefix is None:
            nested_router._prefix = attr_router_name

        if nested_router._is_absolute_prefix:
            return

        if self._prefix and not nested_router._prefix.startswith(self._prefix):
            nested_router._prefix = f"{self._prefix}.{nested_router._prefix}".strip(".")

        if not nested_router._client and self._client:
            nested_router._client = self._client

        nested_router._decorate_endpoints(is_nested=True)

    def set_client(self, client: AsyncJarpcClient | JarpcClient) -> None:
        """
        Sets the client for this router and all nested routers.

        :param client: JARPC Client instance
        :type client: AsyncJarpcClient | JarpcClient
        """
        self._client = client
        for attr_name, attr_value in self.__class__.__dict__.items():
            if attr_name.startswith("_") or isinstance(attr_value, property):
                continue

            if isinstance(attr_value, JarpcClientRouter):
                attr_value.set_client(client)

    @staticmethod
    def _wrap(
        instance: "JarpcClientRouter",
        method_name: str,
        request_model: Type[BaseModel] | None,
        method_signature: Signature,
    ) -> Callable[..., Any]:
        """
        Wraps an endpoint method to handle parameter validation and sending requests via the client.

        :param instance: The instance of the router.
        :type instance: JarpcClientRouter
        :param method_name: The name of the endpoint method.
        :type method_name: str
        :param request_model: The request model used for validation, if applicable.
        :type request_model: Type[BaseModel] | None
        :param method_signature: The signature of the original method.
        :type method_signature: Signature
        :return: A wrapped asynchronous function that handles parameter validation and makes a request.
        """

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            # Separate parameters for service (prefixed with "_") and clear parameters
            service_kwargs = {k: v for k, v in kwargs.items() if k.startswith("_")}
            clear_kwargs = {k: v for k, v in kwargs.items() if not k.startswith("_")}

            # If a request model is defined, validate and construct request parameters
            if request_model is not None:
                # Initialize parameters with default values from the signature
                args_with_defaults = {
                    param_name: param.default
                    for param_name, param in method_signature.parameters.items()
                }

                # Update default arguments with positional arguments
                for index, value in enumerate(args):
                    param_name = list(method_signature.parameters.keys())[
                        index + 1
                    ]  # Skip "self"
                    args_with_defaults[param_name] = value

                # Merge keyword arguments
                combined_params = {**args_with_defaults, **clear_kwargs}

                # Validate and parse parameters using the model if it's a subclass of BaseModel
                if issubclass(request_model, BaseModel):
                    params = request_model(**combined_params)
                else:
                    # Filter out parameters with no default value or empty value
                    params = {
                        k: v for k, v in combined_params.items() if v is not _empty
                    }
            else:
                # If no model is defined, pass only the clear parameters
                params = {}

            # Make a request using the client, if defined
            if instance._client is not None:
                # Construct the full method name with prefix, if any
                full_method_name = (
                    f"{instance._prefix}.{method_name}" if instance._prefix else method_name
                )

                # Send the request and process the response
                response = await instance._client(
                    method=full_method_name,
                    params=params,
                    **service_kwargs,
                )
                return process_return_value(method_signature.return_annotation, response)
            else:
                # If no client is set, print the call for debugging
                full_method_name = (
                    f"{instance._prefix}.{method_name}" if instance._prefix else method_name
                )
                print("Client is None, call:", full_method_name, params)

        # Provide string representation of the wrapped method name
        def __str__(*args, **kwargs) -> str:
            return f"{instance._prefix}.{method_name}" if instance._prefix else method_name

        # Attach string representation to the wrapped function
        wrapped.__str__ = __str__
        wrapped.__repr__ = __str__

        return wrapped
