"""
Interactive Rich Terminal Interface for LZT Terminal Trader.
Provides a clean, intuitive, numbered menu system with real-time operations,
strict simulation mode banners, and zero dummy/mock buttons.
"""

import asyncio
from decimal import Decimal
import os
import sys
import time
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from config import save_env_file, settings
from app.agents import agent_registry
from app.api_client import api_client
from app.database import db
from app.diagnostics import run_diagnostics
from app.finance import finance_manager
from app.listing_inspector import inspector
from app.market_scanner import scanner
from app.orchestrator import orchestrator
from app.pricing import calculate_profit, estimate_fair_resale_price, evaluate_arbitrage_opportunity
from app.purchases import purchase_manager
from app.resale import resale_manager
from app.setup_wizard import run_setup_wizard

console = Console()


class TerminalUI:
    def __init__(self):
        self.console = console

    def print_header(self, title: str):
        self.console.clear()
        mode_text = (
            "[bold yellow]SIMULATION MODE — REAL TRANSACTIONS DISABLED[/bold yellow]"
            if settings.APP_MODE == "simulation" or not settings.get_token()
            else "[bold green]LIVE MODE — REAL TRANSACTIONS ACTIVE[/bold green]"
        )
        self.console.print(
            Panel.fit(
                f"[bold cyan]LZT TERMINAL TRADER v2.0[/bold cyan] | {mode_text}\n"
                f"[bold white]{title}[/bold white]",
                border_style="cyan"
            )
        )

    def pause(self):
        self.console.print("\n[dim]Нажмите Enter, чтобы продолжить...[/dim]")
        input()

    # =========================================================================
    # 1. DASHBOARD
    # =========================================================================
    async def show_dashboard(self):
        self.print_header("1. Главная панель (Dashboard)")
        summary = await finance_manager.get_financial_summary()

        # Metrics Table
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="bold cyan")
        table.add_column("Val", style="bold yellow")
        table.add_column("Key2", style="bold cyan")
        table.add_column("Val2", style="bold yellow")

        table.add_row(
            "Текущий баланс:", f"{summary['current_balance']:.2f} RUB",
            "Потрачено сегодня:", f"{summary['spent_today']:.2f} RUB"
        )
        table.add_row(
            "Дневной лимит:", f"{summary['daily_limit']:.2f} RUB",
            "Остаток лимита:", f"{summary['daily_headroom']:.2f} RUB"
        )
        table.add_row(
            "Всего покупок:", str(summary["total_purchases_count"]),
            "Сумма покупок:", f"{summary['total_spent_all_time']:.2f} RUB"
        )
        table.add_row(
            "Черновиков перепродажи:", str(summary["resale_inventory_count"]),
            "Опубликовано / Продано:", f"{summary['resale_published_count']} / {summary['resale_sold_count']}"
        )
        table.add_row(
            "Реализованная прибыль:", f"[bold green]{summary['realized_profit']:.2f} RUB[/]",
            "Режим работы:", f"{settings.APP_MODE.upper()}"
        )

        self.console.print(Panel(table, title="[bold]Финансовые показатели[/bold]", border_style="green"))

        # Agent status preview
        agent_table = Table(title="Состояние агентов", show_header=True, header_style="bold blue")
        agent_table.add_column("Агент", style="cyan")
        agent_table.add_column("Роль", style="dim")
        agent_table.add_column("Статус", style="bold")
        agent_table.add_column("Запусков")

        for ag in agent_registry.all_agents():
            status_style = "green" if ag.status in ("IDLE", "SUCCESS") else "red" if ag.status == "ERROR" else "yellow"
            agent_table.add_row(ag.name, ag.role, f"[{status_style}]{ag.status}[/]", str(ag.execution_count))

        self.console.print(agent_table)
        self.pause()

    # =========================================================================
    # 2. MARKET SCANNER
    # =========================================================================
    async def show_market_scanner(self):
        self.print_header("2. Сканер рынка Telegram-аккаунтов (Market Scanner)")
        self.console.print("[dim]Поиск актуальных объявлений по критериям...[/dim]")

        query = Prompt.ask("Поисковый запрос (или оставьте пустым)", default="")
        max_price_in = Prompt.ask("Максимальная цена в RUB (Enter для настройки)", default=str(settings.MAX_PURCHASE_PRICE))
        country_in = Prompt.ask("Код страны (ID, US, DE, KZ, BR или пусто)", default="").strip().upper()

        max_price_val = float(max_price_in) if max_price_in else float(settings.MAX_PURCHASE_PRICE)

        with self.console.status("[cyan]Сканирование рынка и фильтрация лотов...[/cyan]"):
            candidates = await scanner.scan_market(
                query=query,
                max_price=max_price_val,
                country=country_in,
                limit=15,
            )

        if not candidates:
            self.console.print("[yellow]По заданным критериям объявлений не найдено.[/yellow]")
            self.pause()
            return

        table = Table(title=f"Найдено предложений: {len(candidates)}", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Заголовок", style="white", max_width=40, overflow="ellipsis")
        table.add_column("Цена", style="yellow")
        table.add_column("Гео", style="dim")
        table.add_column("Риск", style="bold")
        table.add_column("Перепродажа", style="green")
        table.add_column("ROI %", style="bold green")
        table.add_column("Вердикт", style="bold")

        for c in candidates:
            risk_style = "green" if c["risk_level"] == "LOW" else "yellow" if c["risk_level"] == "MEDIUM" else "red"
            verdict_style = "bold green" if c["is_approved"] else "bold red"
            verdict_text = "ОДОБРЕНО" if c["is_approved"] else "ОТКЛОНЕНО"

            table.add_row(
                str(c["item_id"]),
                c["title"],
                f"{c['price']:.2f} ₽",
                c["country"],
                f"[{risk_style}]{c['risk_level']}[/]",
                f"{c['target_resale_price']:.2f} ₽",
                f"{c['roi_percent']:.1f}%",
                f"[{verdict_style}]{verdict_text}[/]",
            )

        self.console.print(table)

        self.console.print("\nДействия:")
        self.console.print("  [ID лота] — Детально проанализировать или купить лот")
        self.console.print("  [Enter]   — Вернуться в главное меню")
        choice = Prompt.ask("Выберите действие", default="")

        if choice.isdigit():
            target_id = int(choice)
            found = next((c for c in candidates if c["item_id"] == target_id), None)
            if found:
                await self._inspect_and_purchase_flow(found)
            else:
                self.console.print(f"[red]Лот #{target_id} не найден в текущих результатах.[/red]")
                self.pause()

    async def _inspect_and_purchase_flow(self, item: Dict[str, Any]):
        self.print_header(f"Анализ лота #{item['item_id']}")
        self.console.print(f"[bold cyan]Заголовок:[/] {item['title']}")
        self.console.print(f"[bold cyan]Описание:[/] {item.get('description', 'Нет описания')}")
        self.console.print(f"[bold cyan]Цена закупки:[/] [yellow]{item['price']:.2f} RUB[/]")
        self.console.print(f"[bold cyan]Оценка перепродажи:[/] [green]{item['target_resale_price']:.2f} RUB[/]")
        self.console.print(f"[bold cyan]Ожидаемая чистая прибыль:[/] [green]{item['net_profit']:.2f} RUB[/] (ROI: {item['roi_percent']:.1f}%)")
        self.console.print(f"[bold cyan]Уровень риска:[/] {item['risk_level']} (Доверие: {item['confidence'] * 100:.0f}%)")
        self.console.print(f"[bold cyan]Объяснение:[/] {item['explanation']}")

        if item.get("contradictions"):
            self.console.print(f"[bold red]Обнаруженные противоречия:[/] {'; '.join(item['contradictions'])}")
        if item.get("flags"):
            self.console.print(f"[bold yellow]Флаги риска:[/] {', '.join(item['flags'])}")

        self.console.print("\nОпции:")
        self.console.print("  [1] Купить этот аккаунт")
        self.console.print("  [2] Назад")
        action = Prompt.ask("Выбор", choices=["1", "2"], default="2")

        if action == "1":
            if not item["is_approved"]:
                force = Confirm.ask("[yellow]Лот имеет предупреждения или низкий ROI. Вы уверены, что хотите купить?[/yellow]", default=False)
                if not force:
                    return

            with self.console.status("[cyan]Выполнение покупки...[/cyan]"):
                success, msg, receipt = await purchase_manager.execute_purchase(
                    item_id=item["item_id"],
                    title=item["title"],
                    price=Decimal(str(item["price"])),
                    operator_confirmed=True,
                )

            if success:
                self.console.print(f"\n[bold green]✔ {msg}[/bold green]")
                # Prompt to draft resale
                draft_resale = Confirm.ask("Создать черновик для перепродажи?", default=True)
                if draft_resale:
                    target_p = Decimal(str(item["target_resale_price"]))
                    draft_id = await resale_manager.create_resale_draft(
                        purchase_id=receipt.get("purchase_id", 0),
                        item_id=item["item_id"],
                        target_price=target_p,
                        original_price=Decimal(str(item["price"])),
                    )
                    self.console.print(f"[green]✔ Создан черновик перепродажи #{draft_id} по цене {target_p:.2f} RUB.[/green]")
            else:
                self.console.print(f"\n[bold red]✖ Покупка отклонена:[/] {msg}")
            self.pause()

    # =========================================================================
    # 3. LISTING ANALYSIS
    # =========================================================================
    async def show_listing_analysis(self):
        self.print_header("3. Детальный инспектор объявлений (Listing Analysis)")
        item_id_in = Prompt.ask("Введите ID объявления на LZT Market (например, 9812401)", default="")
        if not item_id_in.isdigit():
            self.console.print("[red]Некорректный ID.[/red]")
            self.pause()
            return

        item_id = int(item_id_in)
        with self.console.status(f"[cyan]Получение данных лота #{item_id}...[/cyan]"):
            item = await api_client.get_item_details(item_id)

        if not item:
            self.console.print(f"[red]Объявление #{item_id} не найдено.[/red]")
            self.pause()
            return

        inspection = inspector.inspect_listing(item)
        pricing = evaluate_arbitrage_opportunity(item)

        item["target_resale_price"] = float(pricing["target_resale_price"])
        item["net_profit"] = float(pricing["net_profit"])
        item["roi_percent"] = float(pricing["roi_percent"])
        item["risk_level"] = inspection.risk_level
        item["confidence"] = inspection.confidence_score
        item["explanation"] = inspection.explanation
        item["contradictions"] = inspection.contradictions
        item["flags"] = inspection.flags
        item["is_approved"] = pricing["is_approved"] and inspection.is_safe

        await self._inspect_and_purchase_flow(item)

    # =========================================================================
    # 4. PROFIT CALCULATOR
    # =========================================================================
    async def show_profit_calculator(self):
        self.print_header("4. Калькулятор арбитражной прибыли (Profit Calculator)")
        self.console.print("[dim]Точный математический расчёт комиссий, точки безубыточности и ROI через Decimal.[/dim]\n")

        p_price = Prompt.ask("Цена закупки на маркете (RUB)", default="150.0")
        r_price = Prompt.ask("Желаемая цена перепродажи (RUB)", default="250.0")
        b_fee = Prompt.ask("Комиссия покупателя (%)", default=str(settings.BUY_FEE_PERCENT))
        s_fee = Prompt.ask("Комиссия продавца маркета (%)", default=str(settings.RESALE_FEE_PERCENT))

        try:
            metrics = calculate_profit(
                purchase_price=Decimal(p_price),
                resale_price=Decimal(r_price),
                buy_fee_pct=Decimal(b_fee),
                resale_fee_pct=Decimal(s_fee),
            )
        except Exception as e:
            self.console.print(f"[red]Ошибка ввода: {e}[/red]")
            self.pause()
            return

        table = Table(title="Экономическая ведомость сделки", show_header=True, header_style="bold cyan")
        table.add_column("Показатель", style="white")
        table.add_column("Значение", style="bold yellow")

        table.add_row("Цена закупки:", f"{metrics.purchase_price:.2f} RUB")
        table.add_row("Комиссия на покупку:", f"{metrics.buy_fee:.2f} RUB ({b_fee}%)")
        table.add_row("Итого себестоимость (Инвестиция):", f"{metrics.total_investment:.2f} RUB")
        table.add_row("Цена перепродажи:", f"{metrics.resale_price:.2f} RUB")
        table.add_row("Комиссия маркета при продаже:", f"{metrics.resale_fee:.2f} RUB ({s_fee}%)")
        table.add_row("Выплата на баланс после продажи:", f"{metrics.net_payout:.2f} RUB")

        profit_style = "bold green" if metrics.is_profitable else "bold red"
        table.add_row("Чистая прибыль:", f"[{profit_style}]{metrics.net_profit:.2f} RUB[/]")
        table.add_row("Рентабельность инвестиций (ROI):", f"[{profit_style}]{metrics.roi_percent:.2f}%[/]")
        table.add_row("Точка безубыточности (Breakeven):", f"{metrics.breakeven_price:.2f} RUB")

        self.console.print(table)

        if metrics.roi_percent >= settings.MIN_ROI_PERCENT and metrics.net_profit >= settings.MIN_NET_PROFIT:
            self.console.print("[bold green]✔ Сделка соответствует целевым критериям доходности![/bold green]")
        else:
            self.console.print(f"[yellow]Показатели ниже установленных порогов (Мин. ROI: {settings.MIN_ROI_PERCENT}%, Мин. прибыль: {settings.MIN_NET_PROFIT} RUB).[/yellow]")

        self.pause()

    # =========================================================================
    # 5. AGENTS STATUS & ORCHESTRATION
    # =========================================================================
    async def show_agents(self):
        self.print_header("5. Мультиагентная система и Оркестратор (Agents)")

        table = Table(title="Реестр автономных агентов", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim")
        table.add_column("Агент", style="cyan")
        table.add_column("Роль / Назначение", style="white")
        table.add_column("Статус", style="bold")
        table.add_column("Запусков", style="yellow")
        table.add_column("Посл. активность", style="dim")

        for ag in agent_registry.all_agents():
            status_style = "green" if ag.status in ("IDLE", "SUCCESS") else "red" if ag.status == "ERROR" else "yellow"
            table.add_row(
                ag.agent_id,
                ag.name,
                ag.role,
                f"[{status_style}]{ag.status}[/]",
                str(ag.execution_count),
                ag.last_run or "Еще не запускался",
            )

        self.console.print(table)

        self.console.print("\nОпции:")
        self.console.print("  [1] Запустить полный координированный цикл арбитража (Orchestrator Cycle)")
        self.console.print("  [2] Вернуться в главное меню")
        choice = Prompt.ask("Выбор", choices=["1", "2"], default="2")

        if choice == "1":
            auto_buy = Confirm.ask("Разрешить автоматическую покупку одобренных лотов?", default=False)
            with self.console.status("[bold green]Оркестратор координирует работу агентов...[/bold green]"):
                res = await orchestrator.run_pipeline_cycle(auto_purchase=auto_buy)

            self.console.print("\n[bold cyan]Результаты цикла арбитража:[/bold cyan]")
            self.console.print(f"  • Найдено кандидатов: [yellow]{res.get('scanned_candidates', 0)}[/]")
            self.console.print(f"  • Прошли проверку и оценку: [green]{res.get('pricing_approved', 0)}[/]")
            self.console.print(f"  • Выполнено покупок: [cyan]{res.get('purchases_executed', 0)}[/]")
            self.console.print(f"  • Создано черновиков перепродажи: [magenta]{res.get('resales_drafted', 0)}[/]")
            if res.get("errors"):
                self.console.print(f"[red]Ошибки: {'; '.join(res['errors'])}[/red]")
            self.pause()

    # =========================================================================
    # 6. PURCHASES
    # =========================================================================
    async def show_purchases(self):
        self.print_header("6. Управление закупками (Purchases)")
        purchases = await db.get_purchases(limit=30)

        if not purchases:
            self.console.print("[yellow]История покупок пуста.[/yellow]")
        else:
            table = Table(title=f"История покупок (Всего: {len(purchases)})", show_header=True, header_style="bold green")
            table.add_column("#", style="dim")
            table.add_column("ID лота", style="cyan")
            table.add_column("Заголовок", style="white", max_width=40)
            table.add_column("Цена закупки", style="yellow")
            table.add_column("Комиссия", style="dim")
            table.add_column("Статус", style="bold")
            table.add_column("Дата", style="dim")

            for p in purchases:
                st_style = "green" if p["status"] in ("completed", "simulated") else "red"
                table.add_row(
                    str(p["id"]),
                    str(p["item_id"]),
                    p["title"],
                    f"{p['buy_price']:.2f} ₽",
                    f"{p['fee']:.2f} ₽",
                    f"[{st_style}]{p['status']}[/]",
                    str(p["created_at"]),
                )
            self.console.print(table)

        self.console.print("\nДействия:")
        self.console.print("  [1] Совершить прямую покупку по ID лота")
        self.console.print("  [2] Назад в меню")
        choice = Prompt.ask("Выбор", choices=["1", "2"], default="2")

        if choice == "1":
            target_id_str = Prompt.ask("Введите ID лота на LZT Market")
            price_str = Prompt.ask("Цена лота (RUB)")
            if target_id_str.isdigit():
                try:
                    price_dec = Decimal(price_str)
                    confirm = Confirm.ask(f"Подтвердить покупку лота #{target_id_str} за {price_dec:.2f} RUB?", default=True)
                    if confirm:
                        with self.console.status("[cyan]Выполнение покупки...[/cyan]"):
                            succ, msg, rec = await purchase_manager.execute_purchase(
                                item_id=int(target_id_str),
                                title=f"Telegram Account #{target_id_str}",
                                price=price_dec,
                                operator_confirmed=True,
                            )
                        if succ:
                            self.console.print(f"[bold green]✔ {msg}[/bold green]")
                        else:
                            self.console.print(f"[bold red]✖ {msg}[/bold red]")
                except Exception as e:
                    self.console.print(f"[red]Ошибка: {e}[/red]")
            self.pause()

    # =========================================================================
    # 7. RESALE LISTINGS
    # =========================================================================
    async def show_resale_listings(self):
        self.print_header("7. Подготовка и перепродажа аккаунтов (Resale Listings)")
        resales = await db.get_resale_items(limit=30)

        if not resales:
            self.console.print("[yellow]Список лотов перепродажи пуст.[/yellow]")
        else:
            table = Table(title=f"Инвентарь перепродажи (Всего: {len(resales)})", show_header=True, header_style="bold magenta")
            table.add_column("ID", style="dim")
            table.add_column("Лот", style="cyan")
            table.add_column("Заголовок для маркета", style="white", max_width=40)
            table.add_column("Цена закупки", style="yellow")
            table.add_column("Цена продажи", style="bold green")
            table.add_column("Статус", style="bold")

            for r in resales:
                st_style = "cyan" if r["status"] == "draft" else "green" if r["status"] == "published" else "bold yellow"
                table.add_row(
                    str(r["id"]),
                    str(r["item_id"]),
                    r["title"],
                    f"{r['original_price']:.2f} ₽",
                    f"{r['target_price']:.2f} ₽",
                    f"[{st_style}]{r['status']}[/]",
                )
            self.console.print(table)

        self.console.print("\nДействия:")
        self.console.print("  [1] Опубликовать черновик по ID")
        self.console.print("  [2] Пометить лот как проданный (Зафиксировать прибыль)")
        self.console.print("  [3] Назад в меню")
        choice = Prompt.ask("Выбор", choices=["1", "2", "3"], default="3")

        if choice == "1":
            rid = Prompt.ask("Введите ID черновика")
            if rid.isdigit():
                with self.console.status("[cyan]Публикация лота на LZT Market...[/cyan]"):
                    succ, msg, _ = await resale_manager.publish_resale(int(rid))
                if succ:
                    self.console.print(f"[bold green]✔ {msg}[/bold green]")
                else:
                    self.console.print(f"[bold red]✖ {msg}[/bold red]")
            self.pause()
        elif choice == "2":
            rid = Prompt.ask("Введите ID проданного лота")
            if rid.isdigit():
                await db.update_resale_status(int(rid), "sold")
                # Credit profit to ledger
                r_item = next((it for it in resales if it["id"] == int(rid)), None)
                if r_item:
                    payout = Decimal(str(r_item["target_price"])) * (Decimal("1.0") - (settings.RESALE_FEE_PERCENT / Decimal("100.0")))
                    await db.add_ledger_entry("sale", payout, f"Sale of lot #{r_item['item_id']}", f"SALE-{r_item['item_id']}")
                self.console.print("[bold green]✔ Статус обновлён на 'sold'. Прибыль зачислена в ведомость.[/bold green]")
            self.pause()

    # =========================================================================
    # 8. FINANCE
    # =========================================================================
    async def show_finance(self):
        self.print_header("8. Финансовая ведомость и баланс (Finance)")
        summary = await finance_manager.get_financial_summary()
        entries = await finance_manager.get_recent_transactions(limit=20)

        # Overview
        self.console.print(
            f"Текущий баланс: [bold green]{summary['current_balance']:.2f} RUB[/] | "
            f"Потрачено сегодня: [yellow]{summary['spent_today']:.2f} RUB[/] / [dim]{summary['daily_limit']:.2f} RUB[/] | "
            f"Остаток лимита: [cyan]{summary['daily_headroom']:.2f} RUB[/]"
        )

        table = Table(title="Последние транзакции в книге учёта (Ledger)", show_header=True, header_style="bold blue")
        table.add_column("ID", style="dim")
        table.add_column("Тип", style="bold")
        table.add_column("Сумма", style="white")
        table.add_column("Баланс после", style="cyan")
        table.add_column("Описание", style="dim", max_width=45)
        table.add_column("Дата", style="dim")

        for e in entries:
            amt_val = float(e["amount"])
            amt_style = "green" if amt_val > 0 else "red"
            table.add_row(
                str(e["id"]),
                e["tx_type"].upper(),
                f"[{amt_style}]{amt_val:+.2f} ₽[/]",
                f"{float(e['balance_after']):.2f} ₽",
                e["description"],
                str(e["created_at"]),
            )

        self.console.print(table)

        if settings.APP_MODE == "simulation":
            self.console.print("\nДействия (Песочница):")
            self.console.print("  [1] Пополнить виртуальный баланс")
            self.console.print("  [2] Назад")
            c = Prompt.ask("Выбор", choices=["1", "2"], default="2")
            if c == "1":
                amt_str = Prompt.ask("Сумма для пополнения (RUB)", default="5000.0")
                new_b = await finance_manager.add_funds(Decimal(amt_str), "Manual Sandbox Top-up")
                self.console.print(f"[green]Баланс успешно пополнен. Новый баланс: {new_b:.2f} RUB[/green]")
                self.pause()
        else:
            self.pause()

    # =========================================================================
    # 9. SETTINGS
    # =========================================================================
    async def show_settings(self):
        self.print_header("9. Настройки и конфигурация (Settings)")

        table = Table(title="Текущая конфигурация", show_header=True, header_style="bold cyan")
        table.add_column("Параметр", style="cyan")
        table.add_column("Значение", style="yellow")

        table.add_row("APP_MODE", settings.APP_MODE.upper())
        table.add_row("SIMULATION_MODE", str(settings.SIMULATION_MODE))
        table.add_row("LIVE_PURCHASE_ENABLED", str(settings.LIVE_PURCHASE_ENABLED))
        table.add_row("LZT API Token", "******" if settings.get_token() else "[red]Не задан[/red]")
        table.add_row("Дневной бюджет (MAX_DAILY_BUDGET)", f"{settings.MAX_DAILY_BUDGET:.2f} RUB")
        table.add_row("Макс. цена покупки (MAX_PURCHASE_PRICE)", f"{settings.MAX_PURCHASE_PRICE:.2f} RUB")
        table.add_row("Мин. ROI (MIN_ROI_PERCENT)", f"{settings.MIN_ROI_PERCENT:.2f}%")
        table.add_row("Мин. прибыль (MIN_NET_PROFIT)", f"{settings.MIN_NET_PROFIT:.2f} RUB")
        table.add_row("Подтверждение покупок", str(settings.MANUAL_PURCHASE_CONFIRMATION))
        table.add_row("LLM Provider", settings.LLM_PROVIDER)
        table.add_row("База данных", str(settings.DATABASE_PATH))

        self.console.print(table)

        self.console.print("\nОпции:")
        self.console.print("  [1] Переключить режим (Simulation <-> Live)")
        self.console.print("  [2] Изменить лимиты бюджета и покупок")
        self.console.print("  [3] Запустить Setup Wizard (Мастер первоначальной настройки)")
        self.console.print("  [4] Назад в главное меню")

        choice = Prompt.ask("Выбор", choices=["1", "2", "3", "4"], default="4")

        if choice == "1":
            new_mode = "live" if settings.APP_MODE == "simulation" else "simulation"
            if new_mode == "live" and not settings.get_token():
                self.console.print("[red]Нельзя включить LIVE режим без действующего LZT API Token![/red]")
                self.pause()
                return

            confirm = Confirm.ask(f"Переключить режим работы на '{new_mode.upper()}'?", default=True)
            if confirm:
                save_env_file({
                    "APP_MODE": new_mode,
                    "SIMULATION_MODE": str(new_mode == "simulation"),
                    "LIVE_PURCHASE_ENABLED": str(new_mode == "live"),
                })
                self.console.print(f"[green]Режим успешно изменён на {new_mode.upper()}![/green]")
                self.pause()

        elif choice == "2":
            max_d = Prompt.ask("Максимальный дневной бюджет (RUB)", default=str(settings.MAX_DAILY_BUDGET))
            max_p = Prompt.ask("Максимальная цена аккаунта (RUB)", default=str(settings.MAX_PURCHASE_PRICE))
            min_r = Prompt.ask("Минимальный ROI %", default=str(settings.MIN_ROI_PERCENT))
            min_p = Prompt.ask("Минимальная чистая прибыль (RUB)", default=str(settings.MIN_NET_PROFIT))

            save_env_file({
                "MAX_DAILY_BUDGET": str(Decimal(max_d)),
                "MAX_PURCHASE_PRICE": str(Decimal(max_p)),
                "MIN_ROI_PERCENT": str(Decimal(min_r)),
                "MIN_NET_PROFIT": str(Decimal(min_p)),
            })
            self.console.print("[green]Финансовые лимиты успешно сохранены в .env![/green]")
            self.pause()

        elif choice == "3":
            await run_setup_wizard()

    # =========================================================================
    # 10. API CONNECTION
    # =========================================================================
    async def show_api_connection(self):
        self.print_header("10. Проверка подключения к LZT Market API")

        with self.console.status("[cyan]Тестирование сетевого соединения и авторизации...[/cyan]"):
            start = time.perf_counter()
            success, msg, data = await api_client.test_connection()
            latency = (time.perf_counter() - start) * 1000

        table = Table(title="Диагностика API соединения", show_header=True, header_style="bold green")
        table.add_column("Параметр", style="cyan")
        table.add_column("Значение", style="white")

        table.add_row("Base URL", settings.LZT_API_BASE_URL)
        table.add_row("Время отклика (Latency)", f"{latency:.1f} ms")
        table.add_row("Статус авторизации", "[green]OK[/green]" if success else f"[red]FAIL ({msg})[/red]")

        if success and "user" in data:
            user = data["user"]
            table.add_row("Пользователь LZT", str(user.get("username", "Unknown")))
            table.add_row("Баланс аккаунта", f"{float(user.get('balance', 0)):.2f} {user.get('currency', 'rub').upper()}")
            table.add_row("Холд", f"{float(user.get('hold', 0)):.2f}")

        table.add_row("Режим работы", settings.APP_MODE.upper())
        self.console.print(table)
        self.pause()

    # =========================================================================
    # 11. LOGS
    # =========================================================================
    async def show_logs(self):
        self.print_header("11. Системные журналы (Logs)")
        level_filter = Prompt.ask("Фильтр по уровню (INFO, WARNING, ERROR или Enter для всех)", default="").strip().upper()
        lvl = level_filter if level_filter in ("INFO", "WARNING", "ERROR") else None

        logs = await db.get_recent_logs(level=lvl, limit=40)
        if not logs:
            self.console.print("[yellow]Журнал пуст.[/yellow]")
        else:
            table = Table(title=f"Журнал событий (Записей: {len(logs)})", show_header=True, header_style="bold yellow")
            table.add_column("Время", style="dim")
            table.add_column("Уровень", style="bold")
            table.add_column("Модуль", style="cyan")
            table.add_column("Сообщение", style="white")

            for l in logs:
                lvl_style = "green" if l["level"] == "INFO" else "yellow" if l["level"] == "WARNING" else "bold red"
                table.add_row(
                    str(l["created_at"]),
                    f"[{lvl_style}]{l['level']}[/]",
                    l["module"] or "system",
                    l["message"],
                )
            self.console.print(table)

        self.pause()

    # =========================================================================
    # 12. DIAGNOSTICS
    # =========================================================================
    async def show_diagnostics(self):
        self.print_header("12. Диагностика системы и окружения (Diagnostics)")

        with self.console.status("[cyan]Выполнение полного диагностического сканирования...[/cyan]"):
            results = await run_diagnostics()

        table = Table(title="Результаты диагностики", show_header=True, header_style="bold magenta")
        table.add_column("Категория", style="cyan")
        table.add_column("Проверка", style="white")
        table.add_column("Статус", style="bold")
        table.add_column("Подробности", style="dim")

        for c in results["checks"]:
            st = c["status"]
            st_style = "bold green" if st == "PASS" else "bold yellow" if st in ("WARN", "INFO") else "bold red"
            table.add_row(
                c["category"],
                c["name"],
                f"[{st_style}]{st}[/]",
                c["details"],
            )

        self.console.print(table)
        overall_style = "bold green" if results["overall_status"] == "OK" else "bold yellow" if results["overall_status"] == "WARNING" else "bold red"
        self.console.print(f"\nОбщий статус готовности системы: [{overall_style}]{results['overall_status']}[/]")
        self.pause()

    # =========================================================================
    # MAIN MENU LOOP
    # =========================================================================
    async def main_menu_loop(self):
        while True:
            self.print_header("Главное меню терминала")

            menu_table = Table(show_header=False, box=None, padding=(0, 2))
            menu_table.add_column("Col1", style="white")
            menu_table.add_column("Col2", style="white")

            menu_table.add_row(
                "[bold cyan] 1.[/bold cyan] Главная панель (Dashboard)",
                "[bold cyan] 7.[/bold cyan] Перепродажа (Resale Listings)"
            )
            menu_table.add_row(
                "[bold cyan] 2.[/bold cyan] Сканер рынка (Market Scanner)",
                "[bold cyan] 8.[/bold cyan] Финансы и ведомость (Finance)"
            )
            menu_table.add_row(
                "[bold cyan] 3.[/bold cyan] Анализ лота (Listing Analysis)",
                "[bold cyan] 9.[/bold cyan] Настройки (Settings)"
            )
            menu_table.add_row(
                "[bold cyan] 4.[/bold cyan] Калькулятор прибыли (Profit Calc)",
                "[bold cyan]10.[/bold cyan] API Соединение (API Connection)"
            )
            menu_table.add_row(
                "[bold cyan] 5.[/bold cyan] Агенты и Оркестратор (Agents)",
                "[bold cyan]11.[/bold cyan] Журнал логов (Logs)"
            )
            menu_table.add_row(
                "[bold cyan] 6.[/bold cyan] Управление закупками (Purchases)",
                "[bold cyan]12.[/bold cyan] Диагностика (Diagnostics)"
            )
            menu_table.add_row(
                "",
                "[bold red] 0.[/bold red] Выход из программы (Exit)"
            )

            self.console.print(Panel(menu_table, title="[bold]Выберите нужный пункт[/bold]", border_style="cyan"))

            choice = Prompt.ask("Введите номер команды", choices=[str(i) for i in range(13)], default="1")

            try:
                if choice == "1":
                    await self.show_dashboard()
                elif choice == "2":
                    await self.show_market_scanner()
                elif choice == "3":
                    await self.show_listing_analysis()
                elif choice == "4":
                    await self.show_profit_calculator()
                elif choice == "5":
                    await self.show_agents()
                elif choice == "6":
                    await self.show_purchases()
                elif choice == "7":
                    await self.show_resale_listings()
                elif choice == "8":
                    await self.show_finance()
                elif choice == "9":
                    await self.show_settings()
                elif choice == "10":
                    await self.show_api_connection()
                elif choice == "11":
                    await self.show_logs()
                elif choice == "12":
                    await self.show_diagnostics()
                elif choice == "0":
                    self.console.print("\n[yellow]Завершение работы LZT Terminal Trader. До свидания![/yellow]")
                    break
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]Прервано пользователем.[/yellow]")
                break
            except Exception as e:
                self.console.print(f"\n[bold red]Произошла ошибка при выполнении операции:[/] {e}")
                self.pause()


terminal_ui = TerminalUI()
