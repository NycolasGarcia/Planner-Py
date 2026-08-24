from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import select, func

from db.database import SessionLocal
from models.project import Project
from models.project_column import Column
from models.project_card import Card
from models.task_list import TaskList
from models.event import Event
from models.note import Note
from models.settings import Setting

from routes.tasks import _apply_deadline, _serialize_deadline, _delete_owned_event, _task_is_done

projects_bp = Blueprint('projects', __name__)


@projects_bp.route('/projects')
def projects():
    return render_template('projects.html', active_page='projects')


@projects_bp.route('/projects/<int:project_id>')
def project_board(project_id):
    return render_template('project_board.html', active_page='projects', project_id=project_id)


# ---------- Serialização ----------

def _card_effective_source(db, card):
    # Sem meio-termo (ver models/project_card.py): card linkado a uma
    # TaskList usa nome/nota/prazo/progresso/RANK dela, sempre lidos na
    # hora (nunca copiados) — desvincular volta a usar os campos próprios
    # do card, que continuam intactos no banco o tempo todo. Rank é
    # decidido na TaskList quando linkado (não no Card) — mesmo campo que
    # Card.rank, ver models/task_list.py. Sem cor/ícone: nenhum dos dois
    # existe mais em Card nem é usado visualmente em lugar nenhum do board.
    if card.tasklist_id:
        tl = db.get(TaskList, card.tasklist_id)
        if tl:
            event = db.get(Event, tl.event_id) if tl.event_id else None
            progress = {'done': sum(1 for t in tl.tasks if _task_is_done(t)), 'total': len(tl.tasks)}
            return tl.name, tl.notes_id, event, progress, tl.rank
    event = db.get(Event, card.event_id) if card.event_id else None
    return card.name, card.notes_id, event, None, card.rank


def _serialize_card(card, db):
    name, notes_id, event, task_progress, rank = _card_effective_source(db, card)
    return {
        'id':            card.id,
        'column_id':     card.column_id,
        'name':          name,
        'description':   card.description,
        'rank':          rank,
        'notes_id':      notes_id,
        'deadline':      _serialize_deadline(event),
        'tasklist_id':   card.tasklist_id,
        'task_progress': task_progress,
        'order':         card.order,
        'created_at':    card.created_at.isoformat() if card.created_at else None,
    }


def _serialize_column(column, db, include_cards=False):
    data = {
        'id':          column.id,
        'project_id':  column.project_id,
        'name':        column.name,
        'description': column.description,
        'color':       column.color,
        'icon':        column.icon,
        'notes_id':    column.notes_id,
        'order':       column.order,
        'card_count':  len(column.cards),
    }
    if include_cards:
        data['cards'] = [_serialize_card(c, db) for c in column.cards]
    return data


def _project_aggregate_ids(project, db):
    # note_ids/event_ids distintos: do próprio projeto + o efetivo de cada
    # card (já resolvido acima — própria ou da tasklist vinculada, nunca
    # as duas ao mesmo tempo).
    note_ids = set()
    event_ids = set()
    if project.notes_id:
        note_ids.add(project.notes_id)
    if project.event_id:
        event_ids.add(project.event_id)
    for column in project.columns:
        for card in column.cards:
            _, notes_id, event, _, _ = _card_effective_source(db, card)
            if notes_id:
                note_ids.add(notes_id)
            if event:
                event_ids.add(event.id)
    return note_ids, event_ids


def _serialize_project(project, db, include_columns=False):
    event = db.get(Event, project.event_id) if project.event_id else None
    note = db.get(Note, project.notes_id) if project.notes_id else None
    columns = list(project.columns)  # já vem ordenado (order_by="Column.order")
    card_count = sum(len(c.cards) for c in columns)
    tasklist_count = sum(1 for c in columns for card in c.cards if card.tasklist_id)
    note_ids, event_ids = _project_aggregate_ids(project, db)
    data = {
        'id':             project.id,
        'name':           project.name,
        'description':    project.description,
        'color':          project.color,
        'icon':           project.icon,
        'is_pinned':      project.is_pinned,
        'notes_id':       project.notes_id,
        'note_title':     note.title if note else None,
        'deadline':       _serialize_deadline(event),
        'deleted_at':     project.deleted_at.isoformat() if project.deleted_at else None,
        'created_at':     project.created_at.isoformat() if project.created_at else None,
        'column_count':   len(columns),
        'card_count':     card_count,
        'tasklist_count': tasklist_count,
        'note_ids':       sorted(note_ids),
        'event_ids':      sorted(event_ids),
        # 1 segmento por coluna, na ordem do board — ver templates/projects.html
        'progress_bar':   [
            {'column_id': c.id, 'color': c.color, 'card_count': len(c.cards)}
            for c in columns
        ],
    }
    if include_columns:
        data['columns'] = [_serialize_column(c, db, include_cards=True) for c in columns]
    return data


