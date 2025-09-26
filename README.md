# Distributed-messaging-system

Fault-tolerant distributed messaging system

## Project Overview

The Distributed Messaging System is a prototype implementation of a fault-tolerant, scalable, and modular messaging platform built using Python, FastAPI, ZooKeeper, and React.

It is designed to simulate the core principles of real-world distributed messaging frameworks (like Kafka, RabbitMQ), while keeping the implementation simple and educational.

## Key Highlights

- Producers can publish messages to specific topics.
- Consumers can fetch messages from those topics.
- Backend (FastAPI) exposes REST APIs for producers and consumers to interact with the system.
- Frontend (React) provides a user-friendly interface for sending and viewing messages.
- Docker Compose ensures the entire system (backend, frontend, ZooKeeper) can be run with a single command.

## Goals

- Learn and demonstrate fault tolerance in distributed systems.
- Understand the role of ZooKeeper in distributed coordination.
- Build a lightweight message broker with a Python backend.
- Provide a minimal UI for interaction without requiring CLI commands.
- Encourage teamwork using GitHub workflows (branches, commits, pull requests).

## Development Workflow

- Branching
  - main — stable version
  - dev — active development
  - feature branches: `feature/<name>`

## Local AIOHTTP Cluster + Consensus

This repo includes a lightweight AIOHTTP-based messaging cluster with Raft-style leader election layered on top of the existing failure detector. It runs locally without ZooKeeper or Docker.

Requirements

- Python 3.11+ (Windows users: disable "App execution aliases" for python/python3 if needed)
- Packages: `aiohttp`, `aiosqlite`

Setup

- Create venv: `python -m venv .venv` and activate (`.\\.venv\\Scripts\\Activate.ps1` on Windows)
- Install deps: `python -m pip install aiohttp aiosqlite`

Run 3 nodes (each in its own terminal)

- Node 8000: `python -m src.ds_messaging.core.server_node --host 127.0.0.1 --port 8000 --id n0 --peers http://127.0.0.1:8001,http://127.0.0.1:8002 --replication_mode async --quorum 2`
- Node 8001: `python -m src.ds_messaging.core.server_node --host 127.0.0.1 --port 8001 --id n1 --peers http://127.0.0.1:8000,http://127.0.0.1:8002 --replication_mode async --quorum 2`
- Node 8002: `python -m src.ds_messaging.core.server_node --host 127.0.0.1 --port 8002 --id n2 --peers http://127.0.0.1:8000,http://127.0.0.1:8001 --replication_mode async --quorum 2`

Consensus (Raft)

- Roles/term: each node tracks `Follower | Candidate | Leader`, `current_term`, `voted_for` (persisted in SQLite)
- Elections: randomized 300–600ms timeout; candidates broadcast `RequestVote`
- Heartbeats: leaders send `AppendEntries` every 200ms; followers reset election timers
- Step-down: any RPC with higher term causes demotion to Follower

Useful endpoints

- `GET /status` → node, peers, failure-detector state, and consensus `{role, term, leader}`
- `POST /send` → send a message; replicates to peers (async or quorum mode)
- `GET /messages` → list stored messages
- `POST /sync` → pull messages since a sequence
- Consensus RPCs (internal): `POST /request_vote`, `POST /append_entries`

Quick test

- Status: `curl http://127.0.0.1:8000/status`
- Send: `curl -X POST http://127.0.0.1:8000/send -H "Content-Type: application/json" -d "{\"payload\":\"hi\"}"`
- Read: `curl http://127.0.0.1:8001/messages`
  go up \to 5 nodes

Troubleshooting

- "python not found" → install Python 3.11/3.12; uncheck Windows Store alias; reopen terminal
- aiosqlite/aiohttp missing → `python -m pip install aiohttp aiosqlite`
- Import error for `src.*` → run from repo root or set `PYTHONPATH` to the repo root
