"""Modelos de projeção da audiência de rádio (trimestres fechados) — usado pelo painel.
Mesma lógica do notebook Projecao_Radios_2026_v3: modelagem só em trimestres fechados (sem sobreposição),
trimestre móvel mais recente como nowcast, margens a partir dos erros reais de uma validação com origem móvel.
"""
import hashlib
import os
import pickle
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PANDEMIA = pd.period_range("2020Q2", "2021Q2", freq="Q")
ESCALA = 1000          # modelos em milhares de OPM (estabilidade numérica)
DF_T = 6               # graus de liberdade da t multivariada na simulação
N_ORIGENS = 30         # origens da validação (rolling origin)
INICIO = "2017Q1"      # 2016 fica fora da modelagem: falta o jul–set/2016 (trimestre fechado 2016T3)
SEED = 2026
PASTA_CACHE = "cache_modelos"


# ============================================================ dados
def fechados(movel, emissora, ate=None):
    """Trimestres fechados (móveis que terminam em mar, jun, set, dez), indexados por período trimestral."""
    s = movel[movel["emissora"] == emissora].set_index("fim")["opm"].sort_index()
    q = s[s.index.month.isin([3, 6, 9, 12])]
    q.index = pd.PeriodIndex(q.index, freq="Q")
    q = q[~q.index.duplicated(keep="last")]
    q = q[q.index >= pd.Period(INICIO, "Q")]
    if ate is not None:
        q = q[q.index <= pd.Period(ate, "Q")]
    return q.astype(float)


def mes_nowcast(trim):
    """Mês final do trimestre móvel que já cobre 2/3 do trimestre `trim` (ex.: 2026Q3 -> ago/2026)."""
    return (pd.Period(trim, "Q").end_time - pd.DateOffset(months=1)).to_period("M").to_timestamp()


def movel_serie(movel, emissora):
    return movel[movel["emissora"] == emissora].set_index("fim")["opm"].sort_index().astype(float)


# ============================================================ modelos (entrada e saída em milhares)
def _fut(idx, h):
    return pd.period_range(idx[-1] + 1, periods=h, freq="Q")


def _dummies(idx):
    d = pd.DataFrame(index=idx)
    d["pandemia"] = idx.isin(PANDEMIA) * 1.0
    return d


def _base(y):
    return y[~y.index.isin(PANDEMIA)]


def ingenuo(y, h):
    return np.repeat(y.iloc[-1], h)


def media4(y, h):
    return np.repeat(_base(y).iloc[-4:].mean(), h)


def ses(y, h):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    try:
        return np.asarray(ExponentialSmoothing(_base(y).values, trend=None, initialization_method="estimated").fit().forecast(h))
    except Exception:
        return media4(y, h)


def holt_amortecido(y, h):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    try:
        return np.asarray(ExponentialSmoothing(_base(y).values, trend="add", damped_trend=True,
                                               initialization_method="estimated").fit().forecast(h))
    except Exception:
        return media4(y, h)


def _exog(y, h):
    a, b = _dummies(y.index), _dummies(_fut(y.index, h))
    if a["pandemia"].std() == 0:
        return None, None
    return a.values, b.values


def ar1(y, h):
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    a, b = _exog(y, h)
    try:
        return np.asarray(SARIMAX(y.values, exog=a, order=(1, 0, 0), trend="c").fit(disp=False).forecast(h, exog=b))
    except Exception:
        return media4(y, h)


def nivel_local(y, h):
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    a, b = _exog(y, h)
    try:
        return np.asarray(UnobservedComponents(y.values, level="llevel", exog=a).fit(disp=False).forecast(h, exog=b))
    except Exception:
        return media4(y, h)


def ets_sazonal(y, h):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    try:
        return np.asarray(ExponentialSmoothing(y.values, trend=None, seasonal="add", seasonal_periods=4,
                                               initialization_method="estimated").fit().forecast(h))
    except Exception:
        return media4(y, h)


def cagr(y, h):
    """Extrapolação por CAGR (método do Power BI): média dos últimos 4 trimestres × crescimento anual de 2 anos."""
    b = _base(y)
    if len(b) < 12:
        return media4(y, h)
    m0, m2 = b.iloc[-4:].mean(), b.iloc[-12:-8].mean()
    g = (m0 / m2) ** 0.5
    return np.array([m0 * g ** ((i + 1) / 4) for i in range(h)])


