# LogWatch — Backend + Collector

API REST Flask do Sistema Inteligente de Monitoramento de Logs e coletor Python.

## Arquitetura hospedada

```text
Coletor Python ──HTTPS──> API Flask (Render) ──> SQLite
                                  ^
                                  |
                         Dashboard React/Vite
                              (Vercel)
```

O coletor continua sendo um processo externo. Ele lê `.log`/`.txt` e envia as linhas para a API pública.

## Backend local

```bash
cd backend
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Health check:

```text
http://localhost:5000/api/health
```

## Deploy no Render

Este diretório foi preparado para um Web Service Python.

- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- `CORS_ORIGINS`: coloque a URL da Vercel, por exemplo `https://seu-dashboard.vercel.app`
- `LOG_DB_PATH`: em uma instalação com disco persistente, use algo como `/var/data/logwatch.db`.

### Observação sobre SQLite no Render

O projeto continua usando SQLite porque ele faz parte da proposta atual do TCC. Sem armazenamento persistente, o arquivo pode ser perdido quando a instância for reiniciada/recriada. Para uma demonstração acadêmica isso pode ser aceitável; para produção real, a evolução recomendada é PostgreSQL ou um disco persistente.

## Coletor

Depois de publicar a API, rode o coletor em uma máquina que tenha acesso aos arquivos de log:

```bash
cd coletor
pip install -r requirements.txt
python collector.py --path ../sample_logs --api https://SEU-BACKEND.onrender.com --name collector-01
```

Para testar failover, informe várias APIs separadas por vírgula.

## Endpoint de saúde

```text
GET /api/health
```

## Principais endpoints

- `POST /api/ingest`
- `GET /api/logs`
- `GET /api/logs/<id>`
- `POST /api/logs`
- `PUT /api/logs/<id>`
- `PATCH /api/logs/<id>`
- `DELETE /api/logs/<id>`
- `GET /api/stats`
- `GET /api/stats/timeline`
- `GET /api/alerts`
- `POST /api/alerts/<id>/read`
- `GET /api/collectors`
- `POST /api/collectors/heartbeat`
- `GET /api/logs/export.txt`
