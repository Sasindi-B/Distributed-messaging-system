# Test Procedures for Distributed Messaging System

## Overview

This document provides comprehensive testing procedures for validating all four pillars of the distributed messaging system.

## Prerequisites

- 3 server nodes running (ports 8000, 8001, 8002)
- Dashboard accessible at http://127.0.0.1:5173
- curl or PowerShell available for API testing

---

## 1. Fault Tolerance Testing

### 1.1 Failure Detection Test

**Objective:** Verify heartbeat-based failure detection

**Steps:**
1. Start all 3 nodes
2. Check initial status:
   ```bash
   curl http://127.0.0.1:8000/status
   ```
3. Verify all peers show `"alive": true`
4. Stop node on port 8001 (Ctrl+C)
5. Wait 10 seconds (2x heartbeat interval)
6. Check status again:
   ```bash
   curl http://127.0.0.1:8000/status
   ```
7. Verify peer `http://127.0.0.1:8001` shows `"alive": false`

**Expected Results:**
- Peer marked as dead within 10 seconds
- Remaining nodes continue operating
- Messages can still be sent to alive nodes

### 1.2 Leader Failover Test

**Objective:** Verify automatic leader election after leader failure

**Steps:**
1. Identify current leader:
   ```bash
   curl http://127.0.0.1:8000/status | jq '.consensus.leader_id'
   ```
2. Note the leader's port
3. Stop the leader node
4. Wait 1 second (election timeout range: 300-600ms)
5. Check status on remaining nodes:
   ```bash
   curl http://127.0.0.1:8002/status
   ```
6. Verify new leader elected

**Expected Results:**
- New leader elected within 600ms
- New leader has higher term number
- Followers acknowledge new leader
- System accepts new messages

**Metrics to Collect:**
- Election time: Time from leader failure to new leader election
- Term increment: Should increase by 1
- Vote distribution: Check voted_for on each node

### 1.3 Message Replication Test

**Objective:** Verify message redundancy across nodes

**Steps:**
1. Send a message to leader:
   ```bash
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"sender":"test","recipient":"all","payload":"redundancy test"}'
   ```
2. Query each node for messages:
   ```bash
   curl http://127.0.0.1:8000/messages
   curl http://127.0.0.1:8001/messages
   curl http://127.0.0.1:8002/messages
   ```
3. Verify message appears on all nodes with same sequence number

**Expected Results:**
- Message replicated to all nodes
- Same seq, msg_id, and corrected_ts on all nodes
- Committed_seq increments on all nodes

### 1.4 Node Recovery Test

**Objective:** Verify rejoin synchronization for recovered nodes

**Steps:**
1. Stop node on port 8001
2. Send 10 messages to the cluster:
   ```bash
   for i in {1..10}; do
     curl -X POST http://127.0.0.1:8000/send \
       -H "Content-Type: application/json" \
       -d "{\"payload\":\"msg$i\"}"
   done
   ```
3. Restart node 8001
4. Wait 10 seconds for rejoin sync
5. Check messages on recovered node:
   ```bash
   curl http://127.0.0.1:8001/messages
   ```

**Expected Results:**
- Recovered node catches up within 10 seconds
- All 10 messages present on recovered node
- `last_recovery_time` updated in metrics
- No duplicate messages

**Metrics to Collect:**
- Recovery time: Time from node start to full sync
- Messages recovered: Should match messages sent during downtime
- Sync source: Which peer provided recovery data

---

## 2. Data Replication & Consistency Testing

### 2.1 Quorum Replication Test

**Objective:** Verify quorum-based commit behavior

**Setup:** Ensure nodes started with `--replication_mode sync_quorum --quorum 2`

**Steps:**
1. Start all 3 nodes
2. Send message:
   ```bash
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"payload":"quorum test"}'
   ```
3. Verify response status is "ok" (quorum satisfied)
4. Stop 2 nodes (leaving only 1 alive)
5. Attempt to send another message:
   ```bash
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"payload":"should fail"}'
   ```
