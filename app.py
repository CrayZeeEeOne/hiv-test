from flask import Flask, render_template, request, jsonify, send_file, url_for, session, g
import os
import time
from datetime import datetime, timedelta
import io
import pymysql
import requests
from google.oauth2 import id_token
from google.auth.transport import requests as grequests

app = Flask(__name__)
app.secret_key = 'super-secret-key'  # Заміни на безпечний у продакшн

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

USE_LOCAL = os.environ.get('USE_LOCAL_DB') == '1'

if USE_LOCAL:
    print("[DB] Використовується локальна база даних")
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'hivuser',
        'password': 'hivpass123',
        'database': 'hiv_test',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
else:
    print("[DB] Використовується віддалена база на PythonAnywhere")
    DB_CONFIG = {
        'host': 'czeo.mysql.pythonanywhere-services.com',
        'user': 'czeo',
        'password': '123QWEasd_',
        'database': 'czeo$db',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }

GOOGLE_CLIENT_ID = "161637199681-cj1eqhcbbdur3rbmikk92uk7b0rlrc5p.apps.googleusercontent.com"

FACEBOOK_APP_ID = "10078966155483125"
FACEBOOK_APP_SECRET = "7ff23de7f68b9e7b949c406fca97855d"

def get_db():
    if 'db' not in g:
        g.db = pymysql.connect(**DB_CONFIG)
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    conn = get_db()
    with conn.cursor() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS speedtests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                server_id TEXT,
                upload FLOAT,
                download FLOAT,
                upload_time FLOAT,
                download_time FLOAT,
                created_at DATETIME,
                expires_at DATETIME,
                user_id TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS servers (
                id VARCHAR(255) PRIMARY KEY,
                name TEXT,
                url TEXT
            )
        ''')
        c.execute('SELECT COUNT(*) AS count FROM servers')
        if c.fetchone()['count'] == 0:
            servers = [
                ('srv1', 'Сервер 1', 'http://localhost:5000'),
                ('srv2', 'Сервер 2', 'http://localhost:5001'),
                ('srv3', 'Сервер 3', 'http://localhost:5002')
            ]
            c.executemany('INSERT INTO servers (id, name, url) VALUES (%s, %s, %s)', servers)
        conn.commit()

with app.app_context():
    init_db()

def get_servers():
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT id, name FROM servers')
        return [{'id': row['id'], 'name': row['name']} for row in c.fetchall()]

@app.route('/')
def index():
    servers = get_servers()
    logged_in = 'user_id' in session
    user_id = session.get('user_id', 'guest')
    return render_template('index.html',
                         servers=servers,
                         logged_in=logged_in,
                         user_id=user_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    elif request.method == 'POST':
        user_id = request.form.get('user_id')

        if not user_id or len(user_id.strip()) < 3:
            return render_template('login.html', error='Невірний user_id (мін. 3 символи)')

        session['user_id'] = user_id.strip()
        session['logged_in_at'] = datetime.utcnow().isoformat()

        return redirect(url_for('cabinet'))

@app.route('/login/google', methods=['POST'])
def login_google():
    data = request.get_json()
    token = data.get('credential')

    try:
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)
        userid = idinfo['sub']
        email = idinfo.get('email')
        session['user_id'] = f"google_{userid}"
        return jsonify({'message': f"Успішний вхід через Google як {email}"})
    except Exception as e:
        return jsonify({'error': 'Помилка перевірки Google токена'}), 401

@app.route('/login/facebook', methods=['POST'])
def login_facebook():
    data = request.get_json()
    access_token = data.get('accessToken')
    user_id = data.get('userID')

    if not access_token or not user_id:
        return jsonify({'error': 'Відсутній токен або ID користувача'}), 400

    try:
        # Перевіряємо токен
        debug_url = "https://graph.facebook.com/debug_token"
        params = {
            'input_token': access_token,
            'access_token': f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}"
        }

        # Додатковий запит для отримання інформації про користувача
        profile_url = f"https://graph.facebook.com/{user_id}"
        profile_params = {
            'fields': 'id,name,email',
            'access_token': access_token
        }

        # Виконуємо обидва запити паралельно
        debug_response = requests.get(debug_url, params=params)
        profile_response = requests.get(profile_url, params=profile_params)

        debug_data = debug_response.json()
        profile_data = profile_response.json()

        if debug_data.get('data', {}).get('is_valid') and debug_data['data']['user_id'] == user_id:
            # Зберігаємо інформацію про користувача в сесії
            session['user_id'] = f"fb_{user_id}"
            session['user_name'] = profile_data.get('name', 'Facebook User')
            session['user_email'] = profile_data.get('email', '')

            return jsonify({
                'message': f"Успішний вхід через Facebook як {profile_data.get('name', 'Facebook User')}"
            })
        else:
            return jsonify({'error': 'Недійсний токен Facebook'}), 401

    except Exception as e:
        print(f"Facebook login error: {str(e)}")
        return jsonify({'error': 'Помилка при перевірці Facebook токена'}), 500

@app.route('/logout', methods=['POST'])
def logout():
    # Очищаємо всі дані сесії
    session.clear()
    return jsonify({
        'message': 'Успішний вихід',
        'redirect': url_for('index')  # Додаємо URL для редіректу
    })

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

    conn = get_db()
    with conn.cursor() as c:
        c.execute('''
            INSERT INTO speedtests (server_id, upload, download, upload_time, download_time, created_at, expires_at, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (server_id, upload, download, upload_time, download_time, created_at, expires_at, user_id))
        conn.commit()
        test_id = c.lastrowid

    link = url_for('view_result', test_id=test_id, _external=True)
    return jsonify({'link': link})

