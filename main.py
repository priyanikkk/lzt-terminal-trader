"""
Main entry point for the LZT Market AI Multi-Agent Arbitrage System.
Supports interactive terminal dashboard, automated single-cycle runs,
background loop execution, and test suite verification.
"""

import asyncio
import sys
import argparse
import signal
import logging
from rich.console import Console

from config import settings
from database.repository import repository
from orchestrator.orchestrator import orchestrator
from ui.terminal import terminal_ui
from ui.commands import handle_command
from orchestrator.registry import agent_registry
from models.messages import AgentMessage

console = Console()


async def initialize_application():
    """Initializes database schema and boots all 10 core agents."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    )
    # Initialize DB tables
    await repository.init()
    # Initialize Orchestrator and core agents
    orchestrator.initialize_system()


async def run_interactive_shell():
    """Starts the full interactive Rich terminal UI."""
    await terminal_ui.render_full_screen()
    console.print("\n[bold cyan]Interactive Control Console[/] (type [yellow]'help'[/] for commands, [yellow]'exit'[/] to quit)")

    running = True
    while running:
        try:
            cmd = await asyncio.to_thread(input, "\n[lzt-market-agent] > ")
            running = await handle_command(cmd)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Received interrupt signal. Shutting down...[/]")
            orchestrator.stop_autonomous_loop()
            break
        except Exception as e:
            console.print(f"[bold red]Command error:[/] {e}")


async def async_main():
    parser = argparse.ArgumentParser(description="LZT Market AI Multi-Agent Arbitrage System")
    parser.add_argument("--cycle", action="store_true", help="Run a single arbitrage cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Run in continuous background loop mode")
    parser.add_argument("--test", action="store_true", help="Run automated test suite and exit")
    parser.add_argument("--dashboard", action="store_true", help="Render dashboard once and exit")
    args = parser.parse_args()

    await initialize_application()

    if args.test:
        console.print("[cyan]Running QA regression suite...[/]")
        qa = agent_registry.get("qa_agent")
        if qa:
            msg = await qa.execute(AgentMessage(
                agent_id=qa.agent_id,
                task_type="RUN_TESTS",
                input_data={"target": "all"}
            ))
            rep = msg.output_data or {}
            console.print(f"Tests Passed: {rep.get('total_passed')}, Failed: {rep.get('total_failed')}")
            sys.exit(0 if rep.get("is_system_ready") else 1)
        sys.exit(1)

    if args.cycle:
        console.print("[cyan]Running single arbitrage cycle...[/]")
        res = await orchestrator.run_single_arbitrage_cycle()
        console.print(f"[bold green]Result:[/] {res}")
        await terminal_ui.render_full_screen()
        return

    if args.dashboard:
        await terminal_ui.render_full_screen()
        return

    if args.loop:
        console.print("[green]Running in continuous loop mode. Press Ctrl+C to terminate.[/]")
        try:
            await orchestrator.start_autonomous_loop()
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("[yellow]Loop stopped.[/]")
        return

    # Default: Interactive Shell
    await run_interactive_shell()


def cli_entrypoint():
    """Synchronous wrapper for pyproject.toml script entrypoint."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_entrypoint()
