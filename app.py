"""API REST do LogWatch: ingestão, análise, persistência e dashboard."""

import io
import os
import time
import threading
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
from datetime import datetime

import database
import processor

app = Flask(__name__)
cors_origins = os.environ.get("CORS_ORIGINS", "*")
CORS(app, resources={r"/api/*": {"origins": [o.strip() for o in cors_origins.split(",") if o.strip()] or ["*"]}})
database.init_db()

INSTANCE_ID = os.environ.get("INSTANCE_ID", "api-1")

_DEMO_EVENTS = [
    ("INFO", "notification-service", "Notifica??o enviada com sucesso"),
    ("WARNING", "auth-service", "Aumento de tentativas de autentica??o"),
    ("ERROR", "payment-service", "Timeout ao consultar gateway de pagamento"),
    ("CRITICAL", "payment-service", "Database down - conex?o perdida"),
]
_demo_lock = threading.Lock()
_demo_last_event = 0.0
_demo_index = 0



def _int_or(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_structured(payload):
    nivel = str(payload.get("nivel", "INFO")).upper()
    if nivel not in processor.VALID_LEVELS:
        nivel = processor.normalize_level(nivel)
    return {
        "timestamp": payload.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "componente": payload.get("componente") or payload.get("component") or "api",
        "nivel": nivel,
        "mensagem": payload.get("mensagem") or payload.get("message") or "Evento criado via API",
        "origem": payload.get("origem") or "api-dashboard",
        "metodo_http": payload.get("metodo_http") or payload.get("metodo") or payload.get("method"),
        "endpoint": payload.get("endpoint"),
        "status_code": _int_or(payload.get("status_code")),
        "duracao_ms": payload.get("duracao_ms"),
        "trace_id": payload.get("trace_id"),
        "raw_line": payload.get("raw_line"),
    }



@app.post("/api/demo/tick")
def demo_tick():
    """Gera um ?nico evento sint?tico para apresenta??es autorizadas."""
    global _demo_last_event, _demo_index

    if os.environ.get("ENABLE_DEMO_MODE", "").lower() != "true":
        return jsonify({"erro": "modo de demonstra??o desativado"}), 404

    with _demo_lock:
        now = time.monotonic()
        if now - _demo_last_event < 5:
            return jsonify({"status": "aguarde", "demo": True}), 429

        nivel, componente, mensagem = _DEMO_EVENTS[
            _demo_index % len(_DEMO_EVENTS)
        ]
        _demo_index += 1
        _demo_last_event = now

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_line = f"{timestamp} [{nivel}] {componente}: {mensagem}"

    parsed = processor.parse_line(raw_line, origem="demo-apresentacao")
    if parsed is None:
        return jsonify({"erro": "n?o foi poss?vel processar o evento"}), 500

    log_id, alerta_id = database.insert_log(**parsed, raw_line=raw_line)

    return jsonify({
        "status": "created",
        "demo": True,
        "log_id": log_id,
        "nivel": parsed["nivel"],
        "alerta_gerado": alerta_id is not None,
        "origem": "demo-apresentacao",
    }), 201


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "log-monitoring-api", "instance": INSTANCE_ID, "database": "sqlite"})


@app.post("/api/ingest")
def ingest_log():
    payload = request.get_json(silent=True) or {}
    raw_line = payload.get("raw_line")
    origem = payload.get("origem", "desconhecida")
    if not raw_line:
        return jsonify({"erro": "campo 'raw_line' é obrigatório"}), 400
    parsed = processor.parse_line(raw_line, origem=origem)
    if parsed is None:
        return jsonify({"erro": "linha vazia, ignorada"}), 400
    log_id, alerta_id = database.insert_log(**parsed, raw_line=raw_line)
    return jsonify({
        "log_id": log_id, "nivel": parsed["nivel"], "alerta_gerado": alerta_id is not None,
        "alerta_id": alerta_id, "atendido_por": INSTANCE_ID,
    }), 201


@app.get("/api/logs")
def get_logs():
    logs = database.query_logs(
        nivel=request.args.get("nivel"), keyword=request.args.get("keyword"),
        componente=request.args.get("componente"), status_code=_int_or(request.args.get("status_code")),
        metodo_http=request.args.get("metodo_http") or request.args.get("method"),
        limit=_int_or(request.args.get("limit"), 200), offset=_int_or(request.args.get("offset"), 0),
    )
    return jsonify(logs)


@app.get("/api/logs/<int:log_id>")
def get_log(log_id):
    log = database.get_log(log_id)
    return (jsonify(log), 200) if log else (jsonify({"erro": "log não encontrado"}), 404)


@app.post("/api/logs")
def create_log():
    payload = request.get_json(silent=True) or {}
    data = _normalize_structured(payload)
    log_id, alert_id = database.insert_log(**data)
    return jsonify({**database.get_log(log_id), "alerta_id": alert_id}), 201


@app.put("/api/logs/<int:log_id>")
def put_log(log_id):
    payload = request.get_json(silent=True) or {}
    required = ["componente", "nivel", "mensagem"]
    if any(k not in payload for k in required):
        return jsonify({"erro": "PUT exige componente, nivel e mensagem"}), 400
    updated = database.update_log(log_id, payload)
    return (jsonify(updated), 200) if updated else (jsonify({"erro": "log não encontrado"}), 404)


@app.patch("/api/logs/<int:log_id>")
def patch_log(log_id):
    payload = request.get_json(silent=True) or {}
    if not payload:
        return jsonify({"erro": "PATCH exige ao menos um campo"}), 400
    updated = database.update_log(log_id, payload, partial=True)
    return (jsonify(updated), 200) if updated else (jsonify({"erro": "log não encontrado"}), 404)


@app.delete("/api/logs/<int:log_id>")
def delete_log(log_id):
    return jsonify({"status": "deleted", "id": log_id}) if database.delete_log(log_id) else (jsonify({"erro": "log não encontrado"}), 404)


@app.get("/api/stats")
def get_stats():
    return jsonify(database.get_stats())


@app.get("/api/stats/timeline")
def get_timeline():
    return jsonify(database.get_timeline(_int_or(request.args.get("hours"), 24)))


@app.get("/api/alerts")
def get_alerts():
    unread = request.args.get("unread", "false").lower() == "true"
    return jsonify(database.get_alerts(only_unread=unread))


@app.post("/api/alerts/<int:alert_id>/read")
def read_alert(alert_id):
    return jsonify({"status": "ok"}) if database.mark_alert_read(alert_id) else (jsonify({"erro": "alerta não encontrado"}), 404)


@app.get("/api/collectors")
def collectors():
    return jsonify(database.get_collectors())


@app.post("/api/collectors/heartbeat")
def collector_heartbeat():
    payload = request.get_json(silent=True) or {}
    nome = payload.get("nome") or "collector-01"
    database.register_collector(nome, payload.get("hostname", "desconhecido"), payload.get("arquivos", ""), "online")
    return jsonify({"status": "ok", "collector": nome}), 200


@app.get("/api/logs/export.txt")
def export_txt():
    logs = database.query_logs(
        nivel=request.args.get("nivel"), keyword=request.args.get("keyword"),
        componente=request.args.get("componente"), limit=1000, offset=0,
    )
    content = database.export_logs_txt(logs)
    return Response(content, mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=logwatch-export.txt"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
