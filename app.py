from flask import Flask, render_template, request, jsonify, send_file, url_for, session
import os
import time
from datetime import datetime, timedelta
import sqlite3
import io

app = Flask(__name__)
app.secret_key = 'super-secret-key'  # Заміни на надійний ключ у продакшн

UPLOAD_FOLDER = 'uploads'
DB_PATH = 'database/db.sqlite3'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('database', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS speedtests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id TEXT,
            upload REAL,
            download REAL,
            upload_time REAL,
            download_time REAL,
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            user_id TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id TEXT PRIMARY KEY,
            name TEXT,
            url TEXT
        )
    ''')
    c.execute('SELECT COUNT(*) FROM servers')
    if c.fetchone()[0] == 0:
        servers = [
            ('srv1', 'Сервер 1', 'http://localhost:5000'),
            ('srv2', 'Сервер 2', 'http://localhost:5001'),
            ('srv3', 'Сервер 3', 'http://localhost:5002')
        ]
        c.executemany('INSERT INTO servers (id, name, url) VALUES (?, ?, ?)', servers)
    conn.commit()
    conn.close()

init_db()

def get_servers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name FROM servers')
    servers = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    conn.close()
    return servers

@app.route('/')
def index():
    servers = get_servers()
    return render_template('index.html', servers=servers)

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user_id = data.get('user_id')
    if user_id:
        session['user_id'] = user_id
        return jsonify({'message': f'Успішний вхід як {user_id}'})
    else:
        return jsonify({'error': 'Потрібно вказати user_id'}), 400

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Файл не надіслано'}), 400

    size_mb = int(request.form.get('size_mb', '1'))
    filename = f"upload_{time.time()}.bin"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    start = time.time()
    file.save(filepath)
    end = time.time()

    duration = end - start
    speed_mbps = (size_mb * 8) / duration if duration > 0 else 0

    try:
        os.remove(filepath)
    except:
        pass

    return jsonify({'speed': round(speed_mbps, 2), 'time': round(duration, 2)})

@app.route('/download')
def download():
    size_mb = int(request.args.get('size_mb', '1'))
    data = os.urandom(size_mb * 1024 * 1024)
    file_stream = io.BytesIO(data)

    return send_file(
        file_stream,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name='testfile.bin',
        conditional=False
    )

@app.route('/save_result', methods=['POST'])
def save_result():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Немає даних'}), 400

    server_id = data.get('server_id')
    upload = data.get('upload')
    download = data.get('download')
    upload_time = data.get('upload_time')
    download_time = data.get('download_time')
    ttl = data.get('ttl', 3600)
    user_id = session.get('user_id', 'guest')

    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(seconds=ttl)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO speedtests (server_id, upload, download, upload_time, download_time, created_at, expires_at, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (server_id, upload, download, upload_time, download_time, created_at, expires_at, user_id))
    conn.commit()
    test_id = c.lastrowid
    conn.close()

    link = url_for('view_result', test_id=test_id, _external=True)
    return jsonify({'link': link})

@app.route('/result/<int:test_id>')
def view_result(test_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, server_id, upload, download, upload_time, download_time, created_at, expires_at, user_id
        FROM speedtests WHERE id = ?
    ''', (test_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return "Результат не знайдено", 404

    expires_at = row[7]
    if isinstance(expires_at, str):
        expires_at = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S.%f')
    now = datetime.utcnow()

    if expires_at <= now:
        return "Термін дії результату закінчився.", 403

    result = {
        'id': row[0],
        'server_id': row[1],
        'upload': row[2],
        'download': row[3],
        'upload_time': row[4],
        'download_time': row[5],
        'created_at': row[6],
        'expires_at': row[7],
        'user_id': row[8]
    }
    return jsonify(result)

@app.route('/stats')
def stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)

    c.execute('SELECT COUNT(*) FROM speedtests')
    total_tests = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM speedtests WHERE expires_at > ?', (now,))
    available_now = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM speedtests WHERE expires_at BETWEEN ? AND ?', (now, now + timedelta(hours=1)))
    expiring_in_hour = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM speedtests WHERE expires_at BETWEEN ? AND ?', (now, now + timedelta(days=1)))
    expiring_in_day = c.fetchone()[0]

    c.execute('SELECT AVG(upload), MAX(upload) FROM speedtests WHERE created_at > ?', (one_hour_ago,))
    avg_upload_hour, max_upload_hour = c.fetchone()

    c.execute('SELECT AVG(download), MAX(download) FROM speedtests WHERE created_at > ?', (one_hour_ago,))
    avg_download_hour, max_download_hour = c.fetchone()

    c.execute('SELECT AVG(upload), MAX(upload) FROM speedtests WHERE created_at > ?', (one_day_ago,))
    avg_upload_day, max_upload_day = c.fetchone()

    c.execute('SELECT AVG(download), MAX(download) FROM speedtests WHERE created_at > ?', (one_day_ago,))
    avg_download_day, max_download_day = c.fetchone()

    conn.close()

    return jsonify({
        'total_tests': total_tests,
        'available_now': available_now,
        'expiring_in_hour': expiring_in_hour,
        'expiring_in_day': expiring_in_day,
        'avg_upload_hour': round(avg_upload_hour or 0, 2),
        'max_upload_hour': round(max_upload_hour or 0, 2),
        'avg_download_hour': round(avg_download_hour or 0, 2),
        'max_download_hour': round(max_download_hour or 0, 2),
        'avg_upload_day': round(avg_upload_day or 0, 2),
        'max_upload_day': round(max_upload_day or 0, 2),
        'avg_download_day': round(avg_download_day or 0, 2),
        'max_download_day': round(max_download_day or 0, 2),
    })

if __name__ == '__main__':
    app.run(debug=True)
