"""测试环境：用独立 SQLite 文件库，避免依赖本地 PostgreSQL。

必须在 import api/models 之前设好 DATABASE_URL（engine 在 import 时创建）。
每次运行前删掉旧库文件，保证测试之间互不影响。
"""
import os

DB_PATH = "/tmp/tunnelconv_h03_test.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
