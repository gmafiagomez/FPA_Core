from flask import current_app, request, session, abort
from flask.ext.login import current_user
import uuid


from openspending import auth, _version
from openspending.views.home import blueprint as home
from openspending.lib.helpers import static_path
from openspending.lib.helpers import url_for



@home.after_app_request
def after_request(resp):
    resp.headers['Server'] = 'FIND/Beta'
    
    if resp.is_streamed:
        # http://wiki.nginx.org/X-accel#X-Accel-Buffering
        resp.headers['X-Accel-Buffering'] = 'no'
    
    return resp



def get_active_section():
    # TODO: use request.endpoint
    # ["blog", "dataset", "search", "resources", "help", "about"]
    return {'dataset': True}



def make_uuid():
    return unicode(uuid.uuid4())


def generate_csrf_token():
    if request.method == 'POST':
        return
    if 'csrf_token' not in session:
        session['csrf_token'] = make_uuid()
    return session['csrf_token']


@home.app_context_processor
def template_context_processor():
    data = {
        'DEBUG': current_app.config.get('DEBUG'),
        'static_path': static_path,
        'url_for': url_for,
        'section_active': get_active_section(),
        'logged_in': auth.account.logged_in(),
        'current_user': current_user,
        'csrf_token': generate_csrf_token
        }
    return data



def api_form_data():
    data = request.get_json(silent=True)
    if data is None:
        data = dict(request.form.items())
    return data