def combinacao(y, h):
    return np.mean([media4(y, h), ses(y, h), ar1(y, h), nivel_local(y, h)], axis=0)


METODOS = {
    "Combinação (estudo)": combinacao,
    "Nível local": nivel_local,
    "AR(1)": ar1,
    "Suavização exponencial (SES)": ses,
    "Holt com tendência amortecida": holt_amortecido,
    "Média dos últimos 4 trimestres": media4,
    "ETS sazonal": ets_sazonal,
    "Ingênuo (repete o último)": ingenuo,
    "CAGR (método do BI)": cagr,
}
DESCRICAO = {
    "Combinação (estudo)": "Média de 4 modelos (média de 4 trimestres, SES, AR(1) e nível local). É o método validado no estudo V3.",
    "Nível local": "Modelo de espaço de estados com nível que muda aos poucos (passeio aleatório + ruído), com dummy de pandemia.",
    "AR(1)": "Autorregressivo de ordem 1 com constante: volta gradualmente para a média histórica.",
    "Suavização exponencial (SES)": "Média ponderada que dá mais peso aos trimestres recentes; projeção plana.",
    "Holt com tendência amortecida": "Nível + tendência que perde força ao longo do horizonte.",
    "Média dos últimos 4 trimestres": "Repete a média do último ano (sem pandemia).",
    "ETS sazonal": "Suavização com sazonalidade trimestral. Os testes do estudo não acharam sazonalidade significativa.",
    "Ingênuo (repete o último)": "Repete o último trimestre fechado. Serve de régua: um método útil deve errar menos que ele.",
    "CAGR (método do BI)": "Média do último ano × crescimento anual composto dos 2 anos anteriores (lógica do Power BI).",
}


def prever(metodo, y_mil, h):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.asarray(METODOS[metodo](y_mil, h), dtype=float)[:h]


# ============================================================ cache em disco
def _cache(chave, fn):
    os.makedirs(PASTA_CACHE, exist_ok=True)
    arq = os.path.join(PASTA_CACHE, hashlib.md5(chave.encode()).hexdigest() + ".pkl")
    if os.path.exists(arq):
        try:
            return pickle.load(open(arq, "rb"))
        except Exception:
            pass
    r = fn()
    pickle.dump(r, open(arq, "wb"))
    return r


def _assinatura(q, s):
    return hashlib.md5((q.to_json() + s.to_json()).encode()).hexdigest()[:10]


# ============================================================ validação com origem móvel
def backtest(q, s, metodo, H, usar_now):
    """Erros reais (real − previsto, em OPM) para h = 1..H a partir das últimas N_ORIGENS origens.
    Com nowcast: em cada origem T, o trimestre móvel que cobre 2/3 de T+1 entra como observação de T+1
    (o erro de h=1 é o erro do nowcast) e o método projeta T+2..T+H a partir dele.
    Origens e alvos na pandemia ficam de fora."""
    chave = f"bt|{metodo}|{H}|{usar_now}|{_assinatura(q, s)}"

    def calc():
        y = q / ESCALA
        linhas = []
        for T in y.index[-(N_ORIGENS + 1):-1]:
            futuros = y[y.index > T]
            hh = min(H, len(futuros))
            if hh < 1:
                continue
            real = futuros.iloc[:hh].values
            if usar_now:
                m1 = mes_nowcast(T + 1)
                if m1 not in s.index:
                    continue
                v = s[m1] / ESCALA
                resto = prever(metodo, pd.concat([y[:T], pd.Series([v], index=pd.PeriodIndex([T + 1], freq="Q"))]), hh - 1) if hh > 1 else []
                p = np.r_[v, resto]
            else:
                p = prever(metodo, y[:T], hh)
            for i in range(hh):
                linhas.append(dict(origem=T, h=i + 1, alvo=T + i + 1, prev=p[i] * ESCALA, real=real[i] * ESCALA))
        d = pd.DataFrame(linhas)
        if d.empty:
            return d
        d["erro"] = d["real"] - d["prev"]
        fora = d["origem"].isin(PANDEMIA) | d["alvo"].isin(PANDEMIA) | (d["origem"] + 1).isin(PANDEMIA)
        return d[~fora].reset_index(drop=True)

    return _cache(chave, calc)


