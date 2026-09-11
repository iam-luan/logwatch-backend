"""
test_processor.py
Testes unitários do módulo processor.py: validam o parsing, a
normalização de níveis de severidade e o escalonamento automático
por palavras-chave críticas.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from processor import parse_line, normalize_level, escalate_by_keyword


class TestNormalizeLevel:
    def test_nivel_ja_valido_retorna_igual(self):
        assert normalize_level("ERROR") == "ERROR"

    def test_nivel_minusculo_e_normalizado(self):
        assert normalize_level("error") == "ERROR"

    def test_abreviacao_warn_vira_warning(self):
        assert normalize_level("WARN") == "WARNING"

    def test_abreviacao_fatal_vira_critical(self):
        assert normalize_level("FATAL") == "CRITICAL"

    def test_nivel_desconhecido_vira_info(self):
        assert normalize_level("XYZ") == "INFO"


class TestEscalateByKeyword:
    def test_mensagem_com_database_down_eleva_para_critical(self):
        resultado = escalate_by_keyword("Database down - sem conexão", "ERROR")
        assert resultado == "CRITICAL"

    def test_mensagem_normal_mantem_nivel_original(self):
        resultado = escalate_by_keyword("Usuário autenticado com sucesso", "INFO")
        assert resultado == "INFO"


class TestParseLine:
    def test_linha_valida_e_parseada_corretamente(self):
        linha = "2026-09-10 09:12:01 [INFO] auth-service: Usuário autenticado"
        resultado = parse_line(linha, origem="app.log")

        assert resultado is not None
        assert resultado["nivel"] == "INFO"
        assert resultado["componente"] == "auth-service"
        assert resultado["mensagem"] == "Usuário autenticado"
        assert resultado["timestamp"] == "2026-09-10 09:12:01"

    def test_linha_critical_e_classificada_corretamente(self):
        linha = "2026-09-10 09:25:33 [CRITICAL] payment-service: Database down"
        resultado = parse_line(linha, origem="app.log")

        assert resultado["nivel"] == "CRITICAL"

    def test_linha_error_com_palavra_critica_e_escalada(self):
        # Mesmo marcada como ERROR, contém keyword crítica e deve virar CRITICAL
        linha = "2026-09-10 09:25:33 [ERROR] payment-service: Database down inesperadamente"
        resultado = parse_line(linha, origem="app.log")

        assert resultado["nivel"] == "CRITICAL"

    def test_linha_vazia_retorna_none(self):
        assert parse_line("   ", origem="app.log") is None

    def test_linha_fora_do_padrao_ainda_e_processada(self):
        linha = "erro inesperado sem formatação definida"
        resultado = parse_line(linha, origem="app.log")

        assert resultado is not None
        assert resultado["componente"] == "app.log"
        assert resultado["mensagem"] == linha

    def test_linha_com_warn_abreviado_e_normalizada(self):
        linha = "2026-09-10 09:13:44 [WARN] auth-service: Tentativa de login incorreta"
        resultado = parse_line(linha, origem="app.log")

        assert resultado["nivel"] == "WARNING"