6. Verify response is 503 error (quorum not achieved)

**Expected Results:**
- With 2+ nodes: Messages commit successfully
- With 1 node: Messages rejected with 503
- Committed messages remain durable after restart

### 2.2 Deduplication Test

**Objective:** Verify message deduplication by msg_id

**Steps:**
1. Send message with explicit msg_id:
   ```bash
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"msg_id":"test-123","payload":"first"}'
   ```
2. Send same msg_id with different payload:
   ```bash
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"msg_id":"test-123","payload":"duplicate"}'
   ```
3. Query messages:
   ```bash
   curl http://127.0.0.1:8000/messages
   ```
4. Verify only first message is stored

**Expected Results:**
- First message stored successfully
- Second message (same msg_id) ignored silently
- Only one entry with msg_id "test-123" in database

### 2.3 Consistency Verification Test

**Objective:** Verify strong consistency across replicas

**Steps:**
1. Send 50 messages rapidly:
   ```bash
   for i in {1..50}; do
     curl -s -X POST http://127.0.0.1:8000/send \
       -H "Content-Type: application/json" \
       -d "{\"payload\":\"msg$i\"}" &
   done
   wait
   ```
2. Wait for all commits to complete (check commit_index)
3. Query messages from all nodes:
   ```bash
   curl http://127.0.0.1:8000/messages > node0.json
   curl http://127.0.0.1:8001/messages > node1.json
   curl http://127.0.0.1:8002/messages > node2.json
   ```
4. Compare outputs (should be identical)

**Expected Results:**
- All nodes have same number of messages
- Message sequence numbers are identical
- No gaps in sequence numbers
- Same msg_id ordering across all nodes

**Metrics to Collect:**
- Commit latency: Time from send to commit
- Sequence consistency: All nodes agree on seq for each msg_id
- Storage overhead: Database size vs message count

---

## 3. Time Synchronization Testing

### 3.1 Clock Offset Measurement

**Objective:** Verify NTP-style time synchronization

**Steps:**
1. Trigger manual sync on all nodes:
   ```bash
   curl -X POST http://127.0.0.1:8000/time/sync
   curl -X POST http://127.0.0.1:8001/time/sync
   curl -X POST http://127.0.0.1:8002/time/sync
   ```
2. Wait 5 seconds
3. Check time sync stats:
   ```bash
   curl http://127.0.0.1:8000/time/stats
   curl http://127.0.0.1:8001/time/stats
   curl http://127.0.0.1:8002/time/stats
   ```

**Expected Results:**
- Clock offsets < 10ms (local network)
- Sync accuracy < 5ms
- Success rate > 90%
- Drift rate near zero

**Metrics to Collect:**
- Average clock_offset across nodes
- Sync_accuracy per node
- Drift_rate (should be stable over time)

### 3.2 Timestamp Correction Test

**Objective:** Verify timestamp correction for incoming messages

**Steps:**
1. Get current timestamp:
   ```bash
   curl http://127.0.0.1:8000/time
   ```
2. Submit skewed timestamp (e.g., 10 seconds in past):
   ```bash
   curl -X POST http://127.0.0.1:8000/time/correct \
     -H "Content-Type: application/json" \
     -d '{"timestamp":1609459200.0,"sender":"test-node"}'
   ```
3. Check corrected value and accuracy bounds

**Expected Results:**
- Corrected timestamp closer to current time
- Correction_info shows adjustment magnitude
- Accuracy estimate provided

### 3.3 Out-of-Order Message Test

**Objective:** Verify message ordering buffer handles out-of-sequence arrivals

**Steps:**
1. Check initial ordering status:
   ```bash
   curl http://127.0.0.1:8000/ordering/status
   ```
2. Send messages with artificial timestamp skew:
   ```bash
   # Simulate late arrival (old timestamp)
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"ts":1609459200.0,"payload":"late message"}'
   
   # Send current message
   curl -X POST http://127.0.0.1:8000/send \
     -H "Content-Type: application/json" \
     -d '{"payload":"current message"}'
   ```
