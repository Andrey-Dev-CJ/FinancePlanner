let config = null;
let charts = {};
let updateTimeout = null;


// Плагин: вертикальные линии на выплаты + зебра-подсветка спринтов
const periodShadingPlugin = {
    id: 'periodShading',
    beforeDatasetsDraw(chart) {
        const flags = chart.options.periodFlags;
        if (!flags || !chart.chartArea) return;
        const { ctx, chartArea } = chart;
        const xScale = chart.scales.x;
        ctx.save();
        let prevX = null;
        let shade = false;
        for (let i = 0; i < flags.length; i++) {
            if (!flags[i].is_payday) continue;
            const x = xScale.getPixelForValue(i);
            if (prevX !== null && shade) {
                ctx.fillStyle = 'rgba(108, 99, 255, 0.07)';
                ctx.fillRect(prevX, chartArea.top, x - prevX, chartArea.bottom - chartArea.top);
            }
            ctx.strokeStyle = 'rgba(76, 175, 80, 0.4)';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(x, chartArea.top);
            ctx.lineTo(x, chartArea.bottom);
            ctx.stroke();
            ctx.setLineDash([]);
            prevX = x;
            shade = !shade;
        }
        ctx.restore();
    }
};


// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', async () => {
    await loadMe();
    await loadConfig();
    initTabs();
    initAutoUpdate();
    await refreshAll();
});

async function loadConfig() {
    const res = await fetch('/api/config');
    if (res.status === 401) { location.href = '/'; return; }
    config = await res.json();
    updateBalanceDisplay();
    renderAll();
}

function updateBalanceDisplay() {
    document.getElementById('currentBalance').value = config.initial_balance || 0;
    const reserves = config.reserve_envelopes || {};
    const totalReserve = Object.values(reserves).reduce((s, v) => s + (typeof v === 'number' ? v : 0), 0);
    document.getElementById('reserveEnvelopes').value = totalReserve;
}

// ==================== AUTO UPDATE ====================
function initAutoUpdate() {
    // Автоматическое обновление при изменении селектов
    document.getElementById('forecastDays')?.addEventListener('change', debouncedRefresh);
    document.getElementById('sprintCount')?.addEventListener('change', debouncedRefresh);
}

function debouncedRefresh() {
    if (updateTimeout) clearTimeout(updateTimeout);
    updateTimeout = setTimeout(refreshAll, 300);
}

// Единая функция обновления после любого изменения
async function onConfigChanged() {
    await loadConfig();
    await refreshAll();
}

// ==================== TABS ====================
function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        });
    });
}

// ==================== REFRESH ALL ====================
async function refreshAll() {
    await Promise.all([
        refreshSummary(),
        refreshForecast(),
        refreshSprints(),
        refreshRisks(),
        renderCharts()
    ]);
    if (typeof refreshCalendar === 'function') refreshCalendar();  // ← вот эта
}

// ==================== SUMMARY ====================
async function refreshSummary() {
    const res = await fetch('/api/summary');
    const summary = await res.json();
    
    const grid = document.getElementById('summaryGrid');
    const items = [
        { label: 'Доход/мес', value: summary.monthly_income, cls: 'positive' },
        { label: 'Постоянные', value: summary.monthly_fixed, cls: 'negative' },
        { label: 'Переменные', value: summary.monthly_variable, cls: 'negative' },
        { label: 'Остаток', value: summary.monthly_surplus, cls: summary.monthly_surplus >= 0 ? 'positive' : 'negative' },
        { label: 'Событий', value: `${summary.pending_events_count} (${formatMoney(summary.pending_events_cost)})`, cls: 'negative' },
        { label: 'Дни выплат', value: summary.pay_days.join(', '), cls: '' }
    ];
    
    grid.innerHTML = items.map(item => `
        <div class="summary-item">
            <span class="label">${item.label}</span>
            <span class="value ${item.cls}">${typeof item.value === 'number' ? formatMoney(item.value) : item.value}</span>
        </div>
    `).join('');
}

// ==================== FORECAST ====================
async function refreshForecast() {
    const days = parseInt(document.getElementById('forecastDays')?.value || 30);
    const res = await fetch('/api/forecast', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ days })
    });
    const data = await res.json();
    
    renderForecastChart(data.daily);
    renderDeficits(data.deficits);
    renderReserveInfo(data);
}

