# Meta & Context Variables

In distributed RPC systems, you often need to pass implicit metadata alongside your actual payload. For instance:
- Tracing IDs (e.g. OpenTelemetry spans)
- Authentication tokens
- User IP addresses
- Locale or language preferences

`jarpcdantic` provides a robust, asynchronous-safe mechanism for managing metadata via Python's `contextvars` and the JSON-RPC `meta` extension.

## 1. Passing Meta from the Client

When making a request, you can pass a `meta` dictionary to the client call. 

```python
result = await client.get_user_profile(
    user_id=123, 
    meta={"auth_token": "Bearer abc123def456"}
)
```

The client will automatically inject this `meta` dictionary into the JSON-RPC payload, making it available for the transport layer and the remote server.

## 2. Using `meta_context_var`

If you are calling multiple RPC methods and don't want to explicitly pass the `meta` dictionary every time, you can use `meta_context_var`. 

This is highly useful in middleware or when handling incoming web requests (e.g., in a FastAPI middleware) to ensure that downstream RPC calls automatically inherit the context.

```python
from jarpcdantic.context import meta_context_var

async def handle_http_request(request):
    # Set the token for the current asyncio task context
    token = request.headers.get("Authorization")
    
    # Get existing context or create a new one
    ctx = meta_context_var.get({})
    ctx["auth_token"] = token
    meta_context_var.set(ctx)
    
    # Now any client call made in this task will implicitly include the auth_token!
    result = await client.get_user_profile(user_id=123)
    return result
```

## 3. Reading Meta on the Server

On the server side, handlers can access the metadata via the special `_meta` keyword argument, or through `jarpc_request` to access the full request.

```python
from jarpcdantic import JarpcDispatcher

dispatcher = JarpcDispatcher()

@dispatcher.rpc_method
async def get_user_profile(user_id: int, _meta: dict):
    token = _meta.get("auth_token")
    if not token:
        raise Exception("Unauthorized")
        
    return {"user": user_id, "status": "active"}
```

You can also use a Server Middleware to validate `meta` globally before it even reaches the handler!
