import pymysql
DB_HOST = "localhost"
DB_ROOT_USER = "root"         
DB_ROOT_PASSWORD = ""          
DB_NAME = "hiv_test"           
DB_USER = "hivuser"            
DB_PASSWORD = "hivpass123"     
SQL_CREATE_DATABASE = f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
SQL_CREATE_USER = f"CREATE USER IF NOT EXISTS '{DB_USER}'@'localhost' IDENTIFIED BY '{DB_PASSWORD}';"
SQL_GRANT_PRIVILEGES = f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'localhost';"
SQL_FLUSH_PRIVILEGES = "FLUSH PRIVILEGES;"
SQL_CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS servers (
        id VARCHAR(255) PRIMARY KEY,
        name TEXT,
        url TEXT
    )
    """,
    """
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
    """
]

SQL_INSERT_SERVERS = """
    INSERT IGNORE INTO servers (id, name, url) VALUES
    ('srv1', 'Сервер 1', 'http://localhost:5000'),
    ('srv2', 'Сервер 2', 'http://localhost:5001'),
    ('srv3', 'Сервер 3', 'http://localhost:5002')
"""

def run_sql(connection, sql):
    with connection.cursor() as cursor:
        if isinstance(sql, list):
            for query in sql:
                cursor.execute(query)
        else:
            cursor.execute(sql)
    connection.commit()

def main():
    try:
        root_conn = pymysql.connect(
            host=DB_HOST,
            user=DB_ROOT_USER,
            password=DB_ROOT_PASSWORD,
            autocommit=True
        )
        print(f"Підключено до MySQL сервера як '{DB_ROOT_USER}'")

        run_sql(root_conn, SQL_CREATE_DATABASE)
        run_sql(root_conn, SQL_CREATE_USER)
        run_sql(root_conn, SQL_GRANT_PRIVILEGES)
        run_sql(root_conn, SQL_FLUSH_PRIVILEGES)
        print(f"База даних '{DB_NAME}' та користувач '{DB_USER}' створені")

        user_conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        print(f"Підключено до бази '{DB_NAME}' як '{DB_USER}'")

        run_sql(user_conn, SQL_CREATE_TABLES)
        run_sql(user_conn, SQL_INSERT_SERVERS)
        print("Таблиці створені, тестові сервери додані")

    except pymysql.Error as e:
        print(f"Помилка: {e}")
    finally:
        if 'root_conn' in locals():
            root_conn.close()
        if 'user_conn' in locals():
            user_conn.close()
        print("Готово!")

if __name__ == "__main__":
    main()
