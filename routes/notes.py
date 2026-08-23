import os
import webview

from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, current_app
from sqlalchemy import select, func

from db.database import SessionLocal
from models.note import Note
from models.note_folder import NoteFolder
from models.settings import Setting
from models.event import Event
from models.task import Task
from models.task_list import TaskList
from routes.events import _expand_occurrences

notes_bp = Blueprint('notes', __name__)


def _serialize(note):
    return {
        'id':         note.id,
        'title':      note.title,
        'text':       note.text,
        'color':      note.color,
        'icon':       note.icon,
        'order':      note.order,
        'is_pinned':  note.is_pinned,
        'folder_id':  note.folder_id,
        'created_at': note.created_at.isoformat() if note.created_at else None,
        'updated_at': note.updated_at.isoformat() if note.updated_at else None,
        'deleted_at': note.deleted_at.isoformat() if note.deleted_at else None,
    }


def _serialize_folder(folder):
    return {
        'id':         folder.id,
        'name':       folder.name,
        'color':      folder.color,
        'icon':       folder.icon,
        'order':      folder.order,
        'is_pinned':  folder.is_pinned,
        'is_system':  bool(folder.is_system),
        'created_at': folder.created_at.isoformat() if folder.created_at else None,
    }


def _get_lixeira(db):
    return db.execute(select(NoteFolder).where(NoteFolder.is_system == True)).scalars().first()  # noqa: E712


def _trash_retention_days(db):
    # 'none' = sem retenção, exclusão é sempre permanente na hora.
    # Qualquer outro valor (ou ausência de setting) cai no default de 7 dias.
    row = db.query(Setting).filter(Setting.key == 'notes.trash_retention_days').one_or_none()
    value = row.value if row else None
    if value == 'none':
        return None
    try:
        return int(value) if value else 7
    except (TypeError, ValueError):
        return 7


def _purge_expired_trash(db):
    lixeira = _get_lixeira(db)
    if not lixeira:
        return
    retention = _trash_retention_days(db)
    if retention is None:
        # Retenção "nenhum": qualquer coisa que já esteja na Lixeira não
        # deveria ter sido deixada pra trás (delete_note já faz hard-delete
        # direto nesse modo) — mas cobre o caso de ter mudado o setting
        # depois de já existir lixo acumulado.
        db.execute(Note.__table__.delete().where(Note.folder_id == lixeira.id))
        db.commit()
        return
    cutoff = datetime.utcnow() - timedelta(days=retention)
    db.execute(
        Note.__table__.delete().where(
            Note.folder_id == lixeira.id,
            Note.deleted_at.isnot(None),
            Note.deleted_at < cutoff,
        )
    )
    db.commit()


@notes_bp.route('/notes')
def notes():
    return render_template('notes.html', active_page='notes')


@notes_bp.route('/api/notes', methods=['GET'])
def list_notes():
    with SessionLocal() as db:
        _purge_expired_trash(db)
        rows = db.execute(
            select(Note).order_by(Note.is_pinned.desc(), Note.order.asc())
        ).scalars().all()
        return jsonify([_serialize(n) for n in rows])


