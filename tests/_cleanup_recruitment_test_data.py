"""Bersihkan data uji berprefix nama tertentu dari tabel Rekrutmen (DB DEVELOPMENT, agent-run).
Pemakaian: python _cleanup_recruitment_test_data.py "SMOKE-B%"
Tidak mencetak kredensial. Hanya menghapus baris kandidat yang cocok + turunannya.
"""
import os, sys
from urllib.parse import urlparse
import pymysql
from dotenv import load_dotenv

load_dotenv("/app/backend/.env", override=True)  # .env backend adalah sumber kebenaran (bukan env shell)
pattern = sys.argv[1] if len(sys.argv) > 1 else "SMOKE-B%"
u = urlparse(os.environ["DATABASE_URL"])
assert os.environ.get("APP_ENV") == "development", "hanya untuk development"
conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=u.username, password=u.password,
                       database=u.path.lstrip("/"), charset="utf8mb4", autocommit=False)
try:
    with conn.cursor() as cur:
        cur.execute("SELECT id, full_name, stage_status FROM candidates WHERE full_name LIKE %s", (pattern,))
        rows = cur.fetchall()
        print("kandidat cocok:", [(r[1], r[2]) for r in rows])
        ids = [r[0] for r in rows]
        if ids:
            ph = ",".join(["%s"] * len(ids))
            for table in ("candidate_interviews", "candidate_approvals", "candidate_offerings", "candidate_status_history"):
                cur.execute(f"DELETE FROM {table} WHERE candidate_id IN ({ph})", ids)
                print(f"  {table}: -{cur.rowcount}")
            cur.execute(f"DELETE FROM candidates WHERE id IN ({ph})", ids)
            print(f"  candidates: -{cur.rowcount}")
    conn.commit()
    print("cleaned", len(ids))
finally:
    conn.close()
