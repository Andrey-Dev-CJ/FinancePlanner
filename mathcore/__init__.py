"""
MathCore — модуль финансового прогнозирования.

Usage:
    from mathcore import MathCore
    
    core = MathCore.from_config_file('config.json')
    forecast = core.get_forecast(days=90)
    sprints = core.get_sprints(count=6)
    risks = core.get_risks()
"""
from .engine import MathCore
from .models import (
    FinancialConfig, IncomeSource, FixedExpense,
    VariableExpense, Event, PaySchedule, EventStatus
)
from .config import ConfigLoader

__version__ = "1.0.0"
__all__ = [
    'MathCore',
    'FinancialConfig',
    'IncomeSource', 
    'FixedExpense',
    'VariableExpense',
    'Event',
    'PaySchedule',
    'EventStatus',
    'ConfigLoader'
]