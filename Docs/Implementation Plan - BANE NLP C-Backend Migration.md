# Implementation Plan - BANE NLP C-Backend Migration

The goal is to replace the Python-based webhook servers (Flask/aiohttp) with a native C-language backend for maximum throughput and minimal latency.

## User Review Required

> [!WARNING]
> **No C Compiler Detected:** I found no C compiler (`gcc`, `clang`, or `cl.exe`) on your system. To use this backend, you will need to install **MinGW-w64** or **Visual Studio Build Tools**.

> [!IMPORTANT]
> **Hybrid Model:** To maintain AI connectivity (Gemini/NotebookLM), we will keep the AI Pipeline in Python but use the C Backend as the "Gatekeeper" and "Router" for high-frequency requests.

## Proposed Changes

### [NEW] Native C Backend (`backend_c/`)

#### [NEW] [bane_server.c](file:///d:/Bane_NLP/backend_c/bane_server.c)
- Implement a multi-threaded TCP server using **WinSock2**.
- Handle incoming HTTP POST requests (Webhooks) with zero-copy parsing.

#### [NEW] [json_parser.h](file:///d:/Bane_NLP/backend_c/json_parser.h)
- Optimized string-based JSON extraction for Messenger payloads.

#### [NEW] [router_bridge.c](file:///d:/Bane_NLP/backend_c/router_bridge.c)
- Efficiently hand off valid AI tasks to the Python `PipelineEngine` via local socket communication.

## Verification Plan

### Automated Tests
- Once a compiler is installed, compile with: `gcc bane_server.c -o bane_server.exe -lws2_32`
- Run a benchmark using `ab` (Apache Benchmark) to compare Port 5000 (Python) vs Port 8000 (C).

### Manual Verification
- Verify that Messenger webhooks are correctly received by the C server and forwarded to the BANE engine.
