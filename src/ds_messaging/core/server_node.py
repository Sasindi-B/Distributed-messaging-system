import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
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
from src.ds_messaging.time.api import (
    time_handler,
    clock_status_handler,
    sync_trigger_handler,
    timestamp_correct_handler,
    ordering_status_handler,
    force_delivery_handler,
    time_stats_handler,
    reset_stats_handler,
)

from src.ds_messaging.replication.redundancy import RedundancyHandler

ALLOWED_CORS_METHODS = "GET,POST,OPTIONS"
ALLOWED_CORS_HEADERS = "Content-Type,Accept"

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)
    origin = request.headers.get("Origin")
    response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Access-Control-Allow-Methods"] = ALLOWED_CORS_METHODS
    response.headers["Access-Control-Allow-Headers"] = ALLOWED_CORS_HEADERS
    response.headers["Access-Control-Max-Age"] = "86400"
    return response




def make_app(node: Node):
    """
    Build aiohttp app and register routes.
    """
    app = web.Application(middlewares=[cors_middleware])
    app['node'] = node
    app['background_tasks'] = []
    app.add_routes([
        web.post('/send', send_handler),
        web.post('/replicate', replicate_handler),
        web.get('/heartbeat', heartbeat_handler),
        web.post('/request_vote', request_vote_handler),
        web.post('/append_entries', append_entries_handler),
        web.post('/sync', sync_handler),
        web.get('/messages', messages_handler),
        web.get('/status', status_handler),
        web.get('/time', time_handler),
        web.get('/clock', clock_status_handler),
        web.post('/time/sync', sync_trigger_handler),
        web.post('/time/correct', timestamp_correct_handler),
        web.get('/ordering/status', ordering_status_handler),
        web.post('/ordering/force_delivery', force_delivery_handler),
        web.get('/time/stats', time_stats_handler),
        web.post('/time/reset', reset_stats_handler),
    ])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


async def on_startup(app):
    """
    Initialize node DB and start background tasks when app launches.
    """
    node = app['node']
    await node.init_db()

    # Start failure detection
    rejoin_task = asyncio.create_task(rejoin_sync(node))
    heartbeat = asyncio.create_task(heartbeat_task(app))
    app['background_tasks'].extend([rejoin_task, heartbeat])
    # Start consensus timers
    node.consensus = Consensus(node)
    node.consensus.start()

    # Start redundancy catch-up
    redundancy = RedundancyHandler(node)
    redundancy_task = asyncio.create_task(redundancy.catch_up())
    app['background_tasks'].append(redundancy_task)

    # Start periodic time synchronization
    time_sync_task = asyncio.create_task(node.time_sync.sync_task(app))
    app['background_tasks'].append(time_sync_task)


async def on_cleanup(app):
    tasks = app.get('background_tasks', [])
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--peers", default="",
                        help="comma separated peer URLs e.g. http://127.0.0.1:8001")
    parser.add_argument("--replication_mode",
                        choices=['async', 'sync_quorum'], default='async')
    parser.add_argument("--quorum", type=int, default=2)
    return parser.parse_args()


def main():
    args = parse_args()
    peers = [x.strip() for x in args.peers.split(",") if x.strip()]
    node = Node(
        args.host,
        args.port,
        args.id,
        peers,
        replication_quorum=args.quorum,
        replication_mode=args.replication_mode
    )
    app = make_app(node)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()


