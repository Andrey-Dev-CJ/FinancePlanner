"""
MathCore Models — чистые структуры данных.
Никакой логики, только описание сущностей.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime
import calendar as _cal

class ExpenseType(Enum):
    FIXED = "fixed"           # Постоянные (ЖКХ, кредит)
    VARIABLE = "variable"     # Переменные (еда, бензин)
    EVENT = "event"           # Разовые события (свадьба, рыбалка)


class EventStatus(Enum):
    PLANNED = "planned"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class IncomeSource:
    """Источник дохода."""
    id: str
    name: str
    amount: float
    day_of_month: int          # День выплаты (1-31)
    active: bool = True
    description: str = ""


@dataclass
class FixedExpense:
    """Постоянный расход."""
    id: str
    name: str
    amount: float
    day_of_month: int          # День списания
    active: bool = True
    category: str = "fixed"


@dataclass
class VariableExpense:
    """Переменный ежемесячный расход."""
    id: str
    name: str
    amount_per_month: float
    category: str = "general"
    active: bool = True


@dataclass
class Event:
    """Разовое событие/трата."""
    id: str
    name: str
    amount: float
    date: str                  # ISO format: YYYY-MM-DD
    status: EventStatus = EventStatus.PLANNED
    category: str = "event"
    notes: str = ""
    repeat: str = ""          # "" или "monthly"
    repeat_end: str = ""      # конец серии (включительно), ISO YYYY-MM-DD


@dataclass
class PaySchedule:
    """Расписание выплат."""
    pay_days: list = field(default_factory=lambda: [5, 20])
    
    def is_payday(self, day: int) -> bool:
        return day in self.pay_days


@dataclass
class FinancialConfig:
    """Полная конфигурация — всё, что вводит пользователь."""
    income_sources: list = field(default_factory=list)       # List[IncomeSource]
    fixed_expenses: list = field(default_factory=list)       # List[FixedExpense]
    variable_expenses: list = field(default_factory=list)    # List[VariableExpense]
    events: list = field(default_factory=list)               # List[Event]
    pay_schedule: PaySchedule = field(default_factory=PaySchedule)
    initial_balance: float = 0.0
    reserve_envelopes: dict = field(default_factory=dict)    # {"credit": 21500}
    
    # Вычисляемые свойства
    @property
    def monthly_income(self) -> float:
        return sum(i.amount for i in self.income_sources if i.active)
    
    @property
    def monthly_fixed(self) -> float:
        return sum(e.amount for e in self.fixed_expenses if e.active)
    
    @property
    def monthly_variable(self) -> float:
        return sum(e.amount_per_month for e in self.variable_expenses if e.active)
    
    @property
    def monthly_total_expenses(self) -> float:
        return self.monthly_fixed + self.monthly_variable
    
    @property
    def monthly_surplus(self) -> float:
        return self.monthly_income - self.monthly_total_expenses
    
    @property
    def pending_events(self) -> list:
        return [e for e in self.events if e.status == EventStatus.PLANNED]
    
    @property
    def total_pending_events_cost(self) -> float:
        return sum(e.amount for e in self.pending_events)

    
def add_months(d: datetime, n: int) -> datetime:
    mi = d.month - 1 + n
    year = d.year + mi // 12
    month = mi % 12 + 1
    day = min(d.day, _cal.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def expand_events(events, start: datetime, end: datetime) -> list:
    """Раскрывает события (включая месячные серии) в списки дат в окне [start, end]."""
    out = []
    for ev in events:
        if ev.status != EventStatus.PLANNED:
            continue
        base = datetime.strptime(ev.date, '%Y-%m-%d')
        if ev.repeat == 'monthly' and ev.repeat_end:
            limit = datetime.strptime(ev.repeat_end, '%Y-%m-%d')
            for n in range(60):
                occ = add_months(base, n)
                if occ > limit or occ > end:
                    break
                if occ >= start:
                    out.append({'id': ev.id, 'name': ev.name, 'amount': ev.amount,
                                'date': occ.strftime('%Y-%m-%d'),
                                'category': ev.category, 'repeat': True})
        else:
            if start <= base <= end:
                out.append({'id': ev.id, 'name': ev.name, 'amount': ev.amount,
                            'date': ev.date, 'category': ev.category, 'repeat': False})
    return out