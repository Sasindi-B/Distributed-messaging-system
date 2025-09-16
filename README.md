# Distributed-messaging-system
Fault-tolerant distributed messaging system

📖 Project Overview

The Distributed Messaging System is a prototype implementation of a fault-tolerant, scalable, and modular messaging platform built using Python, FastAPI, ZooKeeper, and React.

It is designed to simulate the core principles of real-world distributed messaging frameworks (like Kafka, RabbitMQ), while keeping the implementation simple and educational.

✨ Key Highlights

Producers can publish messages to specific topics.

Consumers can fetch messages from those topics.

ZooKeeper handles coordination tasks such as service discovery, configuration management, and leader election.

Backend (FastAPI) exposes REST APIs for producers and consumers to interact with the system.

Frontend (React) provides a user-friendly interface for sending and viewing messages.

Docker Compose ensures the entire system (backend, frontend, ZooKeeper) can be run with a single command.

🎯 Goals

Learn and demonstrate fault tolerance in distributed systems.

Understand the role of ZooKeeper in distributed coordination.

Build a lightweight message broker with a Python backend.

Provide a minimal UI for interaction without requiring CLI commands.

Encourage teamwork using GitHub workflows (branches, commits, pull requests).
🛠 Development Workflow

Branching

main → stable version

dev → active development

feature branches: feature/<name>
