"""
Show current config and session state.

Commands:
  /info config   — Show provider, model, URL, yolo, reasoning, etc.
  /info stats    — Show session stats (requests, tokens, compactions)
"""

import os
from aicoder.core.config import Config


def _handle_info(args: str, ctx=None) -> None:
    parts = args.strip().split() if args.strip() else ["help"]

    sub = parts[0]

    if sub == "config":
        _print_config()
    elif sub in ("stats", "stat"):
        _print_stats(ctx)
    else:
        print("Usage: /info config|stats")

    # Fire hook so plugins can show their own info
    if ctx and ctx.app and ctx.app.plugin_system:
        ctx.app.plugin_system.call_hooks("on_info", sub)


def _print_config() -> None:
    model = Config.model()
    base_url = Config.base_url()
    api_ep = Config.api_endpoint()
    yolo = Config.yolo_mode()
    show_r = Config.show_reasoning()
    clear_t = Config.clear_thinking()
    effort = Config.reasoning_effort() or "default"
    detail = Config.detail_mode()
    rf = Config.get_reasoning_format()
    debug = Config.debug()
    sup_err = Config.suppress_error_body()

    print(f"Config:")
    print(f"  model:           {model}")
    print(f"  base_url:        {base_url}")
    print(f"  api_endpoint:    {api_ep}")
    print(f"  yolo:            {yolo}")
    print(f"  show_reasoning:  {show_r}")
    print(f"  clear_thinking:  {clear_t}")
    print(f"  reasoning_effort:{effort}")
    print(f"  reasoning_format:{rf}")
    print(f"  detail_mode:     {detail}")
    print(f"  suppress_errors: {sup_err}")
    print(f"  debug:           {debug}")
    print(f"  API_PROVIDER:    {os.environ.get('API_PROVIDER', 'not set')}")
    print(f"  API_KEY:         {'set' if Config.api_key() else 'not set'}")
    ep = os.environ.get("API_ENDPOINT")
    if ep:
        print(f"  API_ENDPOINT:    {ep}")


def _print_stats(ctx) -> None:
    if not ctx or not ctx.app:
        print("No context available")
        return

    stats = ctx.app.stats
    if not stats:
        print("Stats not available")
        return

    print(f"Session Stats:")
    print(f"  api_requests:     {stats.api_requests}")
    print(f"  api_success:      {stats.api_success}")
    print(f"  api_errors:       {stats.api_errors}")
    print(f"  api_time_spent:   {stats.api_time_spent:.1f}s")
    print(f"  compactions:      {stats.compactions}")
    print(f"  prompt_tokens:    {stats.prompt_tokens}")
    print(f"  completion_tokens:{stats.completion_tokens}")
    print(f"  last_api_time:    {stats.last_api_time:.1f}s")

    # Cost is shown in context bar — not duplicated here


def create_plugin(ctx):
    import functools

    handler = functools.partial(_handle_info, ctx=ctx)
    ctx.register_command("info", handler, "Show config /info config|stats")
    return {}
