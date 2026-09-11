"""
processor.py
Processador de logs: responsável pelo parsing, normalização e
classificação por nível de severidade dos registros brutos recebidos
do coletor, conforme descrito na seção 4.4 (Diagrama de Sequência) do TCC.

Formato esperado da linha bruta de log (padrão comum de aplicações):
    2026-09-10 14:32:01 [ERROR] auth-service: Falha ao validar token JWT

Caso a linha não siga o padrão, o processador tenta um parsing
best-effort e classifica como INFO por padrão.
"""

import re
from datetime import datetime

VALID_LEVELS = {"INFO", "WARNING", "ERROR", "CRITICAL"}

# Regex principal: data/hora, nível entre colchetes, componente, mensagem
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s+"
    r"\[(?P<nivel>\w+)\]\s+"
    r"(?P<componente>[\w\-\.]+):\s*"
    r"(?P<mensagem>.*)$"
)

# Palavras-chave que, mesmo sem tag explícita, indicam criticidade alta
CRITICAL_KEYWORDS = [
    "fatal", "crash", "out of memory", "unhandled exception",
    "connection refused", "timeout crítico", "falha catastrófica",
    "database down", "segmentation fault",
]


def normalize_level(raw_level: str) -> str:
    lvl = raw_level.strip().upper()
    if lvl in VALID_LEVELS:
        return lvl
    if lvl in ("WARN",):
        return "WARNING"
    if lvl in ("ERR",):
        return "ERROR"
    if lvl in ("FATAL", "CRIT"):
        return "CRITICAL"
    return "INFO"


def escalate_by_keyword(mensagem: str, nivel_atual: str) -> str:
    """Eleva a severidade para CRITICAL se a mensagem contiver
    palavras-chave de alta gravidade, mesmo que a tag original não indique isso."""
    msg_lower = mensagem.lower()
    for kw in CRITICAL_KEYWORDS:
        if kw in msg_lower:
            return "CRITICAL"
    return nivel_atual


def parse_line(raw_line: str, origem: str = "desconhecida") -> dict | None:
    """
    Realiza o parsing de uma linha bruta de log e retorna um dicionário
    estruturado e normalizado, pronto para persistência.
    Retorna None se a linha estiver vazia ou não puder ser processada.
    """
    line = raw_line.strip()
    if not line:
        return None

    match = LOG_PATTERN.match(line)

    if match:
        data = match.groupdict()
        timestamp_str = data["timestamp"].replace("T", " ")
        try:
            datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        nivel = normalize_level(data["nivel"])
        mensagem = data["mensagem"].strip()
        componente = data["componente"].strip()
    else:
        # Parsing best-effort para linhas fora do padrão esperado
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        componente = origem
        mensagem = line
        nivel = "INFO"
        for lvl in VALID_LEVELS:
            if lvl in line.upper():
                nivel = lvl
                break

    nivel = escalate_by_keyword(mensagem, nivel)

    return {
        "timestamp": timestamp_str,
        "componente": componente,
        "nivel": nivel,
        "mensagem": mensagem,
        "origem": origem,
    }
