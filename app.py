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

if __name__ == '__main__':
    init_db()

    window = webview.create_window(
        'Planner App',
        app,
        frameless=True,
        height=720,
        width=1280,
        resizable=True
    )

    webview.start()