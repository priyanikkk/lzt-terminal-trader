"""
Terminal User Interface and Dashboard built with Rich.
Provides comprehensive visual monitoring across all 13 required system sections.
"""

from decimal import Decimal
from typing import Optional, List
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

from config import settings
from orchestrator.registry import agent_registry
from orchestrator.orchestrator import orchestrator
from database.repository import repository
from services.logging_service import ring_buffer_handler
from orchestrator.agent_factory import agent_factory

console = Console()


class TerminalUI:
    """
    Renders beautiful, information-dense ASCII dashboards and tables for system observability.
    """

    def render_header(self) -> Panel:
        mode_str = "[bold yellow]🧪 SIMULATION MODE (Safe)[/]" if settings.SIMULATION_MODE else "[bold red]💳 LIVE TRADING ACTIVE[/]"
        live_perm = "[bold green]ALLOWED[/]" if settings.LIVE_PURCHASE_ENABLED else "[bold red]DISABLED[/]"
        cb_str = "[bold green]OK[/]"
        monitor = agent_registry.get("system_monitor")
        if monitor and getattr(monitor, "circuit_broken", False):
            cb_str = "[bold red]TRIPPED (Frozen)[/]"

        header_text = (
            f"[bold cyan]LZT MARKET AI MULTI-AGENT ARBITRAGE SYSTEM[/]  |  "
            f"Mode: {mode_str}  |  Live Purchase: {live_perm}  |  Circuit Breaker: {cb_str}"
        )
        return Panel(header_text, style="cyan", box=box.ROUNDED)

    def render_dashboard(self) -> Panel:
        """Section 1: Main Dashboard"""
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Metric", style="bold white")
        table.add_column("Value", style="bold green")

        table.add_row("System Status", "RUNNING" if orchestrator.is_running else "IDLE / STANDBY")
        table.add_row("Arbitrage Cycles Completed", str(orchestrator.cycle_count))
        table.add_row("Active Registered Agents", str(len(agent_registry.list_agents())))
        table.add_row("Items In Flight", str(orchestrator.active_items_in_flight))
        table.add_row("Daily Budget Limit", f"{settings.MAX_DAILY_BUDGET} RUB")
        table.add_row("Max Purchase Cap", f"{settings.MAX_PURCHASE_PRICE} RUB")
        table.add_row("Min Net Profit Target", f"{settings.MIN_NET_PROFIT} RUB")
        table.add_row("Min ROI Target", f"{settings.MIN_ROI_PERCENT}%")

        return Panel(table, title="[bold cyan]1. System Dashboard[/]", border_style="cyan")

    def render_agents_status(self) -> Panel:
        """Section 2: Detailed Agent Status"""
        table = Table(box=box.MINIMAL_DOUBLE_HEAD, expand=True)
        table.add_column("Agent ID", style="cyan", no_wrap=True)
        table.add_column("Role", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Current Task", style="dim")
        table.add_column("Success", style="green", justify="right")
        table.add_column("Errors", style="red", justify="right")
        table.add_column("Avg Time", style="yellow", justify="right")
        table.add_column("Permissions", style="magenta")

        for agent in agent_registry.list_agents():
            status_style = "green" if agent.status == "IDLE" else ("yellow" if agent.status == "BUSY" else "red")
            avg_time = (
                f"{agent.total_execution_time_ms / agent.success_count:.1f}ms"
                if agent.success_count > 0
                else "0.0ms"
            )
            perms_str = ", ".join([p.name.replace("_", "") for p in agent.allowed_permissions])

            table.add_row(
                agent.agent_id,
                agent.role,
                f"[{status_style}]{agent.status}[/]",
                agent.current_task or "-",
                str(agent.success_count),
                str(agent.error_count),
                avg_time,
                perms_str
            )

        return Panel(table, title="[bold cyan]2. Agents Status & Telemetry[/]", border_style="cyan")

    def render_recent_summaries(self) -> Panel:
        """Sections 3-8: Recent Arbitrage Pipeline Ingestion Summaries"""
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Item ID", style="bold cyan")
        table.add_column("Final State", style="bold")
        table.add_column("Buy Price", justify="right")
        table.add_column("Est. Resale", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("ROI", justify="right")
        table.add_column("Risk Level", justify="center")
        table.add_column("Notes / Abort Reason", style="dim")

        if not orchestrator.recent_summaries:
            table.add_row("-", "NO DATA", "-", "-", "-", "-", "-", "Run an arbitrage cycle to populate pipeline data")
        else:
            for s in reversed(orchestrator.recent_summaries[-12:]):
                state_color = "green" if s.final_state.value == "LISTED" else ("red" if s.final_state.value == "REJECTED" else "yellow")
                buy_p = f"{s.pricing.buy_price} RUB" if s.pricing else "-"
                resale_p = f"{s.pricing.estimated_resale_price} RUB" if s.pricing else "-"
                profit = f"+{s.pricing.net_profit} RUB" if s.pricing else "-"
                roi = f"{s.pricing.roi_percent}%" if s.pricing else "-"
                risk = s.risk.risk_level if s.risk else "-"
                reason = s.aborted_reason or ("Listed as #" + str(s.resale.resale_item_id) if s.resale else "Success")

                table.add_row(
                    str(s.item_id),
                    f"[{state_color}]{s.final_state.value}[/]",
                    buy_p,
                    resale_p,
                    f"[bold green]{profit}[/]" if profit != "-" else "-",
                    roi,
                    risk,
                    reason[:50]
                )

        return Panel(table, title="[bold cyan]3-8. Arbitrage Pipeline Progression[/]", border_style="cyan")

    async def render_finance_section(self) -> Panel:
        """Section 9: Financial Ledger and Risk Audit"""
        financer = agent_registry.get("finance_agent")
        if not financer:
            return Panel("Finance agent unavailable", title="9. Finance")

        from models.messages import AgentMessage
        msg = await financer.execute(AgentMessage(
            agent_id=financer.agent_id,
            task_type="AUDIT",
            input_data={"is_simulation": settings.SIMULATION_MODE}
        ))
        rep = msg.output_data

        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Financial Metric", style="white")
        table.add_column("Value", style="bold")

        table.add_row("Total Purchases Count", str(rep.total_purchases_count))
        table.add_row("Total Invested Capital", f"{rep.total_invested} RUB")
        table.add_row("Total Platform Fees Paid", f"{rep.total_fees_paid} RUB")
        table.add_row("Total Realized / Expected Revenue", f"{rep.total_revenue} RUB")
        table.add_row("Net Profit (Strict Decimal)", f"[bold green]+{rep.net_profit} RUB[/]" if rep.net_profit >= 0 else f"[bold red]{rep.net_profit} RUB[/]")
        table.add_row("Total Portfolio ROI", f"{rep.roi_total_percent}%")
        table.add_row("Today's Spent Budget", f"{rep.budget_spent_today} / {rep.daily_budget_limit} RUB")
        table.add_row("Remaining Daily Headroom", f"{rep.budget_remaining_today} RUB")
        table.add_row("Open Inventory Cost", f"{rep.open_inventory_cost} RUB")
        table.add_row("Audit Discrepancies", f"[bold red]{len(rep.discrepancies)} detected[/]" if rep.discrepancies else "[green]None (Clean)[/]")

        return Panel(table, title="[bold cyan]9. Financial Ledger & Budget Accounting[/]", border_style="cyan")

    def render_logs_section(self) -> Panel:
        """Section 10: System Logs (Ring Buffer)"""
        logs = ring_buffer_handler.get_logs(limit=8)
        text = Text()
        if not logs:
            text.append("No log entries recorded yet.\n", style="dim")
        for l in logs:
            lvl_style = "red" if l["level"] == "ERROR" or l["level"] == "CRITICAL" else ("yellow" if l["level"] == "WARNING" else "white")
            text.append(f"[{l['timestamp']}] ", style="dim")
            text.append(f"[{l['level']}] ", style=lvl_style)
            text.append(f"{l['message']}\n")

        return Panel(text, title="[bold cyan]10. Live Event & Audit Log[/]", border_style="cyan")

    def render_agent_factory_section(self) -> Panel:
        """Section 11: Dynamic Agent Factory Overview"""
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Dynamic Agent ID", style="cyan")
        table.add_column("Created At", style="dim")
        table.add_column("Status", style="green")
        table.add_column("Generated Files", style="white")

        if not agent_factory.generation_history:
            table.add_row("-", "-", "READY", "Use 'create-agent' command to generate an agent module")
        else:
            for rec in agent_factory.generation_history:
                table.add_row(
                    rec["agent_id"],
                    rec["created_at"][:19],
                    rec["status"],
                    f"{len(rec['files'])} files created"
                )

        return Panel(table, title="[bold cyan]11. Dynamic Agent Factory[/]", border_style="cyan")

    def render_configuration_section(self) -> Panel:
        """Section 12: Configuration & Risk Thresholds"""
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Setting", style="white")
        table.add_column("Value", style="yellow")

        # Mask secrets
        masked_api = settings.LZT_API_KEY[:4] + "***" + settings.LZT_API_KEY[-4:] if len(settings.LZT_API_KEY) > 8 else ("(Empty - Mock Simulator)" if not settings.LZT_API_KEY else "***")
        masked_tg = settings.TELEGRAM_BOT_TOKEN[:4] + "***" if settings.TELEGRAM_BOT_TOKEN else "(Disabled)"

        table.add_row("LZT API Key", masked_api)
        table.add_row("LZT Base URL", settings.LZT_API_BASE_URL)
        table.add_row("Telegram Admin Bot", masked_tg)
        table.add_row("Min Net Profit Threshold", f"{settings.MIN_NET_PROFIT} RUB")
        table.add_row("Min ROI Threshold", f"{settings.MIN_ROI_PERCENT}%")
        table.add_row("Max Purchase Price Cap", f"{settings.MAX_PURCHASE_PRICE} RUB")
        table.add_row("Max Daily Budget Cap", f"{settings.MAX_DAILY_BUDGET} RUB")
        table.add_row("Buyer Commission Rate", f"{settings.BUY_FEE_PERCENT}%")
        table.add_row("Seller Commission Rate", f"{settings.RESALE_FEE_PERCENT}%")
        table.add_row("LLM Provider", f"{settings.LLM_PROVIDER} ({settings.LLM_MODEL})")

        return Panel(table, title="[bold cyan]12. Security & Operating Limits Configuration[/]", border_style="cyan")

    async def render_full_screen(self):
        """Assembles the full multi-section dashboard."""
        console.clear()
        console.print(self.render_header())
        console.print(self.render_dashboard())
        console.print(self.render_agents_status())
        console.print(self.render_recent_summaries())
        console.print(await self.render_finance_section())
        console.print(self.render_agent_factory_section())
        console.print(self.render_configuration_section())
        console.print(self.render_logs_section())


# Global UI instance
terminal_ui = TerminalUI()
