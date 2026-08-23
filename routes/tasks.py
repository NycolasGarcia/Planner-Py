from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import select, func

from db.database import SessionLocal
from models.task import Task
from models.task_list import TaskList
from models.event import Event
from models.note import Note
from models.settings import Setting
from models.project_card import Card
from models.project_column import Column
from models.project import Project

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/tasks')
def tasks():
    return render_template('tasks.html', active_page='tasks')


def _parse_date(s):
    return date.fromisoformat(s) if s else None


def _task_is_done(task):
    # Task não tem prazo/recorrência próprio (só a TaskList tem) — "feito" é
    # sempre binário: presença de last_check = feito, ponto.
    return task.last_check is not None


def _serialize_deadline(event):
    if not event:
        return None
    return {
        'event_id':            event.id,
        'date':                event.date_start.isoformat(),
        'recurrence_enabled':  event.recurrence_enabled,
    }


def _serialize_task(task):
    # Sem color/icon/notes_id/event_id próprios — task só existe dentro da
    # sua TaskList (herda visual dela no client) e não linka com mais nada.
    return {
        'id':           task.id,
        'task_list_id': task.task_list_id,
        'name':         task.name,
        'rank':         task.rank,
        'order':        task.order,
        'is_done':      _task_is_done(task),
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
        'deleted_at':  tasklist.deleted_at.isoformat() if tasklist.deleted_at else None,
        'created_at':  tasklist.created_at.isoformat() if tasklist.created_at else None,
        'updated_at':  tasklist.updated_at.isoformat() if tasklist.updated_at else None,
    }
    if db is not None:
        data['note_title'] = _find_related_note_title(db, tasklist)
        data['project_name'] = _find_related_project_name(db, tasklist)
    return data


def _apply_deadline(db, tl, deadline_data):
    # Só TaskList tem prazo — Task não linka com Event (ver models/task.py).
    # Prazo é sempre um Event de verdade por trás, nunca uma data literal.
    # deadline_data == None limpa o prazo (apaga o Event, zera event_id).
    if deadline_data is None:
        if tl.event_id:
            event = db.get(Event, tl.event_id)
            tl.event_id = None
            if event:
                db.delete(event)
        return

    date_start = _parse_date(deadline_data.get('date'))
    if not date_start:
        raise ValueError('deadline.date is required')

    if tl.event_id:
        event = db.get(Event, tl.event_id)
    else:
        event = Event(name=tl.name, date_start=date_start)
        db.add(event)
        db.flush()  # autoflush=False na SessionLocal — precisa do id já
        tl.event_id = event.id

    event.name = tl.name
    event.icon = tl.icon
    event.color = tl.color
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


def _delete_owned_event(db, tl):
    # Event "prazo" nunca sabe quem o referencia (ver models/event.py) —
    # quem apaga o dono (só TaskList tem prazo próprio) é responsável por
    # apagar o Event junto, senão vira lixo solto no módulo de Eventos.
    # Zera event_id sempre (não só quando o dono também vai ser apagado em
    # seguida) — necessário pro caso de ida pra Lixeira, onde a TaskList
    # continua existindo.
    if tl.event_id:
        event = db.get(Event, tl.event_id)
        if event:
            db.delete(event)
        tl.event_id = None


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
        # O Event "prazo" da própria lista (se tiver) precisa ressincronizar
        # com o novo visual — tasks não têm Event próprio, então só esse.
        if tl.event_id:
            event = db.get(Event, tl.event_id)
            if event:
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
    # Task só tem nome, rank e last_check (concluída) — sem cor, ícone,
    # nota vinculada ou prazo próprios (ver models/task.py).
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            raise ValueError('name is required')
        task.name = name
    if 'rank' in data:
        task.rank = data['rank']
    task.updated_at = datetime.utcnow()