function renderReserveInfo(data) {
    const info = document.getElementById('reserveInfo');
    if (!info) return;
    
    const need = data.current_required_reserve || 0;
    const bal = config.initial_balance;
    
    if (data.deficit_risk) {
        info.className = 'reserve-info danger';
        info.innerHTML = `⚠️ Сейчас на руках <b>${formatMoney(bal)}</b>, а нужно минимум <b>${formatMoney(need)}</b> — в дальнейшем возможен дефицит.`;
    } else {
        info.className = 'reserve-info ok';
        info.innerHTML = `✅ Сейчас на руках <b>${formatMoney(bal)}</b> — выше необходимого резерва <b>${formatMoney(need)}</b>. Запаса хватает на все будущие обязательства.`;
    }
}

function renderForecastChart(daily) {
    const ctx = document.getElementById('forecastChart').getContext('2d');
    if (charts.forecast) charts.forecast.destroy();
    
    const labels = daily.map(d => d.day_label);
    const values = daily.map(d => d.balance);
    const required = daily.map(d => d.required_reserve ?? 0);
    
    const allValues = values.concat(required);
    const minBalance = Math.min(...allValues, 0);
    const maxBalance = Math.max(...allValues, 0);
    
    charts.forecast = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Баланс',
                    data: values,
                    borderColor: '#6c63ff',
                    backgroundColor: 'rgba(108, 99, 255, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: daily.map(d => d.is_payday ? 5 : (d.has_event ? 4 : 0)),
                    pointBackgroundColor: daily.map(d =>
                        d.is_payday ? '#4caf50' : (d.has_event ? '#ff9800' : '#6c63ff')
                    )
                },
                {
                    label: 'Необходимый резерв',
                    data: required,
                    borderColor: '#ff9800',
                    borderDash: [6, 6],
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.2
                },
                {
                    label: 'Ноль',
                    data: daily.map(() => 0),
                    borderColor: 'rgba(244, 67, 54, 0.5)',
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            periodFlags: daily,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#a0a0cc',
                        usePointStyle: true,
                        filter: (item) => item.text !== 'Ноль'
                    }
                },
                tooltip: {
                    callbacks: {
                        title: (items) => `📅 ${daily[items[0].dataIndex].date}`,
                        afterTitle: (items) => {
                            const d = daily[items[0].dataIndex];
                            const lines = [];
                            if (d.is_payday) lines.push('💵 День выплаты');
                            if (d.has_event) lines.push('🎯 ' + d.event_names.join(', '));
                            return lines;
                        },
                        label: (ctx) => {
                            if (ctx.dataset.label === 'Ноль') return null;
                            return `${ctx.dataset.label}: ${formatMoney(ctx.raw)}`;
                        },
                        afterBody: (items) => {
                            const d = daily[items[0].dataIndex];
                            const margin = d.balance - (d.required_reserve ?? 0);
                            return [`Запас прочности: ${formatMoney(margin)}`];
                        }
                    }
                }
            },
            scales: {
                y: {
                    min: Math.max(minBalance - 5000, -100000),
                    max: maxBalance + 5000,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { callback: v => formatMoney(v), color: '#a0a0cc' }
                },
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#a0a0cc',
                        autoSkip: true,
                        maxTicksLimit: 12,
                        maxRotation: 0
                    }
                }
            }
        },
        plugins: [periodShadingPlugin]
    });
}

function renderDeficits(deficits) {
    const container = document.getElementById('deficitsList');
    if (!deficits || deficits.length === 0) {
        container.innerHTML = '<p class="no-data">✅ Дефицитов не обнаружено</p>';
        return;
    }
    
    container.innerHTML = deficits.map(d => `
        <div class="deficit-item ${d.severity}">
            <div>
                <strong>${d.day_label}</strong> — Баланс: ${formatMoney(d.balance)}
            </div>
            <div>
                Дефицит: ${formatMoney(d.deficit)} | Восстановление: ${d.recovery_days} дн.
            </div>
        </div>
    `).join('');
}

