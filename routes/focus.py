from flask import Blueprint, render_template

focus_bp = Blueprint('focus', __name__)

@focus_bp.route('/focus')
def focus():
    return render_template('focus.html', active_page='focus')