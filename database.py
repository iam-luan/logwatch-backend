"""Camada de persistência SQLite do LogWatch."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.environ.get("LOG_DB_PATH", os.path.join(os.path.dirname(__file__), "logs.db"))
SEVERITY_LEVELS = ["INFO", "WARNING", "ERROR", "CRITICAL"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tb_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    componente VARCHAR(100) NOT NULL,
    nivel VARCHAR(20) NOT NULL,
    mensagem TEXT NOT NULL,
    origem VARCHAR(255),
    metodo_http VARCHAR(10),
    endpoint VARCHAR(255),
    status_code INTEGER,
    duracao_ms REAL,
    trace_id VARCHAR(100),
    raw_line TEXT,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS tb_alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    descricao TEXT NOT NULL,
    severidade VARCHAR(20) NOT NULL,
    data_alerta DATETIME DEFAULT CURRENT_TIMESTAMP,
    lido INTEGER DEFAULT 0,
    FOREIGN KEY (log_id) REFERENCES tb_logs (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tb_coletores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome VARCHAR(100) NOT NULL UNIQUE,
    hostname VARCHAR(255),
    arquivos TEXT,
    ultima_atividade DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'online'
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def connection():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Compatibilidade com o código/testes antigos.
get_connection_context = connection


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connection() as conn:
        conn.executescript(SCHEMA_SQL)
        # Migração simples para bancos criados pela versão anterior do TCC.
        existing = _columns(conn, "tb_logs")
        migrations = {
            "metodo_http": "ALTER TABLE tb_logs ADD COLUMN metodo_http VARCHAR(10)",
            "endpoint": "ALTER TABLE tb_logs ADD COLUMN endpoint VARCHAR(255)",
            "status_code": "ALTER TABLE tb_logs ADD COLUMN status_code INTEGER",
            "duracao_ms": "ALTER TABLE tb_logs ADD COLUMN duracao_ms REAL",
            "trace_id": "ALTER TABLE tb_logs ADD COLUMN trace_id VARCHAR(100)",
            "raw_line": "ALTER TABLE tb_logs ADD COLUMN raw_line TEXT",
        }
        for column, sql in migrations.items():
            if column not in existing:
                conn.execute(sql)

        # Create indexes after migrations to support legacy databases.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_logs_nivel_timestamp ON tb_logs (nivel, timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_logs_componente ON tb_logs (componente)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_logs_status ON tb_logs (status_code)"
        )


def insert_log(timestamp, componente, nivel, mensagem, origem=None, metodo_http=None,
               endpoint=None, status_code=None, duracao_ms=None, trace_id=None, raw_line=None):
    with connection() as conn:
        cur = conn.execute(
            """INSERT INTO tb_logs
            (timestamp, componente, nivel, mensagem, origem, metodo_http, endpoint,
             status_code, duracao_ms, trace_id, raw_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, componente, nivel, mensagem, origem, metodo_http, endpoint,
             status_code, duracao_ms, trace_id, raw_line),
        )
        log_id = cur.lastrowid
        alerta_id = None
        if nivel == "CRITICAL":
            cur2 = conn.execute(
                "INSERT INTO tb_alertas (log_id, tipo, descricao, severidade) VALUES (?, ?, ?, ?)",
                (log_id, "EVENTO_CRITICO", mensagem, nivel),
            )
            alerta_id = cur2.lastrowid
        return log_id, alerta_id


def query_logs(nivel=None, keyword=None, componente=None, status_code=None,
               metodo_http=None, limit=200, offset=0):
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    query = "SELECT * FROM tb_logs WHERE 1=1"
    params = []
    if nivel:
        query += " AND nivel = ?"; params.append(nivel.upper())
    if componente:
        query += " AND componente = ?"; params.append(componente)
    if status_code is not None:
        query += " AND status_code = ?"; params.append(int(status_code))
    if metodo_http:
        query += " AND metodo_http = ?"; params.append(metodo_http.upper())
    if keyword:
        query += " AND (mensagem LIKE ? OR componente LIKE ? OR origem LIKE ? OR endpoint LIKE ?)"
        term = f"%{keyword}%"; params.extend([term, term, term, term])
    query += " ORDER BY datetime(timestamp) DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def count_logs(filters=None):
    filters = filters or {}
    where, params = " WHERE 1=1", []
    if filters.get("nivel"):
        where += " AND nivel = ?"; params.append(filters["nivel"])
    with connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM tb_logs" + where, params).fetchone()[0]


