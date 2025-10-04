#!/usr/bin/env python3
"""
Metrics Collection Script for Distributed Messaging System

This script collects comprehensive metrics from all cluster nodes for evaluation
and report generation.

Usage:
    python collect_metrics.py --nodes 8000,8001,8002 --output metrics_report.json
"""

import asyncio
import aiohttp
import argparse
import json
from datetime import datetime
from typing import List, Dict, Any


class MetricsCollector:
    def __init__(self, nodes: List[str]):
        self.nodes = nodes
        self.metrics = {
            "collection_time": None,
            "nodes": {},
            "cluster_summary": {},
            "time_sync_summary": {},
            "consensus_summary": {},
            "replication_summary": {}
        }
    
    async def collect_node_status(self, session: aiohttp.ClientSession, node: str) -> Dict[str, Any]:
        """Collect /status endpoint data from a node"""
        url = f"http://127.0.0.1:{node}/status"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def collect_time_stats(self, session: aiohttp.ClientSession, node: str) -> Dict[str, Any]:
        """Collect /time/stats endpoint data from a node"""
        url = f"http://127.0.0.1:{node}/time/stats"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def collect_ordering_status(self, session: aiohttp.ClientSession, node: str) -> Dict[str, Any]:
        """Collect /ordering/status endpoint data from a node"""
        url = f"http://127.0.0.1:{node}/ordering/status"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def collect_messages(self, session: aiohttp.ClientSession, node: str) -> Dict[str, Any]:
        """Collect /messages endpoint data from a node"""
        url = f"http://127.0.0.1:{node}/messages"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "message_count": len(data.get("messages", [])),
                        "messages": data.get("messages", [])
                    }
                else:
                    return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def collect_all_metrics(self):
        """Collect metrics from all nodes"""
        print("📊 Collecting metrics from cluster...")
        self.metrics["collection_time"] = datetime.now().isoformat()
        
        async with aiohttp.ClientSession() as session:
            for node in self.nodes:
                print(f"   🔍 Querying node {node}...")
                
                # Collect all endpoints in parallel for this node
                status_task = self.collect_node_status(session, node)
                time_task = self.collect_time_stats(session, node)
                ordering_task = self.collect_ordering_status(session, node)
                messages_task = self.collect_messages(session, node)
                
                status, time_stats, ordering, messages = await asyncio.gather(
                    status_task, time_task, ordering_task, messages_task
                )
                
                self.metrics["nodes"][node] = {
                    "status": status,
                    "time_stats": time_stats,
                    "ordering_status": ordering,
                    "messages": messages
                }
        
        # Generate summaries
        self._generate_summaries()
        
        print("✅ Metrics collection complete\n")
    
    def _generate_summaries(self):
        """Generate high-level summaries from collected metrics"""
        
        # Cluster summary
        alive_nodes = 0
        dead_nodes = 0
        leader_id = None
        states = {}
        
        for node, data in self.metrics["nodes"].items():
            status = data.get("status", {})
            if "error" not in status:
                state = status.get("state", "UNKNOWN")
                states[node] = state
                
                if state == "Leader":
                    leader_id = status.get("node_id")
                
                # Count alive peers
                peers = status.get("peers", {})
                for peer_url, peer_info in peers.items():
                    if peer_info.get("alive"):
                        alive_nodes += 1
                    else:
                        dead_nodes += 1
        
        self.metrics["cluster_summary"] = {
            "total_nodes": len(self.nodes),
            "alive_nodes": alive_nodes,
            "dead_nodes": dead_nodes,
            "leader_id": leader_id,
            "node_states": states
        }
        
        # Time sync summary
        clock_offsets = []
        sync_accuracies = []
        drift_rates = []
        
        for node, data in self.metrics["nodes"].items():
            time_stats = data.get("time_stats", {})
            if "error" not in time_stats:
                if "clock_offset" in time_stats:
                    clock_offsets.append(time_stats["clock_offset"])
                if "sync_accuracy" in time_stats:
                    sync_accuracies.append(time_stats["sync_accuracy"])
                if "drift_rate" in time_stats:
                    drift_rates.append(time_stats["drift_rate"])
        
        self.metrics["time_sync_summary"] = {
            "avg_clock_offset": sum(clock_offsets) / len(clock_offsets) if clock_offsets else 0,
            "max_clock_offset": max(clock_offsets) if clock_offsets else 0,
            "avg_sync_accuracy": sum(sync_accuracies) / len(sync_accuracies) if sync_accuracies else 0,
            "avg_drift_rate": sum(drift_rates) / len(drift_rates) if drift_rates else 0
        }
        
        # Consensus summary
        terms = []
        commit_indices = []
        
        for node, data in self.metrics["nodes"].items():
            status = data.get("status", {})
            if "error" not in status:
                consensus = status.get("consensus", {})
                if "current_term" in consensus:
                    terms.append(consensus["current_term"])
                if "commit_index" in status:
                    commit_indices.append(status["commit_index"])
        
        self.metrics["consensus_summary"] = {
            "current_term": max(terms) if terms else 0,
            "term_consistency": len(set(terms)) == 1 if terms else False,
            "avg_commit_index": sum(commit_indices) / len(commit_indices) if commit_indices else 0,
            "commit_index_consistency": len(set(commit_indices)) == 1 if commit_indices else False
        }
        
        # Replication summary
        message_counts = []
        seq_numbers = []
        
        for node, data in self.metrics["nodes"].items():
            messages = data.get("messages", {})
            if "error" not in messages:
                count = messages.get("message_count", 0)
                message_counts.append(count)
                
                # Check sequence consistency
                msgs = messages.get("messages", [])
                if msgs:
                    seq_numbers.append([m.get("seq") for m in msgs])
        
        self.metrics["replication_summary"] = {
            "total_messages": max(message_counts) if message_counts else 0,
            "message_count_consistency": len(set(message_counts)) == 1 if message_counts else False,
            "min_messages": min(message_counts) if message_counts else 0,
            "max_messages": max(message_counts) if message_counts else 0,
            "sequence_consistency": all(seq == seq_numbers[0] for seq in seq_numbers) if seq_numbers else False
        }
    
    def print_report(self):
        """Print human-readable metrics report"""
        print("=" * 70)
        print("📊 CLUSTER METRICS REPORT")
        print("=" * 70)
        
        print(f"\n⏰ Collection Time: {self.metrics['collection_time']}")
        
        # Cluster summary
        cluster = self.metrics["cluster_summary"]
        print(f"\n🖥️  Cluster Summary:")
        print(f"   Total Nodes: {cluster['total_nodes']}")
        print(f"   Alive Nodes: {cluster['alive_nodes']}")
        print(f"   Dead Nodes: {cluster['dead_nodes']}")
        print(f"   Leader: {cluster['leader_id'] or 'None'}")
        print(f"   Node States:")
        for node, state in cluster["node_states"].items():
            print(f"      Port {node}: {state}")
        
        # Time sync summary
        time_sync = self.metrics["time_sync_summary"]
        print(f"\n⏱️  Time Synchronization:")
        print(f"   Average Clock Offset: {time_sync['avg_clock_offset']:.6f}s")
        print(f"   Max Clock Offset: {time_sync['max_clock_offset']:.6f}s")
        print(f"   Average Sync Accuracy: {time_sync['avg_sync_accuracy']:.6f}s")
        print(f"   Average Drift Rate: {time_sync['avg_drift_rate']:.9f}s/s")
        
        # Consensus summary
        consensus = self.metrics["consensus_summary"]
        print(f"\n🗳️  Consensus:")
        print(f"   Current Term: {consensus['current_term']}")
        print(f"   Term Consistency: {'✅ Yes' if consensus['term_consistency'] else '❌ No'}")
        print(f"   Average Commit Index: {consensus['avg_commit_index']:.1f}")
        print(f"   Commit Consistency: {'✅ Yes' if consensus['commit_index_consistency'] else '❌ No'}")
        
        # Replication summary
        replication = self.metrics["replication_summary"]
        print(f"\n📋 Replication:")
        print(f"   Total Messages: {replication['total_messages']}")
        print(f"   Message Count Range: {replication['min_messages']} - {replication['max_messages']}")
        print(f"   Message Count Consistency: {'✅ Yes' if replication['message_count_consistency'] else '❌ No'}")
        print(f"   Sequence Consistency: {'✅ Yes' if replication['sequence_consistency'] else '❌ No'}")
        
        # Per-node details
        print(f"\n📍 Per-Node Details:")
        for node, data in self.metrics["nodes"].items():
            print(f"\n   Node {node}:")
            
            status = data.get("status", {})
            if "error" in status:
                print(f"      ❌ Error: {status['error']}")
                continue
            
            print(f"      State: {status.get('state', 'UNKNOWN')}")
            print(f"      Node ID: {status.get('node_id', 'N/A')}")
            print(f"      Commit Index: {status.get('commit_index', 0)}")
            print(f"      Next Seq: {status.get('next_seq', 0)}")
            
            consensus = status.get("consensus", {})
            print(f"      Term: {consensus.get('current_term', 0)}")
            print(f"      Voted For: {consensus.get('voted_for', 'None')}")
            
            time_stats = data.get("time_stats", {})
            if "error" not in time_stats:
                print(f"      Clock Offset: {time_stats.get('clock_offset', 0):.6f}s")
                print(f"      Sync Accuracy: {time_stats.get('sync_accuracy', 0):.6f}s")
            
            ordering = data.get("ordering_status", {})
            if "error" not in ordering:
                print(f"      Messages Reordered: {ordering.get('messages_reordered', 0)}")
                print(f"      Buffer Size: {ordering.get('buffer_size', 0)}")
            
            messages = data.get("messages", {})
            if "error" not in messages:
                print(f"      Message Count: {messages.get('message_count', 0)}")
        
        print("\n" + "=" * 70)
    
    def save_results(self, filename: str):
        """Save metrics to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        print(f"💾 Metrics saved to {filename}")
    
    def generate_latex_table(self, filename: str):
        """Generate LaTeX table for report"""
        latex = []
        latex.append("\\begin{table}[h]")
        latex.append("\\centering")
        latex.append("\\begin{tabular}{|l|c|c|c|}")
        latex.append("\\hline")
        latex.append("\\textbf{Node} & \\textbf{State} & \\textbf{Commit Index} & \\textbf{Messages} \\\\")
        latex.append("\\hline")
        
        for node, data in self.metrics["nodes"].items():
            status = data.get("status", {})
            messages = data.get("messages", {})
            
            if "error" not in status and "error" not in messages:
                state = status.get("state", "UNKNOWN")
                commit = status.get("commit_index", 0)
                msg_count = messages.get("message_count", 0)
                
                latex.append(f"Port {node} & {state} & {commit} & {msg_count} \\\\")
        
        latex.append("\\hline")
        latex.append("\\end{tabular}")
        latex.append("\\caption{Cluster Node Status}")
        latex.append("\\label{tab:cluster_status}")
        latex.append("\\end{table}")
        
        with open(filename, 'w') as f:
            f.write("\n".join(latex))
        
        print(f"📄 LaTeX table saved to {filename}")


def main():
    parser = argparse.ArgumentParser(description="Collect metrics from distributed messaging cluster")
    parser.add_argument("--nodes", type=str, default="8000,8001,8002",
                        help="Comma-separated list of node ports")
    parser.add_argument("--output", type=str, default="metrics_report.json",
                        help="Output JSON file for metrics")
    parser.add_argument("--latex", type=str,
                        help="Output LaTeX table file for report")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress console output")
    
    args = parser.parse_args()
    
    nodes = args.nodes.split(",")
    
    collector = MetricsCollector(nodes)
    
    # Collect metrics
    asyncio.run(collector.collect_all_metrics())
    
    # Print report
    if not args.quiet:
        collector.print_report()
    
    # Save results
    collector.save_results(args.output)
    
    # Generate LaTeX table if requested
    if args.latex:
        collector.generate_latex_table(args.latex)
    
    return 0


if __name__ == "__main__":
    exit(main())
