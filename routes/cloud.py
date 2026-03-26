from flask import Blueprint, render_template

cloud_bp = Blueprint('cloud', __name__)

@cloud_bp.route('/cloud')
def cloud():
    return render_template('cloud.html', active_page='cloud')