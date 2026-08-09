/* ===== Финансовый календарь (FullCalendar) + модалка событий ===== */
let calendar = null;
let modalEventId = null;

const cfgReady = () => (typeof config !== 'undefined' && config);

document.addEventListener('DOMContentLoaded', async () => {
    // Ждём, пока app.js загрузит конфиг (до 5 секунд)
    for (let i = 0; i < 50 && !cfgReady(); i++) {
        await new Promise(r => setTimeout(r, 100));
    }
    initCalendar();
    initModalButtons();
});

function initCalendar() {
    const el = document.getElementById('calendar');
    if (!el || typeof FullCalendar === 'undefined') return;

    calendar = new FullCalendar.Calendar(el, {
        initialView: 'dayGridMonth',
        locale: 'ru',
        height: 'auto',
        firstDay: 1,
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        buttonText: { today: 'Сегодня', month: 'Месяц', week: 'Неделя', day: 'День' },
        dayMaxEventRows: 4,
        editable: true,
        events: (info, success) => success(buildCalendarEvents(info.start, info.end)),
        dateClick: (info) => openEventModal(null, info.dateStr),
        eventClick: (info) => {
            if (info.event.extendedProps.system) return;
            openEventModal(info.event.id, info.event.startStr);
        },
        eventDrop: async (info) => {
            if (info.event.extendedProps.system) { info.revert(); return; }
            await apiUpdateEvent(info.event.id, { date: info.event.startStr });
            await onConfigChanged();
        }
    });
    calendar.render();
}

function refreshCalendar() {
    if (calendar) calendar.refetchEvents();
}

/* ===== События видимого диапазона ===== */
function buildCalendarEvents(start, end) {
    if (!cfgReady()) return [];
    const out = [];
    const todayStr = fmtDate(new Date());

    // Пользовательские события (включая раскрытые серии)
        // Пользовательские события
    for (const ev of config.events) {
        const isDone = ev.status === 'done';
        if (ev.repeat === 'monthly' && ev.repeat_end) {
            // серия — раскладываем только по видимому диапазону
            for (const occ of expandEventOccurrences(ev, new Date(start), new Date(end))) {
                out.push(makeUserEvent(ev, occ.date, isDone, true));
            }
        } else {
            // разовое — отдаём как есть, календарь сам разместит в нужном месяце
            out.push(makeUserEvent(ev, ev.date, isDone, false));
        }
    }
    // Системные: выплаты и постоянные расходы
    const cur = new Date(start);
    while (cur < end) {
        const day = cur.getDate();
        const dateStr = fmtDate(cur);

        for (const inc of config.income_sources) {
            if (inc.active && day === inc.day_of_month) {
                out.push(systemEvent(`💵 ${inc.name} +${formatMoney(inc.amount)}`, dateStr, 'income'));
            }
        }
        for (const fe of config.fixed_expenses) {
            if (fe.active && day === fe.day_of_month) {
                out.push(systemEvent(`💳 ${fe.name} −${formatMoney(fe.amount)}`, dateStr, 'fixed'));
            }
        }
        cur.setDate(cur.getDate() + 1);
    }
    return out;
}

function makeUserEvent(ev, dateStr, isDone, isRepeat) {
    const todayStr = fmtDate(new Date());
    const isOverdue = dateStr < todayStr && !isDone;
    return {
        id: ev.id,
        title: `${isDone ? '✅ ' : (isRepeat ? '🔁 ' : '')}${ev.name} · ${formatMoney(ev.amount)}`,
        start: dateStr,
        allDay: true,
        backgroundColor: isDone ? '#2e7d32' : (isOverdue ? '#c62828' : '#6c63ff'),
        borderColor: 'transparent',
        editable: !isDone && !isRepeat,
        extendedProps: { system: false }
    };
}

function systemEvent(title, dateStr, kind) {
    return {
        title,
        start: dateStr,
        allDay: true,
        backgroundColor: kind === 'income' ? 'rgba(76,175,80,0.25)' : 'rgba(244,67,54,0.20)',
        borderColor: kind === 'income' ? '#4caf50' : '#f44336',
        textColor: kind === 'income' ? '#a5d6a7' : '#ef9a9a',
        editable: false,
        extendedProps: { system: true }
    };
}

/* ===== Повторяющиеся события ===== */
function addMonths(d, n) {
    const day = d.getDate();
    const nd = new Date(d);
    nd.setDate(1);
    nd.setMonth(nd.getMonth() + n);
    const last = new Date(nd.getFullYear(), nd.getMonth() + 1, 0).getDate();
    nd.setDate(Math.min(day, last));
    return nd;
}

