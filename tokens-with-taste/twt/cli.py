import argparse
import asyncio
import json
import sqlite3
from datetime import UTC, datetime

import httpx

from .audit import inspect_trace, report
from .catalog import catalog_models, configured_providers, sync
from .store import Store


def since_date(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
    except ValueError as error:
        raise argparse.ArgumentTypeError("--since expects an ISO date or timestamp") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description="TokensWithTaste local proxy and audit")
    parser.add_argument("--db", help="SQLite path (default: TWT_DB or ~/.local/share/twt/catalog.sqlite3)")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    commands.add_parser("sync")
    models = commands.add_parser("models")
    models.add_argument("--free", action="store_true")
    models.add_argument("--tools", action="store_true")
    audit = commands.add_parser("audit")
    audit.add_argument("--flagged", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("trace_id")
    summary = commands.add_parser("report")
    summary.add_argument("--since", type=since_date)
    args = parser.parse_args(argv)
    store = Store(args.db)
    try:
        if args.command == "serve":
            import uvicorn

            from .gateway import create_app
            uvicorn.run(create_app(store=store), host="127.0.0.1", port=args.port)
        elif args.command == "sync":
            try:
                print("\n".join(asyncio.run(sync(store))))
            except (httpx.HTTPError, OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
                parser.exit(1, f"Catalog sync failed ({type(error).__name__}: {error}); existing catalog retained.\n")
        elif args.command == "models":
            rows = [m for m in catalog_models(store, configured_providers()) if m["chat"] and (not args.free or m["free"])
                    and (not args.tools or m["tools"])]
            print("PROVIDER\tMODEL\tFREE\tTOOLS\tJSON\tCONTEXT\tRPM\tINPUT_USD/TOKEN\tOUTPUT_USD/TOKEN")
            for m in rows:
                print("\t".join(str(m[key]) for key in ("provider", "id", "free", "tools", "json", "context_length", "rpm", "input_price", "output_price")))
            print(f"{len(rows)} models")
        elif args.command == "audit":
            for trace in store.traces():
                if not args.flagged or trace["flags"]:
                    print(json.dumps({key: trace[key] for key in ("trace_id", "timestamp", "provider", "model", "cost_usd", "flags")}))
        elif args.command == "inspect":
            trace = store.trace(args.trace_id)
            if trace is None:
                parser.exit(1, "Trace not found\n")
            print(inspect_trace(trace))
        elif args.command == "report":
            print(json.dumps(report(store.traces(args.since)), indent=2))
    finally:
        store.close()
