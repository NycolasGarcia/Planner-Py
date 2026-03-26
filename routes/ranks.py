from flask import Blueprint, render_template

ranks_bp = Blueprint('ranks', __name__)

@ranks_bp.route('/ranks')
def ranks():
    return render_template('ranks.html', active_page='ranks')