# ---------- Aplicação de campos ----------

def _apply_project_fields(db, project, data):
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            raise ValueError('name is required')
        project.name = name
        if project.event_id:
            event = db.get(Event, project.event_id)
            if event:
                event.name = name
    if 'description' in data:
        project.description = data['description'] or None
    if 'color' in data or 'icon' in data:
        if 'color' in data:
            project.color = data['color'] or None
        if 'icon' in data:
            project.icon = data['icon'] or None
        if project.event_id:
            event = db.get(Event, project.event_id)
            if event:
                event.icon = project.icon
                event.color = project.color
    if 'is_pinned' in data:
        project.is_pinned = bool(data['is_pinned'])
    if 'notes_id' in data:
        project.notes_id = data['notes_id']
    if 'deadline' in data:
        _apply_deadline(db, project, data['deadline'])


def _apply_column_fields(db, column, data):
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            raise ValueError('name is required')
        column.name = name
    if 'description' in data:
        column.description = data['description'] or None
    if 'color' in data:
        column.color = data['color'] or None
    if 'icon' in data:
        column.icon = data['icon'] or None
    if 'notes_id' in data:
        column.notes_id = data['notes_id']


CARD_DESCRIPTION_MAX_LEN = 200


def _apply_card_fields(db, card, data):
    # description/rank são SEMPRE do card (o link com tasklist nunca mexe
    # neles) — description limitada a 200 chars, não é pra virar um bloco
    # de texto (o mini-card só mostra um resumo curto). name/notes_id/
    # deadline/RANK só têm efeito quando o card não está E não vai ficar
    # linkado — sem meio-termo (ver models/project_card.py e
    # models/task_list.py): se tasklist_id (o valor final, considerando
    # essa própria requisição) é verdadeiro, esses campos são ignorados —
    # a fonte de verdade passa a ser a TaskList vinculada (rank incluso:
    # quem edita é TaskList.rank, via routes/tasks.py).
    if 'description' in data:
        desc = (data['description'] or None)
        card.description = desc[:CARD_DESCRIPTION_MAX_LEN] if desc else None

    effective_tasklist_id = data['tasklist_id'] if 'tasklist_id' in data else card.tasklist_id
    if not effective_tasklist_id:
        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                raise ValueError('name is required')
            card.name = name
        if 'notes_id' in data:
            card.notes_id = data['notes_id']
        if 'deadline' in data:
            _apply_deadline(db, card, data['deadline'])
        if 'rank' in data:
            card.rank = data['rank']

    if 'tasklist_id' in data:
        card.tasklist_id = data['tasklist_id']
    if 'column_id' in data:
        card.column_id = data['column_id']


# ---------- Lixeira (só Project — Column/Card são exclusão direta) ----------

def _project_trash_retention_days(db):
    row = db.query(Setting).filter(Setting.key == 'projetos.lixeira_retencao_dias').one_or_none()
    value = row.value if row else None
    if value == 'none':
        return None
    try:
        return int(value) if value else 7
    except (TypeError, ValueError):
        return 7


def _project_max_colunas(db):
    row = db.query(Setting).filter(Setting.key == 'projetos.max_colunas').one_or_none()
    value = row.value if row else None
    try:
        return int(value) if value else 6
    except (TypeError, ValueError):
        return 6


def _project_colunas_iniciais(db):
    # Template simples: N colunas já nascem criadas num projeto novo — só
    # um ponto de partida, não um mínimo obrigatório (usuário apaga/adiciona
    # à vontade depois, sem nenhuma trava ligada a esse número).
    row = db.query(Setting).filter(Setting.key == 'projetos.colunas_iniciais').one_or_none()
    value = row.value if row else None
    try:
        return max(0, int(value)) if value else 3
    except (TypeError, ValueError):
        return 3


