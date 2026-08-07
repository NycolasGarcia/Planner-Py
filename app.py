import webbrowser

import webview

from flask import Flask, render_template
from routes import events_bp, tasks_bp, projects_bp, notes_bp, focus_bp, ranks_bp, cloud_bp, settings_bp, profile_bp
from routes.settings import get_settings_dict
from db.init_db import init_db

app = Flask(__name__, static_folder='./static', template_folder='./templates')


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


@app.route("/")
def index():
    return render_template('index.html', active_page='index')


if __name__ == '__main__':
    init_db()

    window = webview.create_window(
        'Planner App',
        app,
        height=720,
        width=1280,
        resizable=True,
        js_api=Api(),
    )

    try:
        webview.start()
    except KeyboardInterrupt:
        pass
