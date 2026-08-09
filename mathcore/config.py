"""
MathCore Config — загрузка и валидация конфигурации.
Поддержка JSON-файлов и программного создания.
"""
import os
import shutil
import json
import uuid
from pathlib import Path
from typing import Optional
from .models import (
    FinancialConfig, IncomeSource, FixedExpense,
    VariableExpense, Event, PaySchedule, EventStatus
)




class ConfigLoader:
    """Загрузка конфигурации из различных источников."""
    
    @staticmethod
    def from_json(filepath: str) -> FinancialConfig:
        """Загружает конфиг из JSON-файла."""
        path = Path(filepath)
        if not path.exists():
            return FinancialConfig()
        
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        
        return ConfigLoader._parse_raw(raw)
    
    @staticmethod
    def from_dict(raw: dict) -> FinancialConfig:
        """Создаёт конфиг из словаря (для API-запросов)."""
        return ConfigLoader._parse_raw(raw)
    
    @staticmethod
    def to_json(config: FinancialConfig, filepath: str):
        """Сохраняет конфиг в JSON с бэкапом предыдущей версии."""
        if os.path.exists(filepath):
            shutil.copy(filepath, filepath + '.bak')
        
        data = {
            'initial_balance': config.initial_balance,
            'reserve_envelopes': config.reserve_envelopes,
            'pay_days': config.pay_schedule.pay_days,
            'income_sources': [
                {'id': i.id, 'name': i.name, 'amount': i.amount,
                'day_of_month': i.day_of_month, 'active': i.active}
                for i in config.income_sources
            ],
            'fixed_expenses': [
                {'id': e.id, 'name': e.name, 'amount': e.amount,
                'day_of_month': e.day_of_month, 'active': e.active,
                'category': e.category}
                for e in config.fixed_expenses
            ],
            'variable_expenses': [
                {'id': e.id, 'name': e.name, 'amount_per_month': e.amount_per_month,
                'category': e.category, 'active': e.active}
                for e in config.variable_expenses
            ],
            'events': [
                {'id': e.id, 'name': e.name, 'amount': e.amount,
                'date': e.date, 'status': e.status.value,
                'category': e.category, 'notes': e.notes,
                'repeat': e.repeat, 'repeat_end': e.repeat_end}
                for e in config.events
            ]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def empty_config() -> FinancialConfig:
        """Пустой конфиг для нового пользователя."""
        return FinancialConfig()
    
    @staticmethod
    def _parse_raw(raw: dict) -> FinancialConfig:
        """Парсит сырой словарь в FinancialConfig."""
        config = FinancialConfig()
        
        config.initial_balance = raw.get('initial_balance', 0)
        config.reserve_envelopes = raw.get('reserve_envelopes', {})
        config.pay_schedule = PaySchedule(
            pay_days=raw.get('pay_days', [5, 20])
        )
        
        for item in raw.get('income_sources', []):
            config.income_sources.append(IncomeSource(
                id=item.get('id', str(uuid.uuid4())[:8]),
                name=item['name'],
                amount=float(item['amount']),
                day_of_month=int(item['day_of_month']),
                active=item.get('active', True)
            ))
        
        for item in raw.get('fixed_expenses', []):
            config.fixed_expenses.append(FixedExpense(
                id=item.get('id', str(uuid.uuid4())[:8]),
                name=item['name'],
                amount=float(item['amount']),
                day_of_month=int(item['day_of_month']),
                active=item.get('active', True),
                category=item.get('category', 'fixed')
            ))
        
        for item in raw.get('variable_expenses', []):
            config.variable_expenses.append(VariableExpense(
                id=item.get('id', str(uuid.uuid4())[:8]),
                name=item['name'],
                amount_per_month=float(item['amount_per_month']),
                category=item.get('category', 'general'),
                active=item.get('active', True)
            ))
        
        for item in raw.get('events', []):
            config.events.append(Event(
                id=item.get('id', str(uuid.uuid4())[:8]),
                name=item['name'],
                amount=float(item['amount']),
                date=item['date'],
                status=EventStatus(item.get('status', 'planned')),
                notes=item.get('notes', ''),
                repeat=item.get('repeat', ''),
                repeat_end=item.get('repeat_end', ''),
                category=item.get('category', 'event')
                
            ))
        
        return config