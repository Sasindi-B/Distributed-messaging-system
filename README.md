# Distributed Messaging System

**A Fault-Tolerant Distributed Messaging Platform with Raft Consensus**

## Team Members

| Name | Registration Number | Email | Responsibility |      
|-|-----|---------------------|-------|----------------|
| Member 1 | IT23651456 | IT23651456@my.sliit.lk | Fault Tolerance |
| Member 2 | IT23749498 | IT23749498@my.sliit.lk | Data Replication & Consistency |
| Member 3 | IT23736832 | IT23736832@my.sliit.lk | Time Synchronization |
| Member 4 | IT23664708 | IT23664708@my.sliit.lk | Consensus & Agreement |

## Project Overview

This is a production-grade distributed messaging system implementing industry-standard fault tolerance patterns. The system ensures **high availability**, **strong consistency**, and **real-time message delivery** across multiple server nodes, designed to handle failures gracefully while maintaining data integrity.

### Architecture

Built with Python and AIOHTTP, the system features:

- **Raft consensus** for distributed coordination and leader election
- **NTP-style time synchronization** for accurate message ordering
- **Quorum-based replication** with configurable consistency models
- **Automatic failure detection and recovery**
- **Real-time React dashboard** for monitoring and control

### Core Features

✅ **Fault Tolerance**
- Message redundancy with configurable replication factor
- Heartbeat-based failure detection (5-second intervals)
- Automatic leader failover with sub-second election times
- Rejoin synchronization for recovered nodes

✅ **Data Replication & Consistency**
- Primary-backup and quorum-based strategies
- Strong consistency via Raft commit indices
- Message deduplication by unique IDs
- Optimized retrieval with SQLite indexing

✅ **Time Synchronization**
- NTP-style clock synchronization across peers
- Clock skew analysis and drift rate tracking
- Out-of-order message reordering with configurable buffers
- Timestamp correction with accuracy bounds


✅ **Consensus & Agreement**
- Full Raft implementation (elections, log replication, commits)
- Randomized election timeouts (300-600ms)
- Batched append entries for efficiency
- Persistent state storage in SQLite


## Quick Start

## Quick Start

### Prerequisites

- **Python 3.11+** (Python 3.13 recommended)
- **pip** package manager
- **Windows PowerShell** or **Linux/macOS terminal**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Sasindi-B/Distributed-messaging-system.git
   cd Distributed-messaging-system
   ```

2. **Create and activate virtual environment**
   
   **Windows:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   
   **Linux/macOS:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install aiohttp aiosqlite pytest
   ```

### Running the Cluster

Start a 3-node cluster with each command in a separate terminal:

**Terminal 1 (Node 0 - Port 8000):**
```bash
python -m src.ds_messaging.core.server_node --host 127.0.0.1 --port 8000 --id nodeA --peers http://127.0.0.1:8001,http://127.0.0.1:8002 --replication_mode sync_quorum --quorum 2
```

**Terminal 2 (Node 1 - Port 8001):**
```bash
python -m src.ds_messaging.core.server_node --host 127.0.0.1 --port 8001 --id nodeB --peers http://127.0.0.1:8000,http://127.0.0.1:8002 --replication_mode sync_quorum --quorum 2
```

**Terminal 3 (Node 2 - Port 8002):**
```bash
python -m src.ds_messaging.core.server_node --host 127.0.0.1 --port 8002 --id nodeC --peers http://127.0.0.1:8000,http://127.0.0.1:8001 --replication_mode sync_quorum --quorum 2
```

### Starting the Dashboard

In a new terminal:
```bash
cd frontend
python -m http.server 5173
```

Open **http://127.0.0.1:5173** in your browser.

## System Architecture

### Components

#### 1. Server Nodes (`src/ds_messaging/core/`)
- **server_node.py**: Main server entry point with AIOHTTP web application
- **storage.py**: SQLite-based message persistence and retrieval
- **message.py**: Message data structures
- **client.py**: Failover-aware client for automatic leader following

#### 2. Fault Tolerance (`src/ds_messaging/failure/`)
- **detector.py**: Heartbeat-based failure detection
- **heartbeat.py**: Periodic health checks and rejoin synchronization
- **replication.py**: Async and quorum-based message replication
- **consensus.py**: Raft consensus implementation (elections, log replication)
- **api.py**: REST endpoints for message send/receive and consensus RPCs

#### 3. Time Synchronization (`src/ds_messaging/time/`)
- **sync_protocol.py**: NTP-style time synchronization
- **clock_skew.py**: Clock drift analysis and monitoring
- **ordering.py**: Message ordering buffer for out-of-sequence arrivals
- **api.py**: Time-related REST endpoints

#### 4. Replication Management (`src/ds_messaging/replication/`)
- **redundancy.py**: Catch-up synchronization for rejoining nodes
- **manager.py**: Replication coordination

#### 5. Frontend (`frontend/`)
- **index.html**: Dashboard entry point
- **app.js**: React components for cluster monitoring
- **styles.css**: Modern UI styling

### Data Flow

