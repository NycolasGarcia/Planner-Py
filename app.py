from flask import Flask, render_template
from routes import events_bp, tasks_bp, projects_bp, notes_bp, focus_bp, ranks_bp, cloud_bp, settings_bp, profile_bp
from db.init_db import init_db

import webview
from threading import Thread

app = Flask(__name__, static_folder='./static', template_folder='./templates')

# Register the blueprints
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

# Variável global para controlar a janela
window = None

def reload_window():
    """Recarrega a janela atual"""
    global window
    if window:
        window.load_url('http://localhost:5000/')  # Recarrega a URL atual
        # Ou use evaluate_js para executar um reload do JavaScript
        window.evaluate_js('window.location.reload();')

if __name__ == '__main__':
    # Inicializa o banco de dados
    init_db()
    
    # Cria a janela
    window = webview.create_window('Planner App', app, frameless=True, height=720, width=1280, resizable=True)
    
    # Adiciona o atalho de teclado F8 para recarregar
    # Nota: Isso só funciona no pywebview 3.0 ou superior
    if hasattr(window, 'events') and hasattr(window.events, 'key_down'):
        def on_key_down(key, **kwargs):
            if key == 'F8':  # Tecla F8
                reload_window()
        window.events.key_down += on_key_down
    
    # Inicia a aplicação
    webview.start()