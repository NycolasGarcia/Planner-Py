from datetime import date, datetime

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import select, func

from db.database import SessionLocal
from models.task import Task
from models.task_list import TaskList
from models.event import Event
from models.note import Note
from models.project_card import Card
from models.project_column import Column
from models.project import Project
from routes.events import _expand_occurrences

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/tasks')
def tasks():
    return render_template('tasks.html', active_page='tasks')


def _parse_date(s):
    return date.fromisoformat(s) if s else None


def _current_occurrence_date(event):
    # Ocorrência mais recente que já devia ter acontecido, até hoje — é
    # contra essa data que o "feito" de uma task recorrente é comparado
    # (ver _task_is_done). Reaproveita o motor de recorrência de Eventos,
    # sem lógica nova.
    occs = _expand_occurrences(event, event.date_start, date.today())
    return occs[-1] if occs else None


def _task_is_done(task, event):
    if not task.last_check:
        return False
    if not event or not event.recurrence_enabled:
        return True  # sem recorrência: presença de last_check = feito
    target = _current_occurrence_date(event)
    return target is not None and task.last_check == target


def _serialize_deadline(event):
    if not event:
        return None
    return {
        'event_id':            event.id,
        'date':                event.date_start.isoformat(),
        'recurrence_enabled':  event.recurrence_enabled,
    }


def _serialize_task(task, event=None):
    # Sem color/icon/description próprios — herdam da TaskList no client
    # (currentTaskList.color/.icon), que já está em memória lá.
    return {
        'id':           task.id,
        'task_list_id': task.task_list_id,
        'name':         task.name,
        'rank':         task.rank,
        'order':        task.order,
        'notes_id':     task.notes_id,
        'deadline':     _serialize_deadline(event),
        'is_done':      _task_is_done(task, event),
        'last_check':   task.last_check.isoformat() if task.last_check else None,
        'created_at':   task.created_at.isoformat() if task.created_at else None,
        'updated_at':   task.updated_at.isoformat() if task.updated_at else None,
    }


def _find_related_note_title(db, tl):
    if not tl.notes_id:
        return None
    note = db.get(Note, tl.notes_id)
    return note.title if note else None


def _find_related_project_name(db, tl):
    # TaskList não sabe se está anexada a um Card (é o Card que segura
    # tasklist_id — ver models/project_card.py) — busca inversa, igual o
    # padrão já usado pra achar quem referencia um Event.
    card = db.execute(select(Card).where(Card.tasklist_id == tl.id)).scalar_one_or_none()
    if not card:
        return None
    column = db.get(Column, card.column_id)
    project = db.get(Project, column.project_id) if column else None
    return project.name if project else None


def _serialize_tasklist(tasklist, event=None, task_count=None, done_count=None, db=None):
    data = {
        'id':          tasklist.id,
        'name':        tasklist.name,
        'description': tasklist.description,
        'color':       tasklist.color,
        'icon':        tasklist.icon,
        'is_pinned':   tasklist.is_pinned,
        'notes_id':    tasklist.notes_id,
        'deadline':    _serialize_deadline(event),
        'task_count':  task_count,
        'done_count':  done_count,
        'order':       tasklist.order,
        'created_at':  tasklist.created_at.isoformat() if tasklist.created_at else None,
        'updated_at':  tasklist.updated_at.isoformat() if tasklist.updated_at else None,
    }
    if db is not None:
        data['note_title'] = _find_related_note_title(db, tasklist)
        data['project_name'] = _find_related_project_name(db, tasklist)
    return data


