"""Leitura e análise das exportações demográficas do EasyMedia (Rádio Recall): audiência por ZONA da Grande Salvador
(OPM#, AFIN%, ALCM#) e PERFIL do ouvinte (PS% por classe, idade e sexo).

Os arquivos ficam em dados/demografico/ (fora da leitura da base principal, que usa dados/*.xlsx). O leitor identifica cada
coluna pelos rótulos das linhas de cabeçalho (faixa horária 05-05/05-00, período 'SAL - JUL/2026 A SET/2026', métrica e
segmento 'SAL - ZONA ...'), nunca pela posição, então aceita um banco só (export padrão) ou vários bancos lado a lado."""
import glob
import os
import re

import pandas as pd

import modelos as M

PASTA = os.path.join("dados", "demografico")
COLUNAS = ["emissora", "inicio", "fim", "faixa", "tipo", "segmento", "metrica", "valor", "amostra_baixa", "origem"]
TIPOS = ["Zona", "Classe", "Idade", "Sexo"]
METRICAS = ["OPM#", "AFIN%", "ALCM#", "PS%"]
ROTULO = {"OPM#": "OPM# (ouvintes por minuto)", "AFIN%": "AFIN% (afinidade, 100 = média)", "ALCM#": "ALCM# (alcance)",
          "PS%": "PS% (perfil do ouvinte)"}
# unidade da variação: OPM# e ALCM# variam em %, AFIN% e PS% em pontos (p.p.)
EM_PONTOS = {"AFIN%", "PS%"}
_RX_FAIXA = re.compile(r"^\d{2}-\d{2}$")
_RX_SEG = re.compile(r"^SAL\s*-\s*(ZONA|CLASSE|IDADE|SEXO)\s*(.*)$", re.I)
_TIPO = {"ZONA": "Zona", "CLASSE": "Classe", "IDADE": "Idade", "SEXO": "Sexo"}
_ZONA_NOME = {"CENTRO/SUL": "Centro/Sul", "ITAPOA": "Itapoã", "LESTE": "Leste", "MUNICÍPIOS - PERIFERIA": "Municípios (periferia)",
              "MUNICIPIOS - PERIFERIA": "Municípios (periferia)", "NORTE": "Norte", "OESTE": "Oeste",
              "PERIF. DIST. NORTE": "Perif. dist. Norte", "PERIF. DIST. OESTE": "Perif. dist. Oeste"}


def segmento(txt):
    """'SAL - ZONA CENTRO/SUL' -> ('Zona', 'Centro/Sul'); 'SAL - IDADE 18/24' -> ('Idade', '18–24'). None se não for segmento."""
    m = _RX_SEG.match(str(txt or "").strip())
    if not m:
        return None
    tipo, resto = _TIPO[m[1].upper()], m[2].strip().upper()
    if tipo == "Zona":
        return tipo, _ZONA_NOME.get(resto, resto.title())
    if tipo == "Idade":
        return tipo, resto.replace("/", "–")
    if tipo == "Sexo":
        if resto.startswith("AMB"):
            return None                     # 'SEXO AMBOS' é o total, não um segmento
        return tipo, resto.title()
    return tipo, resto                      # classe: AB, C, DE


def eh_demografico(linhas):
    """Planilha de zonas/perfil: tem a linha 'Agrupamento' com segmentos (ZONA, CLASSE, IDADE, SEXO FEMININO/MASCULINO)."""
    for r in linhas:
        r = list(r)
        if r and str(r[0] or "").strip().upper() == "AGRUPAMENTO" and any(segmento(x) for x in r[1:]):
            return True
    return False


def _registros(linhas, origem):
    linhas = [list(r) for r in linhas]
    i_seg = next((i for i, r in enumerate(linhas) if r and str(r[0] or "").strip().upper() == "AGRUPAMENTO"
                  and any(segmento(x) for x in r[1:])), None)
    if i_seg is None:
        return []
    ncol = max(len(r) for r in linhas)
    # cabeçalho: cada classe (faixa, período, métrica) é preenchida para a direita a partir da última célula rotulada
    faixa, per, met = [None] * ncol, [None] * ncol, [None] * ncol
    for r in linhas[:i_seg]:
        f = p = m = None
        for j in range(1, ncol):
            c = r[j] if j < len(r) else None
            t = str(c or "").strip()
            if _RX_FAIXA.match(t):
                f = t
            elif M._periodo(t):
                p = M._periodo(t)
            elif M._rotulo(t) in METRICAS:
                m = M._rotulo(t)
            faixa[j] = f or faixa[j]; per[j] = p or per[j]; met[j] = m or met[j]
    seg = [segmento(x) if j else None for j, x in enumerate(linhas[i_seg] + [None] * (ncol - len(linhas[i_seg])))]
    recs = []
    for r in linhas[i_seg + 1:]:
        a = r[0] if r else None
        if not M._eh_emissora(a):
            continue
        est = M.nome_emissora(a)
        for j in range(1, min(ncol, len(r))):
            if not (seg[j] and per[j] and met[j]):
                continue
            v, baixa = M._valor(r[j])
            if v is None:
                continue
            recs.append(dict(emissora=est, inicio=per[j][0], fim=per[j][1], faixa=faixa[j] or "05-05", tipo=seg[j][0],
                             segmento=seg[j][1], metrica=met[j], valor=v, amostra_baixa=baixa, origem=origem))
    return recs


