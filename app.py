import sqlite3
import os
import secrets
from abc import ABC, abstractmethod
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, make_response, flash

app = Flask(__name__)
app.secret_key = 'bbs-net-1987'

DB_PATH = 'data.db'

# Simple in-memory session store.
# Each entry: token -> {user_id, username, role}
sessions = {}
_token_counter = 1000


def create_session(user_id, username, role):
    """
    Create a new session for a user and store it in the session dictionary.

    Generates a token, stores the user's ID, username, and role against it,
    and returns the token. The token is set as a cookie by the calling route.

    Parameters:
        user_id  -- the integer primary key of the user
        username -- the user's username string
        role     -- the user's role string, either 'user' or 'sysop'
    """

    token = str(secrets.token_hex(32))
    sessions[token] = {'user_id': user_id, 'username': username, 'role': role}
    return token


def get_current_user(req):
    """
    Look up the logged-in user from the request cookie.

    Reads the bbs_token cookie and looks it up in the session store.
    Returns the session dict containing user_id, username, and role if found,
    or None if the cookie is missing or the token is not in the store.

    Parameters:
        req -- the Flask request object
    """
    token = req.cookies.get('bbs_token')
    if not token:
        return None
    
    return sessions.get(token)


# -- Database initialisation -------------------------------------------------

def initialise_database():
    """
    Create the database tables and seed data if they do not already exist.

    Connects to the SQLite database file, checks whether the users table
    exists, and returns immediately if it does. Otherwise creates the users
    and nodes tables and inserts the default seed records.

    This function is called once at startup when running the app directly.
    Students receive a pre-built data.db file and this function will return
    early without making any changes.
    """
    conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
        conn.close()
        return
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            region TEXT,
            joined INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            region TEXT,
            description TEXT,
            owner_id INTEGER NOT NULL
        )
    """)
    seed_users = [
        ('sysop',       generate_password_hash('sysop123'), 'sysop', 'Zone 1 North America', 1985),
        ('daemon9',     generate_password_hash('wire99'),   'user',  'Zone 1 North America', 1986),
        ('apostrophe',  generate_password_hash('modem44'),  'user',  'Zone 2 Europe',        1988),
        ('route66',     generate_password_hash('caller1'),  'user',  'Zone 1 North America', 1987),
        ('vaxcat',      generate_password_hash('vt100x'),   'user',  'Zone 3 Pacific',       1989),
    ]
    cursor.executemany(
        "INSERT INTO users (username, password_hash, role, region, joined) VALUES (?,?,?,?,?)",
        seed_users
    )
    seed_nodes = [
        ('The Rusty Nail',        '614-555-0142',    'Zone 1 North America', 'General discussion. Active since 1985. 24hr access.',   1),
        ('Digital Underground',   '212-555-0167',    'Zone 1 North America', 'Tech and phreaking discussion. Files section active.',  2),
        ('EuroLink Node 7',       '+44-71-555-0182', 'Zone 2 Europe',        'European nexus for Zone 2 traffic. Multilingual.',      3),
        ('Route 66 BBS',          '312-555-0199',    'Zone 1 North America', 'Midwest hub. Open to all Zone 1 members.',              4),
        ('Pacific Rim Exchange',  '415-555-0134',    'Zone 3 Pacific',       'West Coast gateway. Echomail and file distribution.',   5),
    ]
    cursor.executemany(
        "INSERT INTO nodes (name, phone, region, description, owner_id) VALUES (?,?,?,?,?)",
        seed_nodes
    )
    conn.commit()
    conn.close()


# -- Singleton DB connection -------------------------------------------------

class DatabaseConnection:
    """
    Manages a single shared connection to the SQLite database.

    Uses the Singleton pattern so only one connection is created for the
    lifetime of the application.
    """
    _instance = None

    def __new__(cls):
        """
        Return the existing instance if one exists, otherwise create a new one
        and open the database connection.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cls._instance._conn.row_factory = sqlite3.Row
        return cls._instance

    def fetchall(self, query, params=()):
        """
        Run a SELECT query and return all matching rows.

        Returns a list of Row objects that can be accessed like dicts.

        Parameters:
            query  -- the SQL query string, using ? placeholders for values
            params -- a tuple of values to substitute into the query
        """
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query, params=()):
        """
        Run a SELECT query and return the first matching row.

        Returns a Row object, or None if no rows match.

        Parameters:
            query  -- the SQL query string, using ? placeholders for values
            params -- a tuple of values to substitute into the query
        """
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()

    def execute(self, query, params=()):
        """
        Run an INSERT, UPDATE, or DELETE query and commit the change.

        Parameters:
            query  -- the SQL query string, using ? placeholders for values
            params -- a tuple of values to substitute into the query
        """
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        self._conn.commit()


