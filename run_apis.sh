#!/bin/bash
# run_apis.sh
# Sobe as duas instâncias da API (primária e secundária) para demonstrar
# a redundância/failover descrita no README.
#
# Uso:
#   ./run_apis.sh          -> inicia as duas instâncias
#   Ctrl+C encerra ambas

cd "$(dirname "$0")"

echo "Iniciando API-1 (primária) na porta 5000..."
INSTANCE_ID=api-1 PORT=5000 python3 app.py &
PID1=$!

echo "Iniciando API-2 (secundária) na porta 5001..."
INSTANCE_ID=api-2 PORT=5001 python3 app.py &
PID2=$!

trap "echo 'Encerrando...'; kill $PID1 $PID2 2>/dev/null" EXIT INT TERM

echo ""
echo "API-1: http://localhost:5000  (PID $PID1)"
echo "API-2: http://localhost:5001  (PID $PID2)"
echo ""
echo "Para testar o failover, derrube a API-1 (ex: 'kill $PID1') enquanto"
echo "o coletor está rodando com: --api http://localhost:5000,http://localhost:5001"
echo ""

wait
