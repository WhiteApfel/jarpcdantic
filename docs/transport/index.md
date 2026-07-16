# Transport Layer Overview

JSON-RPC 2.0 is a transport-agnostic protocol. It defines the structure of the data (the JSON payload), but it does not dictate how that data gets from the client to the server.

Because of this, `jarpcdantic` is completely decoupled from the transport layer. You can use it over HTTP, WebSockets, AMQP (RabbitMQ), raw TCP sockets, or even standard input/output.

## How it works

In `jarpcdantic`, the framework's job is simply to transform native Python calls into JSON strings, and JSON strings back into Python objects. 

The actual transmission of the string is handled by a **Transport Function** that you provide to the `JarpcClient` (on the client side) or the integration hook you write for your web server (on the server side).

- [Pre-defined Transports](predefined.md): Use ready-made transports from the community.
- [Writing a Custom Transport](custom.md): Learn how to write your own transport adapter for any network protocol.
