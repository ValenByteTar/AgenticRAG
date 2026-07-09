import sqlite3
c = sqlite3.connect("chroma_bge_m3/chroma.sqlite3")
cur = c.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)
for t in tables:
    cur.execute(f"PRAGMA table_info({t})")
    cols = [(r[1], r[2]) for r in cur.fetchall()]
    print(f"\n{t}: {cols}")
c.close()
