import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
import argparse
from aiohttp import web
import asyncio
from src.ds_messaging.core.storage import Node
from src.ds_messaging.failure.heartbeat import heartbeat_task, rejoin_sync
from src.ds_messaging.failure.consensus import Consensus
from src.ds_messaging.failure.api import (
    send_handler, replicate_handler, heartbeat_handler,
    sync_handler, messages_handler, status_handler,
    request_vote_handler, append_entries_handler
)

def make_app(node: Node):
    app = web.Application()
    app['node'] = node
    app.add_routes([
        web.post('/send', send_handler),
        web.post('/replicate', replicate_handler),
        web.get('/heartbeat', heartbeat_handler),
        web.post('/request_vote', request_vote_handler),
        web.post('/append_entries', append_entries_handler),
        web.post('/sync', sync_handler),
        web.get('/messages', messages_handler),
        web.get('/status', status_handler),
    ])
    app.on_startup.append(on_startup)
    return app

async def on_startup(app):
    node = app['node']
    await node.init_db()
    # Fix deprecated loop usage
    asyncio.create_task(rejoin_sync(node))
    asyncio.create_task(heartbeat_task(app))
    # Start consensus timers
    node.consensus = Consensus(node)
    node.consensus.start()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--peers", default="", help="comma separated peer URLs e.g. http://127.0.0.1:8001")
    parser.add_argument("--replication_mode", choices=['async', 'sync_quorum'], default='async')
    parser.add_argument("--quorum", type=int, default=2)
    return parser.parse_args()

def main():
    args = parse_args()
    peers = [x.strip() for x in args.peers.split(",") if x.strip()]
    node = Node(args.host, args.port, args.id, peers, replication_quorum=args.quorum, replication_mode=args.replication_mode)
    app = make_app(node)
    web.run_app(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