def _psd(S):
    w, v = np.linalg.eigh((S + S.T) / 2)
    return v @ np.diag(np.clip(w, 1e-6, None)) @ v.T


def fator_alargamento(E):
    """Multiplicador da dispersão que faz a faixa de 80% cobrir 80% na validação (deixa-um-de-fora), entre 1,0 e 1,5."""
    from scipy import stats
    q80 = stats.t.ppf(0.9, DF_T) * np.sqrt((DF_T - 2) / DF_T)
    z = []
    for c in E.columns:
        col = E[c].dropna().values
        if len(col) < 6:
            continue
        for i in range(len(col)):
            sd = np.delete(col, i).std(ddof=1)
            if sd > 0:
                z.append(abs(col[i]) / sd)
    if not z:
        return 1.0
    return float(np.clip(np.quantile(z, 0.8) / q80, 1.0, 1.5))


def projetar(movel, emissora, metodo, ate, h, usar_now=True, corrigir_vies=False, n_sim=40_000, valor_now=None):
    """Projeção de h trimestres após o trimestre fechado `ate`, com simulação dos erros reais da validação."""
    q_all = fechados(movel, emissora)
    q = q_all[q_all.index <= pd.Period(ate, "Q")]
    s_all = movel_serie(movel, emissora)
    corte_mes = mes_nowcast(q.index[-1] + 1)               # o que se sabia na época: até 2 meses após o fim de `ate`
    s = s_all[s_all.index <= corte_mes]
    futuros = pd.period_range(q.index[-1] + 1, periods=h, freq="Q")
    now = bool(usar_now and corte_mes in s.index)
    y = q / ESCALA
    if now:
        v = s[corte_mes] if valor_now is None else valor_now
        resto = prever(metodo, pd.concat([y, pd.Series([v / ESCALA], index=pd.PeriodIndex([futuros[0]], freq="Q"))]), h - 1) * ESCALA if h > 1 else np.array([])
        f = np.r_[v, resto]
    else:
        f = prever(metodo, y, h) * ESCALA

    bt = backtest(q, s, metodo, h, now)
    E = bt.pivot_table(index="origem", columns="h", values="erro").reindex(columns=range(1, h + 1))
    # covariância par a par (usa todas as origens disponíveis em cada horizonte) e projetada para PSD
    C = E.cov(min_periods=4)
    sd_fallback = np.nanmax(np.sqrt(np.diag(C.values))) if np.isfinite(np.diag(C.values)).any() else 0.08 * q.iloc[-1]
    for j in range(h):
        if not np.isfinite(C.iat[j, j]):
            C.iat[j, j] = (sd_fallback * (1 + 0.1 * j)) ** 2
    C = C.fillna(0.0).values
    k = fator_alargamento(E)
    S = _psd(C * (DF_T - 2) / DF_T * k ** 2)
    rng = np.random.default_rng(SEED)
    Z = rng.multivariate_normal(np.zeros(h), S, n_sim) / np.sqrt(rng.chisquare(DF_T, n_sim) / DF_T)[:, None]
    vies = np.nan_to_num(E.mean().values) if corrigir_vies else np.zeros(h)
    centro = f + vies
    sim = centro + Z
    resumo = pd.DataFrame()
    if len(bt):
        resumo = (bt.assign(ae=bt["erro"].abs(), ape=bt["erro"].abs() / bt["real"])
                    .groupby("h").agg(n=("erro", "size"), MAE=("ae", "mean"), MAPE=("ape", "mean"), vies=("erro", "mean"))
                    .reset_index())
    return dict(emissora=emissora, metodo=metodo, q=q, q_all=q_all, s=s, s_all=s_all, futuros=futuros, centro=centro,
                sim=sim, nowcast=now, valor_now=(s[corte_mes] if now else np.nan), fator=k, n_origens=int(E.dropna(how="all").shape[0]),
                validacao=resumo, bt=bt)


def comparar_metodos(movel, emissora, ate, H=4, usar_now=False):
    q = fechados(movel, emissora, ate)
    s = movel_serie(movel, emissora)
    s = s[s.index <= mes_nowcast(q.index[-1] + 1)]
    out = []
    for m in METODOS:
        b = backtest(q, s, m, H, usar_now)
        if len(b):
            out.append(dict(metodo=m, n=len(b), MAE=b["erro"].abs().mean(), MAPE=(b["erro"].abs() / b["real"]).mean(),
                            vies=b["erro"].mean()))
    return pd.DataFrame(out).sort_values("MAE").reset_index(drop=True)


