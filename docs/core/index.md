# Core components

This page provides an overview of the primary components that form the foundation of the jarpcdantic library. 
These components work together to facilitate JARPCdantic communications 
with strong type validation provided by Pydantic. For a high-level introduction to the library, see Overview.

## System Architecture

The JARPCdantic library consists of several interconnected components that handle different aspects 
of the RPC communication process. The following diagram illustrates these core components and their relationships:

## Component Overview

```mermaid
flowchart LR
    subgraph Core Components
        C[AsyncJarpcClient]
        M[AsyncJarpcManager]
        R[JarpcClientRouter]
        D[Data Models<br/>JarpcRequest / JarpcResponse]
        H[Error Handling<br/>JarpcError hierarchy]
        DP[JarpcDispatcher]
    end

    TL[Transport Layer]:::external
    U[Utility Functions]:::external

    C -->|creates requests| D
    M -->|processes requests| D
    D -->|passed between| M
    D -->|passed between| C
    C -->|uses| TL
    R -->|uses| C
    TL -->|delivers to| M
    M -->|uses| DP
    M -->|uses| U
    H -->|used by| C
    H -->|used by| M

```