from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime
import uuid
import csv
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Allowed file extensions for profile pictures
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database initialization
def init_db():
    conn = sqlite3.connect('skillswap.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            location TEXT,
            profile_photo TEXT,
            is_public INTEGER DEFAULT 1,
            availability TEXT,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Skills table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            skill_name TEXT NOT NULL,
            skill_type TEXT NOT NULL, -- 'offered' or 'wanted'
            description TEXT,
            is_approved INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Swap requests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS swap_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER,
            provider_id INTEGER,
            offered_skill_id INTEGER,
            requested_skill_id INTEGER,
            status TEXT DEFAULT 'pending', -- 'pending', 'accepted', 'rejected', 'completed', 'cancelled'
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (requester_id) REFERENCES users (id),
            FOREIGN KEY (provider_id) REFERENCES users (id),
            FOREIGN KEY (offered_skill_id) REFERENCES skills (id),
            FOREIGN KEY (requested_skill_id) REFERENCES skills (id)
        )
    ''')
    
    # Ratings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            swap_id INTEGER,
            rater_id INTEGER,
            rated_id INTEGER,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (swap_id) REFERENCES swap_requests (id),
            FOREIGN KEY (rater_id) REFERENCES users (id),
            FOREIGN KEY (rated_id) REFERENCES users (id)
        )
    ''')
    # Messages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        message TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id) REFERENCES users (id),
        FOREIGN KEY (receiver_id) REFERENCES users (id)
    )