# -- Abstract repository -----------------------------------------------------

class Repository(ABC):
    """
    Base class for all repository classes.

    Provides a shared database connection and defines the interface that all
    repositories must implement.
    """
    def __init__(self, db):
        """
        Store the database connection for use by subclass methods.

        Parameters:
            db -- a DatabaseConnection instance
        """
        self._db = db

    @abstractmethod
    def find_by_id(self, record_id):
        """Look up and return a single record by its primary key."""
        pass


# -- UserRepository ----------------------------------------------------------

class UserRepository(Repository):
    """Handles all database operations for the users table."""

    def find_by_id(self, record_id):
        """
        Return the user with the given ID, or None if not found.

        Parameters:
            record_id -- the integer primary key of the user
        """
        return self._db.fetchone("SELECT * FROM users WHERE id = ?", (record_id,))

    def find_by_username(self, username):
        """
        Return the user with the given username, or None if not found.

        Parameters:
            username -- the username string to look up
        """
        return self._db.fetchone("SELECT * FROM users WHERE username = ?", (username,))

    def get_all(self):
        """Return all users ordered alphabetically by username."""
        return self._db.fetchall("SELECT * FROM users ORDER BY username")

    def create(self, username, password_hash, region):
        """
        Insert a new user record and return the created user row.

        New users are always assigned the role 'user' and a joined year of 2025.

        Parameters:
            username      -- the new user's username string
            password_hash -- the hashed password string
            region        -- the user's region string
        """
        self._db.execute(
            "INSERT INTO users (username, password_hash, role, region, joined) VALUES (?,?,'user',?,2025)",
            (username, password_hash, region)
        )
        return self._db.fetchone("SELECT * FROM users WHERE username = ?", (username,))

    def update_region(self, user_id, region):
        """
        Update the region field for the user with the given ID.

        Parameters:
            user_id -- the integer primary key of the user to update
            region  -- the new region string
        """
        self._db.execute("UPDATE users SET region = ? WHERE id = ?", (region, user_id))


# -- NodeRepository ----------------------------------------------------------

class NodeRepository(Repository):
    """Handles all database operations for the nodes table."""

    def find_by_id(self, record_id):
        """
        Return the node with the given ID, joined with the owner's username.

        Returns None if no node with that ID exists.

        Parameters:
            record_id -- the integer primary key of the node
        """
        return self._db.fetchone("""
            SELECT n.*, u.username AS owner_username
            FROM nodes n JOIN users u ON n.owner_id = u.id
            WHERE n.id = ?
        """, (record_id,))

    def find_by_owner(self, owner_id):
        """
        Return the node owned by the user with the given ID, or None if not found.

        Parameters:
            owner_id -- the integer primary key of the owning user
        """
        return self._db.fetchone("""
            SELECT n.*, u.username AS owner_username
            FROM nodes n JOIN users u ON n.owner_id = u.id
            WHERE n.owner_id = ?
        """, (owner_id,))

    def get_all(self):
        """Return all nodes ordered by ID, each joined with the owner's username."""
        return self._db.fetchall("""
            SELECT n.*, u.username AS owner_username
            FROM nodes n JOIN users u ON n.owner_id = u.id
            ORDER BY n.id
        """)

    def update(self, node_id, name, phone, region, description):
        """
        Update the editable fields of the node with the given ID.

        Parameters:
            node_id     -- the integer primary key of the node to update
            name        -- the new node name string
            phone       -- the new phone number string
            region      -- the new region string
            description -- the new description string
        """
        self._db.execute(
            "UPDATE nodes SET name=?, phone=?, region=?, description=? WHERE id=?",
            (name, phone, region, description, node_id)
        )

    def rename(self, node_id, name):
        """
        Update only the name field of the node with the given ID.

        Parameters:
            node_id -- the integer primary key of the node to rename
            name    -- the new name string
        """
        self._db.execute("UPDATE nodes SET name=? WHERE id=?", (name, node_id))

    def delete(self, node_id):
        """
        Delete the node with the given ID.

        Parameters:
            node_id -- the integer primary key of the node to delete
        """
        self._db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))