def _batch_events(db, ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {e.id: e for e in db.execute(select(Event).where(Event.id.in_(ids))).scalars()}


def _tl_trash_retention_days(db):
    # Mesmo esquema de _trash_retention_days em routes/notes.py — 'none' =
    # sem retenção (delete já é permanente na hora), qualquer outro valor
    # (ou ausência do setting) cai no default de 7 dias.
    row = db.query(Setting).filter(Setting.key == 'tarefas.lixeira_retencao_dias').one_or_none()
    value = row.value if row else None
    if value == 'none':
        return None
    try:
        return int(value) if value else 7
    except (TypeError, ValueError):
        return 7


def _purge_expired_tasklist_trash(db):
    # Diferente da Lixeira de Notas (que faz um DELETE em massa direto na
    # tabela): TaskList tem Tasks dependentes via relationship ORM
    # (cascade="all, delete-orphan"), que só dispara em delete OBJETO A
    # OBJETO (session.delete), não num DELETE de tabela cru — teria Task
    # órfã sobrando (ou erro de FK) se fosse um DELETE em massa aqui.
    retention = _tl_trash_retention_days(db)
    query = select(TaskList).where(TaskList.deleted_at.isnot(None))
    if retention is not None:
        cutoff = datetime.utcnow() - timedelta(days=retention)
        query = query.where(TaskList.deleted_at < cutoff)
    rows = db.execute(query).scalars().all()
    for tl in rows:
        db.delete(tl)
    if rows:
        db.commit()


def _trash_or_delete_tasklist(db, tl, retention):
    # Já estava na lixeira (delete de novo = permanente) ou retenção
    # "nenhum": apaga de verdade agora. Senão, manda pra lixeira — mas o
    # prazo (Event) é apagado JÁ, não fica pendurado ativo no calendário
    # enquanto a lista está descartada (ver _delete_owned_event). Restaurada
    # depois, volta sem prazo — mesma lógica de "recriar é fácil" que já
    # vale pra Task (não guarda snapshot pra "ressuscitar" o Event).
    already_trashed = tl.deleted_at is not None
    if already_trashed or retention is None:
        _delete_owned_event(db, tl)
        db.delete(tl)
    else:
        _delete_owned_event(db, tl)
        tl.deleted_at = datetime.utcnow()


def _full_tasklist_payload(db, tl):
    # Sempre inclui 'tasks' — usado por create/get/update, nunca só um
    # subconjunto dos campos, senão o client (que substitui o objeto
    # inteiro a cada resposta) perde a lista de tasks em qualquer edição
    # de campo da própria TaskList (rename, cor, ícone, pin...).
    event = db.get(Event, tl.event_id) if tl.event_id else None
    done = sum(1 for t in tl.tasks if _task_is_done(t))
    data = _serialize_tasklist(tl, event, len(tl.tasks), done, db)
    # tl.tasks já vem ordenado por Task.order (order_by no relationship)
    data['tasks'] = [_serialize_task(t) for t in tl.tasks]
    return data


# ---------- TaskLists ----------

@tasks_bp.route('/api/tasklists', methods=['GET'])
def list_tasklists():
    with SessionLocal() as db:
        _purge_expired_tasklist_trash(db)
        rows = list(db.execute(select(TaskList)).scalars())
        rows.sort(key=lambda tl: (not tl.is_pinned, tl.name.lower()))

        events = _batch_events(db, [tl.event_id for tl in rows])

        result = []
        for tl in rows:
            tl_tasks = tl.tasks
            done = sum(1 for t in tl_tasks if _task_is_done(t))
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
        _trash_or_delete_tasklist(db, tl, _tl_trash_retention_days(db))
        db.commit()
        return '', 204


@tasks_bp.route('/api/tasklists/<int:tasklist_id>/restore', methods=['POST'])
def restore_tasklist(tasklist_id):
    with SessionLocal() as db:
        tl = db.get(TaskList, tasklist_id)
        if not tl:
            return jsonify({'error': 'not found'}), 404
        tl.deleted_at = None
        db.commit()
        db.refresh(tl)
        return jsonify(_full_tasklist_payload(db, tl))


@tasks_bp.route('/api/tasklists/bulk-delete', methods=['POST'])
def bulk_delete_tasklists():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not ids:
        return jsonify({'error': 'no ids'}), 422
    with SessionLocal() as db:
        retention = _tl_trash_retention_days(db)
        rows = db.execute(select(TaskList).where(TaskList.id.in_(ids))).scalars().all()
        for tl in rows:
            _trash_or_delete_tasklist(db, tl, retention)
        db.commit()
        return jsonify({'updated': len(rows)}), 200


@tasks_bp.route('/api/tasklists/bulk-update', methods=['POST'])
def bulk_update_tasklists():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not ids:
        return jsonify({'error': 'no ids'}), 422
    allowed = ('color', 'icon', 'is_pinned')
    patch = {k: data[k] for k in allowed if k in data}
    if not patch:
        return jsonify({'error': 'no fields to update'}), 422
    with SessionLocal() as db:
        rows = db.execute(select(TaskList).where(TaskList.id.in_(ids))).scalars().all()
        # Reaproveita _apply_tasklist_fields por item (não um UPDATE em
        # massa direto) — é ela quem resincroniza ícone/cor com os Events
        # "prazo" da lista e de cada task dela.
        for tl in rows:
            _apply_tasklist_fields(db, tl, patch)
        db.commit()
        return jsonify({'updated': len(rows)}), 200


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
        return jsonify(_serialize_task(task)), 201


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
        return jsonify(_serialize_task(task))


@tasks_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        db.delete(task)
        db.commit()
        return '', 204


@tasks_bp.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        task.last_check = None if _task_is_done(task) else date.today()
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
        return jsonify(_serialize_task(task))


@tasks_bp.route('/api/tasklists/<int:tasklist_id>/tasks/complete-all', methods=['POST'])
def complete_all_tasks(tasklist_id):
    # Só marca — nunca desmarca (quem já estava concluída, pula).
    with SessionLocal() as db:
        tl = db.get(TaskList, tasklist_id)
        if not tl:
            return jsonify({'error': 'not found'}), 404
        for t in tl.tasks:
            if not _task_is_done(t):
                t.last_check = date.today()
                t.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(tl)
        return jsonify(_full_tasklist_payload(db, tl))


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
