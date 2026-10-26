"""
Main Entry Point for LZT Terminal Trader.
Usage:
    python main.py              # Starts interactive Rich terminal UI (runs wizard if unconfigured)
    python main.py --wizard     # Directly opens the 5-step setup wizard
    python main.py --diag       # Runs system diagnostics and exits
    python main.py --cycle      # Runs a single automated pipeline cycle and exits
    python main.py --test       # Runs test suite and exits
"""

import argparse
import asyncio
from pathlib import Path
import sys
from rich.console import Console
from rich.table import Table

from config import settings
from app.database import db
from app.diagnostics import run_diagnostics
from app.orchestrator import orchestrator
from app.setup_wizard import run_setup_wizard
from app.terminal_ui import terminal_ui

console = Console()


async def initialize_app():
    """Ensures database tables are initialized and directory structure is ready."""
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)
    await db.init_db()


async def async_main():
    parser = argparse.ArgumentParser(description="LZT Terminal Trader - AI Multi-Agent Arbitrage System")
    parser.add_argument("--wizard", action="store_true", help="Launch interactive 5-step setup wizard")
    parser.add_argument("--diag", action="store_true", help="Run system diagnostics and exit")
    parser.add_argument("--cycle", action="store_true", help="Run a single arbitrage cycle and exit")
    parser.add_argument("--test", action="store_true", help="Run automated test suite and exit")
    args = parser.parse_args()

    # Diagnostic flag
    if args.diag:
        await initialize_app()
        res = await run_diagnostics()
        table = Table(title="Диагностика LZT Terminal Trader", show_header=True, header_style="bold magenta")
        table.add_column("Категория", style="cyan")
        table.add_column("Проверка", style="white")
        table.add_column("Статус", style="bold")
        table.add_column("Подробности", style="dim")
        for c in res["checks"]:
            st = c["status"]
            st_style = "green" if st == "PASS" else "yellow" if st in ("WARN", "INFO") else "red"
            table.add_row(c["category"], c["name"], f"[{st_style}]{st}[/]", c["details"])
        console.print(table)
        console.print(f"\nОбщий статус: [bold]{res['overall_status']}[/bold]")
        sys.exit(0 if res["overall_status"] != "ERROR" else 1)

    # Setup Wizard direct launch
    if args.wizard:
        await initialize_app()
        await run_setup_wizard()
        return

    # Single cycle execution
    if args.cycle:
        await initialize_app()
        console.print("[cyan]Запуск цикла арбитража...[/cyan]")
        summary = await orchestrator.run_pipeline_cycle(auto_purchase=False)
        console.print(f"[bold green]Цикл завершён:[/] Проверено: {summary.get('scanned_candidates')}, Одобрено: {summary.get('pricing_approved')}")
        return

    # Run tests flag
    if args.test:
        import pytest
        ret_code = pytest.main(["-v", "tests/"])
        sys.exit(ret_code)

    # First-run detection: if .env doesn't exist, automatically launch setup wizard
    if not settings.is_configured():
        console.print("[yellow]Конфигурационный файл .env не обнаружен. Запуск мастера первоначальной настройки...[/yellow]\n")
        wizard_ok = await run_setup_wizard()
        if not wizard_ok:
            console.print("[red]Настройка отменена. Выход.[/red]")
            return

    # Normal Interactive Terminal Mode
    await initialize_app()
    await terminal_ui.main_menu_loop()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Программа завершена.[/yellow]")


if __name__ == "__main__":
    main()
