from flask import Blueprint, render_template, request, jsonify

from db.database import SessionLocal
from models.settings import Setting

settings_bp = Blueprint('settings', __name__)

# Defaults sempre replicam o comportamento atual do app — nada muda
# visualmente até o usuário mexer em Settings.
DEFAULT_SETTINGS = {
    'theme.mode':                 'dark',
    'theme.primary_color':        'primary',
    'notes.folders_open_default': 'false',
    'notes.preview_font_size':    '16',
    'notes.preview_font_family':  'default',
    'notes.default_open_mode':    'edit',
    'notes.default_sort':         'order-asc',
    'notes.render_accent':        'secondary',
    'notes.toolbar_position':     'auto',
}


def get_settings_dict():
    with SessionLocal() as db:
        rows = db.query(Setting).all()
        values = {row.key: row.value for row in rows}
    return {**DEFAULT_SETTINGS, **values}


@settings_bp.route('/settings')
def settings():
    return render_template('settings.html', active_page='settings')


@settings_bp.route('/api/settings', methods=['GET'])
def list_settings():
    return jsonify(get_settings_dict())


@settings_bp.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'no fields to update'}), 422
    with SessionLocal() as db:
        for key, value in data.items():
            row = db.query(Setting).filter(Setting.key == key).one_or_none()
            if row:
                row.value = None if value is None else str(value)
            else:
                db.add(Setting(key=key, value=None if value is None else str(value)))
        db.commit()
    return jsonify(get_settings_dict())


@settings_bp.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    with SessionLocal() as db:
        db.query(Setting).delete()
        db.commit()
    return jsonify(get_settings_dict())
