"""
Flask-приложение. ТОЛЬКО вызывает MathCore.
Никакой бизнес-логики здесь нет.
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from mathcore import MathCore
import os

app = Flask(__name__)
CORS(app)

CONFIG_FILE = 'config.json'

# Инициализация ядра
if os.path.exists(CONFIG_FILE):
    core = MathCore.from_config_file(CONFIG_FILE)
else:
    core = MathCore.empty()
    core.save_config(CONFIG_FILE)


@app.route('/')
def index():
    return render_template('index.html')


# ===== Данные =====

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'summary': core.get_summary(),
        'income_sources': [
            {'id': i.id, 'name': i.name, 'amount': i.amount,
             'day_of_month': i.day_of_month, 'active': i.active}
            for i in core.config.income_sources
        ],
        'fixed_expenses': [
            {'id': e.id, 'name': e.name, 'amount': e.amount,
             'day_of_month': e.day_of_month, 'active': e.active}
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
             'category': e.category, 'notes': e.notes}
            for e in core.config.events
        ],
        'pay_days': core.config.pay_schedule.pay_days,
        'initial_balance': core.config.initial_balance,
        'reserve_envelopes': core.config.reserve_envelopes
    })


@app.route('/api/config', methods=['POST'])
def update_config():
    """Полное обновление конфига."""
    data = request.json
    core.update_config(data)
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})


# ===== MathCore эндпоинты =====

@app.route('/api/forecast', methods=['POST'])
def get_forecast():
    days = request.json.get('days', 90)
    result = core.get_forecast(days=days)
    return jsonify(result)


@app.route('/api/sprints', methods=['POST'])
def get_sprints():
    count = request.json.get('count', 6)
    sprints = core.get_sprints(count=count)
    return jsonify(sprints)


@app.route('/api/current-sprint', methods=['GET'])
def get_current_sprint():
    return jsonify(core.get_current_sprint())


@app.route('/api/risks', methods=['GET'])
def get_risks():
    return jsonify(core.get_risks())


@app.route('/api/summary', methods=['GET'])
def get_summary():
    return jsonify(core.get_summary())


@app.route('/api/what-if', methods=['POST'])
def what_if():
    params = request.json
    result = core.what_if(
        extra_income=params.get('extra_income', 0),
        extra_expense=params.get('extra_expense', 0),
        skip_event_ids=params.get('skip_event_ids', [])
    )
    return jsonify(result)


# ===== CRUD для сущностей (обновляют конфиг) =====

@app.route('/api/income', methods=['POST'])
def add_income():
    from mathcore.models import IncomeSource
    import uuid
    data = request.json
    item = IncomeSource(
        id=str(uuid.uuid4())[:8],
        name=data['name'],
        amount=float(data['amount']),
        day_of_month=int(data['day_of_month']),
        active=data.get('active', True)
    )
    core.config.income_sources.append(item)
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok', 'id': item.id})


@app.route('/api/income/<item_id>', methods=['DELETE'])
def delete_income(item_id):
    core.config.income_sources = [
        i for i in core.config.income_sources if i.id != item_id
    ]
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})


@app.route('/api/fixed-expenses', methods=['POST'])
def add_fixed():
    from mathcore.models import FixedExpense
    import uuid
    data = request.json
    item = FixedExpense(
        id=str(uuid.uuid4())[:8],
        name=data['name'],
        amount=float(data['amount']),
        day_of_month=int(data['day_of_month']),
        active=data.get('active', True)
    )
    core.config.fixed_expenses.append(item)
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok', 'id': item.id})


@app.route('/api/fixed-expenses/<item_id>', methods=['DELETE'])
def delete_fixed(item_id):
    core.config.fixed_expenses = [
        e for e in core.config.fixed_expenses if e.id != item_id
    ]
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})


@app.route('/api/variable-expenses', methods=['POST'])
def add_variable():
    from mathcore.models import VariableExpense
    import uuid
    data = request.json
    item = VariableExpense(
        id=str(uuid.uuid4())[:8],
        name=data['name'],
        amount_per_month=float(data['amount_per_month']),
        category=data.get('category', 'general'),
        active=data.get('active', True)
    )
    core.config.variable_expenses.append(item)
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok', 'id': item.id})


@app.route('/api/variable-expenses/<item_id>', methods=['DELETE'])
def delete_variable(item_id):
    core.config.variable_expenses = [
        e for e in core.config.variable_expenses if e.id != item_id
    ]
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})


@app.route('/api/events', methods=['POST'])
def add_event():
    from mathcore.models import Event, EventStatus
    import uuid
    data = request.json
    item = Event(
        id=str(uuid.uuid4())[:8],
        name=data['name'],
        amount=float(data['amount']),
        date=data['date'],
        status=EventStatus(data.get('status', 'planned')),
        category=data.get('category', 'event'),
        notes=data.get('notes', ''),
        repeat=data.get('repeat', ''),
        repeat_end=data.get('repeat_end', '')
    )
    core.config.events.append(item)
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok', 'id': item.id})


@app.route('/api/events/<item_id>', methods=['DELETE'])
def delete_event(item_id):
    core.config.events = [e for e in core.config.events if e.id != item_id]
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})


@app.route('/api/events/<item_id>/status', methods=['PUT'])
def update_event_status(item_id):
    from mathcore.models import EventStatus
    for ev in core.config.events:
        if ev.id == item_id:
            ev.status = EventStatus(request.json.get('status', 'planned'))
            break
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})


@app.route('/api/balance', methods=['PUT'])
def update_balance():
    core.config.initial_balance = float(request.json.get('balance', 0))
    core.config.reserve_envelopes = request.json.get('reserve_envelopes', {})
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})

@app.route('/api/events/<item_id>', methods=['PUT'])
def update_event(item_id):
    from mathcore.models import EventStatus
    data = request.json
    for ev in core.config.events:
        if ev.id == item_id:
            if 'name' in data: ev.name = data['name']
            if 'amount' in data: ev.amount = float(data['amount'])
            if 'date' in data: ev.date = data['date']
            if 'category' in data: ev.category = data['category']
            if 'status' in data: ev.status = EventStatus(data['status'])
            if 'repeat' in data: ev.repeat = data['repeat']
            if 'repeat_end' in data: ev.repeat_end = data['repeat_end']
            break
    core.save_config(CONFIG_FILE)
    return jsonify({'status': 'ok'})    

if __name__ == '__main__':
    print("=" * 50)
    print("  💰 Финансовый Планировщик")
    print("  📍 http://localhost:5000")
    print("  🧮 MathCore v1.0 загружен")
    print("=" * 50)
    app.run(debug=True, port=5000)  