"""
Flask-приложение с авторизацией и per-user данными.
ТОЛЬКО вызывает MathCore. Никакой бизнес-логики здесь нет.
"""
import os
import json
import uuid
import shutil
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from mathcore import MathCore

from models_db import User, UserConfig, db
from flask_migrate import Migrate
from mathcore.db_adapter import load_config_from_db, save_config_to_db


_cores = {}


def get_core() -> MathCore:
    uid = session['uid']
    if uid not in _cores:
        user_config = UserConfig.query.get(uid)
        if not user_config:
            user_config = UserConfig(user_id=uid, pay_days=[5, 20])
            db.session.add(user_config)
            db.session.commit()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FINPLAN_SECRET', 'dev-secret-change-me')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
LEGACY_CONFIG = os.path.join(BASE_DIR, 'config.json')
os.makedirs(DATA_DIR, exist_ok=True)


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

# Создать таблицы при первом запуске
with app.app_context():
    db.create_all()

# ================= ПОЛЬЗОВАТЕЛИ И PER-USER ЯДРО =================

def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_users(users: dict):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def user_config_path(uid: str) -> str:
    return os.path.join(DATA_DIR, uid, 'config.json')

_cores = {}

def get_core():
    """Per-user экземпляр MathCore (загрузка из БД)."""
    uid = session['uid']
    if uid not in _cores:
        user_config = db.session.get(UserConfig, uid)
        if not user_config:
            # Создаём пустой конфиг для нового пользователя
            user_config = UserConfig(
                user_id=uid,
                initial_balance=0.0,
                pay_days=[5, 20],
                reserve_envelopes={}
            )
            db.session.add(user_config)
            db.session.commit()
        
        # Загружаем данные из БД в MathCore dataclass-ы
        cfg = load_config_from_db(user_config)
        _cores[uid] = MathCore(cfg)
    
    return _cores[uid]



def save_core():
    """Сохраняет изменения из MathCore обратно в БД."""
    uid = session['uid']
    user_config = db.session.get(UserConfig, uid)
    if not user_config:
        # Создаём пустой конфиг, если его нет
        user_config = UserConfig(user_id=uid, pay_days=[5, 20])
        db.session.add(user_config)
        db.session.flush()
    
    # Конвертируем MathCore dataclass → SQLAlchemy модели и сохраняем
    save_config_to_db(db.session, user_config, _cores[uid].config)

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'uid' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapped

# ================= AUTH =================

@app.route('/')
def index():
    if 'uid' not in session:
        return render_template('login.html')
    return render_template('index.html')

@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if len(username) < 3:
        return jsonify({'error': 'Логин — минимум 3 символа'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Пароль — минимум 6 символов'}), 400
    users = _load_users()
    if username in users:
        return jsonify({'error': 'Такой логин уже занят'}), 400
    first_user = len(users) == 0
    uid = str(uuid.uuid4())[:8]
    users[username] = {'uid': uid, 'hash': generate_password_hash(password)}
    _save_users(users)
    os.makedirs(os.path.join(DATA_DIR, uid), exist_ok=True)
    # Первый пользователь (владелец) автоматически получает старый конфиг
    if first_user and os.path.exists(LEGACY_CONFIG):
        shutil.copy(LEGACY_CONFIG, user_config_path(uid))
    session['uid'] = uid
    session['username'] = username
    return jsonify({'status': 'ok'})

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    user = _load_users().get(username)
    if not user or not check_password_hash(user['hash'], password):
        return jsonify({'error': 'Неверный логин или пароль'}), 400
    session['uid'] = user['uid']
    session['username'] = username
    return jsonify({'status': 'ok'})

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'ok'})


# ================= УПРАВЛЕНИЕ АККАУНТОМ =================

@app.route('/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """Смена пароля: текущий + новый, с проверкой длины."""
    data = request.json or {}
    current = data.get('current_password', '')
    new = data.get('new_password', '')
    if len(new) < 6:
        return jsonify({'error': 'Новый пароль — минимум 6 символов'}), 400
    users = _load_users()
    user = users.get(session['username'])
    if not user or not check_password_hash(user['hash'], current):
        return jsonify({'error': 'Текущий пароль неверен'}), 400
    user['hash'] = generate_password_hash(new)
    _save_users(users)
    return jsonify({'status': 'ok'})

@app.route('/auth/change-username', methods=['POST'])
@login_required
def change_username():
    """Смена логина (uid и данные сохраняются)."""
    data = request.json or {}
    new_name = (data.get('new_username') or '').strip()
    password = data.get('password', '')
    if len(new_name) < 3:
        return jsonify({'error': 'Логин — минимум 3 символа'}), 400
    users = _load_users()
    if new_name in users:
        return jsonify({'error': 'Такой логин уже занят'}), 400
    user = users.get(session['username'])
    if not user or not check_password_hash(user['hash'], password):
        return jsonify({'error': 'Пароль неверен'}), 400
    users[new_name] = users.pop(session['username'])
    _save_users(users)
    session['username'] = new_name
    return jsonify({'status': 'ok'})

@app.route('/auth/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Удаление аккаунта вместе со всеми данными."""
    data = request.json or {}
    users = _load_users()
    user = users.get(session['username'])
    if not user or not check_password_hash(user['hash'], data.get('password', '')):
        return jsonify({'error': 'Пароль неверен'}), 400
    uid = user['uid']
    del users[session['username']]
    _save_users(users)
    user_dir = os.path.join(DATA_DIR, uid)
    if os.path.isdir(user_dir):
        shutil.rmtree(user_dir)          # стираем конфиг пользователя
    _cores.pop(uid, None)
    session.clear()
    return jsonify({'status': 'ok'})



@app.route('/api/me')
@login_required
def me():
    return jsonify({'username': session.get('username', '')})

# ================= PWA =================

@app.route('/sw.js')
def service_worker():
    resp = app.send_static_file('sw.js')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

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



@app.route('/privacy')
def privacy():
    """Публичная страница политики конфиденциальности."""
    return render_template('privacy.html')

if __name__ == '__main__':
    print("=" * 50)
    print("  💰 Финансовый Планировщик (multi-user)")
    print("  📍 http://localhost:5000")
    print("  🧮 MathCore v1.1 + auth")
    print("=" * 50)
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('FINPLAN_PORT', 5000)),
        debug=os.environ.get('FINPLAN_DEBUG', '0') == '1'
    )