''')
    
    # Admin messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create admin user if doesn't exist
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        admin_hash = generate_password_hash('admin123')
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, is_admin)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', 'admin@skillswap.com', admin_hash, 'Administrator', 1))
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect('skillswap.db')
    conn.row_factory = sqlite3.Row
    return conn

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        location = data.get('location', '')
        
        if not all([username, email, password, full_name]):
            return jsonify({'error': 'All required fields must be filled'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
        if cursor.fetchone():
            return jsonify({'error': 'Username or email already exists'}), 400
        
        # Create user
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, location)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, password_hash, full_name, location))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Registration successful'}), 201
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if user['is_banned']:
                return jsonify({'error': 'Account is banned'}), 403
            
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            
            return jsonify({'message': 'Login successful', 'redirect': url_for('dashboard')}), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user's skills
    cursor.execute('''
        SELECT * FROM skills WHERE user_id = ? AND is_approved = 1
    ''', (session['user_id'],))
    skills = cursor.fetchall()
    
    # Get pending swap requests
    cursor.execute('''
        SELECT sr.*, u.full_name as requester_name, s1.skill_name as offered_skill, s2.skill_name as requested_skill
        FROM swap_requests sr
        JOIN users u ON sr.requester_id = u.id
        JOIN skills s1 ON sr.offered_skill_id = s1.id
        JOIN skills s2 ON sr.requested_skill_id = s2.id
        WHERE sr.provider_id = ? AND sr.status = 'pending'
    ''', (session['user_id'],))
    pending_requests = cursor.fetchall()
    
    # Get user's sent requests
    cursor.execute('''
        SELECT sr.*, u.full_name as provider_name, s1.skill_name as offered_skill, s2.skill_name as requested_skill
        FROM swap_requests sr
        JOIN users u ON sr.provider_id = u.id
        JOIN skills s1 ON sr.offered_skill_id = s1.id
        JOIN skills s2 ON sr.requested_skill_id = s2.id
        WHERE sr.requester_id = ?
    ''', (session['user_id'],))
    sent_requests = cursor.fetchall()

    # Get accepted swaps involving the user
    cursor.execute('''
        SELECT sr.*, 
            u1.full_name AS requester_name, 
            u2.full_name AS provider_name, 
            s1.skill_name AS offered_skill,
            s2.skill_name AS requested_skill
        FROM swap_requests sr
        JOIN users u1 ON sr.requester_id = u1.id
        JOIN users u2 ON sr.provider_id = u2.id
        JOIN skills s1 ON sr.offered_skill_id = s1.id
        JOIN skills s2 ON sr.requested_skill_id = s2.id
        WHERE sr.status = 'accepted'
        AND (sr.requester_id = ? OR sr.provider_id = ?)
    ''', (session['user_id'], session['user_id']))
    accepted_swaps = cursor.fetchall()

    
    conn.close()
    return render_template('dashboard.html', 
    skills=skills, 
    pending_requests=pending_requests, 
    sent_requests=sent_requests,
    accepted_swaps=accepted_swaps  # ✅ Add this
    )


@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': 'Current and new passwords are required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT password_hash FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    if not user or not check_password_hash(user['password_hash'], current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400
    
    new_password_hash = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_password_hash, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Password changed successfully'}), 200

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()

    # Get user stats
    cursor.execute('''
        SELECT 
            (SELECT COUNT(*) FROM skills WHERE user_id = ?) AS total_skills,
            (SELECT COUNT(*) FROM swap_requests WHERE requester_id = ?) AS total_requests,
            (SELECT COUNT(*) FROM ratings WHERE rated_id = ?) AS total_reviews,
            (SELECT ROUND(AVG(rating), 1) FROM ratings WHERE rated_id = ?) AS avg_rating
    ''', (user['id'], user['id'], user['id'], user['id']))
    user_stats = cursor.fetchone()

    conn.close()

    return render_template('profile.html', user=user, user_stats=user_stats)

@app.route('/api/upload_profile_picture', methods=['POST'])
def api_upload_profile_picture():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'profile_picture' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['profile_picture']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # Generate unique filename
        filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(file_path)
            
            # Update user's profile picture in database
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET profile_photo = ? WHERE id = ?
            ''', (filename, session['user_id']))
            conn.commit()
            conn.close()
            
            return jsonify({
                'message': 'Profile picture updated successfully',
                'filename': filename,
                'url': url_for('uploaded_file', filename=filename)
            }), 200
            
        except Exception as e:
            return jsonify({'error': 'Failed to save file'}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/upload_profile_picture', methods=['POST'])
def upload_profile_picture():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'profile_picture' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['profile_picture']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # Generate unique filename
        filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(file_path)
            
            # Update user's profile picture in database
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET profile_photo = ? WHERE id = ?
            ''', (filename, session['user_id']))
            conn.commit()
            conn.close()
            
            return jsonify({
                'message': 'Profile picture updated successfully',
                'filename': filename
            }), 200
            
        except Exception as e:
            return jsonify({'error': 'Failed to save file'}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/profile', methods=['GET', 'PUT'])
def api_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            user_dict = dict(user)
            
            user_dict.pop('password_hash', None)
            return jsonify(user_dict)
        else:
            return jsonify({'error': 'User not found'}), 404
    
    elif request.method == 'PUT':
        data = request.get_json()
        full_name = data.get('full_name')
        location = data.get('location')
        availability = data.get('availability')
        is_public = data.get('is_public', 1)
        
        if not full_name:
            return jsonify({'error': 'Full name is required'}), 400
        
        cursor.execute('''
            UPDATE users 
            SET full_name = ?, location = ?, availability = ?, is_public = ?
            WHERE id = ?
        ''', (full_name, location, availability, is_public, session['user_id']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Profile updated successfully'}), 200

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    full_name = data.get('full_name')
    location = data.get('location')
    availability = data.get('availability')
    is_public = data.get('is_public', 1)
    
    if not full_name:
        return jsonify({'error': 'Full name is required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users 
        SET full_name = ?, location = ?, availability = ?, is_public = ?
        WHERE id = ?
    ''', (full_name, location, availability, is_public, session['user_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Profile updated successfully'}), 200

@app.route('/browse')
def browse():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    skill_filter = request.args.get('skill', '')
    conn = get_db()
    cursor = conn.cursor()

    
    query = '''
        SELECT u.id, u.full_name, u.location, u.profile_photo
        FROM users u
        JOIN skills s ON u.id = s.user_id
        WHERE u.is_public = 1 AND u.is_banned = 0 AND s.skill_type = 'offered' AND s.is_approved = 1
    '''
    params = []

    # Exclude current user
    if session.get('user_id'):
        query += ' AND u.id != ?'
        params.append(session['user_id'])

    if skill_filter:
        query += ' AND s.skill_name LIKE ?'
        params.append(f'%{skill_filter}%')

    query += ' GROUP BY u.id ORDER BY u.full_name'

    cursor.execute(query, params)
    users = cursor.fetchall()

    # Get skills for each user
    users_with_skills = []
    for user in users:
        # Get offered skills for this user
        cursor.execute('''
            SELECT id, skill_name, description 
            FROM skills 
            WHERE user_id = ? AND skill_type = 'offered' AND is_approved = 1
        ''', (user['id'],))
        offered_skills = cursor.fetchall()
        
        user_dict = dict(user)
        user_dict['offered_skills'] = [dict(skill) for skill in offered_skills]
        users_with_skills.append(user_dict)

    # Get current user's offered skills for the swap form
    cursor.execute('''
        SELECT id, skill_name 
        FROM skills 
        WHERE user_id = ? AND skill_type = 'offered' AND is_approved = 1
    ''', (session['user_id'],))
    current_user_skills = cursor.fetchall()

    conn.close()

    return render_template('browse.html', 
                         users=users_with_skills, 
                         skill_filter=skill_filter,
                         current_user_skills=current_user_skills)

@app.route('/api/user/<int:user_id>/skills')
def get_user_skills(user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get offered skills for the specified user
    cursor.execute('''
        SELECT id, skill_name, description 
        FROM skills 
        WHERE user_id = ? AND skill_type = 'offered' AND is_approved = 1
    ''', (user_id,))
    offered_skills = cursor.fetchall()
    
    # Get current user's offered skills
    cursor.execute('''
        SELECT id, skill_name 
        FROM skills 
        WHERE user_id = ? AND skill_type = 'offered' AND is_approved = 1
    ''', (session['user_id'],))
    current_user_skills = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'offered_skills': [dict(skill) for skill in offered_skills],
        'current_user_skills': [dict(skill) for skill in current_user_skills]
    })

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    
    cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_admin = 0')
    total_users = cursor.fetchone()['total_users']
    
    cursor.execute('SELECT COUNT(*) as total_swaps FROM swap_requests')
    total_swaps = cursor.fetchone()['total_swaps']
    
    cursor.execute('SELECT COUNT(*) as pending_swaps FROM swap_requests WHERE status = "pending"')
    pending_swaps = cursor.fetchone()['pending_swaps']
    
    cursor.execute('SELECT COUNT(*) as unapproved_skills FROM skills WHERE is_approved = 0')
    unapproved_skills_count = cursor.fetchone()['unapproved_skills']
    
    # Get recent activity
    cursor.execute('''
        SELECT sr.*, u1.full_name as requester, u2.full_name as provider
        FROM swap_requests sr
        JOIN users u1 ON sr.requester_id = u1.id
        JOIN users u2 ON sr.provider_id = u2.id
        ORDER BY sr.created_at DESC LIMIT 10
    ''')
    recent_swaps = cursor.fetchall()
    
    # Get unapproved skills
    cursor.execute('''
        SELECT s.*, u.full_name as user_name
        FROM skills s
        JOIN users u ON s.user_id = u.id
        WHERE s.is_approved = 0
    ''')
    unapproved_skills = cursor.fetchall()
    
    # Get all users
    cursor.execute('''
        SELECT id, full_name, username, email, location, is_banned, created_at
        FROM users 
        WHERE is_admin = 0
        ORDER BY created_at DESC
    ''')
    all_users = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin.html', 
                         total_users=total_users,
                         total_swaps=total_swaps,
                         pending_swaps=pending_swaps,
                         unapproved_skills_count=unapproved_skills_count,
                         recent_swaps=recent_swaps,
                         unapproved_skills=unapproved_skills,
                         all_users=all_users)

