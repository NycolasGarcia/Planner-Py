import webbrowser

import webview

from flask import Flask, render_template, redirect, url_for
from routes import events_bp, tasks_bp, projects_bp, notes_bp, focus_bp, ranks_bp, cloud_bp, settings_bp, profile_bp
from routes.settings import get_settings_dict
from db.init_db import init_db

app = Flask(__name__, static_folder='./static', template_folder='./templates')

# pywebview serve a app inteira (não uma URL) — não dá pra escolher um
# sub-path inicial nesse modo, ele sempre abre em "/" (visto no código do
# pywebview: _resolve_url devolve a raiz do server pra qualquer app WSGI).
# "Tela inicial ao abrir" só é possível fazendo o próprio "/" redirecionar.
_START_PAGE_ENDPOINTS = {
    'events':   'events.events',
    'tasks':    'tasks.tasks',
    'projects': 'projects.projects',
    'notes':    'notes.notes',
    'focus':    'focus.focus',
    'ranks':    'ranks.ranks',
}

_RESOLUTION_PRESETS = {
    '1280x720':  (1280, 720),
    '1600x900':  (1600, 900),
    '1920x1080': (1920, 1080),
    '2560x1440': (2560, 1440),
}


@app.context_processor
def inject_settings():
    # Disponibiliza os settings pra qualquer template (não só settings.html) —
    # base.html injeta isso como window.__settings pro JS de cada página ler.
    return {'settings_dict': get_settings_dict()}


class Api:
    # Pywebview é um mini-browser embutido: um <a href> normal navegaria a
    # própria janela do app pra fora dele. Links (ex: dentro do preview de
    # notas) abrem no navegador padrão do sistema em vez disso.
    def open_external(self, url):
        if isinstance(url, str) and url.startswith(('http://', 'https://')):
            webbrowser.open(url)
        return True

app.register_blueprint(events_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(notes_bp)
app.register_blueprint(focus_bp)
app.register_blueprint(ranks_bp)
app.register_blueprint(cloud_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(profile_bp)


_app_booted = {'done': False}


@app.route("/")
def index():
    # "Tela inicial" é sobre o que aparece no boot da janela, não sobre pra
    # onde "/" deveria levar dali em diante — sem esse flag, o ícone
    # "Início" da sidebar nunca mais abriria o dashboard de verdade, só
    # devolveria pra mesma tela configurada em loop.
    if not _app_booted['done']:
        _app_booted['done'] = True
        endpoint = _START_PAGE_ENDPOINTS.get(get_settings_dict().get('customizacao.tela_inicial'))
        if endpoint:
            return redirect(url_for(endpoint))
    return render_template('index.html', active_page='index')


if __name__ == '__main__':
    init_db()
    settings = get_settings_dict()

    width, height = _RESOLUTION_PRESETS.get(settings.get('customizacao.resolucao'), (1280, 720))
    if settings.get('customizacao.orientacao') == 'vertical':
        width, height = height, width

    window = webview.create_window(
        'Planner App',
        app,
        height=height,
        width=width,
        resizable=settings.get('customizacao.redimensionavel', 'true') != 'false',
        js_api=Api(),
    )

    try:
        webview.start()
    except KeyboardInterrupt:
        pass
