"""Реальный план до января 2027 — общий для тестов и отчёта."""
from mathcore.models import (FinancialConfig, IncomeSource, FixedExpense,
                             VariableExpense, Event, PaySchedule)


def build_config(initial_balance=9745.0):
    cfg = FinancialConfig(
        initial_balance=initial_balance,
        pay_schedule=PaySchedule(pay_days=[5, 20]),
    )
    cfg.income_sources = [
        IncomeSource('inc1', 'Аванс', 39000, 5),
        IncomeSource('inc2', 'Зарплата', 44000, 20),
    ]
    cfg.fixed_expenses = [
        FixedExpense('f1', 'Кредит (с аванса)', 21500, 5),
        FixedExpense('f2', 'Кредит (с зарплаты)', 21500, 20),
        FixedExpense('f3', 'ЖКХ', 3500, 5),
        FixedExpense('f4', 'Хостинги', 900, 6),
        FixedExpense('f5', 'Интернет', 1000, 20),
        FixedExpense('f6', 'VPN', 150, 20),
        FixedExpense('f7', 'Моб. связь', 1510, 27),
    ]
    cfg.variable_expenses = [VariableExpense('v1', 'Бензин', 3000)]

    ev, n = [], 0
    def add(name, amount, date, cat='еда'):
        nonlocal n
        n += 1
        ev.append(Event(f'e{n}', name, amount, date, category=cat))

    # Разовые
    add('Мини-закуп', 3500, '2026-08-10')
    add('Поездка в ГУАП', 1500, '2026-08-16', 'учёба')
    add('Пошлина загранпаспорт', 6000, '2026-08-21', 'документы')
    add('Свадебный подарок', 5000, '2026-08-28', 'подарки')
    add('Стрижка', 2300, '2026-08-28', 'себя')
    add('БСК', 1500, '2026-08-29', 'учёба')
    add('Букет на свадьбу', 4000, '2026-09-05', 'подарки')
    add('Рыбалка Сегозеро', 13000, '2026-09-26', 'отдых')
    add('Посылка в Чехию', 6000, '2026-10-10', 'подарки')
    # Регулярные закупы каждый месяц до января 2027
    for y, m in [(2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1)]:
        if (y, m) != (2026, 8):
            add('Мини-закуп', 3500, f'{y:04d}-{m:02d}-10')
        add('Большой закуп', 8000, f'{y:04d}-{m:02d}-22')

    cfg.events = ev
    return cfg