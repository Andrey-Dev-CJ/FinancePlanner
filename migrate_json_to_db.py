"""
Миграция данных из JSON-файлов в SQLite базу данных.
Запуск: python migrate_json_to_db.py
"""
import os
import json
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app import app, db
from models_db import User, UserConfig, IncomeSource, FixedExpense, VariableExpense, Event

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')


def migrate_user(username: str, user_data: dict):
    """Мигрирует одного пользователя из JSON в БД."""
    uid = user_data['uid']
    password_hash = user_data.get('hash', '')
    consent_at = user_data.get('consent_at')
    
    # Проверяем, существует ли пользователь (используем новый API)
    existing_user = db.session.get(User, uid)
    if existing_user:
        print(f'  🔄 Пользователь {username} (uid={uid}) уже существует — обновляем данные')
    else:
        print(f'  📥 Миграция пользователя: {username} (uid={uid})')
        # Создаём пользователя (используем timezone-aware datetime)
        user = User(
            id=uid,
            username=username,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc),
            consent_at=datetime.fromisoformat(consent_at) if consent_at else None
        )
        db.session.add(user)
    
    # Путь к конфигу пользователя
    config_path = os.path.join(DATA_DIR, uid, 'config.json')
    
    if not os.path.exists(config_path):
        print(f'  ⚠️  Конфиг не найден: {config_path} — создаём пустой')
        user_config = db.session.get(UserConfig, uid)
        if not user_config:
            user_config = UserConfig(
                user_id=uid,
                initial_balance=0.0,
                pay_days=[5, 20],
                reserve_envelopes={}
            )
            db.session.add(user_config)
        db.session.commit()
        return True
    
    # Загружаем JSON-конфиг
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg_data = json.load(f)
    
    # Удаляем старый конфиг пользователя (если есть)
    old_config = db.session.get(UserConfig, uid)
    if old_config:
        db.session.delete(old_config)
        db.session.flush()
    
    # Создаём UserConfig
    user_config = UserConfig(
        user_id=uid,
        initial_balance=cfg_data.get('initial_balance', 0.0),
        pay_days=cfg_data.get('pay_days', [5, 20]),
        reserve_envelopes=cfg_data.get('reserve_envelopes', {})
    )
    db.session.add(user_config)
    
    # Мигрируем доходы
    income_count = 0
    for inc_data in cfg_data.get('income_sources', []):
        income = IncomeSource(
            id=inc_data.get('id', f'inc_{income_count}'),
            config_id=uid,
            name=inc_data['name'],
            amount=float(inc_data['amount']),
            day_of_month=int(inc_data['day_of_month']),
            active=inc_data.get('active', True)
        )
        db.session.add(income)
        income_count += 1
    
    # Мигрируем постоянные расходы
    fixed_count = 0
    for exp_data in cfg_data.get('fixed_expenses', []):
        fixed = FixedExpense(
            id=exp_data.get('id', f'fe_{fixed_count}'),
            config_id=uid,
            name=exp_data['name'],
            amount=float(exp_data['amount']),
            day_of_month=int(exp_data['day_of_month']),
            category=exp_data.get('category', 'fixed'),
            active=exp_data.get('active', True)
        )
        db.session.add(fixed)
        fixed_count += 1
    
    # Мигрируем переменные расходы
    var_count = 0
    for var_data in cfg_data.get('variable_expenses', []):
        variable = VariableExpense(
            id=var_data.get('id', f'var_{var_count}'),
            config_id=uid,
            name=var_data['name'],
            amount_per_month=float(var_data['amount_per_month']),
            category=var_data.get('category', 'general'),
            active=var_data.get('active', True)
        )
        db.session.add(variable)
        var_count += 1
    
    # Мигрируем события
    event_count = 0
    for ev_data in cfg_data.get('events', []):
        # Парсим дату из строки
        date_str = ev_data.get('date', '')
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f'  ⚠️  Некорректная дата события: {date_str} — пропускаем')
            continue
        
        # Парсим repeat_end (если есть)
        repeat_end_str = ev_data.get('repeat_end', '')
        repeat_end = None
        if repeat_end_str:
            try:
                repeat_end = datetime.strptime(repeat_end_str, '%Y-%m-%d').date()
            except ValueError:
                print(f'  ⚠️  Некорректная дата repeat_end: {repeat_end_str}')
        
        event = Event(
            id=ev_data.get('id', f'ev_{event_count}'),
            config_id=uid,
            name=ev_data['name'],
            amount=float(ev_data['amount']),
            date=event_date,
            status=ev_data.get('status', 'planned'),
            category=ev_data.get('category', 'event'),
            notes=ev_data.get('notes', ''),
            repeat=ev_data.get('repeat', ''),
            repeat_end=repeat_end
        )
        db.session.add(event)
        event_count += 1
    
    # Коммитим все изменения для этого пользователя
    db.session.commit()
    
    print(f'  ✅ Мигрировано: {income_count} доходов, {fixed_count} постоянных, '
          f'{var_count} переменных, {event_count} событий')
    return True


def main():
    """Основная функция миграции."""
    print('=' * 60)
    print('  🗄️  Миграция данных: JSON → SQLite')
    print('=' * 60)
    
    # Проверяем существование файла пользователей
    if not os.path.exists(USERS_FILE):
        print(f'❌ Файл не найден: {USERS_FILE}')
        print('   Убедитесь, что приложение запускалось хотя бы один раз.')
        return
    
    # Загружаем список пользователей
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users_data = json.load(f)
    
    print(f'\n📊 Найдено пользователей: {len(users_data)}')
    print('-' * 60)
    
    # Создаём таблицы БД (если ещё не созданы)
    with app.app_context():
        db.create_all()
        print('✅ Таблицы БД готовы\n')
        
        migrated = 0
        skipped = 0
        
        # Мигрируем каждого пользователя
        for username, user_data in users_data.items():
            try:
                if migrate_user(username, user_data):
                    migrated += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f'  ❌ Ошибка при миграции {username}: {e}')
                db.session.rollback()
                skipped += 1
        
        print('-' * 60)
        print(f'\n🎉 Миграция завершена!')
        print(f'   ✅ Успешно мигрировано: {migrated}')
        print(f'   ⚠️  Пропущено: {skipped}')
        print(f'   📁 База данных: finance.db')
        print('\n💡 Теперь можно удалить старые JSON-файлы:')
        print(f'   rm -rf {DATA_DIR}/')
        print(f'   (или сохраните их как бэкап)')


if __name__ == '__main__':
    main()