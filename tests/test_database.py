"""
test_database.py
Testes unitários do módulo database.py: validam a inserção de logs,
a geração automática de alertas para eventos críticos e as consultas
com filtros usadas pelo dashboard.

Usa um banco SQLite temporário e isolado para cada teste, para não
interferir no banco real (logs.db) usado pela aplicação.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Substitui o caminho do banco por um arquivo temporário isolado."""
    db_file = tmp_path / "test_logs.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()
    return db_file


class TestInsertLog:
    def test_insere_log_e_retorna_id(self, temp_db):
        log_id, alerta_id = database.insert_log(
            timestamp="2026-09-10 10:00:00",
            componente="auth-service",
            nivel="INFO",
            mensagem="Login realizado",
        )
        assert log_id == 1
        assert alerta_id is None  # INFO não gera alerta

    def test_log_critical_gera_alerta_automaticamente(self, temp_db):
        log_id, alerta_id = database.insert_log(
            timestamp="2026-09-10 10:05:00",
            componente="payment-service",
            nivel="CRITICAL",
            mensagem="Database down",
        )
        assert log_id is not None
        assert alerta_id is not None  # CRITICAL deve gerar alerta

        alertas = database.get_alerts()
        assert len(alertas) == 1
        assert alertas[0]["severidade"] == "CRITICAL"


class TestQueryLogs:
    def test_filtra_logs_por_nivel(self, temp_db):
        database.insert_log("2026-09-10 10:00:00", "svc-a", "INFO", "msg1")
        database.insert_log("2026-09-10 10:01:00", "svc-a", "ERROR", "msg2")

        resultado = database.query_logs(nivel="ERROR")
        assert len(resultado) == 1
        assert resultado[0]["nivel"] == "ERROR"

    def test_filtra_logs_por_palavra_chave(self, temp_db):
        database.insert_log("2026-09-10 10:00:00", "svc-a", "INFO", "falha ao processar pedido")
        database.insert_log("2026-09-10 10:01:00", "svc-a", "INFO", "usuário logado")

        resultado = database.query_logs(keyword="pedido")
        assert len(resultado) == 1
        assert "pedido" in resultado[0]["mensagem"]


class TestGetStats:
    def test_contagem_por_severidade(self, temp_db):
        database.insert_log("2026-09-10 10:00:00", "svc-a", "INFO", "m1")
        database.insert_log("2026-09-10 10:01:00", "svc-a", "ERROR", "m2")
        database.insert_log("2026-09-10 10:02:00", "svc-a", "ERROR", "m3")

        stats = database.get_stats()
        assert stats["por_severidade"]["INFO"] == 1
        assert stats["por_severidade"]["ERROR"] == 2
        assert stats["total_geral"] == 3


class TestMarkAlertRead:
    def test_marca_alerta_como_lido(self, temp_db):
        _, alerta_id = database.insert_log(
            "2026-09-10 10:00:00", "svc-a", "CRITICAL", "falha grave"
        )
        database.mark_alert_read(alerta_id)

        nao_lidos = database.get_alerts(only_unread=True)
        assert len(nao_lidos) == 0
