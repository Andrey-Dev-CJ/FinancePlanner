"""
Flask-приложение с авторизацией и per-user данными в SQLite.
ТОЛЬКО вызывает MathCore. Никакой бизнес-логики здесь нет.
Единственный источник правды — база данных (instance/finance.db).
"""
import os
import uuid
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash

from mathcore import MathCore
from models_db import db, User, UserConfig
from mathcore.db_adapter import load_config_from_db, save_config_to_db
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FINPLAN_SECRET', 'dev-secret-change-me')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///finance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
db.init_app(app)
migrate = Migrate(app, db)

def _sqlite_pragmas(dbapi_conn, _record):
    """Настройки SQLite на каждое новое соединение."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")   # чтения не блокируют записи
    cur.execute("PRAGMA synchronous=NORMAL") # быстрее, безопасно при WAL
    cur.execute("PRAGMA busy_timeout=5000")  # ждать до 5с вместо "database is locked"
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


# ================= ВСПОМОГАТЕЛЬНОЕ =================

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'uid' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapped

def get_core() -> MathCore:
    """Per-request экземпляр MathCore: свежий из БД на каждый запрос.
    В пределах одного запроса — один и тот же объект (быстро и консистентно).
    Между запросами и воркерами состояние не живёт → можно масштабироваться."""
    core = getattr(g, 'mathcore', None)
    if core is None:
        uid = session['uid']
        user_config = db.session.get(UserConfig, uid)
        if not user_config:
            user_config = UserConfig(user_id=uid, initial_balance=0.0,
                                     pay_days=[5, 20], reserve_envelopes={})
            db.session.add(user_config)
            db.session.commit()
        core = MathCore(load_config_from_db(user_config))
        g.mathcore = core
    return core

def save_core():
    """Сохраняет изменения MathCore ТЕКУЩЕГО запроса в БД."""
    uid = session['uid']
    user_config = db.session.get(UserConfig, uid)
    if not user_config:
        user_config = UserConfig(user_id=uid, pay_days=[5, 20], reserve_envelopes={})
        db.session.add(user_config)
        db.session.flush()
    save_config_to_db(db.session, user_config, get_core().config)

# ================= СТРАНИЦЫ =================

@app.route('/')
def index():
    if 'uid' not in session:
        return render_template('login.html')
    return render_template('index.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/sw.js')
def service_worker():
    resp = app.send_static_file('sw.js')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

# ================= AUTH (всё через БД) =================

@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if len(username) < 3:
        return jsonify({'error': 'Логин — минимум 3 символа'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Пароль — минимум 6 символов'}), 400
    if not data.get('consent'):
        return jsonify({'error': 'Для создания аккаунта нужно согласие с политикой конфиденциальности'}), 400
    if db.session.execute(select(User).filter_by(username=username)).scalar_one_or_none():
        return jsonify({'error': 'Такой логин уже занят'}), 400

    uid = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)
    user = User(id=uid, username=username,
                password_hash=generate_password_hash(password),
                created_at=now, consent_at=now)
    db.session.add(user)
    db.session.add(UserConfig(user_id=uid, initial_balance=0.0,
                              pay_days=[5, 20], reserve_envelopes={}))
    db.session.commit()

    session['uid'] = uid
    session['username'] = username
    return jsonify({'status': 'ok'})

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    user = db.session.execute(select(User).filter_by(username=username)).scalar_one_or_none()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Неверный логин или пароль'}), 400
    session['uid'] = user.id
    session['username'] = user.username
    return jsonify({'status': 'ok'})

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'ok'})

@app.route('/auth/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.json or {}
    current = data.get('current_password', '')
    new = data.get('new_password', '')
    if len(new) < 6:
        return jsonify({'error': 'Новый пароль — минимум 6 символов'}), 400
    user = db.session.get(User, session['uid'])
    if not user or not check_password_hash(user.password_hash, current):
        return jsonify({'error': 'Текущий пароль неверен'}), 400
    user.password_hash = generate_password_hash(new)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/auth/change-username', methods=['POST'])
@login_required
def change_username():
    data = request.json or {}
    new_name = (data.get('new_username') or '').strip()
    password = data.get('password', '')
    if len(new_name) < 3:
        return jsonify({'error': 'Логин — минимум 3 символа'}), 400
    if db.session.execute(select(User).filter_by(username=new_name)).scalar_one_or_none():
        return jsonify({'error': 'Такой логин уже занят'}), 400
    user = db.session.get(User, session['uid'])
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Пароль неверен'}), 400
    user.username = new_name
    db.session.commit()
    session['username'] = new_name
    return jsonify({'status': 'ok'})

@app.route('/auth/delete-account', methods=['POST'])
@login_required
def delete_account():
    data = request.json or {}
    user = db.session.get(User, session['uid'])
    if not user or not check_password_hash(user.password_hash, data.get('password', '')):
        return jsonify({'error': 'Пароль неверен'}), 400
    uid = user.id
    cfg = db.session.get(UserConfig, uid)
    if cfg:
        db.session.delete(cfg)   # cascade удалит доходы/расходы/события
    db.session.delete(user)
    db.session.commit()
    session.clear()
    return jsonify({'status': 'ok'})

@app.route('/api/me')
@login_required
def me():
    return jsonify({'username': session.get('username', '')})

# ================= ДАННЫЕ =================

@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    core = get_core()
    return jsonify({
        'summary': core.get_summary(),
        'income_sources': [
            {'id': i.id, 'name': i.name, 'amount': i.amount,
             'day_of_month': i.day_of_month, 'active': i.active}
            for i in core.config.income_sources
        ],
        'fixed_expenses': [
            {'id': e.id, 'name': e.name, 'amount': e.amount,
             'day_of_month': e.day_of_month, 'active': e.active,
             'category': e.category}
            for e in core.config.fixed_expenses
        ],
        'variable_expenses': [
            {'id': e.id, 'name': e.name, 'amount_per_month': e.amount_per_month,
             'category': e.category, 'active': e.active}
            for e in core.config.variable_expenses
        ],
        'events': [
            {'id': e.id, 'name': e.name, 'amount': e.amount,
             'date': e.date, 'status': e.status.value,
             'category': e.category, 'notes': e.notes,
             'repeat': e.repeat, 'repeat_end': e.repeat_end}
            for e in core.config.events
        ],
        'pay_days': core.config.pay_schedule.pay_days,
        'initial_balance': core.config.initial_balance,
        'reserve_envelopes': core.config.reserve_envelopes
    })

@app.route('/api/config', methods=['POST'])
@login_required
def update_config():
    core = get_core()
    core.update_config(request.json)
    save_core()
    return jsonify({'status': 'ok'})

# ================= MATHCORE ЭНДПОИНТЫ =================

@app.route('/api/forecast', methods=['POST'])
@login_required
def get_forecast():
    days = (request.json or {}).get('days', 90)
    return jsonify(get_core().get_forecast(days=days))

@app.route('/api/sprints', methods=['POST'])
@login_required
def get_sprints():
    count = (request.json or {}).get('count', 6)
    return jsonify(get_core().get_sprints(count=count))

@app.route('/api/current-sprint', methods=['GET'])
@login_required
def get_current_sprint():
    return jsonify(get_core().get_current_sprint())

@app.route('/api/risks', methods=['GET'])
@login_required
def get_risks():
    return jsonify(get_core().get_risks())

@app.route('/api/summary', methods=['GET'])
@login_required
def get_summary():
    return jsonify(get_core().get_summary())

@app.route('/api/what-if', methods=['POST'])
@login_required
def what_if():
    params = request.json or {}
    return jsonify(get_core().what_if(
        extra_income=params.get('extra_income', 0),
        extra_expense=params.get('extra_expense', 0),
        skip_event_ids=params.get('skip_event_ids', [])
    ))

# ================= CRUD =================

@app.route('/api/income', methods=['POST'])
@login_required
def add_income():
    from mathcore.models import IncomeSource
    data = request.json
    item = IncomeSource(
        id=str(uuid.uuid4())[:8], name=data['name'],
        amount=float(data['amount']),
        day_of_month=int(data['day_of_month']),
        active=data.get('active', True))
    get_core().config.income_sources.append(item)
    save_core()
    return jsonify({'status': 'ok', 'id': item.id})

@app.route('/api/income/<item_id>', methods=['DELETE'])
@login_required
def delete_income(item_id):
    core = get_core()
    core.config.income_sources = [i for i in core.config.income_sources if i.id != item_id]
    save_core()
    return jsonify({'status': 'ok'})

@app.route('/api/fixed-expenses', methods=['POST'])
@login_required
def add_fixed():
    from mathcore.models import FixedExpense
    data = request.json
    item = FixedExpense(
        id=str(uuid.uuid4())[:8], name=data['name'],
        amount=float(data['amount']),
        day_of_month=int(data['day_of_month']),
        active=data.get('active', True),
        category=data.get('category', 'fixed'))
    get_core().config.fixed_expenses.append(item)
    save_core()
    return jsonify({'status': 'ok', 'id': item.id})

@app.route('/api/fixed-expenses/<item_id>', methods=['DELETE'])
@login_required
def delete_fixed(item_id):
    core = get_core()
    core.config.fixed_expenses = [e for e in core.config.fixed_expenses if e.id != item_id]
    save_core()
    return jsonify({'status': 'ok'})

@app.route('/api/variable-expenses', methods=['POST'])
@login_required
def add_variable():
    from mathcore.models import VariableExpense
    data = request.json
    item = VariableExpense(
        id=str(uuid.uuid4())[:8], name=data['name'],
        amount_per_month=float(data['amount_per_month']),
        category=data.get('category', 'general'),
        active=data.get('active', True))
    get_core().config.variable_expenses.append(item)
    save_core()
    return jsonify({'status': 'ok', 'id': item.id})

@app.route('/api/variable-expenses/<item_id>', methods=['DELETE'])
@login_required
def delete_variable(item_id):
    core = get_core()
    core.config.variable_expenses = [e for e in core.config.variable_expenses if e.id != item_id]
    save_core()
    return jsonify({'status': 'ok'})

@app.route('/api/events', methods=['POST'])
@login_required
def add_event():
    from mathcore.models import Event, EventStatus
    data = request.json
    item = Event(
        id=str(uuid.uuid4())[:8], name=data['name'],
        amount=float(data['amount']), date=data['date'],
        status=EventStatus(data.get('status', 'planned')),
        category=data.get('category', 'event'),
        notes=data.get('notes', ''),
        repeat=data.get('repeat', ''),
        repeat_end=data.get('repeat_end', ''))
    get_core().config.events.append(item)
    save_core()
    return jsonify({'status': 'ok', 'id': item.id})

@app.route('/api/events/<item_id>', methods=['PUT'])
@login_required
def update_event(item_id):
    from mathcore.models import EventStatus
    data = request.json
    for ev in get_core().config.events:
        if ev.id == item_id:
            if 'name' in data: ev.name = data['name']
            if 'amount' in data: ev.amount = float(data['amount'])
            if 'date' in data: ev.date = data['date']
            if 'category' in data: ev.category = data['category']
            if 'status' in data: ev.status = EventStatus(data['status'])
            if 'repeat' in data: ev.repeat = data['repeat']
            if 'repeat_end' in data: ev.repeat_end = data['repeat_end']
            break
    save_core()
    return jsonify({'status': 'ok'})

@app.route('/api/events/<item_id>', methods=['DELETE'])
@login_required
def delete_event(item_id):
    core = get_core()
    core.config.events = [e for e in core.config.events if e.id != item_id]
    save_core()
    return jsonify({'status': 'ok'})

@app.route('/api/events/<item_id>/status', methods=['PUT'])
@login_required
def update_event_status(item_id):
    from mathcore.models import EventStatus
    for ev in get_core().config.events:
        if ev.id == item_id:
            ev.status = EventStatus((request.json or {}).get('status', 'planned'))
            break
    save_core()
    return jsonify({'status': 'ok'})

@app.route('/api/balance', methods=['PUT'])
@login_required
def update_balance():
    core = get_core()
    core.config.initial_balance = float((request.json or {}).get('balance', 0))
    core.config.reserve_envelopes = (request.json or {}).get('reserve_envelopes', {})
    save_core()
    return jsonify({'status': 'ok'})


with app.app_context():
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        event.listen(db.engine, 'connect', _sqlite_pragmas)  # вешаем ДО create_all
    db.create_all()


if __name__ == '__main__':
    print("=" * 50)
    print("  💰 Финансовый Планировщик (multi-user, SQLite)")
    print("  📍 http://localhost:5000")
    print("  🧮 MathCore v1.1 + auth + DB")
    print("=" * 50)
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('FINPLAN_PORT', 5000)),
        debug=os.environ.get('FINPLAN_DEBUG', '0') == '1'
    )