"""Testes automáticos do painel de rádio. Rodam no modo demonstração (dados fictícios), sem precisar de dados reais.

    pip install -r requirements.txt pytest
    pytest testes -q

Cada teste abre o painel de verdade (streamlit.testing) e confere que nada quebra: as duas abas, os filtros, as janelas
do mapa de calor e da curva, o modo escuro, as visualizações extras, o relatório em PDF e a leitura das planilhas.
"""
import os
import shutil
import sys
import tempfile

import pandas as pd
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ["PAINEL_MODO"] = "demo"

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = os.path.join(RAIZ, "streamlit_app.py")
TEMPO = 300


def abre(estado=None):
    at = AppTest.from_file(APP, default_timeout=TEMPO)
    for k, v in (estado or {}).items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


# ------------------------------------------------------------------------------------------------ painel
def test_abre_as_duas_abas():
    at = abre()
    rotulos = [t.label for t in at.tabs]
    assert [r.split(" ", 1)[-1] for r in rotulos[:2]] == ["Visão geral", "Projeções e cenários"]
    assert any('class="demo"' in m.value for m in at.markdown), "faixa de demonstração não apareceu"
    assert len([k for k in at.session_state["_kpis"] if k["aba"] == "Visão geral"]) >= 1


@pytest.mark.parametrize("serie", ["Banco (trimestre móvel)", "Trimestre fechado", "Ano (média dos bancos)"])
def test_series(serie):
    at = abre()
    at.selectbox(key="p1_serie").set_value(serie)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_visualizacoes():
    at = abre()
    todas = list(at.session_state["vis_sel"])
    extras = ["share", "alcance", "tmed", "yoy", "posicao", "participacao", "sazonal", "mk"]
    at = abre({"vis_sel": todas + extras})
    chaves = {g["chave"] for g in at.session_state["_graf"]}
    for c in ("v_x_share", "v_x_posicao", "v_x_participacao", "v_x_sazonal", "v_x_mk", "t_mk", "t_ranking"):
        assert c in chaves, f"faltou {c}"


def test_so_extras_sem_padrao():
    at = abre({"vis_sel": ["mk", "posicao"]})
    chaves = {g["chave"] for g in at.session_state["_graf"] if g["aba"] == "Visão geral"}
    assert chaves >= {"v_x_mk", "v_x_posicao"}
    assert "v_barras" not in chaves


def test_resumo_em_frases():
    at = abre()
    frases = at.session_state["_resumo"]
    assert len(frases) >= 3
    assert any("ranking" in f for f in frases)


def test_janelas_do_mapa_e_da_curva():
    at = abre()
    at.button(key="exp_calor").click()
    at.run()
    assert not at.exception
    at.button(key="min_calor").click()
    at.run()
    at.button(key="exp_curva").click()
    at.run()
    assert not at.exception


def test_modo_escuro():
    at = abre()
    at.button(key="tema_btn").click()
    at.run()
    assert not at.exception
    assert at.session_state["tema_escuro"] is True
    assert "Modo claro" in at.button(key="tema_btn").label


def test_projecao_tem_resultados():
    at = abre()
    chaves = {g["chave"] for g in at.session_state["_graf"] if g["aba"] == "Projeções e cenários"}
    assert {"v_leque", "v_dist", "t_patamar"} <= chaves


# ------------------------------------------------------------------------------------------------ PDF
def test_pdf_com_e_sem_projecoes():
    import relatorio
    at = abre({"vis_sel": ["resumo", "evolucao", "anual", "ranking", "mk"]})
    g = at.session_state["_graf"]
    vg = [(x["titulo"], x["sub"], x["fig"]) for x in g if x["aba"] == "Visão geral"]
    pj = [(x["titulo"], x["sub"], x["fig"]) for x in g if x["aba"] == "Projeções e cenários"]
    sem = relatorio.gera_pdf(vg, cartoes=at.session_state["_kpis"][0]["cartoes"], resumo=at.session_state["_resumo"],
                             titulo="teste", marca="DADOS FICTÍCIOS")
    com = relatorio.gera_pdf(vg, final={"titulo": "Projeções", "cartoes": [], "graficos": pj}, titulo="teste")
    assert sem.startswith(b"%PDF") and com.startswith(b"%PDF")
    assert len(com) > len(sem) * .8


# ------------------------------------------------------------------------------------------------ dados
def test_dados_de_demonstracao():
    import demo_dados
    import modelos as M
    with tempfile.TemporaryDirectory() as d:
        par = demo_dados.gera(d)
        assert par["demo"] is True
        arqs = sorted(os.listdir(os.path.join(d, "dados")))
        assert len(arqs) == 3
        hist = M.ler_arquivo(os.path.join(d, "dados", "DEMO_Historico_Radio_2020_2026.xlsx"))
        assert set(hist["emissora"]) == {"GFM", "Bahia FM"}
        assert hist["fim"].min() == pd.Timestamp("2020-03-01")
        conc = M.ler_arquivo(os.path.join(d, "dados", "DEMO_Concorrencia_2024_2026.xlsx"))
        assert conc["emissora"].nunique() == 16
        assert (conc["opm"] < conc["alcance"]).all(), "OPM# deveria ser menor que o alcance"


def test_leitor_nao_confunde_colunas():
    """Regressão do problema de out/2026: o período repetido em todas as colunas fazia o alcance virar OPM#."""
    import openpyxl
    import modelos as M
    with tempfile.TemporaryDirectory() as d:
        arq = os.path.join(d, "ranking.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([None] + ["SAL - JUL/2026 A SET/2026"] * 4)
        ws.append(["Emissora", "OPM#", "SHT%", "ALCM#", "TMED#"])
        ws.append(["SAL - GFM/WEB", 25627, 12.54, 521810.08, "02:27:12"])
        wb.save(arq)
        r = M.ler_arquivo(arq).iloc[0]
        assert r["opm"] == 25627 and r["alcance"] == 521810.08


def test_totais_ficam_fora_do_ranking():
    at = abre()
    rk = [g for g in at.session_state["_graf"] if g["chave"] == "t_ranking"][0]["fig"]["tabela"]["linhas"]
    assert not any("Total" in linha[1] for linha in rk)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