def _apply_deadline(db, owner, deadline_data):
    # owner = Task ou TaskList (ambos têm event_id). Prazo é sempre um Event
    # de verdade por trás — nunca uma data literal (ver models/task.py).
    # deadline_data == None limpa o prazo (apaga o Event, zera event_id).
    if deadline_data is None:
        if owner.event_id:
            event = db.get(Event, owner.event_id)
            owner.event_id = None
            if event:
                db.delete(event)
        return

    date_start = _parse_date(deadline_data.get('date'))
    if not date_start:
        raise ValueError('deadline.date is required')

    if owner.event_id:
        event = db.get(Event, owner.event_id)
    else:
        event = Event(name=owner.name, date_start=date_start)
        db.add(event)
        db.flush()  # autoflush=False na SessionLocal — precisa do id já
        owner.event_id = event.id

    # Ícone/cor do Event sempre vêm da TaskList — Task não tem mais visual
    # próprio (ver models/task.py), então mesmo um prazo criado a partir de
    # uma Task individual usa o ícone/cor da lista-mãe dela.
    visual_owner = owner.task_list if isinstance(owner, Task) else owner

    event.name = owner.name
    event.icon = visual_owner.icon
    event.color = visual_owner.color
    event.date_start = date_start
    event.recurrence_enabled = bool(deadline_data.get('recurrence_enabled', False))
    if event.recurrence_enabled:
        event.recurrence_type = deadline_data.get('recurrence_type')
        event.recurrence_end = _parse_date(deadline_data.get('recurrence_end'))
        event.recurrence_interval = deadline_data.get('recurrence_interval')
        weekdays = deadline_data.get('recurrence_weekdays') or []
        event.recurrence_weekdays = ','.join(str(int(w)) for w in weekdays) if weekdays else None
        monthdays = deadline_data.get('recurrence_monthdays') or []
        event.recurrence_monthdays = ','.join(str(int(d)) for d in monthdays) if monthdays else None
    else:
        event.recurrence_type = None
        event.recurrence_end = None
        event.recurrence_interval = None
        event.recurrence_weekdays = None
        event.recurrence_monthdays = None


def _delete_owned_event(db, owner):
    # Event "prazo" nunca sabe quem o referencia (ver models/event.py) —
    # quem apaga o dono é responsável por apagar o Event junto, senão vira
    # lixo solto no módulo de Eventos.
    if owner.event_id:
        event = db.get(Event, owner.event_id)
        if event:
            db.delete(event)


def _apply_tasklist_fields(db, tl, data):
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            raise ValueError('name is required')
        tl.name = name
        if tl.event_id:
            event = db.get(Event, tl.event_id)
            if event:
                event.name = name
    if 'description' in data:
        tl.description = data['description'] or None
    if 'color' in data or 'icon' in data:
        if 'color' in data:
            tl.color = data['color'] or None
        if 'icon' in data:
            tl.icon = data['icon'] or None
        # Tasks não têm ícone/cor próprios — os Events "prazo" delas (e o
        # da própria lista) herdam da TaskList, então precisam ressincronizar
        # junto sempre que a lista muda de visual, não só na criação.
        owned_event_ids = [tl.event_id] + [t.event_id for t in tl.tasks]
        for event in _batch_events(db, owned_event_ids).values():
            event.icon = tl.icon
            event.color = tl.color
    if 'is_pinned' in data:
        tl.is_pinned = bool(data['is_pinned'])
    if 'notes_id' in data:
        tl.notes_id = data['notes_id']
    if 'deadline' in data:
        _apply_deadline(db, tl, data['deadline'])
    tl.updated_at = datetime.utcnow()


def _apply_task_fields(db, task, data):
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            raise ValueError('name is required')
        task.name = name
        if task.event_id:
            event = db.get(Event, task.event_id)
            if event:
                event.name = name
    if 'rank' in data:
        task.rank = data['rank']
    if 'notes_id' in data:
        task.notes_id = data['notes_id']
    if 'deadline' in data:
        _apply_deadline(db, task, data['deadline'])
    task.updated_at = datetime.utcnow()


