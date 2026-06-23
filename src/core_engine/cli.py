from __future__ import annotations

import asyncio

import typer
import uvicorn

from core_engine import seed as seed_module
from core_engine.settings import get_settings
from core_engine.workers import bi, campaigns, content, messaging, router, social

cli = typer.Typer(help="Core-Engine operational entry point.")
worker_cli = typer.Typer(help="Run background workers.")
cli.add_typer(worker_cli, name="worker")


@cli.command()
def seed() -> None:
    """Create idempotent dev fixtures (agency, pipeline, stages, workspace, list)."""

    result = asyncio.run(seed_module.seed())
    for key, value in result.items():
        typer.echo(f"{key}={value}")
    typer.echo(f"\nwrote {seed_module.SEED_FILE}")


@cli.command()
def api() -> None:
    settings = get_settings()
    uvicorn.run(
        "core_engine.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )


@worker_cli.command("messaging")
def worker_messaging() -> None:
    asyncio.run(messaging.run())


@worker_cli.command("messaging-flusher")
def worker_messaging_flusher() -> None:
    asyncio.run(messaging.run_message_buffer_flusher())


@worker_cli.command("social")
def worker_social() -> None:
    asyncio.run(social.run())


@worker_cli.command("router")
def worker_router() -> None:
    asyncio.run(router.run())


@worker_cli.command("bi")
def worker_bi() -> None:
    asyncio.run(bi.run())


@worker_cli.command("campaigns")
def worker_campaigns() -> None:
    asyncio.run(campaigns.run())


@worker_cli.command("content")
def worker_content() -> None:
    asyncio.run(content.run())


if __name__ == "__main__":
    cli()