# -- App setup ---------------------------------------------------------------

database  = DatabaseConnection()
user_repo = UserRepository(database)
node_repo = NodeRepository(database)


# -- Routes ------------------------------------------------------------------

@app.route('/')
def index():
    """
    Render the home page.

    Passes all nodes and the current user to the template.
    Works for both logged-in and anonymous visitors.
    """
    current = get_current_user(request)
    recent = node_repo.get_all()
    return render_template('index.html', recent_nodes=recent, current_user=current)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handle the registration page.

    GET  -- render the registration form.
    POST -- validate the submitted username and password. If the username is
            already taken or either field is empty, flash an error and
            re-render the form. On success, create the user, open a session,
            set the cookie, and redirect to the home page.
    """
    current = get_current_user(request)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        region   = request.form.get('region', '').strip()
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('register.html', current_user=current)
        if user_repo.find_by_username(username):
            flash('Username already taken.', 'error')
            return render_template('register.html', current_user=current)
        user = user_repo.create(username, generate_password_hash(password), region)
        token = create_session(user['id'], user['username'], user['role'])
        resp = make_response(redirect(url_for('index')))
        resp.set_cookie('bbs_token', token)
        return resp
    return render_template('register.html', current_user=current)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle the login page.

    GET  -- render the login form.
    POST -- look up the username and verify the password. On success, create
            a session, set the cookie, and redirect to the home page. On
            failure, flash an error and re-render the form.
    """
    current = get_current_user(request)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = user_repo.find_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            token = create_session(user['id'], user['username'], user['role'])
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('bbs_token', token)
            return resp
        flash('Invalid credentials.', 'error')
    return render_template('login.html', current_user=current)


@app.route('/logout')
def logout():
    """
    Log out the current user.

    Removes the session from the in-memory store and deletes the cookie,
    then redirects to the home page.
    """
    token = request.cookies.get('bbs_token')
    if token and token in sessions:
        del sessions[token]
    resp = make_response(redirect(url_for('index')))
    resp.delete_cookie('bbs_token')
    return resp


@app.route('/directory')
def directory():
    """
    Render the full node directory.

    Passes all nodes and the current user to the template.
    Does not redirect anonymous visitors.
    """
    current = get_current_user(request)
    all_nodes = node_repo.get_all()
    return render_template('directory.html', nodes=all_nodes, current_user=current)


@app.route('/node/<int:node_id>')
def node_view(node_id):
    """
    Render the detail page for a single node.

    Redirects to login if the user is not logged in.
    Redirects to the directory with an error if the node does not exist.

    Parameters:
        node_id -- the integer primary key of the node from the URL
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    node = node_repo.find_by_id(node_id)
    if not node:
        flash('Node not found.', 'error')
        return redirect(url_for('directory'))
    return render_template('node_view.html', node=node, current_user=current)


@app.route('/node/<int:node_id>/edit', methods=['GET', 'POST'])
def node_edit(node_id):
    """
    Handle the node edit form.

    Redirects to login if the user is not logged in.
    Redirects to the directory with an error if the node does not exist.

    GET  -- render the edit form pre-filled with the node's current values.
    POST -- read the owner_id from the submitted form and use it to check
            ownership before saving.

    Parameters:
        node_id -- the integer primary key of the node from the URL
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    
    node = node_repo.find_by_id(node_id)
    if not node:
        flash('Node not found.', 'error')
        return redirect(url_for('directory'))
    
    if request.method == 'POST':
        submitted_owner_id = int(request.form.get('owner_id', 0))
        if submitted_owner_id != current['user_id']:
            flash('Access denied.', 'error')
            return redirect(url_for('directory'))
        node_repo.update(
            node_id,
            request.form.get('name', ''),
            request.form.get('phone', ''),
            request.form.get('region', ''),
            request.form.get('description', '')
        )
        flash('Node updated.')
        return redirect(url_for('node_view', node_id=node_id))

    # Changed this because no accounts were able to edit since it referenced an html file that 
    # wasn't in the template
    return render_template('node_edit.html', node=node, current_user=current)