@app.route('/result/<int:test_id>')
def view_result(test_id):
    conn = get_db()
    with conn.cursor() as c:
        c.execute('''
            SELECT id, server_id, upload, download, upload_time, download_time, created_at, expires_at, user_id
            FROM speedtests WHERE id = %s
        ''', (test_id,))
        row = c.fetchone()

    if not row:
        return "Результат не знайдено", 404

    # Перевірка і перетворення expires_at
    expires_at = row['expires_at']
    if isinstance(expires_at, str):
        expires_at_dt = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')
    else:
        expires_at_dt = expires_at

    now = datetime.utcnow()

    if expires_at_dt <= now:
        return "Термін дії результату закінчився.", 403

    # Переконатися, що expires_at і created_at у форматі рядка для шаблону
    if not isinstance(row['created_at'], str):
        row['created_at'] = row['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    if not isinstance(row['expires_at'], str):
        row['expires_at'] = expires_at_dt.strftime('%Y-%m-%d %H:%M:%S')

    # Віддати html сторінку з передачею результату
    return render_template('result.html', result=row)

@app.route('/cabinet')
def cabinet():
    try:
        # Додаткове логування для діагностики
        app.logger.info(f"Session data: {dict(session)}")

        if 'user_id' not in session:
            app.logger.warning("Unauthorized access attempt to cabinet")
            return redirect(url_for('login_page', next=request.url))

        user_id = session['user_id']
        app.logger.info(f"User {user_id} accessing cabinet")

        if not isinstance(user_id, str) or not user_id.strip():
            app.logger.error(f"Invalid user_id format: {user_id}")
            session.clear()
            return redirect(url_for('login_page', next=request.url))

        conn = get_db()
        with conn.cursor() as c:
            now = datetime.utcnow()
            app.logger.info(f"Executing DB queries for user {user_id}")

            # Спрощений запит для тестування
            c.execute('''
                SELECT id, server_id, upload, download, upload_time,
                       download_time, created_at, expires_at
                FROM speedtests
                WHERE user_id = %s AND expires_at > %s
                ORDER BY created_at DESC
                LIMIT 50
            ''', (user_id, now))

            tests = c.fetchall()
            app.logger.info(f"Found {len(tests)} tests for user {user_id}")

        if not tests:
            app.logger.info(f"No active tests for user {user_id}")
            return render_template('cabinet.html',
                                tests=None,
                                message="У вас ще немає результатів тестів",
                                user_id=user_id)

        # Форматування даних
        for test in tests:
            test['created_at'] = test['created_at'].strftime('%Y-%m-%d %H:%M:%S') if test['created_at'] else 'N/A'
            test['expires_at'] = test['expires_at'].strftime('%Y-%m-%d %H:%M:%S') if test['expires_at'] else 'N/A'

        return render_template('cabinet.html',
                            tests=tests,
                            user_id=user_id)

    except pymysql.Error as e:
        app.logger.error(f"Database error in cabinet: {str(e)}")
        return render_template('error.html',
                           message="Тимчасові проблеми з базою даних",
                           user_id=user_id if 'user_id' in session else None), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in cabinet: {str(e)}", exc_info=True)
        return render_template('error.html',
                           message="Внутрішня помилка сервера",
                           user_id=user_id if 'user_id' in session else None), 500

@app.route('/stats')
def stats():
    conn = get_db()
    with conn.cursor() as c:
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)

        def fetch_scalar(query, args=()):
            c.execute(query, args)
            return c.fetchone()['count']

        c.execute('SELECT COUNT(*) as count FROM speedtests')
        total_tests = c.fetchone()['count']

        c.execute('SELECT COUNT(*) as count FROM speedtests WHERE expires_at > %s', (now,))
        available_now = c.fetchone()['count']

        c.execute('SELECT COUNT(*) as count FROM speedtests WHERE expires_at BETWEEN %s AND %s', (now, now + timedelta(hours=1)))
        expiring_in_hour = c.fetchone()['count']

        c.execute('SELECT COUNT(*) as count FROM speedtests WHERE expires_at BETWEEN %s AND %s', (now, now + timedelta(days=1)))
        expiring_in_day = c.fetchone()['count']

        def avg_max(query, args):
            c.execute(query, args)
            res = c.fetchone()
            return (round(res['avg'] or 0, 2), round(res['max'] or 0, 2))

        avg_upload_hour, max_upload_hour = avg_max('SELECT AVG(upload) as avg, MAX(upload) as max FROM speedtests WHERE created_at > %s', (one_hour_ago,))
        avg_download_hour, max_download_hour = avg_max('SELECT AVG(download) as avg, MAX(download) as max FROM speedtests WHERE created_at > %s', (one_hour_ago,))
        avg_upload_day, max_upload_day = avg_max('SELECT AVG(upload) as avg, MAX(upload) as max FROM speedtests WHERE created_at > %s', (one_day_ago,))
        avg_download_day, max_download_day = avg_max('SELECT AVG(download) as avg, MAX(download) as max FROM speedtests WHERE created_at > %s', (one_day_ago,))

    return jsonify({
        'total_tests': total_tests,
        'available_now': available_now,
        'expiring_in_hour': expiring_in_hour,
        'expiring_in_day': expiring_in_day,
        'avg_upload_hour': avg_upload_hour,
        'max_upload_hour': max_upload_hour,
        'avg_download_hour': avg_download_hour,
        'max_download_hour': max_download_hour,
        'avg_upload_day': avg_upload_day,
        'max_upload_day': max_upload_day,
        'avg_download_day': avg_download_day,
        'max_download_day': max_download_day,
    })

if __name__ == '__main__':
    app.run(debug=True)