# API Routes
@app.route('/api/skills', methods=['GET', 'POST'])
def api_skills():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.get_json()
        skill_name = data.get('skill_name')
        skill_type = data.get('skill_type')
        description = data.get('description', '')
        
        if not skill_name or skill_type not in ['offered', 'wanted']:
            return jsonify({'error': 'Invalid skill data'}), 400
        
        cursor.execute('''
            INSERT INTO skills (user_id, skill_name, skill_type, description)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], skill_name, skill_type, description))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Skill added successfully'}), 201
    
    # GET request
    cursor.execute('SELECT * FROM skills WHERE user_id = ?', (session['user_id'],))
    skills = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(skills)

@app.route('/api/skills/<int:skill_id>', methods=['DELETE'])
def api_delete_skill(skill_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM skills WHERE id = ? AND user_id = ?', (skill_id, session['user_id']))
    
    if cursor.rowcount == 0:
        return jsonify({'error': 'Skill not found'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Skill deleted successfully'})

@app.route('/api/swap-request', methods=['POST'])
def api_swap_request():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    provider_id = data.get('provider_id')
    offered_skill_id = data.get('offered_skill_id')
    requested_skill_id = data.get('requested_skill_id')
    message = data.get('message', '')
    
    if not all([provider_id, offered_skill_id, requested_skill_id]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO swap_requests (requester_id, provider_id, offered_skill_id, requested_skill_id, message)
        VALUES (?, ?, ?, ?, ?)
    ''', (session['user_id'], provider_id, offered_skill_id, requested_skill_id, message))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Swap request sent successfully'}), 201