@notes_bp.route('/api/notes', methods=['POST'])
def create_note():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required'}), 422
    with SessionLocal() as db:
        now = datetime.utcnow()
        max_order = db.execute(select(func.max(Note.order))).scalar() or 0
        note = Note(
            title=title,
            text=data.get('text'),
            color=data.get('color') or None,
            icon=data.get('icon'),
            order=max_order + 1,
            is_pinned=bool(data.get('is_pinned', False)),
            folder_id=data.get('folder_id'),
            created_at=now,
            updated_at=now,
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return jsonify(_serialize(note)), 201


@notes_bp.route('/api/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    with SessionLocal() as db:
        note = db.get(Note, note_id)
        if not note:
            return jsonify({'error': 'not found'}), 404
        return jsonify(_serialize(note))


@notes_bp.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        note = db.get(Note, note_id)
        if not note:
            return jsonify({'error': 'not found'}), 404
        lixeira = _get_lixeira(db)
        content_changed = False
        if 'title' in data:
            title = (data['title'] or '').strip()
            if not title:
                return jsonify({'error': 'title is required'}), 422
            note.title = title
            content_changed = True
        if 'text' in data:
            note.text = data['text']
            content_changed = True
        if 'color' in data:
            note.color = data['color'] or None
        if 'icon' in data:
            note.icon = data['icon']
        if 'is_pinned' in data:
            note.is_pinned = bool(data['is_pinned'])
        if 'order' in data:
            note.order = int(data['order'])
        if 'folder_id' in data:
            new_folder_id = data['folder_id']
            # Ir pra Lixeira só acontece via DELETE (é o que carimba
            # deleted_at) — PUT genérico não pode simular isso.
            if lixeira and new_folder_id == lixeira.id:
                return jsonify({'error': 'cannot move to Lixeira directly, use delete'}), 422
            note.folder_id = new_folder_id
            # Mover pra qualquer outra pasta (inclusive "sem pasta") é a
            # forma de restaurar uma nota que estava na Lixeira.
            if note.deleted_at is not None:
                note.deleted_at = None
        if content_changed:
            note.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(note)
        return jsonify(_serialize(note))


@notes_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    with SessionLocal() as db:
        note = db.get(Note, note_id)
        if not note:
            return jsonify({'error': 'not found'}), 404
        lixeira = _get_lixeira(db)
        already_trashed = bool(lixeira and note.folder_id == lixeira.id)
        retention = _trash_retention_days(db)
        if already_trashed or retention is None or not lixeira:
            db.delete(note)
        else:
            note.folder_id = lixeira.id
            note.deleted_at = datetime.utcnow()
        db.commit()
        return '', 204


@notes_bp.route('/api/notes/reorder', methods=['POST'])
def reorder_notes():
    # Uma chamada só por container que mudou depois de um drag (drag entre
    # pastas só precisa reindexar o destino — a origem perder um item não
    # quebra a ordem relativa de quem ficou, os valores só não são mais
    # contíguos, e order nunca é comparado ENTRE containers diferentes).
    # folder_id/is_pinned são opcionais: só vêm quando o container de
    # destino representa essa mudança (pasta específica, ou a área de
    # soltas de Fixadas/Outras) — soltar DENTRO de uma pasta nunca mexe
    # em is_pinned da nota.
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    with SessionLocal() as db:
        lixeira = _get_lixeira(db)
        if 'folder_id' in data and lixeira and data['folder_id'] == lixeira.id:
            return jsonify({'error': 'cannot move to Lixeira directly, use delete'}), 422
        by_id = {n.id: n for n in db.execute(select(Note).where(Note.id.in_(order))).scalars()}
        for idx, note_id in enumerate(order):
            note = by_id.get(note_id)
            if not note:
                continue
            note.order = idx
            if 'folder_id' in data:
                note.folder_id = data['folder_id']
                if note.deleted_at is not None:
                    note.deleted_at = None
            if 'is_pinned' in data:
                note.is_pinned = bool(data['is_pinned'])
        db.commit()
        return '', 204


@notes_bp.route('/api/note-folders/reorder', methods=['POST'])
def reorder_note_folders():
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    with SessionLocal() as db:
        by_id = {f.id: f for f in db.execute(select(NoteFolder).where(NoteFolder.id.in_(order))).scalars()}
        for idx, folder_id in enumerate(order):
            folder = by_id.get(folder_id)
            if folder and not folder.is_system:
                folder.order = idx
        db.commit()
        return '', 204


@notes_bp.route('/api/note-folders', methods=['GET'])
def list_note_folders():
    with SessionLocal() as db:
        rows = db.execute(select(NoteFolder).order_by(NoteFolder.order.asc())).scalars().all()
        return jsonify([_serialize_folder(f) for f in rows])


@notes_bp.route('/api/note-folders', methods=['POST'])
def create_note_folder():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 422
    with SessionLocal() as db:
        max_order = db.execute(select(func.max(NoteFolder.order))).scalar() or 0
        folder = NoteFolder(
            name=name,
            color=data.get('color') or None,
            icon=data.get('icon'),
            order=max_order + 1,
            is_pinned=bool(data.get('is_pinned', False)),
        )
        db.add(folder)
        db.commit()
        db.refresh(folder)
        return jsonify(_serialize_folder(folder)), 201


@notes_bp.route('/api/note-folders/<int:folder_id>', methods=['PUT'])
def update_note_folder(folder_id):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        folder = db.get(NoteFolder, folder_id)
        if not folder:
            return jsonify({'error': 'not found'}), 404
        if folder.is_system:
            return jsonify({'error': 'Lixeira cannot be edited'}), 422
        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                return jsonify({'error': 'name is required'}), 422
            folder.name = name
        if 'color' in data:
            folder.color = data['color'] or None
        if 'icon' in data:
            folder.icon = data['icon']
        if 'order' in data:
            folder.order = int(data['order'])
        if 'is_pinned' in data:
            folder.is_pinned = bool(data['is_pinned'])
        db.commit()
        db.refresh(folder)
        return jsonify(_serialize_folder(folder))


@notes_bp.route('/api/note-folders/<int:folder_id>', methods=['DELETE'])
def delete_note_folder(folder_id):
    with SessionLocal() as db:
        folder = db.get(NoteFolder, folder_id)
        if not folder:
            return jsonify({'error': 'not found'}), 404
        if folder.is_system:
            return jsonify({'error': 'Lixeira cannot be deleted'}), 422
        # SQLite não aplica ON DELETE SET NULL sem PRAGMA foreign_keys=ON —
        # desvincula as notas explicitamente antes de apagar a pasta.
        db.execute(
            Note.__table__.update().where(Note.folder_id == folder_id).values(folder_id=None)
        )
        db.delete(folder)
        db.commit()
        return '', 204


@notes_bp.route('/api/notes/<int:note_id>/export', methods=['POST'])
def export_note(note_id):
    data   = request.get_json(silent=True) or {}
    fmt    = 'txt' if data.get('format') == 'txt' else 'md'

    with SessionLocal() as db:
        note = db.get(Note, note_id)
        if not note:
            return jsonify({'error': 'not found'}), 404
        filename = (note.title or 'nota') + '.' + fmt
        text     = note.text or ''

    file_types = ('Markdown Files (*.md)', 'Text Files (*.txt)')
    if fmt == 'txt':
        file_types = file_types[::-1]

    result = webview.windows[0].create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=filename,
        file_types=file_types,
    )
    if not result:
        return jsonify({'cancelled': True}), 200

    path = result[0] if isinstance(result, (list, tuple)) else result
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return jsonify({'path': str(path)}), 200


@notes_bp.route('/api/notes/bulk-update', methods=['POST'])
def bulk_update_notes():
    data = request.get_json(silent=True) or {}
    ids  = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'no ids'}), 422
    # folder_id aceita null de propósito (tirar da pasta) — não pode entrar
    # no mesmo filtro "and v is not None" usado pelos outros campos.
    allowed = ('color', 'icon', 'is_pinned', 'folder_id')
    if not any(k in data for k in allowed):
        return jsonify({'error': 'no fields to update'}), 422
    with SessionLocal() as db:
        lixeira = _get_lixeira(db)
        if 'folder_id' in data and lixeira and data['folder_id'] == lixeira.id:
            return jsonify({'error': 'cannot move to Lixeira directly, use delete'}), 422
        rows = db.execute(select(Note).where(Note.id.in_(ids))).scalars().all()
        for note in rows:
            if 'color' in data:
                note.color = data['color'] or None
            if 'icon' in data:
                note.icon = data['icon']
            if 'is_pinned' in data:
                note.is_pinned = bool(data['is_pinned'])
            if 'folder_id' in data:
                note.folder_id = data['folder_id']
                if note.deleted_at is not None:
                    note.deleted_at = None
        db.commit()
    return jsonify({'updated': len(rows)}), 200


