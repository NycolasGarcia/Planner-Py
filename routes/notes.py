import os
import webview

from flask import Blueprint, render_template, request, jsonify, current_app
from sqlalchemy import select, func

from db.database import SessionLocal
from models.note import Note
from models.note_folder import NoteFolder

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
    }


def _serialize_folder(folder):
    return {
        'id':         folder.id,
        'name':       folder.name,
        'color':      folder.color,
        'icon':       folder.icon,
        'order':      folder.order,
        'is_pinned':  folder.is_pinned,
        'created_at': folder.created_at.isoformat() if folder.created_at else None,
    }


@notes_bp.route('/notes')
def notes():
    return render_template('notes.html', active_page='notes')


@notes_bp.route('/api/notes', methods=['GET'])
def list_notes():
    with SessionLocal() as db:
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
        max_order = db.execute(select(func.max(Note.order))).scalar() or 0
        note = Note(
            title=title,
            text=data.get('text'),
            color=data.get('color'),
            icon=data.get('icon'),
            order=max_order + 1,
            is_pinned=bool(data.get('is_pinned', False)),
            folder_id=data.get('folder_id'),
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
        if 'title' in data:
            title = (data['title'] or '').strip()
            if not title:
                return jsonify({'error': 'title is required'}), 422
            note.title = title
        if 'text' in data:
            note.text = data['text']
        if 'color' in data:
            note.color = data['color']
        if 'icon' in data:
            note.icon = data['icon']
        if 'is_pinned' in data:
            note.is_pinned = bool(data['is_pinned'])
        if 'order' in data:
            note.order = int(data['order'])
        if 'folder_id' in data:
            note.folder_id = data['folder_id']
        db.commit()
        db.refresh(note)
        return jsonify(_serialize(note))


@notes_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    with SessionLocal() as db:
        note = db.get(Note, note_id)
        if not note:
            return jsonify({'error': 'not found'}), 404
        db.delete(note)
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
            color=data.get('color'),
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
        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                return jsonify({'error': 'name is required'}), 422
            folder.name = name
        if 'color' in data:
            folder.color = data['color']
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
        rows = db.execute(select(Note).where(Note.id.in_(ids))).scalars().all()
        for note in rows:
            if 'color' in data:
                note.color = data['color']
            if 'icon' in data:
                note.icon = data['icon']
            if 'is_pinned' in data:
                note.is_pinned = bool(data['is_pinned'])
            if 'folder_id' in data:
                note.folder_id = data['folder_id']
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
