# Pre-defined Transports

If you don't want to write your own transport layer from scratch, you can use the community package `jarpc-clients` which provides ready-to-use transports for HTTP (via `aiohttp` and `requests`) and AMQP (via `cabbage` / `cabbagok`).

## Installation

Install the package directly from the repository (or PyPI if available):

```bash
pip install jarpc-clients
```

Make sure you also install the underlying library required for your chosen transport (e.g., `pip install aiohttp` or `pip install cabbagok`).

## AiohttpTransport (HTTP)

The `AiohttpTransport` sends JSON-RPC requests via HTTP POST. It perfectly matches the asynchronous signature required by `jarpcdantic.JarpcClient`.

```python
import asyncio
from jarpcdantic import JarpcClient
from jarpc_clients.aiohttp_client import AiohttpTransport

async def main():
    # 1. Initialize the transport with the server URL
    transport = AiohttpTransport(url="http://api.example.com/rpc")
    
    # 2. Attach the transport to the Jarpcdantic client
    client = JarpcClient(transport=transport)
    
    # 3. Call remote methods
    result = await client.get_user(user_id=42)
    print(result)

    # Clean up the internal aiohttp session when done
    await transport.close_session()

asyncio.run(main())
```

> [!TIP]
> You can pass additional arguments like `headers`, `ssl`, or `timeout` into the `AiohttpTransport` constructor via `request_kwargs`.

## CabbagokTransport (AMQP / RabbitMQ)

The `CabbagokTransport` sends JSON-RPC requests over RabbitMQ using the `cabbagok` library. This is extremely useful for building microservices that communicate asynchronously.

```python
import asyncio
from jarpcdantic import JarpcClient
from jarpc_clients.cabbagok_client import CabbagokTransport
from cabbagok import AsyncAmqpRpc

async def main():
    # 1. Setup the AMQP RPC connection
    amqp_rpc = AsyncAmqpRpc(amqp_url="amqp://guest:guest@localhost/")
    await amqp_rpc.connect()

    # 2. Initialize the transport
    transport = CabbagokTransport(
        amqp_rpc=amqp_rpc, 
        exchange="my_microservices_exchange"
    )
    
    # 3. Attach it to Jarpcdantic
    client = JarpcClient(transport=transport)
    
    # 4. Call a remote microservice method (the routing key will be the method name)
    result = await client.process_payment(amount=100.50)
    print(result)

asyncio.run(main())
```

## CabbagokServer (AMQP / RabbitMQ Server)

When building the receiving side (the server) over `cabbagok`, you can avoid boilerplate queue binding by using `CabbagokServer`. It automatically subscribes the queue and binds all methods registered in your `jarpcdantic` dispatcher to the RabbitMQ exchange.

```python
import asyncio
from cabbagok import AsyncAmqpRpc
from jarpcdantic import AsyncJarpcManager
from jarpc_clients.cabbagok_server import CabbagokServer

# 1. Define your dispatcher and manager
from my_module import dispatcher
manager = AsyncJarpcManager(dispatcher)

async def main():
    # 2. Setup the AMQP RPC connection
    amqp_rpc = AsyncAmqpRpc(amqp_url="amqp://guest:guest@localhost/")
    await amqp_rpc.run()

    # 3. Setup and start the Server
    server = CabbagokServer(
        amqp_rpc=amqp_rpc,
        manager=manager,
        queue="my_microservices_queue",
        exchange="my_microservices_exchange"
    )
    
    # This will bind all method names in the dispatcher as routing keys
    await server.start()
    
    print("Server is running...")
    
    # Keep running
    while True:
        await asyncio.sleep(3600)

asyncio.run(main())
```

## RequestsTransport (Synchronous HTTP)

`jarpc-clients` also includes a `RequestsTransport` based on the synchronous `requests` library. However, since `jarpcdantic` expects an `awaitable` transport for non-blocking I/O, you should prefer `AiohttpTransport` in async codebases. 

If you absolutely must use the synchronous `RequestsTransport` in `jarpcdantic`, you will need to wrap its execution in `asyncio.to_thread` manually.