3. Check ordering buffer:
   ```bash
   curl http://127.0.0.1:8000/ordering/status
   ```
4. Wait 5 seconds (buffer window)
5. Verify messages delivered in corrected timestamp order

**Expected Results:**
- Late messages held in buffer
- Messages delivered in timestamp order
- Reorder count increments
- Buffer utilization tracked

**Metrics to Collect:**
- messages_reordered count
- buffer_utilization percentage
- average_message_age in buffer

---

## 4. Consensus & Agreement Testing

### 4.1 Leader Election Under Load

**Objective:** Measure election performance during high message rate

**Steps:**
1. Start load generator (100 msg/sec):
   ```bash
   python scripts/load_test.py --rate 100 --duration 60
   ```
2. After 10 seconds, kill current leader
3. Observe election time
4. Verify no messages lost during election

**Expected Results:**
- Election completes in < 600ms
- New leader continues message processing
- No gaps in sequence numbers
- All committed messages preserved

**Metrics to Collect:**
- Election time
- Messages lost (should be 0)
- Throughput during election
- Recovery time to normal throughput

### 4.2 Network Partition Test

**Objective:** Verify behavior under network partition

**Setup:** Use firewall rules to simulate partition

**Windows:**
```powershell
# Block traffic to node 8001
netsh advfirewall firewall add rule name="BlockNode8001" dir=out action=block remoteport=8001 protocol=TCP
```

**Linux:**
```bash
# Block traffic to node 8001
sudo iptables -A OUTPUT -p tcp --dport 8001 -j DROP
```

**Steps:**
1. Partition network to isolate one node
2. Send messages to majority partition
3. Verify messages commit successfully
4. Check isolated node status (should step down if leader)
5. Restore network
6. Verify isolated node rejoins and syncs

**Expected Results:**
- Majority partition continues operating
- Isolated node becomes Follower
- After partition heals, isolated node catches up
- No split-brain (two leaders)

**Cleanup:**
```powershell
# Windows
netsh advfirewall firewall delete rule name="BlockNode8001"
```
```bash
# Linux
sudo iptables -D OUTPUT -p tcp --dport 8001 -j DROP
```

### 4.3 Term Increment Test

**Objective:** Verify term management during elections

**Steps:**
1. Check initial term on all nodes:
   ```bash
   curl http://127.0.0.1:8000/status | jq '.consensus.current_term'
   ```
2. Trigger election by stopping leader
3. Check term after election:
   ```bash
   curl http://127.0.0.1:8002/status | jq '.consensus.current_term'
   ```
4. Verify term incremented by exactly 1

**Expected Results:**
- Term increases by 1 per election
- All nodes converge to same term
- Higher term always wins conflicts

### 4.4 Commit Index Propagation Test

**Objective:** Verify followers adopt leader's commit index

**Steps:**
1. Send 10 messages to leader
2. Check commit_index on leader:
   ```bash
   curl http://127.0.0.1:8000/status | jq '.commit_index'
   ```
3. Check commit_index on followers:
   ```bash
   curl http://127.0.0.1:8001/status | jq '.commit_index'
   curl http://127.0.0.1:8002/status | jq '.commit_index'
   ```
4. Verify all nodes have same commit_index

**Expected Results:**
- Followers' commit_index matches leader's
- Propagation occurs within one heartbeat interval (200ms)
- All nodes deliver messages up to commit_index

---

## 5. Integration Testing

### 5.1 End-to-End Message Flow Test

**Objective:** Validate complete message lifecycle

**Steps:**
1. Send message via dashboard
2. Observe in browser console:
   - Send request to follower → 307 redirect
   - Automatic retry to leader → 200 OK
   - Message appears in message log
3. Verify on all nodes via API
4. Check metrics updated correctly