def _delete_project_cascade_events(db, project):
    # Cascade ORM (Project -> Column -> Card) apaga as linhas — mas Event
    # "prazo" não sabe quem o referencia (ver models/event.py), então quem
    # apaga o dono precisa apagar o Event junto, senão vira lixo solto no
    # módulo de Eventos. TaskLists vinculadas a cards NÃO são tocadas
    # (ver models/project_card.py) — sobrevivem intactas e desvinculadas.
    for column in project.columns:
        for card in column.cards:
            _delete_owned_event(db, card)


def _purge_expired_project_trash(db):
    # Mesmo motivo do purge de TaskList (routes/tasks.py): cascade real só
    # dispara em delete OBJETO A OBJETO, nunca num DELETE em massa direto
    # na tabela — teria Column/Card órfã sobrando senão.
    retention = _project_trash_retention_days(db)
    query = select(Project).where(Project.deleted_at.isnot(None))
    if retention is not None:
        cutoff = datetime.utcnow() - timedelta(days=retention)
        query = query.where(Project.deleted_at < cutoff)
    rows = db.execute(query).scalars().all()
    for project in rows:
        _delete_project_cascade_events(db, project)
        db.delete(project)
    if rows:
        db.commit()


def _trash_or_delete_project(db, project, retention):
    # Já estava na lixeira (delete de novo = permanente) ou retenção
    # "nenhum": apaga de verdade agora. Senão, manda pra lixeira — columns/
    # cards ficam intocados (só o Project ganha deleted_at), só o prazo
    # PRÓPRIO do projeto é apagado já (mesma lógica de TaskList: não fica
    # pendurado ativo no calendário enquanto o projeto está descartado).
    already_trashed = project.deleted_at is not None
    if already_trashed or retention is None:
        _delete_project_cascade_events(db, project)
        _delete_owned_event(db, project)
        db.delete(project)
    else:
        _delete_owned_event(db, project)
        project.deleted_at = datetime.utcnow()


# ---------- Projects ----------

@projects_bp.route('/api/projects', methods=['GET'])
def list_projects():
    with SessionLocal() as db:
        _purge_expired_project_trash(db)
        rows = list(db.execute(select(Project)).scalars())
        rows.sort(key=lambda p: (not p.is_pinned, p.name.lower()))
        return jsonify([_serialize_project(p, db) for p in rows])


@projects_bp.route('/api/projects', methods=['POST'])
def create_project():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 422
    with SessionLocal() as db:
        project = Project(name=name, is_pinned=False)
        try:
            _apply_project_fields(db, project, {k: v for k, v in data.items() if k != 'name'})
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.add(project)
        db.flush()  # autoflush=False na SessionLocal — precisa do id já, pras colunas abaixo
        for i in range(_project_colunas_iniciais(db)):
            db.add(Column(name=f'Coluna {i + 1}', project_id=project.id, order=i))
        db.commit()
        db.refresh(project)
        return jsonify(_serialize_project(project, db, include_columns=True)), 201


@projects_bp.route('/api/projects/<int:project_id>', methods=['GET'])
def get_project(project_id):
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if not project:
            return jsonify({'error': 'not found'}), 404
        return jsonify(_serialize_project(project, db, include_columns=True))