@app.route('/node/<int:node_id>/rename', methods=['GET', 'POST'])
def node_rename(node_id):
    """
    Handle the node rename form.

    Redirects to login if the user is not logged in.
    Redirects to the directory with an error if the node does not exist.

    GET  -- checks ownership and renders the rename form if the check passes.
    POST -- saves the new name and redirects to the node detail page.

    Parameters:
        node_id -- the integer primary key of the node from the URL
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    node = node_repo.find_by_id(node_id)

    if not node:
        flash('Node not found.', 'error')
        return redirect(url_for('directory'))
    
    if request.method == 'GET':
        if node['owner_id'] != current['user_id'] and current['role'] != 'sysop':
            flash('Access denied.', 'error')
            return redirect(url_for('directory'))
        return render_template('node_rename.html', node=node, current_user=current)
    node_repo.rename(node_id, request.form.get('name', node['name']))
    flash('Node renamed.')
    return redirect(url_for('node_view', node_id=node_id))


@app.route('/node/<int:node_id>/delete', methods=['GET', 'POST'])
def node_delete(node_id):
    """
    Handle node deletion.

    Redirects to login if the user is not logged in.
    Redirects to the directory with an error if the node does not exist.

    GET  -- renders a confirmation page.
    POST -- deletes the node and redirects to the directory.

    Parameters:
        node_id -- the integer primary key of the node from the URL
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    node = node_repo.find_by_id(node_id)
    if not node:
        flash('Node not found.', 'error')
        return redirect(url_for('directory'))
    if request.method == 'POST':
        node_repo.delete(node_id)
        flash('Node removed from registry.')
        return redirect(url_for('directory'))
    return render_template('node_delete_confirm.html', node=node, current_user=current)


@app.route('/profile/<int:user_id>')
def profile(user_id):
    """
    Render the profile page for a user.
    Redirects to login if the user is not logged in.
    Redirects to the home page with an error if the user does not exist.
    Passes the viewed user, their node, and the current user to the template.

    Parameters:
        user_id -- the integer primary key of the user from the URL
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    
    user = user_repo.find_by_id(user_id)

    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('index'))

    # If the input user ID != to the session user ID they are redirected back to index.html
    if current['role'] != "sysop" and user_id != current['user_id']:
        return redirect(url_for('index'))
    
    node = node_repo.find_by_owner(user_id)
    return render_template('profile.html', viewed_user=user, node=node, current_user=current)


@app.route('/profile/<int:user_id>/edit', methods=['GET', 'POST'])
def profile_by_id_edit(user_id):
    """
    Handle the profile edit form accessed by user ID.

    Redirects to login if the user is not logged in.
    Redirects to the home page with an error if the user does not exist.

    GET  -- render the edit form with the target user's current region.
    POST -- update the target user's region and redirect to their profile.

    Parameters:
        user_id -- the integer primary key of the user from the URL
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))

    if user_id != current["user_id"]:
        return redirect(url_for('index'))

    user = user_repo.find_by_id(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        user_repo.update_region(user_id, request.form.get('region', ''))
        flash('Profile updated.')
        return redirect(url_for('profile', user_id=user_id))
    return render_template('profile_id_edit.html', user=user, current_user=current)


@app.route('/profile/edit', methods=['GET', 'POST'])
def profile_edit():
    """
    Handle the profile edit form for the logged-in user.

    Redirects to login if the user is not logged in.

    GET  -- fetch the current user's record and render the edit form.
    POST -- update the current user's region and redirect to their profile.
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    if request.method == 'POST':
        user_repo.update_region(current['user_id'], request.form.get('region', ''))
        flash('Profile updated.')
        return redirect(url_for('profile', user_id=current['user_id']))
    user = user_repo.find_by_id(current['user_id'])
    return render_template('profile_edit.html', user=user, current_user=current)


@app.route('/sysop')
def sysop():
    """
    Render the sysop administration panel.

    Redirects to login if the user is not logged in.
    Redirects to the home page with an error if the user is not a sysop.
    Passes all users and all nodes to the template.
    """
    current = get_current_user(request)
    if not current:
        return redirect(url_for('login'))
    if current['role'] != 'sysop':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    all_users = user_repo.get_all()
    all_nodes = node_repo.get_all()
    return render_template('sysop.html', users=all_users, nodes=all_nodes, current_user=current)

if __name__ == '__main__':
    initialise_database()
    app.run(debug=True, port=5000)