import argparse
from aiohttp import web
from storage import Node
from api import send_handler, replicate_handler, heartbeat_handler, sync_handler, messages_handler
from heartbeat import heartbeat_task, rejoin_sync

def make_app(node: Node):
    app = web.Application()
    app['node'] = node
    app.add_routes([
        web.post('/send', send_handler),
        web.post('/replicate', replicate_handler),
        web.get('/heartbeat', heartbeat_handler),
        web.post('/sync', sync_handler),
        web.get('/messages', messages_handler),
    ])
    app.on_startup.append(on_startup)
    return app

async def on_startup(app):
    node = app['node']
    await node.init_db()
    app.loop.create_task(rejoin_sync(node))
    app.loop.create_task(heartbeat_task(app))

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