def fator_conversao(q_por_emissora, oficial, tipo="ano"):
    """Fator número oficial ÷ média dos trimestres fechados, com média e desvio entre os pares disponíveis.
    tipo="ano" usa chaves como "2025"; tipo="semestre" usa "1S25", "2S25"."""
    raz = []
    for e, d in oficial.items():
        q = q_por_emissora.get(e)
        if q is None:
            continue
        for k, v in d.items():
            k = str(k)
            if tipo == "ano" and k.isdigit():
                qs = [pd.Period(f"{k}Q{i}", "Q") for i in (1, 2, 3, 4)]
            elif tipo == "semestre" and len(k) == 4 and k[1] == "S":
                a = 2000 + int(k[2:])
                qs = [pd.Period(f"{a}Q{i}", "Q") for i in ((1, 2) if k[0] == "1" else (3, 4))]
            else:
                continue
            if all(t in q.index for t in qs):
                raz.append(v / q[qs].mean())
    if len(raz) >= 2:
        return float(np.mean(raz)), float(np.std(raz, ddof=1)), len(raz)
    return 1.0, 0.01, len(raz)


# ============================================================ leitura e atualização dos dados
MES_ABR = {m: i + 1 for i, m in enumerate("JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ".split())}
_RX = None


NOMES_EMISSORAS = {   # trecho do nome no EasyMedia -> nome no painel (ordem importa: o mais específico primeiro)
    "BAHIA FM": "Bahia FM", "GFM": "GFM", "PIATA": "Piatã FM", "PIATÃ": "Piatã FM", "ITAPOAN": "Itapoan FM",
    "SALVADOR FM": "Salvador FM", "A TARDE": "A Tarde FM", "METROPOLITANA": "Metropolitana FM", "METROPOLE": "Metrópole FM",
    "SOCIEDADE AM": "Sociedade AM", "SOCIEDADE FM": "Sociedade FM", "BAIANA": "Baiana FM", "EDUCADORA": "Educadora FM",
    "NOVABRASIL": "NovaBrasil FM", "ANTENA 1": "Antena 1", "BAND FM": "Band FM", "REDE ALELUIA": "Rede Aleluia", "88.3": "88.3 FM",
    "POPULAR": "Popular FM",
}
COLUNAS = ["emissora", "inicio", "fim", "opm", "sht", "alcance", "tmed", "amostra_baixa", "origem"]


# totais de mercado do EasyMedia: entram na base para consulta, mas não são emissoras (ficam fora do ranking e da projeção)
TOTAIS = {"TOTAL EMISSORAS": "Total emissoras", "TOTAL FM": "Total FM", "TOTAL WEB": "Total web", "TOTAL RADIO": "Total rádio",
          "TOTAL RÁDIO": "Total rádio"}


def nome_emissora(txt):
    t = str(txt).upper().replace("SAL -", "").replace("SAL-", "").strip()
    if t in TOTAIS:
        return TOTAIS[t]
    for k, v in NOMES_EMISSORAS.items():
        if k in t:
            return v
    t = t.replace("/WEB", "").strip()
    if not t:
        return None
    import re
    return re.sub(r"\b(Fm|Am)\b", lambda m: m.group(1).upper(), t.title())     # "Rádio Cidade Fm" -> "Rádio Cidade FM"


def _rx():
    import re
    global _RX
    _RX = _RX or re.compile(r"SAL\s*-\s*(\w{3})/(\d{4})\s*A\s*(\w{3})/(\d{4})", re.I)
    return _RX


def _valor(c):
    """Número do EasyMedia. 'NA'/vazio -> None. '#1.511' (amostra pequena) -> (1511, True).
    Aceita '1.511' e '1.511,5' (padrão brasileiro) e também '95678.48' (ponto decimal, comum em CSV)."""
    import re
    if c is None:
        return None, False
    if isinstance(c, bool):
        return None, False
    if isinstance(c, (int, float)):
        return (None, False) if pd.isna(c) else (float(c), False)
    t = str(c).strip()
    if t in ("", "None", "nan", "-", "NA", "N/A", "#N/A"):
        return None, False
    baixa = t.startswith("#")
    t = t.lstrip("#").strip()
    if "," in t:                                        # 1.511,5 -> 1511.5
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):        # 1.511 / 2.096.052 -> milhar
        t = t.replace(".", "")
    try:
        return float(t), baixa
    except ValueError:
        return None, False