// ==================== SPRINTS ====================
async function refreshSprints() {
    const count = parseInt(document.getElementById('sprintCount')?.value || 6);
    const res = await fetch('/api/sprints', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ count })
    });
    const sprints = await res.json();
    
    const container = document.getElementById('sprintsList');
    container.innerHTML = sprints.map(s => `
        <div class="sprint-card ${s.status} ${s.is_current ? 'current' : ''}">
            <div class="sprint-header">
                <span class="sprint-title">
                    ${s.is_current ? '🔥 Текущий спринт' : 'Спринт ' + s.sprint_number}:
                    ${s.start_label} — ${s.end_label} (${s.days} дн.)
                </span>
                <span class="sprint-balance ${s.available_budget >= 0 ? 'positive' : 'negative'}">
                    ${s.available_budget >= 0 ? '+' : ''}${formatMoney(s.available_budget)}
                </span>
            </div>
            <div class="sprint-details">
                <div class="sprint-detail">
                    <div class="label">${s.is_current ? 'На руках + доход' : 'Доход'}</div>
                    <div>${formatMoney(s.carry_in + s.income_expected)}</div>
                </div>
                <div class="sprint-detail">
                    <div class="label">Расходы</div>
                    <div>${formatMoney(s.fixed_expenses + s.variable_expenses)}</div>
                </div>
                <div class="sprint-detail">
                    <div class="label">События</div>
                    <div>${formatMoney(s.events_total)}</div>
                </div>
            </div>
            ${s.events.length > 0 ? `
                <div class="sprint-events">
                    <strong>События:</strong> ${s.events.map(e => `${e.name} (${formatMoney(e.amount)})`).join(', ')}
                </div>
            ` : ''}
        </div>
    `).join('');
}

// ==================== RISKS ====================
async function refreshRisks() {
    const res = await fetch('/api/risks');
    const risks = await res.json();
    
    const container = document.getElementById('risksList');
    const items = [];
    
    if (risks.deficits && risks.deficits.length > 0) {
        risks.deficits.forEach(d => {
            items.push({
                text: `🔴 Дефицит ${formatMoney(d.deficit)} ${d.day_label}`,
                cls: d.severity === 'critical' ? 'critical' : 'warning'
            });
        });
    }
    
    if (risks.runway) {
        items.push({
            text: `⏱️ ${risks.runway.message}`,
            cls: risks.runway.days < 30 ? 'warning' : 'info'
        });
    }
    
    if (items.length === 0) {
        items.push({ text: '✅ Рисков не обнаружено', cls: 'info' });
    }
    
    container.innerHTML = items.map(i => `
        <div class="risk-item ${i.cls}">${i.text}</div>
    `).join('');
}

// ==================== CHARTS ====================
function renderCharts() {
    renderExpensePieChart();
    renderIncomeExpenseChart();
}

function renderExpensePieChart() {
    const ctx = document.getElementById('expensePieChart').getContext('2d');
    if (charts.pie) charts.pie.destroy();
    
    const fixed = config.fixed_expenses.reduce((s, e) => s + e.amount, 0);
    const variable = config.variable_expenses.reduce((s, e) => s + e.amount_per_month, 0);
    const events = config.events.filter(e => e.status !== 'done').reduce((s, e) => s + e.amount, 0);
    
    charts.pie = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Постоянные', 'Переменные', 'События'],
            datasets: [{
                data: [fixed, variable, events],
                backgroundColor: ['#6c63ff', '#48c6ef', '#ff9800'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#a0a0cc',
                        padding: 16,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                }
            }
        }
    });
}

function renderIncomeExpenseChart() {
    const ctx = document.getElementById('incomeExpenseChart').getContext('2d');
    if (charts.bar) charts.bar.destroy();
    
    const income = config.income_sources.reduce((s, i) => s + i.amount, 0);
    const fixed = config.fixed_expenses.reduce((s, e) => s + e.amount, 0);
    const variable = config.variable_expenses.reduce((s, e) => s + e.amount_per_month, 0);
    
    charts.bar = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Доход', 'Постоянные', 'Переменные', 'Остаток'],
            datasets: [{
                data: [income, fixed, variable, income - fixed - variable],
                backgroundColor: ['#4caf50', '#f44336', '#ff9800', '#6c63ff'],
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            layout: { padding: 10 },
            scales: {
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { callback: v => formatMoney(v), color: '#a0a0cc' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#a0a0cc' }
                }
            }
        }
    });
}

// ==================== RENDER TABLES ====================
function renderAll() {
    renderIncome();
    renderFixedExpenses();
    renderVariableExpenses();
    renderEvents();
}

function renderIncome() {
    const tbody = document.getElementById('incomeTable');
    tbody.innerHTML = config.income_sources.map(item => `
        <tr>
            <td>${item.name}</td>
            <td>${formatMoney(item.amount)}</td>
            <td>${item.day_of_month}-е число</td>
            <td>${item.active ? '✅' : '❌'}</td>
            <td><button class="btn btn-danger" onclick="deleteIncome('${item.id}')">✕</button></td>
        </tr>
    `).join('') || '<tr><td colspan="5" class="no-data">Нет доходов</td></tr>';
}

