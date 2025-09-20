

# Distributed Messaging System

A fault-tolerant distributed messaging system prototype demonstrating core principles of distributed systems like replication, failure detection, and quorum-based consistency.


## Getting Started

### Prerequisites

*   Python 3.7+
*   `aiohttp` library (install with `pip install aiohttp`)

### Running the Nodes

The system is composed of multiple nodes. **Each node must be run in its own terminal window.**

**Terminal 1 - Node 1 (Port 8000):**
```bash
python -m src.ds_messaging.core.server_node --port 8000 --id node1 --peers "http://127.0.0.1:8001,http://127.0.0.1:8002"
```

**Terminal 2 - Node 2 (Port 8001):**
```bash
python -m src.ds_messaging.core.server_node --port 8001 --id node2 --peers "http://127.0.0.1:8000,http://127.0.0.1:8002"
```

**Terminal 3 - Node 3 (Port 8002):**
```bash
python -m src.ds_messaging.core.server_node --port 8002 --id node3 --peers "http://127.0.0.1:8000,http://127.0.0.1:8001"
```

**Terminal 4 - Node 4 (Port 8003 - Quorum Node):**
*(Wait for the first three nodes to start before running this one)*
```bash
python -m src.ds_messaging.core.server_node --port 8003 --id node4 --peers "http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002" --replication_mode sync_quorum --quorum 3
```

## Testing the System

We provide a Postman collection to test all fault tolerance features.

### Importing the Postman Collection

1.  **Locate the Collection File:** The collection is in `docs/postman/Fault_tolerence.postman_collection.json`.
2.  **Import into Postman:**
    - Open Postman and click the **Import** button.
    - Drag and drop the `.json` file or select it via "Upload Files".
    - Click **Import**.

### Running the Tests

1.  **Start all the nodes** [as described above](#running-the-nodes).
2.  In Postman, find the imported collection: **"Distributed Messaging System - Fault Tolerance Tests"**.
3.  Click the **Run** button to open the Collection Runner.
4.  Click **Start Fault tolerence** to run the entire test suite.

The tests will execute in order, simulating a complete scenario:
1.  **Health Check:** Verify all nodes are running.
2.  **Basic Operations:** Send a message and verify it replicates.
3.  **Failure Detection:** Simulate a node failure, send a message, and verify recovery.
4.  **Quorum Testing:** Test synchronous replication with quorum requirements.

## API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/send` | POST | Send a new message to the system |
| `/replicate` | POST | (Internal) Directly replicate a message to this node |
| `/heartbeat` | GET | Check if the node is alive |
| `/messages` | GET | Retrieve all messages stored on this node |
| `/status` | GET | Get detailed status of the node (id, peers, mode, etc.) |
| `/sync` | POST | Synchronize messages from a given sequence number |


