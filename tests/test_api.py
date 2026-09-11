"""
test_api.py
Testes de integração dos endpoints REST da API (app.py), usando o
cliente de testes do Flask. Cobrem o fluxo completo: ingestão de log
bruto -> parsing -> persistência -> geração de alerta -> consulta.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app
import database


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente de testes Flask, usando um banco SQLite isolado por teste."""
    db_file = tmp_path / "test_api.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()

    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as test_client:
        yield test_client


class TestHealthCheck:
    def test_health_retorna_status_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestIngestEndpoint:
    def test_ingest_log_valido_retorna_201(self, client):
        payload = {
            "raw_line": "2026-09-10 09:12:01 [INFO] auth-service: Login OK",
            "origem": "app.log",
        }
        resp = client.post("/api/ingest", json=payload)
        assert resp.status_code == 201

        data = resp.get_json()
        assert data["nivel"] == "INFO"
        assert data["alerta_gerado"] is False

    def test_ingest_log_critical_gera_alerta(self, client):
        payload = {
            "raw_line": "2026-09-10 09:25:33 [CRITICAL] payment-service: Database down",
            "origem": "app.log",
        }
        resp = client.post("/api/ingest", json=payload)
        data = resp.get_json()

        assert resp.status_code == 201
        assert data["nivel"] == "CRITICAL"
        assert data["alerta_gerado"] is True

    def test_ingest_sem_raw_line_retorna_400(self, client):
        resp = client.post("/api/ingest", json={"origem": "app.log"})
        assert resp.status_code == 400


class TestLogsEndpoint:
    def test_get_logs_retorna_lista_vazia_inicialmente(self, client):
        resp = client.get("/api/logs")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_get_logs_apos_ingestao(self, client):
        client.post("/api/ingest", json={
            "raw_line": "2026-09-10 09:12:01 [ERROR] svc-a: falha grave",
            "origem": "app.log",
        })
        resp = client.get("/api/logs?nivel=ERROR")
        data = resp.get_json()

        assert len(data) == 1
        assert data[0]["nivel"] == "ERROR"


class TestAlertsEndpoint:
    def test_alertas_criticos_aparecem_no_endpoint(self, client):
        client.post("/api/ingest", json={
            "raw_line": "2026-09-10 09:25:33 [CRITICAL] payment-service: Database down",
            "origem": "app.log",
        })
        resp = client.get("/api/alerts?unread=true")
        data = resp.get_json()

        assert len(data) == 1
        assert data[0]["severidade"] == "CRITICAL"

    def test_marcar_alerta_como_lido_remove_da_lista_nao_lidos(self, client):
        client.post("/api/ingest", json={
            "raw_line": "2026-09-10 09:25:33 [CRITICAL] payment-service: Database down",
            "origem": "app.log",
        })
        alerta_id = client.get("/api/alerts").get_json()[0]["id"]

        resp = client.post(f"/api/alerts/{alerta_id}/read")
        assert resp.status_code == 200

        nao_lidos = client.get("/api/alerts?unread=true").get_json()
        assert len(nao_lidos) == 0


class TestStatsEndpoint:
    def test_stats_reflete_logs_inseridos(self, client):
        client.post("/api/ingest", json={
            "raw_line": "2026-09-10 09:12:01 [INFO] svc-a: ok",
            "origem": "app.log",
        })
        client.post("/api/ingest", json={
            "raw_line": "2026-09-10 09:13:01 [ERROR] svc-a: falha",
            "origem": "app.log",
        })

        resp = client.get("/api/stats")
        data = resp.get_json()

        assert data["total_geral"] == 2
        assert data["por_severidade"]["INFO"] == 1
        assert data["por_severidade"]["ERROR"] == 1
