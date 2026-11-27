"""
test_collector_failover.py
Testes unitários da função send_to_api do coletor, validando o
comportamento de redundância/failover entre múltiplas instâncias da
API sem precisar subir servidores reais (usa mocks de requests.post).
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "coletor"))

from collector import send_to_api


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


class TestFailover:
    @patch("collector.requests.post")
    def test_usa_api_primaria_quando_disponivel(self, mock_post):
        mock_post.return_value = _mock_response(
            201, {"log_id": 1, "nivel": "INFO", "alerta_gerado": False, "atendido_por": "api-1"}
        )

        send_to_api(["http://api-1", "http://api-2"], "linha de log", "origem-teste")

        # Apenas a primária deve ter sido chamada
        assert mock_post.call_count == 1
        assert "api-1" in mock_post.call_args[0][0]

    @patch("collector.requests.post")
    def test_faz_failover_para_secundaria_quando_primaria_falha(self, mock_post):
        import requests

        def side_effect(url, **kwargs):
            if "api-1" in url:
                raise requests.exceptions.ConnectionError("primária fora do ar")
            return _mock_response(
                201, {"log_id": 2, "nivel": "CRITICAL", "alerta_gerado": True, "atendido_por": "api-2"}
            )

        mock_post.side_effect = side_effect

        send_to_api(["http://api-1", "http://api-2"], "linha crítica", "origem-teste")

        # Deve ter tentado a primária (falhou) e depois a secundária (sucesso)
        assert mock_post.call_count == 2
        urls_chamadas = [call.args[0] for call in mock_post.call_args_list]
        assert any("api-1" in u for u in urls_chamadas)
        assert any("api-2" in u for u in urls_chamadas)

    @patch("collector.requests.post")
    def test_nao_falha_quando_todas_as_apis_estao_indisponiveis(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("fora do ar")

        # Não deve lançar exceção mesmo com todas as instâncias fora do ar
        send_to_api(["http://api-1", "http://api-2"], "linha qualquer", "origem-teste")

        assert mock_post.call_count == 2
