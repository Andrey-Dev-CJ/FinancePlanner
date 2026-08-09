from .models import FinancialConfig, IncomeSource, FixedExpense, VariableExpense, Event, EventStatus, PaySchedule
from models_db import UserConfig

def load_config_from_db(user_config: UserConfig) -> FinancialConfig:
    """Загружает FinancialConfig из БД для MathCore."""
    cfg = FinancialConfig()
    cfg.initial_balance = user_config.initial_balance
    cfg.pay_schedule = PaySchedule(pay_days=user_config.pay_days or [5, 20])
    cfg.reserve_envelopes = user_config.reserve_envelopes or {}
    
    for src in user_config.income_sources:
        cfg.income_sources.append(IncomeSource(
            id=src.id, name=src.name, amount=src.amount,
            day_of_month=src.day_of_month, active=src.active
        ))
    
    for exp in user_config.fixed_expenses:
        cfg.fixed_expenses.append(FixedExpense(
            id=exp.id, name=exp.name, amount=exp.amount,
            day_of_month=exp.day_of_month, category=exp.category, active=exp.active
        ))
    
    for exp in user_config.variable_expenses:
        cfg.variable_expenses.append(VariableExpense(
            id=exp.id, name=exp.name, amount_per_month=exp.amount_per_month,
            category=exp.category, active=exp.active
        ))
    
    for ev in user_config.events:
        cfg.events.append(Event(
            id=ev.id, name=ev.name, amount=ev.amount,
            date=ev.date.strftime('%Y-%m-%d'),
            status=EventStatus(ev.status),
            category=ev.category, notes=ev.notes,
            repeat=ev.repeat,
            repeat_end=ev.repeat_end.strftime('%Y-%m-%d') if ev.repeat_end else ''
        ))
    
    return cfg

def save_config_to_db(user_config: UserConfig, cfg: FinancialConfig):
    """Сохраняет изменения из MathCore обратно в БД."""
    user_config.initial_balance = cfg.initial_balance
    user_config.pay_days = cfg.pay_schedule.pay_days
    user_config.reserve_envelopes = cfg.reserve_envelopes
    
    # Удаляем старые записи и создаём новые (простой подход)
    # Для продакшена лучше делать upsert/diff
    user_config.income_sources = []
    for src in cfg.income_sources:
        user_config.income_sources.append(IncomeSource(
            id=src.id, name=src.name, amount=src.amount,
            day_of_month=src.day_of_month, active=src.active
        ))
    
    # Аналогично для fixed_expenses, variable_expenses, events
    # ... (код похожий)
    
    db.session.commit()