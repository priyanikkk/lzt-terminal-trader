# Рабочий процесс и Конечный Автомат (Workflow FSM)

## 1. Схема жизненного цикла лота

Каждое найденное объявление проходит строгий конечный автомат состояний (`ListingStateMachine`):

```mermaid
stateDiagram-v2
    [*] --> DISCOVERED : Обнаружение через MarketScanner

    DISCOVERED --> INSPECTED : Проверка характеристик (ListingInspector)
    DISCOVERED --> REJECTED : Технический дефект / Спамблок
    DISCOVERED --> FAILED : Ошибка исполнения

    INSPECTED --> PRICED : Экономический расчёт (PricingAgent)
    INSPECTED --> REJECTED : Нарушение правил / Промпт-инъекция

    PRICED --> RISK_APPROVED : Одобрение рисков (RiskAssessmentAgent)
    PRICED --> REJECTED : Низкий ROI / Ниже порога прибыли

    RISK_APPROVED --> PURCHASE_PENDING : Блокировка мьютекса & Лимиты
    RISK_APPROVED --> REJECTED : Вето по риску продавца

    PURCHASE_PENDING --> PURCHASE_CONFIRMED : Успешная покупка
    PURCHASE_PENDING --> UNKNOWN_TRANSACTION_STATUS : Сетевой сбой / 5xx
    PURCHASE_PENDING --> FAILED : Ошибка API маркета

    UNKNOWN_TRANSACTION_STATUS --> PURCHASE_CONFIRMED : Ручная сверка / Статус активен
    UNKNOWN_TRANSACTION_STATUS --> FAILED : Сделка отменена
    UNKNOWN_TRANSACTION_STATUS --> REQUIRES_REVIEW : Требуется вмешательство

    PURCHASE_CONFIRMED --> RESALE_PREPARED : Подготовка заголовка и описания (ResaleAgent)

    RESALE_PREPARED --> LISTED : Успешная публикация на маркете
    RESALE_PREPARED --> REQUIRES_REVIEW : Ручной апрув публикации (если включен)

    LISTED --> SOLD : Покупка другим пользователем
    LISTED --> CANCELLED : Снято с продажи

    REJECTED --> [*]
    SOLD --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

---

## 2. Гарантии целостности переходов

1. **Невозможность пропуска этапов:** Попытка прямого перехода из `DISCOVERED` в `PURCHASE_PENDING` вызывает немедленное исключение `InvalidStateTransitionError`.
2. **Терминальные состояния:** Состояния `REJECTED`, `SOLD`, `FAILED` и `CANCELLED` являются терминальными; из них невозможно перевести лот в активные фазы без явного создания нового цикла.
3. **Обработка неоднозначности (`UNKNOWN_TRANSACTION_STATUS`):**
   - Если во время вызова метода `fast-buy` произошёл сетевой тайм-аут, обрыв сокета или HTTP 500/502/504, система категорически **запрещает немедленный повторный запрос**.
   - Лот помечается как `UNKNOWN_TRANSACTION_STATUS`.
   - Система выполняет предварительный вызов `check_item_status` или ожидает подтверждения статуса на стороне баланса, исключая списание средств за две покупки одного лота.