@notes_bp.route('/api/notes/export-bulk', methods=['POST'])
def export_notes_bulk():
    data = request.get_json(silent=True) or {}
    ids  = data.get('ids', [])
    fmt  = 'txt' if data.get('format') == 'txt' else 'md'
    if not ids:
        return jsonify({'error': 'no ids'}), 422

    with SessionLocal() as db:
        rows = db.execute(
            select(Note).where(Note.id.in_(ids))
        ).scalars().all()
        notes_data = [(n.title or 'nota', n.text or '') for n in rows]

    result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
    if not result:
        return jsonify({'cancelled': True}), 200

    folder = result[0] if isinstance(result, (list, tuple)) else result
    for title, text in notes_data:
        safe = ''.join(c for c in title if c.isalnum() or c in ' _-').strip() or 'nota'
        with open(os.path.join(folder, safe + '.' + fmt), 'w', encoding='utf-8') as f:
            f.write(text)

    return jsonify({'count': len(notes_data)}), 200


@notes_bp.route('/api/icons')
def list_icons():
    icons_dir = os.path.join(current_app.static_folder, 'bootstrap-icons-1.13.1')
    names = sorted(
        'bi-' + f[:-4]
        for f in os.listdir(icons_dir)
        if f.endswith('.svg')
    )
    return jsonify(names)


