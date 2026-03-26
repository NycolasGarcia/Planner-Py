from flask import Blueprint, render_template

notes_bp = Blueprint('notes', __name__)

@notes_bp.route('/notes')
def notes():
    return render_template('notes.html', active_page='notes')