```
Client → Leader Node → Raft Consensus → Quorum Replication → Commit
                    ↓
            Timestamp Correction
                    ↓
            Ordering Buffer
                    ↓
            SQLite Storage
                    ↓
            Available for Retrieval
```

## API Reference

## API Reference

### Message Operations

**Send Message**
```bash
POST /send
Content-Type: application/json

{
  "sender": "producer-A",
  "recipient": "consumer-B",
  "payload": "Hello distributed world",
  "msg_id": "unique-id-123"  # optional, auto-generated if omitted
}

Response: { "status": "ok", "seq": 42, "msg_id": "...", "corrected_ts": ... }
```

**Get Messages**
```bash
GET /messages?limit=50&after=10&sender=producer-A&recipient=consumer-B

Response: { "messages": [...], "next_after": 60 }
```

**Replicate Message** (internal)
```bash
POST /replicate
{ "msg": { ... } }
```

### Cluster Status

**Node Status**
```bash
GET /status

Returns:
{
  "node_id": "nodeA",
  "port": 8000,
  "peers": [...],
  "peer_status": { "http://127.0.0.1:8001": { "alive": true, "last_ok": 1234567890 } },
  "replication_mode": "sync_quorum",
  "quorum": 2,
  "committed_seq": 100,
  "commit_index": 100,
  "consensus": {
    "role": "Leader",
    "current_term": 5,
    "leader_id": "nodeA",
    "leader_url": "http://127.0.0.1:8000"
  },
  "metrics": {
    "average_store_latency": 0.002,
    "average_correction_magnitude": 0.0001,
    "last_recovery_time": 1234567890
  },
  "recent_deliveries": [...]
}
```

### Time Synchronization

**Get Time**
```bash
GET /time

Returns: { "server_receive_time": ..., "synchronized_time": ..., "clock_offset": ... }
```

**Manual Sync**
```bash
POST /time/sync

Triggers immediate time synchronization with peers
```

**Correct Timestamp**
```bash
POST /time/correct
{ "timestamp": 1234567890.123, "sender": "node-id" }

Returns corrected timestamp with accuracy bounds
```

**Time Statistics**
```bash
GET /time/stats

Comprehensive time sync metrics and drift analysis
```

### Message Ordering

**Ordering Status**
```bash
GET /ordering/status

Returns buffer utilization, reorder counts, deliverable messages
```

**Force Delivery**
```bash
POST /ordering/force_delivery

Emergency operation to deliver all buffered messages
```

### Consensus RPCs (Internal)

**Request Vote**
```bash
POST /request_vote
{ "term": 5, "candidate_id": "nodeA", "last_log_index": 100, "last_log_term": 4 }
```

**Append Entries**
```bash
POST /append_entries
{ "term": 5, "leader_id": "nodeA", "prev_log_index": 99, "entries": [...], "leader_commit": 100 }
```

## Configuration Options

### Server Node Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--host` | string | `127.0.0.1` | Host IP address to bind |
| `--port` | int | **required** | Port number for the server |
| `--id` | string | **required** | Unique node identifier |
| `--peers` | string | `""` | Comma-separated peer URLs |
| `--replication_mode` | choice | `async` | `async` or `sync_quorum` |
| `--quorum` | int | `2` | Minimum replicas for quorum commit |

### Replication Modes

- **async**: Fire-and-forget replication for maximum throughput
- **sync_quorum**: Wait for quorum acknowledgment before commit (strong consistency)

### Consensus Parameters (Code Configuration)

- **Election timeout**: 300-600ms (randomized)
- **Heartbeat interval**: 200ms
- **Time sync interval**: 30 seconds
- **Ordering buffer window**: 5 seconds
- **Heartbeat check interval**: 5 seconds

## Testing

### Running Unit Tests

```bash
python -m pytest
```

**Current Test Coverage:**
- ✅ Consensus: RequestVote, AppendEntries, term updates
- ✅ Timestamp correction: basic, sender-specific, edge cases
- ✅ Message ordering: buffer operations, reordering, delivery

### Manual Testing Procedures

See `docs/TEST_PROCEDURES.md` for detailed failure scenario testing.

### Load Testing

Use `scripts/load_test.py` to generate synthetic traffic and measure performance.

## Dashboard Features

The React frontend provides real-time monitoring and control:

### Monitoring Panels
- **Node Overview**: ID, host, port, role, term, leader URL
- **Peer Health**: Live/dead status, last heartbeat time
- **Delivery Metrics**: Average latency, timestamp corrections, recovery times
- **Time Sync Status**: Clock offset, accuracy, drift rate, peer offsets
- **Recent Deliveries**: Last 5 messages with corrected timestamps
- **Message Log**: Paginated, filterable by sender/recipient/sequence

### Interactive Controls
- **Message Filters**: Limit, after sequence, sender, recipient
- **Manual Time Sync**: Trigger immediate peer synchronization
- **Timestamp Correction**: Submit timestamps for correction analysis
- **Ordering Buffer**: View buffer status, force delivery of pending messages
- **Auto-refresh**: Toggleable polling (3.5s intervals)

