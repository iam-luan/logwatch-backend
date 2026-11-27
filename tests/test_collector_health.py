import pytest

import database


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_collector_health.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()
    return db_file


def test_get_collectors_marca_offline_apos_30_segundos(db):
    database.register_collector("coletor-01", "servidor-01", "app.log")

    with database.connection() as conn:
        conn.execute(
            """UPDATE tb_coletores
               SET ultima_atividade = datetime('now', '-31 seconds')
               WHERE nome = ?""",
            ("coletor-01",),
        )

    coletores = database.get_collectors()

    assert len(coletores) == 1
    assert coletores[0]["status"] == "offline"


def test_heartbeat_reativa_coletor_offline(db):
    database.register_collector(
        "coletor-01", "servidor-01", "app.log", status="offline"
    )
    database.register_collector(
        "coletor-01", "servidor-01", "app.log", status="online"
    )

    coletores = database.get_collectors()

    assert len(coletores) == 1
    assert coletores[0]["status"] == "online"