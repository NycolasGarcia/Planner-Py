from flask import Blueprint, render_template, request, jsonify

from db.database import SessionLocal
from models.settings import Setting

settings_bp = Blueprint('settings', __name__)

# Defaults sempre replicam o comportamento atual do app — nada muda
# visualmente até o usuário mexer em Settings.
DEFAULT_SETTINGS = {
    'theme.mode':                 'dark',
    'theme.primary_color':        'primary',
    'customizacao.tela_inicial':    'index',
    'customizacao.resolucao':       '1280x720',
    'customizacao.orientacao':      'horizontal',
    'customizacao.redimensionavel': 'true',
    'customizacao.fonte':           'default',
    'notes.folders_open_default': 'false',
    'notes.preview_font_size':    '16',
    'notes.preview_font_family':  'default',
    'notes.default_open_mode':    'edit',
    'notes.default_sort':         'order-asc',
    'notes.render_accent':        'secondary',
    'notes.toolbar_position':     'auto',
    'notes.trash_visibility':     'if-has-items',
    'notes.trash_retention_days': '7',
    'eventos.formato_data':          'dmy',
    'eventos.formato_hora':          '24h',  # '24h' | 'ampm'
    'eventos.ano_completo':          'true',
    'eventos.primeiro_dia_semana':   'sun',  # default real do FullCalendar sem override (locale pt-br não seta week.dow)
    'eventos.nav_position':       'auto',
    'eventos.painel_inicial':     'calendar',
    'eventos.ressaltar_seg':      'false',
    'eventos.ressaltar_ter':      'false',
    'eventos.ressaltar_qua':      'false',
    'eventos.ressaltar_qui':      'false',
    'eventos.ressaltar_sex':      'false',
    'eventos.ressaltar_sab':      'false',
    'eventos.ressaltar_dom':      'false',
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