function renderFixedExpenses() {
    const tbody = document.getElementById('fixedExpensesTable');
    tbody.innerHTML = config.fixed_expenses.map(item => `
        <tr>
            <td>${item.name}</td>
            <td>${formatMoney(item.amount)}</td>
            <td>${item.day_of_month}-е число</td>
            <td>${item.category || '—'}</td>
            <td><button class="btn btn-danger" onclick="deleteFixedExpense('${item.id}')">✕</button></td>
        </tr>
    `).join('') || '<tr><td colspan="5" class="no-data">Нет расходов</td></tr>';
}

function renderVariableExpenses() {
    const tbody = document.getElementById('variableExpensesTable');
    tbody.innerHTML = config.variable_expenses.map(item => `
        <tr>
            <td>${item.name}</td>
            <td>${formatMoney(item.amount_per_month)}</td>
            <td>${item.category || '—'}</td>
            <td><button class="btn btn-danger" onclick="deleteVariableExpense('${item.id}')">✕</button></td>
        </tr>
    `).join('') || '<tr><td colspan="4" class="no-data">Нет расходов</td></tr>';
}

function renderEvents() {
    const container = document.getElementById('eventsList');
    const sorted = [...config.events].sort((a, b) => new Date(a.date) - new Date(b.date));
    const today = new Date().toISOString().split('T')[0];
    
    container.innerHTML = sorted.map(ev => {
        const isDone = ev.status === 'done';
        const isOverdue = ev.date < today && !isDone;
        const statusClass = isDone ? 'done' : (isOverdue ? 'overdue' : '');
        
        return `
            <div class="event-item ${statusClass}">
                <div class="event-info">
                    <div class="event-name">${isDone ? '✅' : (isOverdue ? '🔴' : '📌')} ${ev.name}</div>
                    <div class="event-date">${formatDate(ev.date)} | ${ev.category || '—'}</div>
                </div>
                <div class="event-amount">${formatMoney(ev.amount)}</div>
                ${!isDone ? `
                    <button class="btn btn-success" onclick="markEventDone('${ev.id}')">✓</button>
                    <button class="btn btn-danger" onclick="deleteEvent('${ev.id}')">✕</button>
                ` : ''}
            </div>
        `;
    }).join('') || '<p class="no-data">Нет событий</p>';
}

// ==================== CRUD (все вызывают onConfigChanged) ====================
async function addIncome() {
    const item = {
        name: document.getElementById('incName').value,
        amount: parseFloat(document.getElementById('incAmount').value),
        day_of_month: parseInt(document.getElementById('incDay').value)
    };
    
    await fetch('/api/income', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(item)
    });
    
    clearInputs('inc');
    await onConfigChanged();
}

async function deleteIncome(id) {
    await fetch(`/api/income/${id}`, { method: 'DELETE' });
    await onConfigChanged();
}

async function addFixedExpense() {
    const item = {
        name: document.getElementById('feName').value,
        amount: parseFloat(document.getElementById('feAmount').value),
        day_of_month: parseInt(document.getElementById('feDay').value),
        category: document.getElementById('feCategory').value || 'fixed'
    };
    
    await fetch('/api/fixed-expenses', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(item)
    });
    
    clearInputs('fe');
    await onConfigChanged();
}

async function deleteFixedExpense(id) {
    await fetch(`/api/fixed-expenses/${id}`, { method: 'DELETE' });
    await onConfigChanged();
}

async function addVariableExpense() {
    const item = {
        name: document.getElementById('veName').value,
        amount_per_month: parseFloat(document.getElementById('veAmount').value),
        category: document.getElementById('veCategory').value || 'general'
    };
    
    await fetch('/api/variable-expenses', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(item)
    });
    
    clearInputs('ve');
    await onConfigChanged();
}

async function deleteVariableExpense(id) {
    await fetch(`/api/variable-expenses/${id}`, { method: 'DELETE' });
    await onConfigChanged();
}

async function addEvent() {
    const item = {
        name: document.getElementById('evName').value,
        amount: parseFloat(document.getElementById('evAmount').value),
        date: document.getElementById('evDate').value,
        category: document.getElementById('evCategory').value || 'event'
    };
    
    await fetch('/api/events', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(item)
    });
    
    clearInputs('ev');
    await onConfigChanged();
}

async function deleteEvent(id) {
    await fetch(`/api/events/${id}`, { method: 'DELETE' });
    await onConfigChanged();
}

async function markEventDone(id) {
    await fetch(`/api/events/${id}/status`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status: 'done' })
    });
    await onConfigChanged();
}