def _tempo(c):
    """TMED# como texto 'HH:MM:SS' (aceita texto, datetime.time ou timedelta vindos do Excel)."""
    import datetime as _dt
    if c is None:
        return None
    if isinstance(c, _dt.time):
        return c.strftime("%H:%M:%S")
    if isinstance(c, _dt.timedelta):
        seg = int(c.total_seconds())
        return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
    t = str(c).strip().lstrip("#").strip()
    return None if t in ("", "None", "nan", "NA", "N/A", "-") else t


def _periodo(txt):
    m = _rx().match(str(txt or "").strip())
    if not m:
        return None
    return pd.Timestamp(int(m[2]), MES_ABR[m[1].upper()], 1), pd.Timestamp(int(m[4]), MES_ABR[m[3].upper()], 1)


def _eh_emissora(a):
    """Linha de dado: coluna A = 'SAL - NOME DA EMISSORA' (o total do meio não é emissora)."""
    t = str(a or "").strip().upper()
    nome = t.replace("SAL -", "").replace("SAL-", "").strip()
    if nome in TOTAIS:
        return True
    return t.startswith(("SAL -", "SAL-")) and "TOTAL" not in t and "SEXO" not in t and _periodo(t) is None


def _linhas_para_registros(linhas, origem):
    """Formato "longo" (histórico): A = emissora (só na 1ª linha do bloco), B = 'SAL - MMM/AAAA A MMM/AAAA', C = OPM#."""
    recs, est = [], None
    for r in linhas:
        a, b, c = (list(r) + [None] * 3)[:3]
        if a is not None and str(a).strip():
            est = nome_emissora(a) if _eh_emissora(a) else None    # outro texto em A (cabeçalho, total) encerra o bloco
        per = _periodo(b)
        v, baixa = _valor(c)
        if not (per and est) or v is None:
            continue
        recs.append(dict(emissora=est, inicio=per[0], fim=per[1], opm=v, amostra_baixa=baixa, origem=origem))
    return recs


METRICAS = ("OPM#", "SHT%", "ALCM#", "TMED#")


def _rotulo(x):
    return str(x or "").strip().upper().replace(" ", "")


def _linha_metricas(linhas, i):
    """Procura, perto da linha de períodos `i`, a linha com os rótulos OPM# / SHT% / ALCM# / TMED#.
    Abaixo é o padrão do ranking; acima acontece no export de um banco só (métricas em cima, períodos embaixo)."""
    for k in (i + 1, i + 2, i - 1, i - 2, i - 3):
        if 0 <= k < len(linhas) and k != i:
            rot = [_rotulo(x) for x in linhas[k]]
            if sum(m in rot for m in METRICAS) >= 2:
                return k
    return None