function expandEventOccurrences(ev, start, end) {
    const res = [];
    const base = new Date(ev.date + 'T00:00:00');
    if (ev.repeat === 'monthly' && ev.repeat_end) {
        const limit = new Date(ev.repeat_end + 'T00:00:00');
        for (let n = 0; n < 60; n++) {
            const d = addMonths(base, n);
            if (d > limit || d > end) break;
            if (d >= start) res.push({ date: fmtDate(d), repeat: true });
        }
    } else if (base >= start && base <= end) {
        res.push({ date: ev.date, repeat: false });
    }
    return res;
}

/* ===== Модальное окно ===== */
function openEventModal(eventId, dateStr) {
    modalEventId = eventId;
    const ev = eventId ? config.events.find(e => e.id === eventId) : null;

    document.getElementById('modalTitle').textContent = ev ? 'Событие' : 'Новое событие';
    document.getElementById('modalName').value = ev ? ev.name : '';
    document.getElementById('modalAmount').value = ev ? ev.amount : '';
    document.getElementById('modalDate').value = ev ? ev.date : dateStr;
    document.getElementById('modalCategory').value = ev ? (ev.category || '') : '';

    const repBox = document.getElementById('modalRepeat');
    const repEnd = document.getElementById('modalRepeatEnd');
    const repGroup = document.getElementById('repeatEndGroup');
    if (repBox && repEnd && repGroup) {
        const repeatOn = !!(ev && ev.repeat === 'monthly');
        repBox.checked = repeatOn;
        repEnd.value = ev && ev.repeat_end ? ev.repeat_end : '';
        repGroup.style.display = repeatOn ? 'flex' : 'none';
    }

    document.getElementById('modalDone').style.display = (ev && ev.status !== 'done') ? 'inline-block' : 'none';
    document.getElementById('modalDelete').style.display = ev ? 'inline-block' : 'none';
    document.getElementById('eventModal').style.display = 'flex';
}

function closeEventModal() {
    document.getElementById('eventModal').style.display = 'none';
}

function initModalButtons() {
    const saveBtn = document.getElementById('modalSave');
    if (!saveBtn) return;   // модалки ещё нет в DOM — молча выходим

    saveBtn.onclick = async () => {
        const payload = {
            name: document.getElementById('modalName').value.trim(),
            amount: parseFloat(document.getElementById('modalAmount').value) || 0,
            date: document.getElementById('modalDate').value,
            category: document.getElementById('modalCategory').value.trim() || 'event'
        };
        if (!payload.name || !payload.date) { alert('Нужны название и дата'); return; }

        // Поля серии — строго внутри payload, никаких висячих "repeat:"
        const repBox = document.getElementById('modalRepeat');
        if (repBox) {
            payload.repeat = repBox.checked ? 'monthly' : '';
            payload.repeat_end = document.getElementById('modalRepeatEnd').value || '';
        }

        if (modalEventId) await apiUpdateEvent(modalEventId, payload);
        else await fetch('/api/events', { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(payload) });

        closeEventModal();
        await onConfigChanged();
    };

    document.getElementById('modalDelete').onclick = async () => {
        if (!modalEventId || !confirm('Удалить событие?')) return;
        await fetch(`/api/events/${modalEventId}`, { method: 'DELETE' });
        closeEventModal();
        await onConfigChanged();
    };

    document.getElementById('modalDone').onclick = async () => {
        if (!modalEventId) return;
        await fetch(`/api/events/${modalEventId}/status`, {
            method: 'PUT', headers: jsonHeaders(), body: JSON.stringify({ status: 'done' })
        });
        closeEventModal();
        await onConfigChanged();
    };

    document.getElementById('modalClose').onclick = closeEventModal;
    document.getElementById('eventModal').onclick = (e) => {
        if (e.target.id === 'eventModal') closeEventModal();
    };

    const repBox = document.getElementById('modalRepeat');
    if (repBox) {
        repBox.onchange = (e) => {
            document.getElementById('repeatEndGroup').style.display = e.target.checked ? 'flex' : 'none';
        };
    }
}

async function apiUpdateEvent(id, payload) {
    await fetch(`/api/events/${id}`, { method: 'PUT', headers: jsonHeaders(), body: JSON.stringify(payload) });
}

function jsonHeaders() {
    return { 'Content-Type': 'application/json' };
}

function fmtDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
} 

/* ===== Автообновление календаря ===== */

// 1) После ЛЮБОГО изменения конфига (модалка, вкладки, drag&drop) — перезапрос событий
if (typeof onConfigChanged === 'function') {
    const _origOnConfigChanged = onConfigChanged;
    onConfigChanged = async function () {
        await _origOnConfigChanged();
        refreshCalendar();
    };
}

// 2) При открытии вкладки «Календарь» — перерисовать размер и дозапросить события
//    (FullCalendar плохо инициализируется на скрытой вкладке)
document.addEventListener('click', (e) => {
    const tab = e.target.closest('.tab');
    if (tab && tab.dataset.tab === 'calendar') {
        setTimeout(() => {
            if (calendar) {
                calendar.updateSize();
                calendar.refetchEvents();
            }
        }, 0);
    }
});