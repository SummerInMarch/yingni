"""定时执行诺诺的头像选择；与聊天请求共享数据库锁。"""
import app


def main():
    with app.db() as conn:
        rows = conn.execute('SELECT role,content FROM messages ORDER BY id DESC LIMIT 10').fetchall()
        name = conn.execute("SELECT value FROM state WHERE key='nono_name'").fetchone()
    app.schedule_avatar_decision([dict(row) for row in reversed(rows)], name[0] if name else '诺诺')
    app.avatar_executor.shutdown(wait=True)


if __name__ == '__main__':
    main()
