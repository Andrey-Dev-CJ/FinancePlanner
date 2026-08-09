"""Отчёт по сценарию до января 2027: что почём."""
from datetime import datetime
from collections import defaultdict
from scenario import build_config
from mathcore.forecast import ForecastEngine
from mathcore.deviation import DeviationDetector

START = datetime(2026, 8, 6)
END = datetime(2027, 1, 31)


def main():
    cfg = build_config()
    daily = ForecastEngine(cfg).calculate_daily_balance(START, (END - START).days)
    det = DeviationDetector(cfg)
    required = det.calculate_required_reserve(daily)

    print(f'Старт {START:%d.%m.%Y} · баланс {cfg.initial_balance:,.0f} ₽ · '
          f'необходимый резерв {required[0]:,.0f} ₽')
    for d in det.detect_deficits(daily):
        print(f'  ⚠️ дефицит {d["date"]}: {d["balance"]:,.0f} ₽, '
              f'восстановление {d["recovery_days"]} дн.')

    months = {}
    for p in daily:
        m = months.setdefault(p['date'][:7],
                              {'inc': 0, 'exp': 0, 'min': 1e18, 'min_d': '', 'end': 0})
        m['inc'] += p['income_received']
        m['exp'] += p['expenses_paid']
        if p['balance'] < m['min']:
            m['min'], m['min_d'] = p['balance'], p['date']
        m['end'] = p['balance']

    print(f'\n{"Месяц":<8}{"Доход":>10}{"Расход":>10}{"Мин. баланс":>16}{"Конец месяца":>14}')
    for k, m in months.items():
        print(f'{k:<8}{m["inc"]:>10,.0f}{m["exp"]:>10,.0f}'
              f'{m["min"]:>10,.0f} ({m["min_d"][8:10]}.{m["min_d"][5:7]}){m["end"]:>14,.0f}')

    totals = defaultdict(float)
    for e in cfg.events:
        totals[e.name] += e.amount
    print('\nСобытия за период:')
    for name, s in sorted(totals.items(), key=lambda x: -x[1]):
        print(f'  {name:<24}{s:>10,.0f} ₽')


if __name__ == '__main__':
    main()