**Expected Results:**
- Seamless leader following in UI
- Message replicated to all nodes
- Metrics reflect operation (latency, corrections)
- Recent deliveries updated

### 5.2 Dashboard Feature Test

**Objective:** Verify all dashboard controls work correctly

**Test Matrix:**

| Feature | Test Action | Expected Result |
|---------|-------------|-----------------|
| Message send | Fill form, submit | Success message, appears in log |
| Message filters | Set sender filter | Only matching messages shown |
| Manual time sync | Click "Trigger Time Sync" | Success box with sync stats |
| Timestamp correction | Submit epoch timestamp | Corrected value with accuracy |
| Ordering status | Click "Fetch Status" | Buffer stats displayed |
| Force delivery | Click "Force Delivery" | Deliverable count updated |
| Auto-refresh toggle | Click "Pause Auto-Refresh" | Polling stops |
| Leader failover | Stop leader, send message | UI switches to new leader |

---

## 6. Performance Testing

### 6.1 Throughput Benchmark

**Objective:** Measure maximum message throughput

**Steps:**
1. Run load test script:
   ```bash
   python scripts/load_test.py --rate 1000 --duration 60
   ```
2. Monitor commit rate via status endpoint
3. Calculate average throughput

**Metrics to Collect:**
- Messages sent per second
- Messages committed per second
- Average commit latency
- CPU and memory usage

**Expected Baseline:**
- 500+ msg/sec on local network
- < 100ms commit latency (quorum mode)
- Linear scaling with additional nodes

### 6.2 Storage Overhead Test

**Objective:** Measure storage efficiency

**Steps:**
1. Send 1000 messages
2. Check database size:
   ```bash
   ls -lh messages.db.*
   ```
3. Calculate overhead: (DB size) / (message count)

**Expected Results:**
- ~1KB per message (including metadata)
- Minimal overhead from indexing
- SQLite compression efficient

---

## 7. Stress Testing

### 7.1 Rapid Leader Changes

**Objective:** Test system stability under frequent elections

**Steps:**
1. Start load (50 msg/sec)
2. Kill leader every 5 seconds
3. Run for 2 minutes
4. Verify message consistency across all nodes

**Expected Results:**
- No message loss
- No sequence gaps
- All nodes converge to same state

### 7.2 Resource Exhaustion

**Objective:** Test behavior under resource constraints

**Steps:**
1. Limit node memory (Docker or cgroups)
2. Send large messages (near limit)
3. Monitor for errors or crashes

**Expected Results:**
- Graceful degradation under pressure
- Error messages logged
- No data corruption

---

## Test Report Template

After running tests, document results:

### Test Summary
- Date: YYYY-MM-DD
- Cluster Configuration: 3 nodes, quorum=2
- Test Duration: X hours
- Test Cases Executed: X/Y passed

### Performance Results
| Metric | Value |
|--------|-------|
| Throughput | X msg/sec |
| Commit Latency (p50) | X ms |
| Commit Latency (p99) | X ms |
| Election Time | X ms |
| Time Sync Accuracy | X ms |
| Recovery Time | X sec |

### Failure Scenarios
- Leader failures: X tests, Y% success
- Network partitions: X tests, Y% success
- Node crashes: X tests, Y% success

### Consistency Verification
- Messages replicated: X/Y (100%)
- Sequence consistency: Pass/Fail
- Deduplication: Pass/Fail

### Issues Found
1. Issue description → Resolution
2. ...

---

## Automated Test Execution

Run all unit tests:
```bash
python -m pytest -v
```

Run integration test suite:
```bash
python scripts/run_integration_tests.py
```

Generate test report:
```bash
python scripts/generate_test_report.py --output report.pdf
```

---

## Continuous Testing

For long-running stability tests:
1. Start cluster
2. Run chaos monkey:
   ```bash
   python scripts/chaos_monkey.py --duration 3600
   ```
3. Monitor for crashes or inconsistencies
4. Generate final report

---

**End of Test Procedures**