def get_log(log_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM tb_logs WHERE id = ?", (log_id,)).fetchone()
        return dict(row) if row else None


def update_log(log_id, data, partial=False):
    allowed = {"timestamp", "componente", "nivel", "mensagem", "origem", "metodo_http",
               "endpoint", "status_code", "duracao_ms", "trace_id", "raw_line"}
    changes = {k: v for k, v in data.items() if k in allowed}
    if not changes:
        return get_log(log_id)
    with connection() as conn:
        if "nivel" in changes and changes["nivel"]:
            changes["nivel"] = changes["nivel"].upper()
        sets = ", ".join(f"{k} = ?" for k in changes)
        values = list(changes.values()) + [log_id]
        cur = conn.execute(f"UPDATE tb_logs SET {sets} WHERE id = ?", values)
        if cur.rowcount == 0:
            return None
        # Se virar CRITICAL em uma edição, cria alerta apenas se ainda não houver um alerta desse log.
        if changes.get("nivel") == "CRITICAL":
            exists = conn.execute("SELECT 1 FROM tb_alertas WHERE log_id = ? LIMIT 1", (log_id,)).fetchone()
            if not exists:
                msg = changes.get("mensagem") or conn.execute("SELECT mensagem FROM tb_logs WHERE id = ?", (log_id,)).fetchone()[0]
                conn.execute("INSERT INTO tb_alertas (log_id, tipo, descricao, severidade) VALUES (?, ?, ?, ?)",
                             (log_id, "EVENTO_CRITICO", msg, "CRITICAL"))
    return get_log(log_id)


def delete_log(log_id):
    with connection() as conn:
        cur = conn.execute("DELETE FROM tb_logs WHERE id = ?", (log_id,))
        return cur.rowcount > 0


def get_stats():
    with connection() as conn:
        rows = conn.execute("SELECT nivel, COUNT(*) AS total FROM tb_logs GROUP BY nivel").fetchall()
        counts = {lvl: 0 for lvl in SEVERITY_LEVELS}
        for r in rows:
            counts[r["nivel"]] = r["total"]
        total = sum(counts.values())
        components = conn.execute(
            "SELECT componente, COUNT(*) AS total FROM tb_logs GROUP BY componente ORDER BY total DESC LIMIT 10"
        ).fetchall()
        http = conn.execute(
            "SELECT COALESCE(metodo_http, 'N/A') metodo, COUNT(*) total FROM tb_logs GROUP BY metodo ORDER BY total DESC"
        ).fetchall()
        return {
            "por_severidade": counts,
            "total_geral": total,
            "por_componente": [dict(c) for c in components],
            "por_metodo_http": [dict(x) for x in http],
        }


def get_timeline(hours=24):
    hours = max(1, min(int(hours), 168))
    agora = datetime.now()
    limite_inferior = agora - timedelta(hours=hours)

    ultimo_bucket = agora.replace(minute=0, second=0, microsecond=0)
    primeiro_bucket = ultimo_bucket - timedelta(hours=hours - 1)

    buckets = {
        (primeiro_bucket + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"): {
            nivel: 0 for nivel in SEVERITY_LEVELS
        }
        for i in range(hours)
    }

    with connection() as conn:
        total_logs = conn.execute(
            "SELECT COUNT(*) FROM tb_logs"
        ).fetchone()[0]

        if total_logs == 0:
            return []

        rows = conn.execute(
            """SELECT strftime('%Y-%m-%d %H:00:00', timestamp) AS bucket,
                      nivel,
                      COUNT(*) AS total
               FROM tb_logs
               WHERE datetime(timestamp) >= datetime(?)
                 AND datetime(timestamp) <= datetime(?)
               GROUP BY bucket, nivel
               ORDER BY bucket""",
            (
                limite_inferior.strftime("%Y-%m-%d %H:%M:%S"),
                agora.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        ).fetchall()

    for row in rows:
        bucket = row["bucket"]
        nivel = row["nivel"]

        if bucket in buckets and nivel in SEVERITY_LEVELS:
            buckets[bucket][nivel] = row["total"]

    return [
        {
            "hora": datetime.strptime(bucket, "%Y-%m-%d %H:%M:%S").strftime("%H:%M"),
            **valores,
        }
        for bucket, valores in buckets.items()
    ]


def get_alerts(only_unread=False, limit=50):
    query = """SELECT a.*, l.mensagem AS log_mensagem, l.componente, l.timestamp, l.origem
               FROM tb_alertas a JOIN tb_logs l ON a.log_id = l.id"""
    if only_unread:
        query += " WHERE a.lido = 0"
    query += " ORDER BY datetime(a.data_alerta) DESC LIMIT ?"
    with connection() as conn:
        return [dict(r) for r in conn.execute(query, (max(1, min(int(limit), 200)),)).fetchall()]


def mark_alert_read(alert_id):
    with connection() as conn:
        cur = conn.execute("UPDATE tb_alertas SET lido = 1 WHERE id = ?", (alert_id,))
        return cur.rowcount > 0


def register_collector(nome, hostname, arquivos, status="online"):
    with connection() as conn:
        conn.execute(
            """INSERT INTO tb_coletores (nome, hostname, arquivos, ultima_atividade, status)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
               ON CONFLICT(nome) DO UPDATE SET hostname=excluded.hostname, arquivos=excluded.arquivos,
               ultima_atividade=CURRENT_TIMESTAMP, status=excluded.status""",
            (nome, hostname, arquivos, status),
        )


def get_collectors():
    with connection() as conn:
        rows = conn.execute(
            """SELECT id, nome, hostname, arquivos, ultima_atividade,
                      CASE
                          WHEN status = 'offline' THEN 'offline'
                          WHEN datetime(ultima_atividade) < datetime('now', '-30 seconds') THEN 'offline'
                          ELSE 'online'
                      END AS status
               FROM tb_coletores
               ORDER BY ultima_atividade DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def export_logs_txt(logs=None):
    logs = logs if logs is not None else query_logs(limit=1000)
    lines = []
    for log in reversed(logs):
        ts = log.get("timestamp") or ""
        level = log.get("nivel") or "INFO"
        component = log.get("componente") or "desconhecida"
        message = log.get("mensagem") or ""
        lines.append(f"{ts} [{level}] {component}: {message}")
    return "\n".join(lines) + ("\n" if lines else "")
