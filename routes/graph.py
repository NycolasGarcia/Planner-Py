from flask import Blueprint, render_template

graph_bp = Blueprint('graph', __name__)

@graph_bp.route('/graph')
def graph():
    return render_template('graph.html', active_page='graph')
