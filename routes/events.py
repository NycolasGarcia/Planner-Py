from datetime import date, datetime, time, timedelta

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import select

from db.database import SessionLocal
from models.event import Event

events_bp = Blueprint('events', __name__)


@events_bp.route('/events')
def events():
    return render_template('events.html', active_page='events')


def _parse_date(s):
    return date.fromisoformat(s) if s else None


def _parse_time(s):
    return time.fromisoformat(s) if s else None


def _serialize(event):
    return {
        'id':                   event.id,
        'name':                 event.name,
        'color':                event.color,
        'icon':                 event.icon,
        'date_start':           event.date_start.isoformat() if event.date_start else None,
        'time_start':           event.time_start.isoformat() if event.time_start else None,
        'time_end':             event.time_end.isoformat() if event.time_end else None,
        'duration_days':        event.duration_days,
        'recurrence_enabled':   event.recurrence_enabled,
        'recurrence_type':      event.recurrence_type,
        'recurrence_end':       event.recurrence_end.isoformat() if event.recurrence_end else None,
        'recurrence_interval':  event.recurrence_interval,
        'recurrence_weekdays':  [int(x) for x in event.recurrence_weekdays.split(',') if x != ''] if event.recurrence_weekdays else [],
        'recurrence_monthdays': [int(x) for x in event.recurrence_monthdays.split(',') if x != ''] if event.recurrence_monthdays else [],
        'notes_id':             event.notes_id,
        'task_id':              event.task_id,
        'created_at':           event.created_at.isoformat() if event.created_at else None,
    }


