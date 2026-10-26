"""
First-Run Setup Wizard for LZT Terminal Trader.
Guides users through an interactive 5-step onboarding process:
1. Welcome & Mode Selection
2. LZT Market API Token & Live Test
3. AI Analysis Provider
4. Financial Safety Limits
5. Summary & .env Persistence
"""

import asyncio
from decimal import Decimal
import getpass
from typing import Any, Dict
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from config import save_env_file, settings
from app.api_client import api_client

console = Console()


async def run_setup_wizard() -> bool:
    """
    Executes the 5-step interactive setup wizard.
    Returns True if configuration was successfully saved, False if cancelled.
    """
    console.clear()
    console.print(
        Panel.fit(
            "[bold cyan]LZT TERMINAL TRADER[/bold cyan] — [bold yellow]Первоначальная настройка[/bold yellow]\n"
            "[dim]Добро пожаловать в систему автоматизации и арбитража LZT Market.[/dim]",
            border_style="cyan"
        )
    )

    config_updates: Dict[str, Any] = {}

    # =========================================================================
    # ШАГ 1: Выбор режима работы (Simulation vs Live)
    # =========================================================================
    console.print("\n[bold green]ШАГ 1/5: Режим работы (Operating Mode)[/bold green]")
    console.print(
        "  [1] [bold yellow]SIMULATION (Песочница)[/] — Без риска, без реальных покупок, реалистичные демо-данные. (Рекомендуется для старта)\n"
        "  [2] [bold red]LIVE (Реальный)[/] — Подключение к реальному API lzt.market с реальным балансом."
    )
    mode_choice = Prompt.ask("Выберите режим", choices=["1", "2"], default="1")
    if mode_choice == "2":
        config_updates["APP_MODE"] = "live"
        config_updates["SIMULATION_MODE"] = "False"
        config_updates["LIVE_PURCHASE_ENABLED"] = "True"
        is_live = True
    else:
        config_updates["APP_MODE"] = "simulation"
        config_updates["SIMULATION_MODE"] = "True"
        config_updates["LIVE_PURCHASE_ENABLED"] = "False"
        is_live = False

    # =========================================================================
    # ШАГ 2: LZT Market API Token
    # =========================================================================
    console.print("\n[bold green]ШАГ 2/5: LZT Market API Токен[/bold green]")
    console.print(
        "[dim]Токен можно получить в профиле LZT Market: Настройки -> Доступ к API.[/dim]\n"
        "[dim]Если токена нет прямо сейчас, нажмите Enter для запуска в режиме симуляции.[/dim]"
    )

    token_input = Prompt.ask("Введите LZT API Token (или оставьте пустым)", default="")
    token_input = token_input.strip()

    if token_input:
        config_updates["LZT_API_TOKEN"] = token_input
        config_updates["LZT_API_KEY"] = token_input

        # Тестирование подключения
        with console.status("[cyan]Проверка токена через lzt.market API...[/cyan]"):
            # Временно применим токен для теста
            settings.LZT_API_TOKEN = token_input
            settings.APP_MODE = "live"
            settings.SIMULATION_MODE = False
            success, msg, data = await api_client.test_connection()

        if success:
            console.print(f"[bold green]✔ Подключение успешно![/] Пользователь: [cyan]{data.get('username')}[/], Баланс: [yellow]{data.get('balance', 0):.2f} RUB[/]")
        else:
            console.print(f"[bold red]✖ Ошибка авторизации:[/] {msg}")
            fallback_sim = Confirm.ask("Переключиться в безопасный режим SIMULATION?", default=True)
            if fallback_sim:
                config_updates["APP_MODE"] = "simulation"
                config_updates["SIMULATION_MODE"] = "True"
                config_updates["LIVE_PURCHASE_ENABLED"] = "False"
                is_live = False
    else:
        config_updates["LZT_API_TOKEN"] = ""
        config_updates["LZT_API_KEY"] = ""
        config_updates["APP_MODE"] = "simulation"
        config_updates["SIMULATION_MODE"] = "True"
        config_updates["LIVE_PURCHASE_ENABLED"] = "False"
        is_live = False
        console.print("[yellow]Токен не указан. Активирован режим симуляции (Sandbox).[/yellow]")

    # =========================================================================
    # ШАГ 3: Настройка AI / LLM анализатора
    # =========================================================================
    console.print("\n[bold green]ШАГ 3/5: Анализатор текста и описаний (AI / Heuristic)[/bold green]")
    console.print(
        "  [1] [bold green]Встроенный эвристический движок (Local / Heuristic)[/] — 100% бесплатно, быстро, защита от инъекций. (Рекомендуется)\n"
        "  [2] OpenAI (GPT-4o-mini)\n"
        "  [3] Google Gemini\n"
        "  [4] Anthropic Claude"
    )
    ai_choice = Prompt.ask("Выберите модуль анализа", choices=["1", "2", "3", "4"], default="1")
    if ai_choice == "1":
        config_updates["LLM_PROVIDER"] = "local"
        config_updates["LLM_API_KEY"] = ""
    elif ai_choice == "2":
        config_updates["LLM_PROVIDER"] = "openai"
        config_updates["LLM_API_KEY"] = Prompt.ask("Введите OpenAI API Key", default="")
        config_updates["LLM_MODEL"] = Prompt.ask("Модель", default="gpt-4o-mini")
    elif ai_choice == "3":
        config_updates["LLM_PROVIDER"] = "gemini"
        config_updates["LLM_API_KEY"] = Prompt.ask("Введите Gemini API Key", default="")
        config_updates["LLM_MODEL"] = Prompt.ask("Модель", default="gemini-1.5-flash")
    elif ai_choice == "4":
        config_updates["LLM_PROVIDER"] = "anthropic"
        config_updates["LLM_API_KEY"] = Prompt.ask("Введите Anthropic API Key", default="")
        config_updates["LLM_MODEL"] = Prompt.ask("Модель", default="claude-3-5-haiku-latest")

    # =========================================================================
    # ШАГ 4: Финансовые лимиты и безопасность
    # =========================================================================
    console.print("\n[bold green]ШАГ 4/5: Финансовые лимиты и безопасность[/bold green]")
    max_daily = Prompt.ask("Максимальный дневной бюджет (RUB)", default="3000.0")
    max_price = Prompt.ask("Максимальная цена за 1 аккаунт (RUB)", default="350.0")
    min_roi = Prompt.ask("Минимальный ROI % для покупки", default="25.0")
    min_profit = Prompt.ask("Минимальная чистая прибыль (RUB)", default="50.0")
    confirm_buy = Confirm.ask("Требовать ручное подтверждение оператора перед покупкой?", default=True)

    config_updates["MAX_DAILY_BUDGET"] = str(Decimal(max_daily))
    config_updates["MAX_PURCHASE_PRICE"] = str(Decimal(max_price))
    config_updates["MIN_ROI_PERCENT"] = str(Decimal(min_roi))
    config_updates["MIN_NET_PROFIT"] = str(Decimal(min_profit))
    config_updates["MANUAL_PURCHASE_CONFIRMATION"] = str(confirm_buy)

    # Пути
    config_updates["DATABASE_PATH"] = "data/trader.db"
    config_updates["LOGS_PATH"] = "logs/trader.log"

    # =========================================================================
    # ШАГ 5: Итоги и сохранение
    # =========================================================================
    console.print("\n[bold green]ШАГ 5/5: Сводка конфигурации[/bold green]")
    table = Table(title="Параметры для сохранения в .env", show_header=True, header_style="bold magenta")
    table.add_column("Параметр", style="cyan")
    table.add_column("Значение", style="yellow")

    for k, v in config_updates.items():
        val_display = "******" if "KEY" in k or "TOKEN" in k and v else v
        table.add_row(k, str(val_display))

    console.print(table)

    save_ok = Confirm.ask("Сохранить настройки в файл .env и запустить терминал?", default=True)
    if save_ok:
        save_env_file(config_updates)
        console.print("[bold green]✔ Файл .env успешно сохранён![/bold green]\n")
        await asyncio.sleep(1.0)
        return True
    else:
        console.print("[yellow]Настройка отменена.[/yellow]\n")
        return False
