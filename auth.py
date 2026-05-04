"""
Authentication Module
Handles user login, logout, and session management
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
from typing import Optional
from config import Config


def _execute_query(cursor, query, params=None):
    """Execute query using %s placeholders and translate to ? for SQLite."""
    if Config.DATABASE_TYPE != 'postgresql':
        query = query.replace('%s', '?')
    if params:
        return cursor.execute(query, params)
    return cursor.execute(query)

# Create authentication blueprint
auth_bp = Blueprint('auth', __name__)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'


class User(UserMixin):
    """User model for Flask-Login"""

    def __init__(self, id: int, username: str, email: str, role: str):
        self.id = id
        self.username = username
        self.email = email
        self.role = role

    @staticmethod
    def get(user_id: int) -> Optional['User']:
        """Get user by ID"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            _execute_query(cursor, 'SELECT id, username, email, role FROM users WHERE id = %s', (user_id,))
            row = cursor.fetchone()

            if row:
                return User(
                    id=row['id'],
                    username=row['username'],
                    email=row['email'],
                    role=row['role']
                )
        finally:
            conn.close()

        return None

    @staticmethod
    def get_by_username(username: str) -> Optional['User']:
        """Get user by username"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            _execute_query(cursor, 'SELECT id, username, email, role FROM users WHERE username = %s', (username,))
            row = cursor.fetchone()

            if row:
                return User(
                    id=row['id'],
                    username=row['username'],
                    email=row['email'],
                    role=row['role']
                )
        finally:
            conn.close()

        return None

    @staticmethod
    def authenticate(username: str, password: str) -> Optional['User']:
        """Authenticate user with username and password"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            _execute_query(cursor, 'SELECT id, username, email, role, password_hash FROM users WHERE username = %s', (username,))
            row = cursor.fetchone()

            if row and check_password_hash(row['password_hash'], password):
                # Update last login
                _execute_query(cursor, 'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s', (row['id'],))
                conn.commit()

                return User(
                    id=row['id'],
                    username=row['username'],
                    email=row['email'],
                    role=row['role']
                )
        finally:
            conn.close()

        return None

    @staticmethod
    def create(username: str, email: str, password: str, role: str = 'analyst') -> Optional['User']:
        """Create a new user"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            password_hash = generate_password_hash(password)
            if Config.DATABASE_TYPE == 'postgresql':
                _execute_query(cursor, '''INSERT INTO users (username, email, password_hash, role)
                   VALUES (%s, %s, %s, %s) RETURNING id''', (username, email, password_hash, role))
                user_id = cursor.fetchone()['id']
                conn.commit()
            else:
                _execute_query(cursor, '''INSERT INTO users (username, email, password_hash, role)
                   VALUES (%s, %s, %s, %s)''', (username, email, password_hash, role))
                conn.commit()
                user_id = cursor.lastrowid

            return User(id=user_id, username=username, email=email, role=role)
        except sqlite3.IntegrityError:
            return None  # Username or email already exists
        finally:
            conn.close()

    def has_role(self, role: str) -> bool:
        """Check if user has specific role"""
        role_hierarchy = {
            'analyst': 1,
            'senior_analyst': 2,
            'admin': 3
        }
        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(role, 99)
        return user_level >= required_level


def get_db_connection():
    """Get database connection (supports both SQLite and PostgreSQL)"""
    if Config.DATABASE_TYPE == 'postgresql':
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(
            Config.get_db_connection_string(),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        return conn
    else:
        conn = sqlite3.connect(Config.SQLITE_DB)
        conn.row_factory = sqlite3.Row
        return conn


@login_manager.user_loader
def load_user(user_id: int):
    """Load user for Flask-Login"""
    return User.get(int(user_id))


def role_required(role: str):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.has_role(role):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================================================
# Authentication Routes
# ============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)

        user = User.authenticate(username, password)

        if user:
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.username}!', 'success')

            # Redirect to next page or index
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout current user"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        # Validation
        if not username or not email or not password:
            flash('All fields are required', 'error')
        elif password != password_confirm:
            flash('Passwords do not match', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            user = User.create(username, email, password)

            if user:
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Username or email already exists', 'error')

    return render_template('register.html')


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('profile.html', user=current_user)


# ============================================================================
# Initialization Helper
# ============================================================================

def init_auth(app):
    """Initialize authentication for Flask app"""
    login_manager.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Create users table if it doesn't exist (skip if PostgreSQL - migration script handles it)
    if Config.DATABASE_TYPE != 'postgresql':
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'analyst' CHECK(role IN ('analyst', 'senior_analyst', 'admin')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')

            # Create default admin user if no users exist
            _execute_query(cursor, 'SELECT COUNT(*) as count FROM users')
            if cursor.fetchone()['count'] == 0:
                admin_password = generate_password_hash('admin')
                _execute_query(cursor, '''INSERT INTO users (username, email, password_hash, role)
                       VALUES (%s, %s, %s, %s)''', ('admin', 'admin@localhost', admin_password, 'admin'))
            print("✅ Created default admin user (username: admin, password: admin)")
            print("⚠️  CHANGE THIS PASSWORD IMMEDIATELY!")

            conn.commit()
        finally:
            conn.close()