def _batch_events(db, ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {e.id: e for e in db.execute(select(Event).where(Event.id.in_(ids))).scalars()}


def _full_tasklist_payload(db, tl):
    # Sempre inclui 'tasks' — usado por create/get/update, nunca só um
    # subconjunto dos campos, senão o client (que substitui o objeto
    # inteiro a cada resposta) perde a lista de tasks em qualquer edição
    # de campo da própria TaskList (rename, cor, ícone, pin...).
    events = _batch_events(db, [tl.event_id] + [t.event_id for t in tl.tasks])
    done = sum(1 for t in tl.tasks if _task_is_done(t, events.get(t.event_id)))
    data = _serialize_tasklist(tl, events.get(tl.event_id), len(tl.tasks), done, db)
    # tl.tasks já vem ordenado por Task.order (order_by no relationship)
    data['tasks'] = [_serialize_task(t, events.get(t.event_id)) for t in tl.tasks]
    return data


# ---------- TaskLists ----------

@tasks_bp.route('/api/tasklists', methods=['GET'])
def list_tasklists():
    with SessionLocal() as db:
        rows = list(db.execute(select(TaskList)).scalars())
        rows.sort(key=lambda tl: (not tl.is_pinned, tl.name.lower()))

        event_ids = []
        for tl in rows:
            event_ids.append(tl.event_id)
            event_ids.extend(t.event_id for t in tl.tasks)
        events = _batch_events(db, event_ids)

        result = []
        for tl in rows:
            tl_tasks = tl.tasks
            done = sum(1 for t in tl_tasks if _task_is_done(t, events.get(t.event_id)))
            result.append(_serialize_tasklist(tl, events.get(tl.event_id), len(tl_tasks), done, db))
        return jsonify(result)


@tasks_bp.route('/api/tasklists', methods=['POST'])
def create_tasklist():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 422
    with SessionLocal() as db:
        max_order = db.execute(select(func.coalesce(func.max(TaskList.order), -1))).scalar()
        tl = TaskList(name=name, is_pinned=False, order=max_order + 1)
        try:
            _apply_tasklist_fields(db, tl, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.add(tl)
        db.commit()
        db.refresh(tl)
        return jsonify(_full_tasklist_payload(db, tl)), 201


@tasks_bp.route('/api/tasklists/<int:tasklist_id>', methods=['GET'])
def get_tasklist(tasklist_id):
    with SessionLocal() as db:
        tl = db.get(TaskList, tasklist_id)
        if not tl:
            return jsonify({'error': 'not found'}), 404
        return jsonify(_full_tasklist_payload(db, tl))


@tasks_bp.route('/api/tasklists/<int:tasklist_id>', methods=['PUT'])
def update_tasklist(tasklist_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        tl = db.get(TaskList, tasklist_id)
        if not tl:
            return jsonify({'error': 'not found'}), 404
        try:
            _apply_tasklist_fields(db, tl, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.commit()
        db.refresh(tl)
        return jsonify(_full_tasklist_payload(db, tl))


@tasks_bp.route('/api/tasklists/<int:tasklist_id>', methods=['DELETE'])
def delete_tasklist(tasklist_id):
    with SessionLocal() as db:
        tl = db.get(TaskList, tasklist_id)
        if not tl:
            return jsonify({'error': 'not found'}), 404
        for t in tl.tasks:
            _delete_owned_event(db, t)
        _delete_owned_event(db, tl)
        db.delete(tl)  # cascade ORM apaga as tasks (delete-orphan no model)
        db.commit()
        return '', 204


@tasks_bp.route('/api/tasklists/reorder', methods=['POST'])
def reorder_tasklists():
    # Mesmo padrão do reorder de tasks — uma sequência global (fixadas +
    # outras juntas, na ordem que vieram) vira o novo "order" de cada uma.
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    with SessionLocal() as db:
        by_id = {tl.id: tl for tl in db.execute(select(TaskList)).scalars()}
        for idx, tl_id in enumerate(order):
            if tl_id in by_id:
                by_id[tl_id].order = idx
        db.commit()
        return '', 204


# ---------- Tasks ----------

@tasks_bp.route('/api/tasklists/<int:tasklist_id>/tasks', methods=['POST'])
def create_task(tasklist_id):
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 422
    with SessionLocal() as db:
        tl = db.get(TaskList, tasklist_id)
        if not tl:
            return jsonify({'error': 'not found'}), 404
        max_order = db.execute(
            select(func.coalesce(func.max(Task.order), -1)).where(Task.task_list_id == tasklist_id)
        ).scalar()
        task = Task(name=name, task_list_id=tasklist_id, order=max_order + 1)
        try:
            _apply_task_fields(db, task, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.add(task)
        db.commit()
        db.refresh(task)
        event = db.get(Event, task.event_id) if task.event_id else None
        return jsonify(_serialize_task(task, event)), 201


@tasks_bp.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        try:
            _apply_task_fields(db, task, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.commit()
        db.refresh(task)
        event = db.get(Event, task.event_id) if task.event_id else None
        return jsonify(_serialize_task(task, event))


@tasks_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        _delete_owned_event(db, task)
        db.delete(task)
        db.commit()
        return '', 204


@tasks_bp.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        event = db.get(Event, task.event_id) if task.event_id else None
        if _task_is_done(task, event):
            task.last_check = None
        elif event and event.recurrence_enabled:
            task.last_check = _current_occurrence_date(event) or date.today()
        else:
            task.last_check = date.today()
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
        return jsonify(_serialize_task(task, event))


@tasks_bp.route('/api/tasklists/<int:tasklist_id>/tasks/reorder', methods=['POST'])
def reorder_tasks(tasklist_id):
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    with SessionLocal() as db:
        by_id = {t.id: t for t in db.execute(
            select(Task).where(Task.task_list_id == tasklist_id)
        ).scalars()}
        for idx, task_id in enumerate(order):
            if task_id in by_id:
                by_id[task_id].order = idx
        db.commit()
        return '', 204