### Leader Following
The dashboard automatically detects follower nodes and redirects send requests to the current leader, updating the base URL transparently.

## Implementation Highlights

### 1. Fault Tolerance

**Failure Detection:**
- Heartbeat-based monitoring every 5 seconds
- Exponential backoff for unreachable peers
- Automatic peer status updates

**Redundancy:**
- Configurable replication factor
- Async (eventual consistency) or quorum (strong consistency)
- Deduplication via unique message IDs

**Recovery:**
- `rejoin_sync` pulls missing messages on reconnection
- Catch-up from any available peer
- Recovery timestamp tracking

### 2. Data Replication

**Strategies:**
- **Primary-backup**: Leader coordinates all writes
- **Quorum-based**: Wait for majority acknowledgment

**Consistency:**
- Strong consistency via Raft commit indices
- Read-your-writes guarantees after quorum commit
- Follower commit index adoption from leader heartbeats

**Optimization:**
- SQLite indexes on sender, recipient, sequence
- Efficient pagination with `LIMIT` and `OFFSET`
- `INSERT OR IGNORE` for zero-overhead deduplication

### 3. Time Synchronization

**NTP-Style Protocol:**
- Four-timestamp exchange with peers
- Median offset calculation for robustness
- Network delay compensation

**Clock Skew Analysis:**
- Linear regression for drift rate estimation
- Predicted offset for proactive correction
- Acceptable threshold monitoring

**Message Ordering:**
- Configurable buffer window (default 5s)
- Delivers messages in timestamp order
- Force delivery option for emergency scenarios

### 4. Consensus & Agreement

**Raft Implementation:**
- Persistent state (term, voted_for, log) in SQLite
- Leader election with randomized timeouts
- Log replication with batch append entries
- Commit index propagation via heartbeats

**Optimizations:**
- Timeout-aware HTTP clients
- Efficient serialization (JSON)
- Background task coordination

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Election time | 300-600ms |
| Heartbeat interval | 200ms |
| Message commit latency (quorum) | ~50-100ms (local network) |
| Time sync accuracy | <10ms (typical) |
| Throughput | ~500+ msg/sec (3-node cluster) |
| Storage overhead | Minimal (SQLite, ~1KB per message) |

## Troubleshooting

## Troubleshooting

### Common Issues

**"python not found"**
- Install Python 3.11+ from python.org
- On Windows, uncheck "App execution aliases" in Windows Settings
- Restart terminal after installation

**"Module not found: aiohttp"**
```bash
pip install aiohttp aiosqlite
```

**"Import error for src.*"**
- Ensure you're running from the repository root directory
- Or set PYTHONPATH: `export PYTHONPATH=/path/to/repo` (Linux) or `$env:PYTHONPATH="C:\path\to\repo"` (PowerShell)

**"Address already in use"**
- Another process is using the port
- Use different ports: `--port 8100 --peers http://127.0.0.1:8101,...`

**"No leader elected"**
- Ensure at least 2 nodes are running (quorum of 3 requires 2 nodes)
- Check network connectivity between peers
- Verify peer URLs are correct and reachable

**"Messages not appearing"**
- Check if sending to a follower: it should redirect to leader (307)
- Verify quorum is satisfied (2 out of 3 nodes alive for quorum=2)
- Check `/status` for commit_index progression

### Logs

All nodes log to console with timestamps. Look for:
- `INFO` messages for normal operations
- `WARNING` for recoverable issues (peer failures, sync errors)
- `ERROR` for critical problems

### Debug Mode

Set log level in `src/ds_messaging/core/server_node.py`:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Project Structure

```
Distributed-messaging-system/
├── src/
│   └── ds_messaging/
│       ├── core/               # Core server logic
│       │   ├── server_node.py  # Main entry point
│       │   ├── storage.py      # SQLite persistence
│       │   ├── message.py      # Data structures
│       │   └── client.py       # Failover client
│       ├── failure/            # Fault tolerance
│       │   ├── api.py          # REST endpoints
│       │   ├── consensus.py    # Raft implementation
│       │   ├── detector.py     # Failure detection
│       │   ├── heartbeat.py    # Health monitoring
│       │   └── replication.py  # Message replication
│       ├── time/               # Time synchronization
│       │   ├── api.py          # Time endpoints
│       │   ├── sync_protocol.py# NTP-style sync
│       │   ├── clock_skew.py   # Drift analysis
│       │   └── ordering.py     # Message ordering
│       └── replication/        # Replication management
│           └── redundancy.py   # Catch-up sync
├── tests/                      # Unit tests
│   ├── test_consensus.py
│   ├── test_timestamp_corrector.py
│   └── test_ordering_buffer.py
├── frontend/                   # React dashboard
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── vendor/                 # React libraries
├── scripts/                    # Helper scripts
│   ├── load_test.py
│   └── collect_metrics.py
├── docs/                       # Documentation
│   └── TEST_PROCEDURES.md
├── pyproject.toml             # Project metadata
└── README.md                  # This file
```


