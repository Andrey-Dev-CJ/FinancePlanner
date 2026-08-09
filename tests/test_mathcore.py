import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pytest

from mathcore.models import (add_months, expand_events, Event, EventStatus)
from mathcore.forecast import ForecastEngine
from mathcore.deviation import DeviationDetector
from mathcore.sprint import SprintEngine
from scenario import build_config


class TestModels:
    def test_add_months_simple(self):
        assert add_months(datetime(2026, 8, 10), 1) == datetime(2026, 9, 10)

    def test_add_months_clamp(self):
        assert add_months(datetime(2027, 1, 31), 1) == datetime(2027, 2, 28)

    def test_expand_single(self):
        ev = Event('e1', 'X', 100, '2026-09-05')
        occ = expand_events([ev], datetime(2026, 8, 1), datetime(2026, 9, 30))
        assert len(occ) == 1 and occ[0]['date'] == '2026-09-05'
        assert expand_events([ev], datetime(2026, 9, 6), datetime(2026, 10, 30)) == []

    def test_expand_monthly_series(self):
        ev = Event('e1', 'Закуп', 3500, '2026-08-10',
                   repeat='monthly', repeat_end='2027-01-31')
        occ = expand_events([ev], datetime(2026, 8, 6), datetime(2027, 1, 31))
        assert [o['date'] for o in occ] == ['2026-08-10', '2026-09-10', '2026-10-10',
                                            '2026-11-10', '2026-12-10', '2027-01-10']

    def test_expand_done_ignored(self):
        ev = Event('e1', 'X', 100, '2026-09-05', status=EventStatus.DONE)
        assert expand_events([ev], datetime(2026, 8, 1), datetime(2026, 12, 31)) == []


class TestForecastConventions:
    def test_start_day_income_not_added(self):
        daily = ForecastEngine(build_config()).calculate_daily_balance(datetime(2026, 8, 5), 3)
        assert daily[0]['income_received'] == 0

    def test_first_cycle_fixed_skipped(self):
        # 06–19.08: только переменные (14×100) и события (3500+1500), без постоянных
        daily = ForecastEngine(build_config()).calculate_daily_balance(datetime(2026, 8, 6), 13)
        assert sum(p['expenses_paid'] for p in daily) == pytest.approx(1400 + 5000)

    def test_payday_income(self):
        daily = ForecastEngine(build_config()).calculate_daily_balance(datetime(2026, 8, 6), 15)
        d20 = next(p for p in daily if p['date'] == '2026-08-20')
        assert d20['income_received'] == 44000

    def test_required_reserve_is_guarantee(self):
        # Если на руках >= необходимого резерва — дефицит невозможен; если меньше — будет
        start, days = datetime(2026, 8, 6), 60
        base = ForecastEngine(build_config()).calculate_daily_balance(start, days)
        need = DeviationDetector(build_config()).calculate_required_reserve(base)[0]

        f_ok = ForecastEngine(build_config(need)).calculate_daily_balance(start, days)
        assert min(p['balance'] for p in f_ok) >= 0

        f_bad = ForecastEngine(build_config(need - 100)).calculate_daily_balance(start, days)
        assert min(p['balance'] for p in f_bad) < 0


class TestSprints:
    def test_current_sprint(self):
        sp = SprintEngine(build_config()).calculate_sprints(datetime(2026, 8, 6), 2)
        assert sp[0]['is_current'] and sp[0]['carry_in'] == 9745
        assert sp[0]['fixed_expenses'] == 0  # текущий цикл уже оплачен


class TestScenarioUntilJan2027:
    START, END = datetime(2026, 8, 6), datetime(2027, 1, 31)

    def _daily(self):
        days = (self.END - self.START).days
        return ForecastEngine(build_config()).calculate_daily_balance(self.START, days)

    def test_deficit_only_end_of_august(self):
        neg = [p['date'] for p in self._daily() if p['balance'] < 0]
        assert neg and all('2026-08-29' <= d <= '2026-09-04' for d in neg)

    def test_depth_limited(self):
        assert min(p['balance'] for p in self._daily()) >= -1300

    def test_month_ends(self):
        b = {p['date']: p['balance'] for p in self._daily()}
        assert b['2026-10-31'] == pytest.approx(12965, abs=50)
        assert b['2026-11-30'] == pytest.approx(31405, abs=50)
        assert b['2026-12-31'] == pytest.approx(49745, abs=50)
        assert b['2027-01-31'] == pytest.approx(68085, abs=50)

    def test_monthly_surplus_nov_jan(self):
        b = {p['date']: p['balance'] for p in self._daily()}
        assert b['2026-12-31'] - b['2026-11-30'] == pytest.approx(18340, abs=50)