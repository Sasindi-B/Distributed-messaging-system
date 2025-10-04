#!/usr/bin/env python3
"""
Load Testing Script for Distributed Messaging System

This script generates synthetic message traffic to measure system throughput,
latency, and behavior under load.

Usage:
    python load_test.py --rate 100 --duration 60 --nodes 8000,8001,8002
"""

import asyncio
import aiohttp
import argparse
import time
import json
import statistics
from typing import List, Dict
from datetime import datetime


class LoadTester:
    def __init__(self, nodes: List[str], rate: int, duration: int):
        self.nodes = nodes
        self.rate = rate  # messages per second
        self.duration = duration  # seconds
        self.results = {
            "sent": 0,
            "succeeded": 0,
            "failed": 0,
            "redirects": 0,
            "latencies": [],
            "errors": [],
            "start_time": None,
            "end_time": None
        }
        
    async def send_message(self, session: aiohttp.ClientSession, msg_id: int, node: str):
        """Send a single message and record metrics"""
        url = f"http://127.0.0.1:{node}/send"
        payload = {
            "msg_id": f"load-test-{msg_id}",
            "sender": "load-tester",
            "recipient": "all",
            "payload": f"Load test message {msg_id} at {time.time()}"
        }
        
        start = time.time()
        try:
            async with session.post(url, json=payload, allow_redirects=False) as resp:
                latency = time.time() - start
                
                if resp.status == 200:
                    self.results["succeeded"] += 1
                    self.results["latencies"].append(latency)
                elif resp.status == 307:
                    # Follow redirect to leader
                    self.results["redirects"] += 1
                    leader_url = resp.headers.get("Location")
                    if leader_url:
                        async with session.post(leader_url, json=payload) as leader_resp:
                            latency = time.time() - start
                            if leader_resp.status == 200:
                                self.results["succeeded"] += 1
                                self.results["latencies"].append(latency)
                            else:
                                self.results["failed"] += 1
                                self.results["errors"].append(f"Leader returned {leader_resp.status}")
                    else:
                        self.results["failed"] += 1
                        self.results["errors"].append("Redirect without Location header")
                else:
                    self.results["failed"] += 1
                    self.results["errors"].append(f"HTTP {resp.status}")
                    
        except Exception as e:
            self.results["failed"] += 1
            self.results["errors"].append(str(e))
            
        self.results["sent"] += 1
        
    async def run_load_test(self):
        """Run the load test for specified duration"""
        print(f"🚀 Starting load test:")
        print(f"   Rate: {self.rate} msg/sec")
        print(f"   Duration: {self.duration} sec")
        print(f"   Nodes: {', '.join(self.nodes)}")
        print()
        
        self.results["start_time"] = datetime.now().isoformat()
        
        # Calculate interval between messages
        interval = 1.0 / self.rate
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            msg_count = 0
            end_time = time.time() + self.duration
            
            while time.time() < end_time:
                # Pick a random node to send to (test load balancing)
                node = self.nodes[msg_count % len(self.nodes)]
                
                # Create task to send message
                task = asyncio.create_task(self.send_message(session, msg_count, node))
                tasks.append(task)
                msg_count += 1
                
                # Status update every 10 seconds
                if msg_count % (self.rate * 10) == 0:
                    print(f"⏱️  {msg_count} messages sent | "
                          f"Success: {self.results['succeeded']} | "
                          f"Failed: {self.results['failed']}")
                
                # Wait for next message interval
                await asyncio.sleep(interval)
            
            # Wait for all tasks to complete
            print("🔄 Waiting for pending requests to complete...")
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.results["end_time"] = datetime.now().isoformat()
        
    def print_report(self):
        """Print detailed test report"""
        print("\n" + "=" * 70)
        print("📊 LOAD TEST REPORT")
        print("=" * 70)
        
        print(f"\n⏰ Test Duration:")
        print(f"   Start: {self.results['start_time']}")
        print(f"   End: {self.results['end_time']}")
        
        print(f"\n📨 Message Statistics:")
        print(f"   Sent: {self.results['sent']}")
        print(f"   Succeeded: {self.results['succeeded']}")
        print(f"   Failed: {self.results['failed']}")
        print(f"   Redirects: {self.results['redirects']}")
        print(f"   Success Rate: {self.results['succeeded'] / self.results['sent'] * 100:.2f}%")
        
        if self.results['latencies']:
            latencies = self.results['latencies']
            print(f"\n⚡ Latency Statistics (seconds):")
            print(f"   Mean: {statistics.mean(latencies):.4f}s")
            print(f"   Median: {statistics.median(latencies):.4f}s")
            print(f"   Min: {min(latencies):.4f}s")
            print(f"   Max: {max(latencies):.4f}s")
            print(f"   Std Dev: {statistics.stdev(latencies):.4f}s")
            
            # Percentiles
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
            
            print(f"\n   Percentiles:")
            print(f"   P50: {p50:.4f}s")
            print(f"   P95: {p95:.4f}s")
            print(f"   P99: {p99:.4f}s")
        
        # Throughput calculation
        actual_duration = len(self.results['latencies']) / self.rate if self.rate > 0 else 0
        throughput = self.results['succeeded'] / self.duration if self.duration > 0 else 0
        
        print(f"\n🚀 Throughput:")
        print(f"   Target Rate: {self.rate} msg/sec")
        print(f"   Actual Rate: {throughput:.2f} msg/sec")
        print(f"   Efficiency: {throughput / self.rate * 100:.2f}%")
        
        if self.results['errors']:
            print(f"\n❌ Error Summary ({len(self.results['errors'])} errors):")
            # Count error types
            error_counts = {}
            for error in self.results['errors']:
                error_counts[error] = error_counts.get(error, 0) + 1
            
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {count}x {error}")
        
        print("\n" + "=" * 70)
        
    def save_results(self, filename: str):
        """Save results to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"💾 Results saved to {filename}")


async def check_cluster_health(nodes: List[str]) -> bool:
    """Check if cluster nodes are reachable"""
    print("🔍 Checking cluster health...")
    async with aiohttp.ClientSession() as session:
        for node in nodes:
            try:
                url = f"http://127.0.0.1:{node}/status"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"   ✅ Node {node}: {data.get('state', 'UNKNOWN')}")
                    else:
                        print(f"   ⚠️  Node {node}: HTTP {resp.status}")
                        return False
            except Exception as e:
                print(f"   ❌ Node {node}: {str(e)}")
                return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Load test for distributed messaging system")
    parser.add_argument("--rate", type=int, default=100,
                        help="Target message rate (msg/sec)")
    parser.add_argument("--duration", type=int, default=60,
                        help="Test duration in seconds")
    parser.add_argument("--nodes", type=str, default="8000,8001,8002",
                        help="Comma-separated list of node ports")
    parser.add_argument("--output", type=str, default="load_test_results.json",
                        help="Output file for results")
    parser.add_argument("--skip-health-check", action="store_true",
                        help="Skip initial cluster health check")
    
    args = parser.parse_args()
    
    nodes = args.nodes.split(",")
    
    # Health check
    if not args.skip_health_check:
        if not asyncio.run(check_cluster_health(nodes)):
            print("❌ Cluster health check failed. Ensure all nodes are running.")
            return 1
        print()
    
    # Run load test
    tester = LoadTester(nodes, args.rate, args.duration)
    
    try:
        asyncio.run(tester.run_load_test())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    
    # Print report
    tester.print_report()
    
    # Save results
    tester.save_results(args.output)
    
    return 0


if __name__ == "__main__":
    exit(main())
