import base64
import os

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask.ext.login import LoginManager
from flask.ext.login import current_user
from flask.ext.login import login_required
from flask.ext.login import login_user
from flask.ext.login import logout_user
import flask
import jwt
import requests


app = Flask(__name__)

# NOTE: Change this to something else!
# FIXME: Change this to use os.environ.get
app.secret_key = 'BF7E16AC-8128-11E5-AD07-B098F0F8B08E'

required = {
    'base_url': {
        'description': 'the base URL for your Okta org',
        'example': 'https://example.okta.com'
    },
    'api_token': {
        'description': 'the API token for your Okta org',
        'example': '01A2bCd3efGh-ij-4K-Lmn5OPqrSTuvwXYZaBCD6EF'
    },
    'client_id': {
        'description': 'an OAuth Client ID for your Okta org',
        'example': 'a0bcdEfGhIJkLmNOPQr1'
    }
}

okta = {}
for key in required.keys():
    env_key = "OKTA_" + key.upper()
    okta[key] = os.environ.get(env_key)
    if okta[key]:
        del(required[key])


# Note: This will only work for one org
# doing a "SAML-esq" login will require a change to how id_tokens are processed
# change this to a dictionary, where the key is the domain name
public_key = None

# This is only used for social transaction calls
headers = {
    'Authorization': 'SSWS {}'.format(okta['api_token']),
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


login_manager = LoginManager()
login_manager.setup_app(app)


class UserSession:
    def __init__(self, user_id):
        self.authenticated = True
        self.user_id = user_id

    def is_active(self):
        # In this example, "active" and "authenticated" are the same thing
        return self.authenticated

    def is_authenticated(self):
        # "Has the user authenticated?"
        # See also: http://stackoverflow.com/a/19533025
        return self.authenticated

    def is_anonymous(self):
        return not self.authenticated

    def get_id(self):
        return self.user_id


# Note that this loads users based on user_id
# which is stored in the browser cookie, I think
@login_manager.user_loader
def load_user(user_id):
    # print "Loading user: " + user_id
    return UserSession(user_id)


def fetch_jwt_public_key(base_url=None):
    if base_url is None:
        raise Exception('base_url required')
    jwks_url = "{}/oauth2/v1/keys".format(base_url)
    r = requests.get(jwks_url)
    jwks = r.json()
    x5c = jwks['keys'][0]['x5c'][0]
    pem_data = base64.b64decode(str(x5c))
    cert = x509.load_der_x509_certificate(pem_data, default_backend())
    return cert.public_key()


@app.route("/spa")
def spa():
    return render_template(
        'spa.html',
        okta=okta)


@app.route("/secret")
@login_required
def logged_in():
    opts = {'user': current_user}
    return render_template(
        'secret.html',
        opts=opts,
        okta=okta)


def parse_jwt(token):
    rv = jwt.decode(
        token,
        public_key,
        algorithms='RS256',
        audience=okta['client_id'])
    return rv


@app.route("/login", methods=['POST'])
def login_via_jwt():
    token = request.form['id_token']
    decoded = parse_jwt(token)
    user_id = decoded['sub']
    user = UserSession(user_id)
    login_user(user)
    return(str(decoded))


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main_page', _external=True, _scheme='https'))


# FIXME: Use decoded['sub'] to fetch the user profile from Okta,
# returning that in the result
@app.route("/users/me")
def users_me():
    authorization = request.headers.get('Authorization')
    token = authorization.replace('Bearer ', '')
    decoded = parse_jwt(token)
    rv = {'user_id': decoded['sub']}
    return flask.jsonify(**rv)


@app.route("/")
def main_page():
    if len(required.keys()) > 0:
        return render_template(
            'error.html',
            required=required,
            okta=okta)

    target_origin = url_for('main_page', _external=True, _scheme='https')
    return render_template(
        'main_page.html',
        target_origin=target_origin,
        okta=okta)


if __name__ == "__main__":
    try:
        public_key = fetch_jwt_public_key(okta['base_url'])
    except:
        pass

    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    if port == 5000:
        app.debug = True
    app.run(port=port)