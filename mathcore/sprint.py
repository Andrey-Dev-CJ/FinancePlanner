"""
MathCore Sprint — расчёт спринтов (периодов между выплатами).
"""
from datetime import datetime, timedelta
from typing import List, Dict
from .models import FinancialConfig, EventStatus, expand_events


class SprintEngine:
    """Расчёт спринтов на основе расписания выплат."""

    def __init__(self, config: FinancialConfig):
        self.config = config
        self.pay_days = sorted(config.pay_schedule.pay_days)

    def calculate_sprints(self, start_date: datetime = None, count: int = 6) -> List[Dict]:
        """
        Спринт = период от выплаты до выплаты.
        Первый спринт — всегда ТЕКУЩИЙ (идёт прямо сейчас).
        """
        if start_date is None:
            start_date = datetime.now()
        today = datetime.now()

        sprints = []
        sprint_start = self._prev_payday(start_date)

        for i in range(count):
            sprint_end = self._next_payday(sprint_start + timedelta(days=1))
            is_current = sprint_start <= today < sprint_end

            # Для текущего спринта учитываем только БУДУЩЕЕ:
            # доходы/постоянные — строго после сегодня,
            # события — начиная с сегодня.
            if is_current:
                income_start = today + timedelta(days=1)
                fixed = self._get_fixed_between(today + timedelta(days=1), sprint_end)
                var_start = today
            else:
                income_start = sprint_start
                fixed = self._get_fixed_between(sprint_start, sprint_end)
                var_start = sprint_start

            sprint_income = self._get_income_between(income_start, sprint_end)
            days = (sprint_end - var_start).days
            sprint_variable = (self.config.monthly_variable / 30.0) * days
            sprint_events = self._get_events_between(today if is_current else sprint_start, sprint_end)
            events_total = sum(e['amount'] for e in sprint_events)

            carry_in = self.config.initial_balance if is_current else 0.0
            available = carry_in + sprint_income - fixed - sprint_variable - events_total

            if available < 0:
                status = 'deficit'
            elif available < self.config.monthly_income * 0.05:
                status = 'tight'
            else:
                status = 'ok'

            sprints.append({
                'sprint_number': i + 1,
                'start_date': sprint_start.strftime('%Y-%m-%d'),
                'end_date': sprint_end.strftime('%Y-%m-%d'),
                'start_label': sprint_start.strftime('%d.%m'),
                'end_label': sprint_end.strftime('%d.%m'),
                'days': days,
                'is_current': is_current,
                'carry_in': round(carry_in, 2),
                'income_expected': sprint_income,
                'fixed_expenses': round(fixed, 2),
                'variable_expenses': round(sprint_variable, 2),
                'events': sprint_events,
                'events_total': events_total,
                'available_budget': round(available, 2),
                'status': status
            })

            sprint_start = sprint_end

        return sprints

    def get_current_sprint(self) -> Dict:
        """Текущий (идущий прямо сейчас) спринт."""
        sprints = self.calculate_sprints(count=1)
        return sprints[0] if sprints else {}

    # ===== Служебные =====

    def _prev_payday(self, from_date: datetime) -> datetime:
        """Ближайшая выплата НАЗАД (включая сам день)."""
        current = from_date
        for _ in range(62):
            if current.day in self.pay_days:
                return current
            current -= timedelta(days=1)
        return from_date

    def _next_payday(self, from_date: datetime) -> datetime:
        """Ближайшая выплата вперёд (включая сам день)."""
        current = from_date
        for _ in range(62):
            if current.day in self.pay_days:
                return current
            current += timedelta(days=1)
        return from_date + timedelta(days=15)

    def _get_income_between(self, start: datetime, end: datetime) -> float:
        total = 0
        current = start
        while current < end:
            for inc in self.config.income_sources:
                if inc.active and current.day == inc.day_of_month:
                    total += inc.amount
            current += timedelta(days=1)
        return total

    def _get_fixed_between(self, start: datetime, end: datetime) -> float:
        total = 0
        current = start
        while current < end:
            for exp in self.config.fixed_expenses:
                if exp.active and current.day == exp.day_of_month:
                    total += exp.amount
            current += timedelta(days=1)
        return total

    def _get_events_between(self, start: datetime, end: datetime) -> List[Dict]:
        occ = expand_events(self.config.events, start, end - timedelta(days=1))
        return sorted(occ, key=lambda x: x['date'])