def _find_interval_anchors(event, search_start, search_end):
    step = event.recurrence_interval or 1
    if search_start <= event.date_start:
        cur = event.date_start
    else:
        days_since = (search_start - event.date_start).days
        steps_needed = -(-days_since // step)  # ceil division
        cur = event.date_start + timedelta(days=steps_needed * step)
    anchors = []
    while cur <= search_end:
        anchors.append(cur)
        cur += timedelta(days=step)
    return anchors


def _find_weekday_anchors(event, search_start, search_end):
    weekdays = set(int(x) for x in (event.recurrence_weekdays or '').split(',') if x != '')
    anchors = []
    cur = search_start
    while cur <= search_end:
        # date.weekday(): 0=segunda...6=domingo — mesma convenção do model.
        if cur.weekday() in weekdays:
            anchors.append(cur)
        cur += timedelta(days=1)
    return anchors


def _find_monthday_anchors(event, search_start, search_end):
    days = set(int(x) for x in (event.recurrence_monthdays or '').split(',') if x != '')
    anchors = []
    y, m = search_start.year, search_start.month
    while date(y, m, 1) <= search_end:
        for day in days:
            try:
                occ = date(y, m, day)
                if search_start <= occ <= search_end:
                    anchors.append(occ)
            except ValueError:
                pass  # mês sem esse dia (ex: 31 em abril) — sem ocorrência
        m += 1
        if m > 12:
            m = 1
            y += 1
    return sorted(anchors)


def _find_yearday_anchors(event, search_start, search_end):
    month, day = event.date_start.month, event.date_start.day
    anchors = []
    for y in range(search_start.year, search_end.year + 1):
        try:
            occ = date(y, month, day)
            if search_start <= occ <= search_end:
                anchors.append(occ)
        except ValueError:
            pass  # 29 de fevereiro em ano não bissexto
    return anchors


_ANCHOR_FINDERS = {
    'interval': _find_interval_anchors,
    'weekdays': _find_weekday_anchors,
    'monthday': _find_monthday_anchors,
    'yearday':  _find_yearday_anchors,
}


def _expand_occurrences(event, range_start, range_end):
    """Datas (date) em que `event` ocorre dentro de [range_start, range_end].

    Uma linha de Event = uma REGRA (não uma ocorrência por linha) — isso
    aqui expande a regra em datas de verdade pro intervalo pedido. Cada
    "anchor" (dia em que a regra dispara) por sua vez se expande em
    `duration_days` dias consecutivos (faixa diária com o mesmo horário
    em cada um, não um bloco contínuo sem interrupção entre os dias).
    """
    duration = event.duration_days or 1

    if not event.recurrence_enabled:
        span_start = event.date_start
        span_end = span_start + timedelta(days=duration - 1)
        lo, hi = max(range_start, span_start), min(range_end, span_end)
        if lo > hi:
            return []
        return [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]

    end_limit = range_end
    if event.recurrence_end and event.recurrence_end < end_limit:
        end_limit = event.recurrence_end
    if event.date_start > end_limit:
        return []

    # anchors podem cair até (duration-1) dias antes do início do range
    # pedido e ainda assim ter dias dentro dele (ex: anchor 2 dias antes,
    # duration 5 -> ainda cobre 3 dias dentro do range).
    search_start = max(event.date_start, range_start - timedelta(days=duration - 1))
    search_end = end_limit
    if search_start > search_end:
        return []

    finder = _ANCHOR_FINDERS.get(event.recurrence_type)
    anchors = finder(event, search_start, search_end) if finder else []

    occurrences = set()
    for anchor in anchors:
        for i in range(duration):
            d = anchor + timedelta(days=i)
            if range_start <= d <= range_end:
                occurrences.add(d)
    return sorted(occurrences)


@events_bp.route('/api/events', methods=['GET'])
def list_events():
    # FullCalendar chama isso como fonte de eventos, sempre com start/end
    # do intervalo visível — sem os dois, cai num intervalo largo (ano
    # corrente) só pra não devolver tudo sem limite nenhum.
    start = _parse_date(request.args.get('start', '')[:10]) or date.today().replace(month=1, day=1)
    end = _parse_date(request.args.get('end', '')[:10]) or date.today().replace(month=12, day=31)

    with SessionLocal() as db:
        rows = db.execute(select(Event)).scalars().all()
        result = []
        for event in rows:
            for occ_date in _expand_occurrences(event, start, end):
                item = {
                    'id':    str(event.id),
                    'title': event.name,
                    'allDay': not event.time_start,
                    'extendedProps': {
                        'event_id':  event.id,
                        'occurrence_date': occ_date.isoformat(),
                        'icon':      event.icon,
                        'color':     event.color,
                        'recurrence_enabled': event.recurrence_enabled,
                    },
                }
                if event.time_start:
                    item['start'] = f"{occ_date.isoformat()}T{event.time_start.isoformat()}"
                    if event.time_end:
                        item['end'] = f"{occ_date.isoformat()}T{event.time_end.isoformat()}"
                else:
                    item['start'] = occ_date.isoformat()
                result.append(item)
        return jsonify(result)


@events_bp.route('/api/events/by-date', methods=['GET'])
def events_by_date():
    # Usado pela Agenda: uma data só, já resolvida (não precisa expandir
    # o mês inteiro pra mostrar a lista de um dia).
    day = _parse_date(request.args.get('date', ''))
    if not day:
        return jsonify({'error': 'date is required'}), 422
    with SessionLocal() as db:
        rows = db.execute(select(Event)).scalars().all()
        result = []
        for event in rows:
            if day in _expand_occurrences(event, day, day):
                result.append(_serialize(event))
        result.sort(key=lambda e: (e['time_start'] or '', e['name']))
        return jsonify(result)


def _apply_fields(event, data):
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            raise ValueError('name is required')
        event.name = name
    if 'color' in data:
        event.color = data['color'] or None
    if 'icon' in data:
        event.icon = data['icon'] or None
    if 'date_start' in data:
        event.date_start = _parse_date(data['date_start'])
        if not event.date_start:
            raise ValueError('date_start is required')
    if 'time_start' in data:
        event.time_start = _parse_time(data['time_start'])
    if 'time_end' in data:
        event.time_end = _parse_time(data['time_end'])
    if 'duration_days' in data:
        event.duration_days = int(data['duration_days']) if data['duration_days'] else None
    if 'recurrence_enabled' in data:
        event.recurrence_enabled = bool(data['recurrence_enabled'])
    if 'recurrence_type' in data:
        event.recurrence_type = data['recurrence_type'] or None
    if 'recurrence_end' in data:
        event.recurrence_end = _parse_date(data['recurrence_end'])
    if 'recurrence_interval' in data:
        event.recurrence_interval = int(data['recurrence_interval']) if data['recurrence_interval'] else None
    if 'recurrence_weekdays' in data:
        weekdays = data['recurrence_weekdays'] or []
        event.recurrence_weekdays = ','.join(str(int(w)) for w in weekdays) if weekdays else None
    if 'recurrence_monthdays' in data:
        monthdays = data['recurrence_monthdays'] or []
        event.recurrence_monthdays = ','.join(str(int(d)) for d in monthdays) if monthdays else None
    if 'notes_id' in data:
        event.notes_id = data['notes_id']
    if 'task_id' in data:
        event.task_id = data['task_id']

    # Trava de consistência (mesma regra decidida pro form): numa recorrência
    # semanal/mensal, o dia da semana/mês de date_start SEMPRE faz parte do
    # conjunto marcado — nunca dá pra criar uma regra cujo próprio dia de
    # início não dispara. E com Duração ativa (>1 dia), um único anchor por
    # regra (o do date_start) — múltiplos anchors + duração multi-dia geram
    # blocos sobrepostos entre si (ex: anchor de segunda com duração 3 dias
    # colide com o anchor de quarta, que também cobre a quarta-feira).
    if event.recurrence_enabled and event.recurrence_type == 'weekdays':
        anchor_weekday = event.date_start.weekday()
        if event.duration_days and event.duration_days > 1:
            event.recurrence_weekdays = str(anchor_weekday)
        else:
            weekdays = set(int(x) for x in (event.recurrence_weekdays or '').split(',') if x != '')
            weekdays.add(anchor_weekday)
            event.recurrence_weekdays = ','.join(str(w) for w in sorted(weekdays))
    if event.recurrence_enabled and event.recurrence_type == 'monthday':
        anchor_day = event.date_start.day
        if event.duration_days and event.duration_days > 1:
            event.recurrence_monthdays = str(anchor_day)
        else:
            monthdays = set(int(x) for x in (event.recurrence_monthdays or '').split(',') if x != '')
            monthdays.add(anchor_day)
            event.recurrence_monthdays = ','.join(str(d) for d in sorted(monthdays))


@events_bp.route('/api/events', methods=['POST'])
def create_event():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 422
    date_start = _parse_date(data.get('date_start'))
    if not date_start:
        return jsonify({'error': 'date_start is required'}), 422

    with SessionLocal() as db:
        event = Event(name=name, date_start=date_start)
        try:
            _apply_fields(event, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.add(event)
        db.commit()
        db.refresh(event)
        return jsonify(_serialize(event)), 201


@events_bp.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    with SessionLocal() as db:
        event = db.get(Event, event_id)
        if not event:
            return jsonify({'error': 'not found'}), 404
        return jsonify(_serialize(event))


@events_bp.route('/api/events/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        event = db.get(Event, event_id)
        if not event:
            return jsonify({'error': 'not found'}), 404
        try:
            _apply_fields(event, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.commit()
        db.refresh(event)
        return jsonify(_serialize(event))


@events_bp.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    with SessionLocal() as db:
        event = db.get(Event, event_id)
        if not event:
            return jsonify({'error': 'not found'}), 404
        db.delete(event)
        db.commit()
        return '', 204
