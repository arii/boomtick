"""Core CLI group, shared options, and output helpers."""
import json
import sys
import click
from dev_tools.utils import mask_sensitive_data


class LazyOrchestrator:
    """Lazy proxy for the Orchestrator to defer heavy imports and initialization."""

    def __init__(self, factory):
        # Use super().__setattr__ to avoid recursion during initialization
        super().__setattr__("_factory", factory)
        super().__setattr__("_instance", None)

    def _get_instance(self):
        if self._instance is None:
            super().__setattr__("_instance", self._factory())
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    def __setattr__(self, name, value):
        if name in ("_instance", "_factory"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_instance(), name, value)

    def __dir__(self):
        return dir(self._get_instance())


DEFAULT_GH_API_LIMIT = 10


def limit_option(default_val=DEFAULT_GH_API_LIMIT, help_text="Limit the number of items to process"):
    """Click decorator adding a --limit option."""
    def decorator(f):
        return click.option("--limit", type=int, default=default_val, help=help_text)(f)

    return decorator


def json_option(f):
    """
    Decorator to add --json option to subcommands.
    Allows --json to be placed after the command (e.g., 'td command --json').
    Automatically updates ctx.obj['JSON'] if the option is provided.
    """
    import functools

    f = click.option("--json/--no-json", "json_output", default=None, help="Output results in JSON format")(f)

    @click.pass_context
    @functools.wraps(f)
    def wrapper(ctx, *args, **kwargs):
        json_output = kwargs.pop("json_output", None)
        if json_output is not None and ctx.obj is not None:
            ctx.obj["JSON"] = json_output
        return ctx.invoke(f, *args, **kwargs)

    return wrapper


CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "ignore_unknown_options": True,
    "allow_extra_args": True,
}


# CLI Group


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("--json/--no-json", "json_output", default=True, help="Output results in JSON format")
@click.option("--no-cache", is_flag=True, default=False, help="Bypass the disk cache for GitHub API calls")
@click.pass_context
def cli(ctx, json_output, no_cache):
    """Unified Tech-Dancer DevTools CLI"""
    ctx.ensure_object(dict)

    # If the user explicitly passed --no-json (if supported) or we want to detect if it's a TTY
    # But for now, we follow the requirement to be JSON by default for machine consumption.
    ctx.obj["JSON"] = json_output
    ctx.obj["NO_CACHE"] = no_cache

    def orchestrator_factory():
        from dev_tools.orchestrator import Orchestrator

        return Orchestrator(no_cache=no_cache)

    from dev_tools.cli import LazyOrchestrator as lazy_orchestrator_cls
    ctx.obj["ORCHESTRATOR"] = lazy_orchestrator_cls(orchestrator_factory)


# --- Utility Helpers ---


def out(ctx, msg, data=None):
    """Emit a command result as JSON or text."""
    if ctx.obj["JSON"]:
        payload = {"status": "success"}
        if data:
            payload.update(data)
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(msg)


def err(ctx, msg, code=1, data=None):
    # Ensure sensitive data is masked in the error message
    """Emit a command error and exit."""
    masked_msg = mask_sensitive_data(msg)
    if ctx.obj["JSON"]:
        payload = {"status": "error", "message": masked_msg, "code": code}
        if data:
            payload.update({"data": data})
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(f"❌ Error: {masked_msg}", err=True)
    sys.exit(code)


def _handle_unexpected_error(ctx, command_name, error):
    """Centralized error handling for unexpected exceptions."""
    message = f"Unexpected error in {command_name}: {str(error)}"
    err(ctx, message, code=1)


def _gate_json_option(func):
    """Per-command --json/--no-json passthrough (group flag is global)."""
    import click as _click

    @_click.option("--json/--no-json", "json_output", default=None,
                   help="Override JSON output for this command")
    @_click.pass_context
    def wrapper(ctx, json_output, *args, **kwargs):
        if json_output is not None:
            ctx.obj["JSON"] = json_output
        return ctx.invoke(func, *args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def _get_body_content(ctx, orch, file, body):
    if file and body:
        err(ctx, "Provide --file or --body, not both")
    if not file and not body:
        err(ctx, "Provide either --file or --body")

    content = body if body is not None else (orch._read_safe_file(file) if file else None)
    if content is None:
        err(ctx, "Provide --file or --body")
    return content


def _handle_gate(ctx, res, label):
    msg = (
        f"{label}: "
        f"Current={res.get('current', res.get('size_kb'))}, "
        f"Baseline={res.get('baseline', res.get('baseline_kb'))}"
    )
    if res["status"] == "error":
        err(ctx, msg, data=res)
    else:
        out(ctx, msg, data=res)


def get_config():
    """Active project config via the CLI shim."""
    from dev_tools.cli import get_config as _get_config
    return _get_config()