def _snippet(text, q, radius=40):
    idx = text.lower().find(q.lower())
    if idx == -1:
        return text[:radius * 2]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(q) + radius)
    snippet = text[start:end]
    return ('…' if start > 0 else '') + snippet + ('…' if end < len(text) else '')


_MONTH_NAMES = [
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]


@notes_bp.route('/api/search')
def search():
    # Escopo: Notes (título/pasta/trecho) + Events (nome/mês/dia) + Tasks
    # (nome de task/nome de tasklist). Formato pensado pra crescer — cada
    # módulo futuro (Projects...) entra como uma chave nova.
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({
            'notes':  {'title': [], 'folder': [], 'content': []},
            'events': {'name': [], 'month': [], 'day': []},
            'tasks':  {'task': [], 'tasklist': []},
        })

    with SessionLocal() as db:
        lixeira = _get_lixeira(db)
        rows = db.execute(select(Note)).scalars().all()
        folders_by_id = {f.id: f for f in db.execute(select(NoteFolder)).scalars().all()}

        ql = q.lower()
        title_hits, folder_hits, content_hits = [], [], []
        for n in rows:
            # folder_id é NULL pras notas soltas — "!= lixeira.id" no SQL
            # descartaria elas também (NULL != x é NULL, não TRUE). Filtra
            # aqui em Python, onde a comparação direta funciona como esperado.
            if lixeira and n.folder_id == lixeira.id:
                continue
            folder = folders_by_id.get(n.folder_id)
            base = {
                'id':          n.id,
                'title':       n.title,
                'icon':        n.icon,
                'color':       n.color,
                'folder_id':   n.folder_id,
                'folder_name': folder.name if folder else None,
            }
            if n.title and ql in n.title.lower():
                title_hits.append(base)
            if folder and ql in folder.name.lower():
                folder_hits.append(base)
            if n.text and ql in n.text.lower():
                content_hits.append({**base, 'snippet': _snippet(n.text, q)})

        # Mês/dia: "agosto" tem que achar um evento recorrente que começou em
        # abril mas continua até agosto — mas só ESSE ano (usuário foi
        # explícito: "agosto" nunca deveria trazer um evento de 2032).
        # Reaproveita o mesmo motor de recorrência do calendário
        # (_expand_occurrences), só que limitado ao ano corrente em vez de
        # rodar pra sempre — evento não-recorrente cai no caso simples
        # (só a própria date_start dentro da janela).
        today = date.today()
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)
        month_idx = next((i for i, name in enumerate(_MONTH_NAMES, start=1) if name.startswith(ql)), None)
        target_day = int(q) if q.isdigit() and 1 <= int(q) <= 31 else None

        events = db.execute(select(Event)).scalars().all()
        name_hits, month_hits, day_hits = [], [], []
        for e in events:
            base = {
                'id':         e.id,
                'name':       e.name,
                'icon':       e.icon,
                'color':      e.color,
                'date_start': e.date_start.isoformat(),
            }
            if e.name and ql in e.name.lower():
                name_hits.append(base)
            if month_idx or target_day:
                occurrences = _expand_occurrences(e, year_start, year_end)
                if month_idx and any(o.month == month_idx for o in occurrences):
                    month_hits.append(base)
                if target_day and any(o.day == target_day for o in occurrences):
                    day_hits.append(base)

        tasklists = db.execute(select(TaskList)).scalars().all()
        tasklists_by_id = {tl.id: tl for tl in tasklists}
        tasklist_hits = [
            {'id': tl.id, 'name': tl.name, 'icon': tl.icon, 'color': tl.color}
            for tl in tasklists if ql in tl.name.lower()
        ]
        task_hits = []
        for t in db.execute(select(Task)).scalars().all():
            if not (t.name and ql in t.name.lower()):
                continue
            tl = tasklists_by_id.get(t.task_list_id)
            task_hits.append({
                'id': t.id, 'name': t.name,
                'task_list_id': t.task_list_id,
                'task_list_name': tl.name if tl else None,
            })

        return jsonify({
            'notes': {
                'title':   title_hits,
                'folder':  folder_hits,
                'content': content_hits,
            },
            'events': {
                'name':  name_hits,
                'month': month_hits,
                'day':   day_hits,
            },
            'tasks': {
                'task':     task_hits,
                'tasklist': tasklist_hits,
            },
        })