// ==================== WHAT-IF ====================
async function runWhatIf() {
    const income = parseFloat(document.getElementById('whatIfIncome').value) || 0;
    const expense = parseFloat(document.getElementById('whatIfExpense').value) || 0;
    
    const res = await fetch('/api/what-if', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            extra_income: income,
            extra_expense: expense
        })
    });
    const result = await res.json();
    
    document.getElementById('whatIfResult').style.display = 'block';
    document.getElementById('whatIfContent').innerHTML = `
        <div class="whatif-item">
            <strong>Исходных дефицитов:</strong> ${result.original_deficits}
        </div>
        <div class="whatif-item">
            <strong>Чистое влияние:</strong> ${formatMoney(result.net_impact)}
        </div>
        <div class="whatif-item">
            <strong>Рекомендация:</strong> ${result.recommendation}
        </div>
    `;
}

// ==================== SETTINGS ====================
async function updatePayDays() {
    const daysStr = document.getElementById('payDays').value;
    const days = daysStr.split(',').map(d => parseInt(d.trim())).filter(d => !isNaN(d));
    
    if (days.length === 0) {
        alert('Введите корректные дни');
        return;
    }
    
    config.pay_days = days;
    await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(config)
    });
    
    await onConfigChanged();
    alert('Сохранено!');
}

async function updateBalance() {
    const balance = parseFloat(document.getElementById('currentBalance').value) || 0;
    await fetch('/api/balance', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ balance, reserve_envelopes: config.reserve_envelopes })
    });
    await onConfigChanged();
}

async function updateReserve() {
    const reserve = parseFloat(document.getElementById('reserveEnvelopes').value) || 0;
    config.reserve_envelopes = { 'reserve': reserve };
    await fetch('/api/balance', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ balance: config.initial_balance, reserve_envelopes: config.reserve_envelopes })
    });
    await onConfigChanged();
}

function exportConfig() {
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'finance_config.json';
    a.click();
}

function importConfig(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const imported = JSON.parse(e.target.result);
            await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(imported)
            });
            await onConfigChanged();
            alert('Конфигурация импортирована!');
        } catch (err) {
            alert('Ошибка при импорте: ' + err.message);
        }
    };
    reader.readAsText(file);
}

// ==================== HELPERS ====================
function clearInputs(prefix) {
    document.querySelectorAll(`[id^="${prefix}"]`).forEach(el => {
        if (el.tagName === 'SELECT') el.selectedIndex = 0;
        else el.value = '';
    });
}

function formatMoney(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount || 0);
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
}


async function loadMe() {
    const res = await fetch('/api/me');
    if (!res.ok) return;
    const me = await res.json();
    const el = document.getElementById('userName');
    if (el) el.textContent = '👤 ' + me.username;
    const btn = document.getElementById('logoutBtn');
    if (btn) {
        btn.style.display = 'inline-block';
        btn.onclick = async () => {
            await fetch('/auth/logout', { method: 'POST' });
            location.href = '/';
        };
    }
}


// ==================== ACCOUNT ====================
async function changePassword() {
    const cur = document.getElementById('curPass').value;
    const nw = document.getElementById('newPass').value;
    const nw2 = document.getElementById('newPass2').value;
    if (!cur) { alert('Введите текущий пароль'); return; }
    if (nw.length < 6) { alert('Новый пароль — минимум 6 символов'); return; }
    if (nw !== nw2) { alert('Новые пароли не совпадают'); return; }
    const res = await fetch('/auth/change-password', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ current_password: cur, new_password: nw })
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Ошибка'); return; }
    alert('✅ Пароль изменён');
    ['curPass', 'newPass', 'newPass2'].forEach(id => document.getElementById(id).value = '');
}

async function changeUsername() {
    const newName = document.getElementById('newLogin').value.trim();
    const pass = document.getElementById('loginPass').value;
    if (newName.length < 3) { alert('Логин — минимум 3 символа'); return; }
    const res = await fetch('/auth/change-username', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ new_username: newName, password: pass })
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Ошибка'); return; }
    alert('✅ Логин изменён');
    location.reload();
}

async function deleteAccount() {
    if (!confirm('Удалить аккаунт и ВСЕ данные безвозвратно?')) return;
    if (!confirm('Точно? События, расходы и настройки будут стёрты.')) return;
    const pass = document.getElementById('deletePass').value;
    const res = await fetch('/auth/delete-account', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ password: pass })
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Ошибка'); return; }
    location.href = '/';
}