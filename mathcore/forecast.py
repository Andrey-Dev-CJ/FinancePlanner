"""
MathCore Forecast — прогнозирование баланса по дням.
Чистая математика: вход = конфиг, выход = массив точек.
"""
from datetime import datetime, timedelta, date
import calendar as _cal
from typing import List, Dict
from .models import FinancialConfig, EventStatus, expand_events


class ForecastEngine:
    """Движок прогнозирования баланса."""

    def __init__(self, config: FinancialConfig):
        self.config = config

    # ================= ОСНОВНОЙ РАСЧЁТ =================

    def calculate_daily_balance(self, start_date: datetime, days: int = 90) -> List[Dict]:
        """
        Баланс по дням.

        Соглашения:
        - initial_balance = деньги на руках СЕЙЧАС, включая сегодняшнюю выплату;
          поэтому в день старта (i == 0) доходы НЕ прибавляются.
        - Постоянные расходы внутри первого цикла (до первой следующей выплаты)
          НЕ списываются: они оплачены с открывающей выплаты и уже учтены
          в initial_balance. Со второго цикла списываются в свой день.
        """
        balance = self.config.initial_balance
        results = []

        income_map = self._build_income_map()
        fixed_map = self._build_fixed_expense_map()
        events_map = self._build_events_map(start_date, start_date + timedelta(days=days))
        variable_daily = self.config.monthly_variable / 30.0

        first_cycle_end = self._first_cycle_end(start_date)

        for i in range(days + 1):
            current_date = start_date + timedelta(days=i)
            day_of_month = current_date.day
            date_str = current_date.strftime('%Y-%m-%d')

            daily_income = 0.0
            daily_expenses = 0.0
            day_events = []

            # 1) ДОХОДЫ — во все дни, кроме дня старта
            if i > 0 and day_of_month in income_map:
                daily_income = income_map[day_of_month]
                balance += daily_income

            # 2) ПОСТОЯННЫЕ РАСХОДЫ — со второго цикла
            if current_date >= first_cycle_end and day_of_month in fixed_map:
                daily_expenses += fixed_map[day_of_month]
                balance -= fixed_map[day_of_month]

            # 3) ПЕРЕМЕННЫЕ РАСХОДЫ — равномерно каждый день
            balance -= variable_daily
            daily_expenses += variable_daily

            # 4) СОБЫТИЯ — в свою дату (включая сегодня), серии раскрыты
            if date_str in events_map:
                for ev in events_map[date_str]:
                    balance -= ev['amount']
                    daily_expenses += ev['amount']
                    day_events.append(ev['name'])

            results.append({
                'date': date_str,
                'day_label': current_date.strftime('%d.%m'),
                'balance': round(balance, 2),
                'is_payday': day_of_month in income_map,
                'has_event': len(day_events) > 0,
                'event_names': day_events,
                'income_received': daily_income,
                'expenses_paid': round(daily_expenses, 2)
            })

        return results

    def calculate_monthly_projection(self, months: int = 6) -> List[Dict]:
        """Проекция по месяцам (агрегированная)."""
        projections = []
        balance = self.config.initial_balance

        for m in range(months):
            month_income = self.config.monthly_income
            month_expenses = self.config.monthly_total_expenses
            month_events_cost = self._get_month_events_cost(m)

            balance += month_income - month_expenses - month_events_cost

            projections.append({
                'month_offset': m,
                'income': month_income,
                'fixed_expenses': self.config.monthly_fixed,
                'variable_expenses': self.config.monthly_variable,
                'events_cost': month_events_cost,
                'net': month_income - month_expenses - month_events_cost,
                'cumulative_balance': round(balance, 2)
            })

        return projections

    # ================= СЛУЖЕБНЫЕ =================

    def _first_cycle_end(self, start_date: datetime) -> datetime:
        """Первая выплата СТРОГО после start_date — конец текущего цикла."""
        pay_days = set(self.config.pay_schedule.pay_days)
        current = start_date + timedelta(days=1)
        for _ in range(62):
            if current.day in pay_days:
                return current
            current += timedelta(days=1)
        return start_date + timedelta(days=30)

    def _build_income_map(self) -> Dict[int, float]:
        """День месяца -> сумма дохода."""
        income_map = {}
        for inc in self.config.income_sources:
            if inc.active:
                day = min(inc.day_of_month, 31)
                income_map[day] = income_map.get(day, 0) + inc.amount
        return income_map

    def _build_fixed_expense_map(self) -> Dict[int, float]:
        """День месяца -> сумма постоянных расходов."""
        fixed_map = {}
        for exp in self.config.fixed_expenses:
            if exp.active:
                day = min(exp.day_of_month, 31)
                fixed_map[day] = fixed_map.get(day, 0) + exp.amount
        return fixed_map

    def _build_events_map(self, start: datetime, end: datetime) -> Dict[str, List[Dict]]:
        """Дата -> список событий (включая раскрытые месячные серии)."""
        events_map = {}
        for occ in expand_events(self.config.events, start, end):
            events_map.setdefault(occ['date'], []).append({
                'name': occ['name'],
                'amount': occ['amount']
            })
        return events_map

    def _get_month_events_cost(self, month_offset: int) -> float:
        """
        Сумма событий в месяце со смещением month_offset от текущего.
        Месячные серии (repeat='monthly') раскрываются через expand_events:
        месяц получает все вхождения серии, а не только базовую дату.
        """
        today = date.today()
        mi = today.month - 1 + month_offset
        year = today.year + mi // 12
        month = mi % 12 + 1

        start = datetime(year, month, 1)
        end = datetime(year, month, _cal.monthrange(year, month)[1])

        return sum(occ['amount'] for occ in expand_events(self.config.events, start, end))