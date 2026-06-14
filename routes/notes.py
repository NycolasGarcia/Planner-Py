import os
import webview

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import select, func

from db.database import SessionLocal
from models.note import Note

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
        'created_at': note.created_at.isoformat() if note.created_at else None,
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


@notes_bp.route('/api/notes/<int:note_id>/export', methods=['POST'])
def export_note(note_id):
    with SessionLocal() as db:
        note = db.get(Note, note_id)
        if not note:
            return jsonify({'error': 'not found'}), 404
        filename = (note.title or 'nota') + '.txt'
        text     = note.text or ''

    result = webview.windows[0].create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=filename,
        file_types=('Text Files (*.txt)',)
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
    fields = {k: v for k, v in data.items() if k in ('color', 'icon', 'is_pinned') and v is not None}
    if not fields:
        return jsonify({'error': 'no fields to update'}), 422
    with SessionLocal() as db:
        rows = db.execute(select(Note).where(Note.id.in_(ids))).scalars().all()
        for note in rows:
            for k, v in fields.items():
                setattr(note, k, v)
        db.commit()
    return jsonify({'updated': len(rows)}), 200


@notes_bp.route('/api/notes/export-bulk', methods=['POST'])
def export_notes_bulk():
    data = request.get_json(silent=True) or {}
    ids  = data.get('ids', [])
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
        with open(os.path.join(folder, safe + '.txt'), 'w', encoding='utf-8') as f:
            f.write(text)

    return jsonify({'count': len(notes_data)}), 200
