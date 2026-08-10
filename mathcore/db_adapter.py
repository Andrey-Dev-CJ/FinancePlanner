"""
Адаптер между SQLAlchemy-моделями (БД) и MathCore dataclass-ами.
MathCore не знает про БД, БД не знает про MathCore — этот модуль переводит между ними.
"""
from datetime import datetime
from sqlalchemy.orm import Session

from .models import (
    FinancialConfig, IncomeSource, FixedExpense, 
    VariableExpense, Event, EventStatus, PaySchedule
)


def load_config_from_db(user_config) -> FinancialConfig:
    """
    Загружает FinancialConfig из SQLAlchemy UserConfig.
    
    Args:
        user_config: SQLAlchemy модель UserConfig (из models_db)
    
    Returns:
        FinancialConfig dataclass для MathCore
    """
    cfg = FinancialConfig()
    
    # Базовые поля
    cfg.initial_balance = user_config.initial_balance or 0.0
    cfg.pay_schedule = PaySchedule(pay_days=user_config.pay_days or [5, 20])
    cfg.reserve_envelopes = user_config.reserve_envelopes or {}
    
    # Доходы
    for src in user_config.income_sources:
        cfg.income_sources.append(IncomeSource(
            id=src.id,
            name=src.name,
            amount=src.amount,
            day_of_month=src.day_of_month,
            active=src.active
        ))
    
    # Постоянные расходы
    for exp in user_config.fixed_expenses:
        cfg.fixed_expenses.append(FixedExpense(
            id=exp.id,
            name=exp.name,
            amount=exp.amount,
            day_of_month=exp.day_of_month,
            category=exp.category or 'fixed',
            active=exp.active
        ))
    
    # Переменные расходы
    for var in user_config.variable_expenses:
        cfg.variable_expenses.append(VariableExpense(
            id=var.id,
            name=var.name,
            amount_per_month=var.amount_per_month,
            category=var.category or 'general',
            active=var.active
        ))
    
    # События (самое сложное — конвертация дат и enum)
    for ev in user_config.events:
        cfg.events.append(Event(
            id=ev.id,
            name=ev.name,
            amount=ev.amount,
            date=ev.date.strftime('%Y-%m-%d'),  # Date → строка
            status=EventStatus(ev.status),  # строка → Enum
            category=ev.category or 'event',
            notes=ev.notes or '',
            repeat=ev.repeat or '',
            repeat_end=ev.repeat_end.strftime('%Y-%m-%d') if ev.repeat_end else ''
        ))
    
    return cfg


def save_config_to_db(session: Session, user_config, cfg: FinancialConfig):
    """
    Сохраняет изменения из FinancialConfig обратно в БД.
    
    Стратегия: удаляем старые записи и создаём новые (проще, чем diff/upsert).
    Для небольших объёмов данных (десятки записей) это оптимально.
    
    Args:
        session: SQLAlchemy session
        user_config: SQLAlchemy модель UserConfig
        cfg: FinancialConfig dataclass из MathCore
    """
    # Обновляем базовые поля
    user_config.initial_balance = cfg.initial_balance
    user_config.pay_days = cfg.pay_schedule.pay_days
    user_config.reserve_envelopes = cfg.reserve_envelopes
    user_config.updated_at = datetime.utcnow()
    
    # Удаляем старые связанные записи (cascade должен сделать это автоматически,
    # но явно для надёжности)
    for inc in list(user_config.income_sources):
        session.delete(inc)
    for exp in list(user_config.fixed_expenses):
        session.delete(exp)
    for var in list(user_config.variable_expenses):
        session.delete(var)
    for ev in list(user_config.events):
        session.delete(ev)
    
    session.flush()  # Применяем удаления перед добавлением новых
    
    # Импортируем SQLAlchemy-модели здесь, чтобы избежать circular import
    from models_db import IncomeSource as DBIncomeSource
    from models_db import FixedExpense as DBFixedExpense
    from models_db import VariableExpense as DBVariableExpense
    from models_db import Event as DBEvent
    
    # Создаём новые записи из MathCore dataclass-ов
    
    # Доходы
    for src in cfg.income_sources:
        db_inc = DBIncomeSource(
            id=src.id,
            config_id=user_config.user_id,
            name=src.name,
            amount=src.amount,
            day_of_month=src.day_of_month,
            active=src.active
        )
        session.add(db_inc)
    
    # Постоянные расходы
    for exp in cfg.fixed_expenses:
        db_exp = DBFixedExpense(
            id=exp.id,
            config_id=user_config.user_id,
            name=exp.name,
            amount=exp.amount,
            day_of_month=exp.day_of_month,
            category=exp.category,
            active=exp.active
        )
        session.add(db_exp)
    
    # Переменные расходы
    for var in cfg.variable_expenses:
        db_var = DBVariableExpense(
            id=var.id,
            config_id=user_config.user_id,
            name=var.name,
            amount_per_month=var.amount_per_month,
            category=var.category,
            active=var.active
        )
        session.add(db_var)
    
    # События (конвертация строк в Date объекты)
    for ev in cfg.events:
        # Парсим дату из строки
        try:
            event_date = datetime.strptime(ev.date, '%Y-%m-%d').date()
        except ValueError:
            continue  # Пропускаем события с некорректной датой
        
        # Парсим repeat_end (если есть)
        repeat_end = None
        if ev.repeat_end:
            try:
                repeat_end = datetime.strptime(ev.repeat_end, '%Y-%m-%d').date()
            except ValueError:
                repeat_end = None
        
        db_ev = DBEvent(
            id=ev.id,
            config_id=user_config.user_id,
            name=ev.name,
            amount=ev.amount,
            date=event_date,
            status=ev.status.value,  # Enum → строка
            category=ev.category,
            notes=ev.notes,
            repeat=ev.repeat,
            repeat_end=repeat_end
        )
        session.add(db_ev)
    
    session.commit()