def ler_arquivo(arq, nome=None):
    """Lê uma exportação demográfica (.xlsx, todas as abas). `arq` pode ser caminho ou objeto de arquivo (upload)."""
    import openpyxl
    nome = nome or (arq if isinstance(arq, str) else getattr(arq, "name", "arquivo"))
    wb = openpyxl.load_workbook(arq, data_only=True, read_only=True)
    recs = []
    for ws in wb.worksheets:
        recs += _registros(list(ws.iter_rows(values_only=True)), f"{os.path.basename(str(nome))}:{ws.title}")
    d = pd.DataFrame(recs).reindex(columns=COLUNAS)
    if len(d):
        meses = (d["fim"].dt.year - d["inicio"].dt.year) * 12 + d["fim"].dt.month - d["inicio"].dt.month
        d = d[(meses == 2) & d["emissora"].notna()]
    chave = ["emissora", "fim", "faixa", "tipo", "segmento", "metrica"]
    return d.drop_duplicates(chave, keep="last").sort_values(chave).reset_index(drop=True)


def carregar(pasta=PASTA):
    """Todas as planilhas demográficas de dados/demografico/ numa base longa."""
    arqs = sorted(a for a in glob.glob(os.path.join(pasta, "*.xlsx")) if not os.path.basename(a).startswith("~$"))
    partes = [ler_arquivo(a) for a in arqs]
    partes = [p for p in partes if len(p)]
    if not partes:
        return pd.DataFrame(columns=COLUNAS)
    chave = ["emissora", "fim", "faixa", "tipo", "segmento", "metrica"]
    return pd.concat(partes, ignore_index=True).drop_duplicates(chave, keep="last").sort_values(chave).reset_index(drop=True)


# ------------------------------------------------------------------------------------------------------ análises
def tabela(d, metrica, fim, faixa="05-05", tipo="Zona"):
    """Emissora × segmento de um banco (valores da métrica)."""
    x = d[(d["metrica"] == metrica) & (d["fim"] == pd.Timestamp(fim)) & (d["faixa"] == faixa) & (d["tipo"] == tipo)]
    return x.pivot_table(index="emissora", columns="segmento", values="valor", aggfunc="last")


def participacao(d, fim, faixa="05-05", tipo="Zona"):
    """Participação (%) de cada emissora dentro de cada segmento, pelo OPM# (soma das emissoras do arquivo = 100)."""
    t = tabela(d, "OPM#", fim, faixa, tipo)
    return t / t.sum(axis=0) * 100


def variacao(d, metrica, fim, ref, faixa="05-05", tipo="Zona"):
    """Variação entre dois bancos: % para OPM#/ALCM#, pontos (p.p.) para AFIN%/PS%."""
    a, b = tabela(d, metrica, fim, faixa, tipo), tabela(d, metrica, ref, faixa, tipo)
    cols = [c for c in a.columns if c in b.columns]
    idx = [e for e in a.index if e in b.index]
    a, b = a.loc[idx, cols], b.loc[idx, cols]
    return (a - b) if metrica in EM_PONTOS else (a / b - 1) * 100


def destaques(var):
    """Por segmento: quem mais subiu e quem mais caiu. Lista de dicts (segmento, sobe, v_sobe, cai, v_cai)."""
    out = []
    for seg in var.columns:
        s = var[seg].dropna()
        if s.empty:
            continue
        out.append(dict(segmento=seg, sobe=s.idxmax(), v_sobe=float(s.max()), cai=s.idxmin(), v_cai=float(s.min()),
                        n_sobem=int((s > 0).sum()), n_caem=int((s < 0).sum())))
    return out


def referencia_padrao(fins, fim):
    """Banco de comparação: o mesmo banco do ano anterior, se existir; senão o banco anterior disponível."""
    fim = pd.Timestamp(fim)
    ano_ant = fim - pd.DateOffset(years=1)
    if ano_ant in fins:
        return ano_ant
    antes = [f for f in fins if f < fim]
    return antes[-1] if antes else None


def decomposicao(d, movel, emissora, fim, ref, faixa="05-05"):
    """Cruza as zonas com a base principal: quanto cada zona contribuiu (em p.p.) para a variação total do OPM# da emissora
    entre `ref` e `fim`. Devolve (tabela por zona, resumo) ou (None, None) se faltar dado."""
    z = d[(d["emissora"] == emissora) & (d["tipo"] == "Zona") & (d["metrica"] == "OPM#") & (d["faixa"] == faixa)]
    a = z[z["fim"] == pd.Timestamp(fim)].set_index("segmento")["valor"]
    b = z[z["fim"] == pd.Timestamp(ref)].set_index("segmento")["valor"]
    zonas = [s for s in a.index if s in b.index]
    if not zonas or b[zonas].sum() <= 0:
        return None, None
    a, b = a[zonas], b[zonas]
    tab = pd.DataFrame({"antes": b, "agora": a, "variacao_pct": (a / b - 1) * 100, "contrib_pp": (a - b) / b.sum() * 100,
                        "peso_pct": a / a.sum() * 100})
    s = movel[movel["emissora"] == emissora].set_index("fim")["opm"] if movel is not None and len(movel) else pd.Series(dtype=float)
    tot_fim, tot_ref = s.get(pd.Timestamp(fim)), s.get(pd.Timestamp(ref))
    resumo = dict(soma_zonas_fim=float(a.sum()), soma_zonas_ref=float(b.sum()), var_zonas_pct=float((a.sum() / b.sum() - 1) * 100),
                  opm_base_fim=None if tot_fim is None or pd.isna(tot_fim) else float(tot_fim),
                  opm_base_ref=None if tot_ref is None or pd.isna(tot_ref) else float(tot_ref))
    resumo["cobertura_pct"] = (resumo["soma_zonas_fim"] / resumo["opm_base_fim"] * 100) if resumo["opm_base_fim"] else None
    resumo["var_base_pct"] = ((tot_fim / tot_ref - 1) * 100) if resumo["opm_base_fim"] and resumo["opm_base_ref"] else None
    return tab.sort_values("contrib_pp", ascending=False), resumo