def _largo_para_registros(linhas, origem):
    """Formato "largo" (ranking da concorrência): uma linha de períodos ('SAL - JAN/2024 A MAR/2024' ...), a linha de
    métricas (OPM#, SHT%, ALCM#, TMED#) e uma linha por emissora (coluna A = 'SAL - ...').
    O período pode vir só na 1ª coluna do bloco (células mescladas, como no EasyMedia) ou repetido em todas as colunas
    do bloco: cada coluna é lida pelo rótulo da métrica, nunca pela posição."""
    linhas = [list(r) for r in linhas]
    for i, r in enumerate(linhas):
        pers = {j: _periodo(x) for j, x in enumerate(r)}
        pers = {j: p for j, p in pers.items() if p}
        if not pers:
            continue
        km = _linha_metricas(linhas, i)
        if km is None and len(pers) < 2:
            continue                      # um período só e sem linha de métricas: é o formato longo (histórico)
        met = [_rotulo(x) for x in linhas[km]] if km is not None else []

        # período e métrica de cada coluna
        blocos = {}                       # período -> {métrica: coluna}
        atual, vistos = None, set()
        for j in range(1, max(len(r), len(met))):
            cab = r[j] if j < len(r) else None
            if j in pers:
                if pers[j] != atual:
                    atual, vistos = pers[j], set()
                elif _rotulo(met[j] if j < len(met) else "") in vistos:
                    vistos = set()        # mesmo período repetido e a métrica recomeçou: bloco duplicado
            elif cab not in (None, "") and str(cab).strip():
                atual = None              # outro cabeçalho (ex.: coluna do ano '2024') encerra o bloco
            if atual is None:
                continue
            rot = met[j] if j < len(met) else ""
            if not met:                   # sem linha de métricas: a 1ª coluna de cada período é o OPM#
                rot = "OPM#" if j in pers else ""
            if not rot:
                continue
            if rot in vistos:             # a métrica se repete sem período novo em cima: não dá para saber o período
                atual = None
                continue
            vistos.add(rot)
            blocos.setdefault(atual, {})[rot] = j

        recs = []
        for r2 in linhas[max(i, km if km is not None else i) + 1:]:
            a = r2[0] if r2 else None
            if not _eh_emissora(a):
                continue
            est = nome_emissora(a)
            pega = lambda col: r2[col] if col is not None and col < len(r2) else None
            for (ini, fim), cols in blocos.items():
                if "OPM#" not in cols:
                    continue
                opm, baixa = _valor(pega(cols["OPM#"]))
                if opm is None:
                    continue
                sht, _ = _valor(pega(cols.get("SHT%")))
                alc, _ = _valor(pega(cols.get("ALCM#")))
                recs.append(dict(emissora=est, inicio=ini, fim=fim, opm=opm, sht=sht, alcance=alc,
                                 tmed=_tempo(pega(cols.get("TMED#"))), amostra_baixa=baixa, origem=origem))
        return recs
    return []


def ler_arquivo(arq, nome=None):
    """Lê planilhas do EasyMedia (.xlsx, todas as abas; formato longo do histórico ou largo do ranking de concorrência)
    ou o CSV exportado (separador ';'). `arq` pode ser um caminho ou um objeto de arquivo (ex.: upload do Streamlit)."""
    nome = nome or (arq if isinstance(arq, str) else getattr(arq, "name", "arquivo"))
    recs = []
    if str(nome).lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(arq, data_only=True, read_only=True)
        for ws in wb.worksheets:
            linhas = list(ws.iter_rows(values_only=True))
            org = f"{os.path.basename(str(nome))}:{ws.title}"
            largo = _largo_para_registros(linhas, org)
            recs += largo if largo else _linhas_para_registros(linhas, org)
    else:
        raw = open(arq, "rb").read() if isinstance(arq, str) else arq.read()
        for enc in ("utf-8-sig", "latin-1"):
            try:
                txt = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        sep = ";" if txt.count(";") >= txt.count(",") else ","
        linhas = [[x.strip().strip('"') for x in l.split(sep)] for l in txt.splitlines()]
        org = os.path.basename(str(nome))
        largo = _largo_para_registros(linhas, org)
        recs = largo if largo else _linhas_para_registros(linhas, org)
    d = pd.DataFrame(recs).reindex(columns=COLUNAS)
    if len(d):
        meses = (d["fim"].dt.year - d["inicio"].dt.year) * 12 + d["fim"].dt.month - d["inicio"].dt.month
        d = d[(meses == 2) & d["emissora"].notna()]                  # só trimestres (3 meses)
        d["amostra_baixa"] = d["amostra_baixa"].fillna(False).astype(bool)
    return d.drop_duplicates(["emissora", "fim"], keep="last").sort_values(["emissora", "fim"]).reset_index(drop=True)


def mesclar(base, novo):
    """Junta a base atual com dados novos (o novo prevalece). Devolve (base_mesclada, novos, alterados)."""
    chave = ["emissora", "fim"]
    b = base.copy()
    b["fim"] = pd.to_datetime(b["fim"]); b["inicio"] = pd.to_datetime(b["inicio"])
    j = novo.merge(b[chave + ["opm"]], on=chave, how="left", suffixes=("", "_antes"))
    novos = j[j["opm_antes"].isna()][chave + ["opm"]]
    alterados = j[j["opm_antes"].notna() & (j["opm"].round(0) != j["opm_antes"].round(0))][chave + ["opm_antes", "opm"]]
    # o novo prevalece, mas colunas que ele não traz (ex.: share) ficam com o valor da base
    m = pd.concat([b, novo], ignore_index=True).groupby(chave, as_index=False, sort=False).last()
    return m.sort_values(chave).reset_index(drop=True), novos.reset_index(drop=True), alterados.reset_index(drop=True)