@app.route('/api/swap-request/<int:request_id>', methods=['PUT', 'DELETE'])
def api_swap_request_action(request_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'DELETE':
        cursor.execute('''
            DELETE FROM swap_requests 
            WHERE id = ? AND requester_id = ? AND status = 'pending'
        ''', (request_id, session['user_id']))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Request not found or cannot be deleted'}), 404
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Request deleted successfully'})
    
    
    data = request.get_json()
    action = data.get('action')
    
    if action not in ['accept', 'reject']:
        return jsonify({'error': 'Invalid action'}), 400
    
    status = 'accepted' if action == 'accept' else 'rejected'
    
    cursor.execute('''
        UPDATE swap_requests 
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND provider_id = ? AND status = 'pending'
    ''', (status, request_id, session['user_id']))
    
    if cursor.rowcount == 0:
        return jsonify({'error': 'Request not found or already processed'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': f'Request {action}ed successfully'})

# --- ADMIN API ROUTES ---

@app.route('/api/admin/skills/<int:skill_id>/approve', methods=['PUT'])
def approve_skill(skill_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE skills SET is_approved = 1 WHERE id = ?', (skill_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Skill approved successfully'})

@app.route('/api/admin/skills/<int:skill_id>/reject', methods=['DELETE'])
def reject_skill(skill_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM skills WHERE id = ?', (skill_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Skill rejected and deleted successfully'})

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, full_name, username, email, location, is_banned FROM users')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/admin/swaps/<int:swap_id>/cancel', methods=['PUT'])
def cancel_swap(swap_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE swap_requests SET status = "cancelled" WHERE id = ?', (swap_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Swap cancelled'}), 200


@app.route('/api/admin/users/<int:user_id>/ban', methods=['PUT'])
def ban_user(user_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'User banned'}), 200

@app.route('/api/admin/users/<int:user_id>/unban', methods=['PUT'])
def unban_user(user_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'User unbanned'}), 200

