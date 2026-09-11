"""Gera novas linhas de log para uma demonstração ao vivo do coletor."""
import itertools
import time
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "sample_logs" / "app-servidor-01.log"
EVENTS = [
    "[INFO] notification-service: Notificação enviada com sucesso",
    "[WARNING] auth-service: Aumento de tentativas de autenticação",
    "[ERROR] payment-service: Timeout ao consultar gateway",
    "[CRITICAL] payment-service: Database down - conexão perdida",
]

for i, event in zip(itertools.count(1), itertools.cycle(EVENTS)):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with TARGET.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp} {event} - demo #{i}\n")
    print(f"[demo] nova linha adicionada: {event}")
    time.sleep(5)
