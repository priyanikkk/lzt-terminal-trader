"""
Interactive CLI command processor for terminal control.
"""

import asyncio
from typing import List
from rich.console import Console
from rich.table import Table

from ui.terminal import terminal_ui
from orchestrator.orchestrator import orchestrator
from orchestrator.agent_factory import agent_factory, AgentSpecification
from core.permissions import Permission
from orchestrator.registry import agent_registry
from models.messages import AgentMessage

console = Console()


async def handle_command(cmd: str) -> bool:
    """
    Executes operator command.
    Returns False if exit requested, True otherwise.
    """
    cmd = cmd.strip().lower()
    if not cmd:
        return True

    if cmd in ["exit", "quit", "q"]:
        orchestrator.stop_autonomous_loop()
        console.print("[yellow]Exiting LZT Multi-Agent System. Goodbye![/]")
        return False

    elif cmd in ["dashboard", "status", "view"]:
        await terminal_ui.render_full_screen()

    elif cmd in ["cycle", "run"]:
        console.print("[cyan]Executing single arbitrage cycle...[/]")
        result = await orchestrator.run_single_arbitrage_cycle()
        console.print(f"[green]Cycle Result:[/] {result}")

    elif cmd == "loop":
        if orchestrator.is_running:
            console.print("[yellow]Autonomous loop is already active.[/]")
        else:
            console.print("[green]Starting autonomous loop in background...[/]")
            asyncio.create_task(orchestrator.start_autonomous_loop())

    elif cmd == "stop":
        orchestrator.stop_autonomous_loop()
        console.print("[yellow]Autonomous loop stopped.[/]")

    elif cmd == "agents":
        console.print(terminal_ui.render_agents_status())

    elif cmd == "finance":
        console.print(await terminal_ui.render_finance_section())

    elif cmd in ["test", "diagnostics", "qa"]:
        console.print("[cyan]Triggering QAAgent test and diagnostics suite...[/]")
        qa = agent_registry.get("qa_agent")
        if qa:
            msg = await qa.execute(AgentMessage(
                agent_id=qa.agent_id,
                task_type="RUN_TESTS",
                input_data={"target": "all"}
            ))
            rep = msg.output_data or {}
            color = "green" if rep.get("is_system_ready") else "red"
            console.print(f"[{color}]QA Report:[/] Ready={rep.get('is_system_ready')}, Passed={rep.get('total_passed')}, Failed={rep.get('total_failed')}")
            if rep.get("failures"):
                for f in rep["failures"]:
                    console.print(f"[red]Failure:[/] {f}")
        else:
            console.print("[red]QAAgent not available.[/]")

    elif cmd == "create-agent":
        console.print("[cyan]AgentFactory: Specifying new dynamic agent 'MarketSentimentAgent'...[/]")
        spec = AgentSpecification(
            agent_id="market_sentiment_agent",
            name="Market Sentiment Agent",
            class_name="MarketSentimentAgent",
            role="Temporal Price & Channel Sentiment Analysis",
            description="Analyzes Telegram channel count and age trajectory for high-liquidity arbitrage opportunities.",
            task_type="ANALYZE_SENTIMENT",
            allowed_permissions=[Permission.SCAN_MARKET, Permission.CALCULATE_PRICING],
            tools=["statistical_liquidity_calculator", "channel_growth_metric"],
            logic_summary="Computes liquidity index and growth trajectory of channel accounts"
        )
        try:
            res = await agent_factory.build_and_register_agent(spec)
            console.print(f"[bold green]Agent Successfully Created & Registered![/] {res}")
        except Exception as e:
            console.print(f"[bold red]Failed creating agent:[/] {e}")

    elif cmd == "reset-cb":
        monitor = agent_registry.get("system_monitor")
        if monitor and hasattr(monitor, "reset_circuit_breaker"):
            monitor.reset_circuit_breaker()
            console.print("[green]Circuit breaker has been reset.[/]")

    elif cmd == "help":
        table = Table(title="Available Terminal Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="white")
        table.add_row("cycle / run", "Run one single complete arbitrage cycle")
        table.add_row("loop", "Start autonomous continuous background loop")
        table.add_row("stop", "Stop autonomous background loop")
        table.add_row("status / dashboard", "Redraw full multi-section dashboard")
        table.add_row("agents", "Display table of registered agents and metrics")
        table.add_row("finance", "Display financial ledger and budget audit")
        table.add_row("test / diagnostics", "Run QAAgent automated regression suite")
        table.add_row("create-agent", "Demonstrate AgentFactory generating a new agent")
        table.add_row("reset-cb", "Reset system circuit breaker after error clearing")
        table.add_row("exit / quit", "Exit system")
        console.print(table)

    else:
        console.print(f"[red]Unknown command: '{cmd}'. Type 'help' for available commands.[/]")

    return True