@app.route('/api/admin/users/<int:user_id>/delete', methods=['DELETE'])
def delete_user(user_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    
    # Delete related records first
    cursor.execute('DELETE FROM swap_requests WHERE requester_id = ? OR provider_id = ?', (user_id, user_id))
    cursor.execute('DELETE FROM ratings WHERE rater_id = ? OR rated_id = ?', (user_id, user_id))
    cursor.execute('DELETE FROM skills WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    
    conn.commit()
    conn.close()
    return jsonify({'message': 'User deleted successfully'})

@app.route('/api/admin/messages', methods=['GET', 'POST'])
def admin_messages():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.get_json()
        title = data.get('title')
        message = data.get('message')

        if not title or not message:
            return jsonify({'error': 'Title and message are required'}), 400

        cursor.execute('INSERT INTO admin_messages (title, message) VALUES (?, ?)', (title, message))
        conn.commit()
        conn.close()
        return jsonify({'message': 'System message sent successfully'})
    
   
    cursor.execute('SELECT * FROM admin_messages ORDER BY created_at DESC')
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(messages)

@app.route('/api/admin/export')
def export_data():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    import csv
    from io import StringIO
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.username, s.skill_name, s.skill_type, s.description
        FROM skills s
        JOIN users u ON u.id = s.user_id
    ''')
    rows = cursor.fetchall()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Username', 'Skill Name', 'Skill Type', 'Description'])
    for row in rows:
        writer.writerow(row)
    
    conn.close()
    return Response(output.getvalue(), mimetype='text/csv')

@app.route('/api/admin/stats')
def admin_stats():
    if 'user_id' not in session or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    
    # Get comprehensive stats
    cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_admin = 0')
    total_users = cursor.fetchone()['total_users']
    
    cursor.execute('SELECT COUNT(*) as total_swaps FROM swap_requests')
    total_swaps = cursor.fetchone()['total_swaps']
    
    cursor.execute('SELECT COUNT(*) as pending_swaps FROM swap_requests WHERE status = "pending"')
    pending_swaps = cursor.fetchone()['pending_swaps']
    
    cursor.execute('SELECT COUNT(*) as unapproved_skills FROM skills WHERE is_approved = 0')
    unapproved_skills = cursor.fetchone()['unapproved_skills']
    
    cursor.execute('SELECT COUNT(*) as banned_users FROM users WHERE is_banned = 1')
    banned_users = cursor.fetchone()['banned_users']
    
    conn.close()
    
    return jsonify({
        'total_users': total_users,
        'total_swaps': total_swaps,
        'pending_swaps': pending_swaps,
        'unapproved_skills': unapproved_skills,
        'banned_users': banned_users
    })

# File serving route for uploaded images
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


#messages route to view matches
@app.route('/messages')
def messages():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT u.id, u.full_name
        FROM users u
        JOIN swap_requests sr ON (
            (sr.requester_id = ? AND sr.provider_id = u.id)
            OR
            (sr.provider_id = ? AND sr.requester_id = u.id)
        )
        WHERE sr.status = 'accepted' AND u.id != ?
    ''', (session['user_id'], session['user_id'], session['user_id']))
    
    matches = cursor.fetchall()
    conn.close()

    return render_template('messages.html', matches=matches)

@app.route('/api/messages/<int:user_id>')
def get_messages(user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages
        WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
        ORDER BY timestamp ASC
    ''', (session['user_id'], user_id, user_id, session['user_id']))
    
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(messages)

@app.route('/api/messages/send', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    receiver_id = data.get('receiver_id')
    message = data.get('message')

    if not receiver_id or not message:
        return jsonify({'error': 'Missing fields'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (sender_id, receiver_id, message)
        VALUES (?, ?, ?)
    ''', (session['user_id'], receiver_id, message))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Message sent'}), 201


@app.route('/api/ratings', methods=['POST'])
def submit_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    swap_id = data.get('swap_id')
    rated_id = data.get('rated_id')
    rating = data.get('rating')
    feedback = data.get('feedback', '')

    if not swap_id or not rated_id or not rating:
        return jsonify({'error': 'Missing required fields'}), 400

    if not (1 <= int(rating) <= 5):
        return jsonify({'error': 'Rating must be between 1 and 5'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Check if this rating already exists
    cursor.execute('''
        SELECT id FROM ratings
        WHERE swap_id = ? AND rater_id = ?
    ''', (swap_id, session['user_id']))

    if cursor.fetchone():
        return jsonify({'error': 'You have already rated this swap'}), 400

    cursor.execute('''
        INSERT INTO ratings (swap_id, rater_id, rated_id, rating, feedback)
        VALUES (?, ?, ?, ?, ?)
    ''', (swap_id, session['user_id'], rated_id, rating, feedback))

    conn.commit()
    conn.close()

    return jsonify({'message': 'Rating submitted successfully'}), 201


if __name__ == '__main__':
    if not os.path.exists('static/uploads'):
        os.makedirs('static/uploads')
    
    init_db()
    app.run(debug=True)