@projects_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if not project:
            return jsonify({'error': 'not found'}), 404
        try:
            _apply_project_fields(db, project, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.commit()
        db.refresh(project)
        return jsonify(_serialize_project(project, db, include_columns=True))


@projects_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if not project:
            return jsonify({'error': 'not found'}), 404
        _trash_or_delete_project(db, project, _project_trash_retention_days(db))
        db.commit()
        return '', 204


@projects_bp.route('/api/projects/<int:project_id>/restore', methods=['POST'])
def restore_project(project_id):
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if not project:
            return jsonify({'error': 'not found'}), 404
        project.deleted_at = None
        db.commit()
        db.refresh(project)
        return jsonify(_serialize_project(project, db))


# ---------- Columns ----------

@projects_bp.route('/api/projects/<int:project_id>/columns', methods=['POST'])
def create_column(project_id):
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 422
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if not project:
            return jsonify({'error': 'not found'}), 404
        current_count = db.execute(
            select(func.count()).select_from(Column).where(Column.project_id == project_id)
        ).scalar()
        if current_count >= _project_max_colunas(db):
            return jsonify({'error': 'max columns reached'}), 422
        max_order = db.execute(
            select(func.coalesce(func.max(Column.order), -1)).where(Column.project_id == project_id)
        ).scalar()
        column = Column(name=name, project_id=project_id, order=max_order + 1)
        try:
            _apply_column_fields(db, column, {k: v for k, v in data.items() if k != 'name'})
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.add(column)
        db.commit()
        db.refresh(column)
        return jsonify(_serialize_column(column, db)), 201


@projects_bp.route('/api/columns/<int:column_id>', methods=['PUT'])
def update_column(column_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        column = db.get(Column, column_id)
        if not column:
            return jsonify({'error': 'not found'}), 404
        try:
            _apply_column_fields(db, column, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.commit()
        db.refresh(column)
        return jsonify(_serialize_column(column, db))


@projects_bp.route('/api/columns/<int:column_id>', methods=['DELETE'])
def delete_column(column_id):
    with SessionLocal() as db:
        column = db.get(Column, column_id)
        if not column:
            return jsonify({'error': 'not found'}), 404
        # Cascade ORM apaga os Cards da coluna (models/project_column.py) —
        # tasklists vinculadas a eles sobrevivem (ver models/project_card.py).
        for card in column.cards:
            _delete_owned_event(db, card)
        db.delete(column)
        db.commit()
        return '', 204


@projects_bp.route('/api/projects/<int:project_id>/columns/reorder', methods=['POST'])
def reorder_columns(project_id):
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    with SessionLocal() as db:
        by_id = {c.id: c for c in db.execute(select(Column).where(Column.project_id == project_id)).scalars()}
        for idx, column_id in enumerate(order):
            if column_id in by_id:
                by_id[column_id].order = idx
        db.commit()
        return '', 204


# ---------- Cards ----------

@projects_bp.route('/api/columns/<int:column_id>/cards', methods=['POST'])
def create_card(column_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        column = db.get(Column, column_id)
        if not column:
            return jsonify({'error': 'not found'}), 404

        tasklist_id = data.get('tasklist_id')
        tl = None
        if tasklist_id:
            tl = db.get(TaskList, tasklist_id)
            if not tl:
                return jsonify({'error': 'tasklist not found'}), 404
            if tl.card is not None:
                return jsonify({'error': 'tasklist already linked to another card'}), 422

        # Nome nasce copiado da tasklist quando já cria linkado — fica
        # irrelevante assim que o link existe (ver _card_effective_source),
        # só existe pra satisfazer NOT NULL e sobrar algo coerente se um
        # dia for desvinculado.
        name = (data.get('name') or (tl.name if tl else '')).strip()
        if not name:
            return jsonify({'error': 'name is required'}), 422

        max_order = db.execute(
            select(func.coalesce(func.max(Card.order), -1)).where(Card.column_id == column_id)
        ).scalar()
        card = Card(name=name, column_id=column_id, order=max_order + 1, tasklist_id=tasklist_id)
        try:
            rest = {k: v for k, v in data.items() if k not in ('name', 'tasklist_id')}
            _apply_card_fields(db, card, rest)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.add(card)
        db.commit()
        db.refresh(card)
        return jsonify(_serialize_card(card, db)), 201


@projects_bp.route('/api/cards/<int:card_id>', methods=['PUT'])
def update_card(card_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        card = db.get(Card, card_id)
        if not card:
            return jsonify({'error': 'not found'}), 404
        if 'tasklist_id' in data and data['tasklist_id']:
            tl = db.get(TaskList, data['tasklist_id'])
            if not tl:
                return jsonify({'error': 'tasklist not found'}), 404
            if tl.card is not None and tl.card.id != card.id:
                return jsonify({'error': 'tasklist already linked to another card'}), 422
        try:
            _apply_card_fields(db, card, data)
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        db.commit()
        db.refresh(card)
        return jsonify(_serialize_card(card, db))


@projects_bp.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    with SessionLocal() as db:
        card = db.get(Card, card_id)
        if not card:
            return jsonify({'error': 'not found'}), 404
        # Prazo PRÓPRIO do card (se autônomo) é apagado junto, senão vira
        # lixo solto no módulo de Eventos. TaskList vinculada (se houver)
        # NÃO é tocada — sobrevive intacta, só perde o vínculo (ver
        # models/project_card.py).
        _delete_owned_event(db, card)
        db.delete(card)
        db.commit()
        return '', 204


@projects_bp.route('/api/columns/<int:column_id>/cards/reorder', methods=['POST'])
def reorder_cards(column_id):
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    with SessionLocal() as db:
        by_id = {c.id: c for c in db.execute(select(Card).where(Card.column_id == column_id)).scalars()}
        for idx, card_id in enumerate(order):
            if card_id in by_id:
                by_id[card_id].order = idx
        db.commit()
        return '', 204
