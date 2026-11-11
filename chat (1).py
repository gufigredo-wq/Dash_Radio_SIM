"""Assistente do painel de rádio.

Dois modos, com a mesma interface (streamlit_app.py):
• IA (Gemini): `perguntar_ia(...)`. O modelo interpreta a pergunta e chama FERRAMENTAS de consulta; quem executa as
  consultas é o painel, nos dados internos (banco). O modelo recebe só o resultado de cada consulta, nunca a base inteira,
  e escreve a resposta com os números e uma leitura (insights). Se o modelo principal cair ou estourar o limite de
  requisições, entra o reserva (Flash-Lite). Chave em GEMINI_API_KEY (Secrets ou variável de ambiente).
• Respostas prontas: `responder(...)`, sem IA. É o que roda sem chave ou se a IA falhar.
"""
import html
import re
import unicodedata

import pandas as pd

PROPRIAS = ["Bahia FM", "GFM"]
NOMES = {"GFM": "GFM 90.1"}
MESES = "jan fev mar abr mai jun jul ago set out nov dez".split()
METRICAS = {"opm": "OPM# (ouvintes por minuto)", "sht": "SHT% (share)", "alcance": "ALCM# (alcance)", "tmed": "TMED# (tempo médio, min)"}

MODELO_PADRAO = "gemini-3.5-flash"
MODELO_RESERVA = "gemini-3.5-flash-lite"   # entra quando o principal cai ou estoura o limite de requisições
CODIGOS_RESERVA = {404, 408, 429, 500, 502, 503, 504}
PAUSA_PRINCIPAL = {429: 60, 503: 60, 500: 30, 502: 30, 504: 30, 408: 30, 404: 600}   # segundos usando só a reserva
_ESTADO = {"principal_pausado_ate": 0.0}  # vale para o servidor todo: o limite de requisições é da chave, não da sessão
MAX_PASSOS = 6
MAX_LINHAS = 80
HISTORICO = 8

SUGESTOES = ["Como foi o último banco?", "Ranking das emissoras", "Quem mais cresceu?",
             "O que é OPM e share?", "Como a projeção é feita?"]
SUGESTOES_IA = ["Destaques do último banco", "A GFM vai fechar o ano acima da previsão do BI?",
                "Em que zonas a Bahia FM cresceu?", "Compare a Bahia FM com 2025", "Quem mais ganhou share no ano?"]
BOAS_VINDAS = ("Olá! Sou o assistente do painel de rádio. Pergunte sobre a **audiência** (OPM#), o **share**, o "
               "**alcance** e o **perfil** da Bahia FM, da GFM e das concorrentes. Toque numa sugestão ou escreva do seu "
               "jeito, por exemplo: *como está a GFM?*")
APELIDOS = {"gfm": "GFM", "gfm 90 1": "GFM", "90 1": "GFM", "g fm": "GFM", "bahia fm": "Bahia FM", "bahiafm": "Bahia FM",
            "total": "Total emissoras", "mercado": "Total emissoras", "total fm": "Total FM", "total web": "Total web",
            "total radio": "Total rádio"}


# ---------------------------------------------------------------------------------------------- utilidades
def br(v, casas=0):
    return "–" if v is None or pd.isna(v) else f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sinal(v, casas=0):
    return "–" if v is None or pd.isna(v) else ("+" if v > 0 else "") + br(v, casas)


def rot_banco(fim):
    fim = pd.Timestamp(fim)
    ini = fim - pd.DateOffset(months=2)
    return f"{MESES[ini.month - 1]}–{MESES[fim.month - 1]}/{str(fim.year)[2:]}"


def nome(e):
    return NOMES.get(e, e)


def minutos(t):
    """'02:31:10' (ou '#02:31:10') -> 151,2 minutos."""
    if t is None or (isinstance(t, float) and pd.isna(t)):
        return None
    m = re.search(r"(\d+):(\d+):(\d+)", str(t))
    return round(int(m[1]) * 60 + int(m[2]) + int(m[3]) / 60, 1) if m else None


class Fonte:
    """Os dados que as ferramentas consultam: bancos (trimestres móveis), parâmetros oficiais, demográfico e a projeção."""

    def __init__(self, movel, par=None, demografico=None, projetar=None, demo=False):
        m = movel.copy()
        m["fim"] = pd.to_datetime(m["fim"])
        m["tmed_min"] = m["tmed"].map(minutos) if "tmed" in m else None
        self.movel = m
        self.par = par or {}
        self.dem = demografico if demografico is not None else pd.DataFrame()
        self.projetar = projetar               # função(emissora, patamar) -> dict, fornecida pelo painel
        self.demo = demo

    def emissoras(self):
        ult = self.movel.sort_values("fim").groupby("emissora")["opm"].last().sort_values(ascending=False)
        return list(ult.index)

    def serie(self, e, metrica="opm"):
        col = "tmed_min" if metrica == "tmed" else metrica
        s = self.movel[self.movel["emissora"] == e].set_index("fim")[col].dropna().sort_index()
        return s[~s.index.duplicated(keep="last")].astype(float)


def _e_total(e):
    return str(e).lower().startswith("total")


def _acha_emissora(t, fonte):
    nomes = {norm(e): e for e in fonte.emissoras()}
    for e in list(nomes.values()):
        base = norm(re.sub(r"\s+(FM|AM)$", "", e))
        nomes.setdefault(base, e)
    for chave in sorted(list(nomes) + list(APELIDOS), key=len, reverse=True):
        if len(chave) > 1 and re.search(rf"(?<![a-z0-9]){re.escape(chave)}(?![a-z0-9])", t):
            e = nomes.get(chave) or APELIDOS[chave]
            if e in fonte.emissoras():
                return e
    return None


def _resolve(nomes_, fonte):
    if not nomes_:
        return []
    if isinstance(nomes_, str):
        nomes_ = [nomes_]
    out = []
    for n in nomes_:
        e = _acha_emissora(norm(n), fonte)
        if e and e not in out:
            out.append(e)
    return out


def _fmt(metrica, v):
    return f"{br(v, 2)}%" if metrica == "sht" else f"{br(v, 1)} min" if metrica == "tmed" else br(v)


# ---------------------------------------------------------------------------------------------- núcleo (o mesmo do painel de TV)
def norm(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]+", " ", t)).strip()


def para_html(md):
    """Markdown simples das respostas (negrito, itálico, quebras e itens) -> HTML seguro."""
    t = html.escape(md)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    linhas = []
    for l in t.split("\n"):
        m = re.match(r"^(\s*)(?:[•\-*]|\d+[.)])\s+(.*)$", l)
        if re.match(r"^#{1,6}\s+", l):
            linhas.append(f'<b class="tt">{re.sub(r"^#{1,6}\s+", "", l)}</b>')
        elif m and not l.startswith("**"):
            num = re.match(r"^\s*(\d+[.)])", l)
            cls = "sub" if len(m[1]) >= 2 else "it"
            linhas.append(f'<span class="{cls}">{(num[1] + " ") if num else ""}{m[2]}</span>')
        elif l.startswith("  ") and l.strip():
            linhas.append(f'<span class="sub">{l.strip()}</span>')
        else:
            linhas.append(l)
    out = "<br>".join(linhas)
    for tag in ("</span>", "</b>"):
        out = out.replace(tag + "<br>", tag)
    return re.sub(r"(<br>){3,}", "<br><br>", out).strip()


def _r(v, casas=2):
    try:
        return None if v is None or pd.isna(v) else round(float(v), casas)
    except (TypeError, ValueError):
        return str(v)


def _periodo(txt, padrao):
    if not txt:
        return padrao
    try:
        return pd.Timestamp(str(txt)[:7] + "-01")
    except Exception:
        return padrao


def executar(nome, args, fonte):
    """Roda uma ferramenta com os argumentos do modelo. Nunca levanta exceção: erros voltam como {'erro': ...}."""
    if nome not in FERRAMENTAS:
        return {"erro": f"ferramenta desconhecida: {nome}"}
    func, _, props, _ = FERRAMENTAS[nome]
    limpos = {k: v for k, v in (args or {}).items() if k in props}
    try:
        out = func(fonte, **limpos)
    except Exception as ex:
        return {"erro": f"falha na consulta ({ex.__class__.__name__})"}
    if isinstance(out.get("linhas"), list) and len(out["linhas"]) > MAX_LINHAS:
        n = len(out["linhas"])
        out["linhas"] = out["linhas"][:MAX_LINHAS]
        out["aviso"] = f"mostrando {MAX_LINHAS} de {n} linhas; refine o período ou as séries"
    return out


def _declaracoes():
    from google.genai import types
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(name=n, description=d, parameters_json_schema={"type": "object", "properties": p, "required": r})
        for n, (_, d, p, r) in FERRAMENTAS.items()])]


def _texto(resp):
    partes = []
    for c in (resp.candidates or [])[:1]:
        for pt in (c.content.parts if c.content and c.content.parts else []):
            if getattr(pt, "text", None) and not getattr(pt, "thought", False):
                partes.append(pt.text)
    return "".join(partes).strip()


def _pergunta_um_modelo(cli, modelo, conteudos_ini, fonte):
    from google.genai import types
    conteudos = list(conteudos_ini)
    cfg = types.GenerateContentConfig(system_instruction=instrucoes(fonte), tools=_declaracoes(),
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    consultas = []
    for _ in range(MAX_PASSOS):
        resp = cli.models.generate_content(model=modelo, contents=conteudos, config=cfg)
        chamadas = resp.function_calls or []
        if not chamadas:
            txt = _texto(resp)
            return (txt or "Não consegui formular uma resposta. Tente perguntar de outro jeito."), consultas
        conteudos.append(resp.candidates[0].content)        # mantém a vez do modelo como veio (inclui assinaturas)
        partes = []
        for ch in chamadas:
            args = dict(ch.args or {})
            consultas.append({"ferramenta": ch.name, "args": args})
            partes.append(types.Part.from_function_response(name=ch.name, response=executar(ch.name, args, fonte)))
        conteudos.append(types.Content(role="user", parts=partes))
    # passou do limite de consultas: pede a resposta final sem ferramentas
    resp = cli.models.generate_content(model=modelo, contents=conteudos,
                                       config=types.GenerateContentConfig(system_instruction=instrucoes(fonte)))
    return (_texto(resp) or "A pergunta exigiu consultas demais. Tente algo mais específico."), consultas


def _justifica_reserva(ex):
    """Erro em que vale tentar o modelo reserva? Devolve o código (ou 0 para falhas de rede), ou None."""
    codigo = getattr(ex, "code", None)
    if isinstance(codigo, int):
        return codigo if codigo in CODIGOS_RESERVA else None
    nome = ex.__class__.__name__.lower()
    return 0 if ("timeout" in nome or "connect" in nome or "network" in nome) else None


def perguntar_ia(pergunta, fonte, chave, modelo=None, historico=(), cliente=None, reserva=None, agora=None):
    """Pergunta -> (resposta em markdown, consultas [{'ferramenta', 'args'}], modelo que respondeu).

    Tenta o modelo principal; se ele cair ou estourar o limite (429, 5xx, tempo esgotado, modelo inexistente), refaz a
    pergunta do zero no modelo reserva e deixa o principal em pausa por alguns segundos. Levanta exceção se os dois falharem."""
    import time
    from google import genai
    from google.genai import types
    agora = agora if agora is not None else time.time()
    cli = cliente or genai.Client(api_key=chave)
    principal, reserva = modelo or MODELO_PADRAO, reserva if reserva is not None else MODELO_RESERVA
    conteudos = [types.Content(role="user" if q == "eu" else "model", parts=[types.Part(text=t)])
                 for q, t in list(historico)[-HISTORICO:] if t]
    conteudos.append(types.Content(role="user", parts=[types.Part(text=pergunta)]))
    ordem = [principal] if not reserva or reserva == principal else (
        [reserva] if agora < _ESTADO["principal_pausado_ate"] else [principal, reserva])
    for k, mod in enumerate(ordem):
        try:
            txt, consultas = _pergunta_um_modelo(cli, mod, conteudos, fonte)
            return txt, consultas, mod
        except Exception as ex:
            codigo = _justifica_reserva(ex)
            ultimo = k == len(ordem) - 1
            if mod == principal and codigo is not None:
                _ESTADO["principal_pausado_ate"] = agora + PAUSA_PRINCIPAL.get(codigo, 30)
            if ultimo or codigo is None:
                raise
    raise RuntimeError("nenhum modelo disponível")


# ---------------------------------------------------------------------------------------------- ferramentas (consultas)
def _var(s, fim, meses):
    a = s.get(fim - pd.DateOffset(months=meses))
    return None if a is None or pd.isna(a) else s[fim] - a


def f_serie_bancos(fonte, emissoras=None, metrica="opm", inicio=None, fim=None, periodicidade="movel"):
    ems = _resolve(emissoras, fonte) or PROPRIAS
    met = metrica if metrica in METRICAS else "opm"
    fim_ = _periodo(fim, fonte.movel["fim"].max())
    ini_ = _periodo(inicio, fim_ - pd.DateOffset(months=11))
    linhas = []
    for e in ems:
        s = fonte.serie(e, met)
        if periodicidade == "ano":
            s = s[(s.index.month >= 3) & (s.index.year >= ini_.year) & (s.index.year <= fim_.year)]
            for ano, g in s.groupby(s.index.year):
                linhas.append({"emissora": e, "ano": int(ano), "media_dos_bancos_internos": _r(g.mean(), 2),
                               "bancos": len(g), "ano_completo": len(g) == 10})
            continue
        s = s[(s.index >= ini_) & (s.index <= fim_)]
        if periodicidade == "trimestre":
            s = s[s.index.month.isin([3, 6, 9, 12])]
        linhas += [{"emissora": e, "banco": rot_banco(f), "fim": f"{f:%Y-%m}", "valor": _r(v, 2)} for f, v in s.items()]
    per = f"{ini_.year} a {fim_.year}" if periodicidade == "ano" else f"{rot_banco(ini_)} a {rot_banco(fim_)}"
    return {"metrica": METRICAS[met], "periodo": per, "periodicidade": periodicidade, "linhas": linhas}


def f_ranking(fonte, metrica="opm", banco=None, criterio="valor", ordem="desc", limite=10, incluir_totais=False):
    met = metrica if metrica in METRICAS else "opm"
    alvo = _periodo(banco, fonte.movel["fim"].max())
    linhas = []
    for e in fonte.emissoras():
        if _e_total(e) and not incluir_totais:
            continue
        s = fonte.serie(e, met)
        if alvo not in s.index:
            continue
        linhas.append({"emissora": e, "valor": _r(s[alvo], 2), "var_banco_anterior": _r(_var(s, alvo, 1), 2),
                       "var_ano_anterior": _r(_var(s, alvo, 12), 2)})
    chave = criterio if criterio in ("valor", "var_banco_anterior", "var_ano_anterior") else "valor"
    if chave == "valor":
        for k, l in enumerate(sorted(linhas, key=lambda l: -(l["valor"] or 0)), 1):
            l["posicao"] = k
    linhas = [l for l in linhas if l[chave] is not None]
    linhas.sort(key=lambda l: l[chave], reverse=(ordem != "asc"))
    return {"metrica": METRICAS[met], "banco": rot_banco(alvo), "criterio": chave,
            "linhas": linhas[:max(1, min(int(limite or 10), 30))]}


def f_comparar_periodos(fonte, emissoras=None, metrica="opm", a_inicio=None, a_fim=None, b_inicio=None, b_fim=None):
    ems = _resolve(emissoras, fonte) or PROPRIAS
    met = metrica if metrica in METRICAS else "opm"
    ult = fonte.movel["fim"].max()
    pa = (_periodo(a_inicio, pd.Timestamp(ult.year, 3, 1)), _periodo(a_fim, ult))
    pb = (_periodo(b_inicio, pa[0] - pd.DateOffset(years=1)), _periodo(b_fim, pa[1] - pd.DateOffset(years=1)))
    linhas = []
    for e in ems:
        s = fonte.serie(e, met)
        va, vb = s[(s.index >= pa[0]) & (s.index <= pa[1])], s[(s.index >= pb[0]) & (s.index <= pb[1])]
        ma, mb = (va.mean() if len(va) else None), (vb.mean() if len(vb) else None)
        linhas.append({"emissora": e, "media_a": _r(ma, 2), "bancos_a": len(va), "media_b": _r(mb, 2), "bancos_b": len(vb),
                       "diferenca": _r(ma - mb if ma is not None and mb is not None else None, 2),
                       "variacao_pct": _r((ma / mb - 1) * 100 if ma and mb else None, 1)})
    return {"metrica": METRICAS[met], "periodo_a": f"{rot_banco(pa[0])} a {rot_banco(pa[1])}",
            "periodo_b": f"{rot_banco(pb[0])} a {rot_banco(pb[1])}", "observacao": "médias simples dos bancos", "linhas": linhas}


def f_demografico(fonte, emissoras=None, tipo="Zona", metrica=None, banco=None, comparar_com=None, faixa="05-05"):
    d = fonte.dem
    if d is None or d.empty:
        return {"erro": "o painel não tem dados demográficos carregados"}
    d = d.copy()
    d["fim"] = pd.to_datetime(d["fim"])
    ems = _resolve(emissoras, fonte) or PROPRIAS
    tipo = tipo if tipo in ("Zona", "Classe", "Idade", "Sexo") else "Zona"
    met = metrica or ("OPM#" if tipo == "Zona" else "PS%")
    d = d[(d["tipo"] == tipo) & (d["metrica"] == met) & (d["faixa"] == faixa) & d["emissora"].isin(ems)]
    if d.empty:
        return {"erro": f"sem dados de {tipo} / {met} para essas emissoras", "metricas_validas": "Zona: OPM#, AFIN%, ALCM# · Classe/Idade/Sexo: PS%"}
    alvo = _periodo(banco, d["fim"].max())
    ref = _periodo(comparar_com, alvo - pd.DateOffset(years=1))
    a = d[d["fim"] == alvo].set_index(["emissora", "segmento"])["valor"]
    b = d[d["fim"] == ref].set_index(["emissora", "segmento"])["valor"]
    linhas = [{"emissora": e, "segmento": s, "valor": _r(v, 2), "valor_comparacao": _r(b.get((e, s)), 2),
               "diferenca": _r(v - b[(e, s)] if (e, s) in b.index else None, 2)} for (e, s), v in a.items()]
    return {"tipo": tipo, "metrica": met, "banco": rot_banco(alvo), "comparado_com": rot_banco(ref) if len(b) else "sem dado",
            "bancos_disponiveis": f"{rot_banco(d['fim'].min())} a {rot_banco(d['fim'].max())}", "linhas": linhas}


def f_projecao(fonte, emissora="GFM", patamar=None):
    e = (_resolve(emissora, fonte) or ["GFM"])[0]
    if e not in PROPRIAS:
        return {"erro": "a projeção existe só para a Bahia FM e a GFM"}
    if fonte.projetar is None:
        return {"erro": "projeção indisponível neste ambiente"}
    return fonte.projetar(e, patamar)


def f_oficiais(fonte, emissora="GFM"):
    e = (_resolve(emissora, fonte) or ["GFM"])[0]
    chave = {"GFM": "GFM", "Bahia FM": "Bahia FM"}.get(e)
    if not chave:
        return {"erro": "números oficiais existem só para a Bahia FM e a GFM"}
    return {"emissora": e, "oficiais": fonte.par.get("oficial", {}).get(chave, {}),
            "previsao_bi": fonte.par.get("previsao_bi", {}).get(chave, {}),
            "legenda": "AAAA = ano; 1SAA/2SAA = 1º/2º semestre; previsão BI: S1, S2 e ano (método CAGR)"}


_EMS_TXT = "Nomes das emissoras ou totais de mercado, como no catálogo (ex.: 'GFM', 'Bahia FM', 'Total emissoras')."
_MET = {"type": "string", "enum": list(METRICAS)}
FERRAMENTAS = {
    "serie_bancos": (f_serie_bancos, "Valores por banco (trimestre móvel) de emissoras num período. periodicidade: 'movel' (todos "
                     "os bancos), 'trimestre' (só jan–mar, abr–jun, jul–set, out–dez) ou 'ano' (média dos bancos internos, regra "
                     "do número oficial).", {
        "emissoras": {"type": "array", "items": {"type": "string"}, "description": _EMS_TXT}, "metrica": _MET,
        "inicio": {"type": "string", "description": "Mês final do 1º banco, AAAA-MM (jul–set/26 = 2026-09)."},
        "fim": {"type": "string", "description": "Mês final do último banco, AAAA-MM (padrão: o mais recente)."},
        "periodicidade": {"type": "string", "enum": ["movel", "trimestre", "ano"]}}, ["emissoras"]),
    "ranking": (f_ranking, "Ranking das emissoras num banco por valor, variação vs banco anterior ou vs mesmo banco do ano anterior.", {
        "metrica": _MET, "banco": {"type": "string", "description": "Mês final do banco AAAA-MM (padrão: o mais recente)."},
        "criterio": {"type": "string", "enum": ["valor", "var_banco_anterior", "var_ano_anterior"]},
        "ordem": {"type": "string", "enum": ["desc", "asc"]}, "limite": {"type": "integer"},
        "incluir_totais": {"type": "boolean"}}, ["metrica"]),
    "comparar_periodos": (f_comparar_periodos, "Compara a média dos bancos de dois períodos (padrão: bancos do ano até o mais recente "
                          "vs os mesmos bancos do ano anterior).", {
        "emissoras": {"type": "array", "items": {"type": "string"}, "description": _EMS_TXT}, "metrica": _MET,
        "a_inicio": {"type": "string", "description": "AAAA-MM"}, "a_fim": {"type": "string", "description": "AAAA-MM"},
        "b_inicio": {"type": "string", "description": "AAAA-MM"}, "b_fim": {"type": "string", "description": "AAAA-MM"}},
        ["emissoras"]),
    "demografico": (f_demografico, "Audiência por zona de Salvador (OPM#, AFIN% = afinidade, ALCM#) ou perfil (PS% = participação "
                    "por classe, idade, sexo) num banco, com comparação a outro banco (padrão: mesmo banco do ano anterior).", {
        "emissoras": {"type": "array", "items": {"type": "string"}, "description": _EMS_TXT},
        "tipo": {"type": "string", "enum": ["Zona", "Classe", "Idade", "Sexo"]},
        "metrica": {"type": "string", "enum": ["OPM#", "AFIN%", "ALCM#", "PS%"]},
        "banco": {"type": "string", "description": "AAAA-MM"}, "comparar_com": {"type": "string", "description": "AAAA-MM"}},
        ["emissoras", "tipo"]),
    "projecao": (f_projecao, "Projeção do fechamento do ano (OPM#) da Bahia FM ou da GFM: próximos trimestres, fechamento com faixa "
                 "de 80%, chance de ficar acima de um patamar (padrão: previsão do BI) e média necessária.", {
        "emissora": {"type": "string", "enum": PROPRIAS},
        "patamar": {"type": "number", "description": "Valor anual de referência em OPM# (opcional)."}}, ["emissora"]),
    "numeros_oficiais": (f_oficiais, "Números oficiais anuais e semestrais e a previsão do BI da Bahia FM ou da GFM.", {
        "emissora": {"type": "string", "enum": PROPRIAS}}, ["emissora"]),
}


def instrucoes(fonte):
    m = fonte.movel
    ems = [e for e in fonte.emissoras()]
    ini, fim = m["fim"].min(), m["fim"].max()
    conc_ini = m.loc[~m["emissora"].isin(PROPRIAS), "fim"].min()
    d = fonte.dem
    dem = f"{rot_banco(d['fim'].min())} a {rot_banco(d['fim'].max())}" if d is not None and len(d) else "sem dados"
    return f"""Você é o assistente do Painel de Audiência de Rádio da Rede Bahia (emissoras próprias: Bahia FM e GFM 90.1).
Responda em português do Brasil, de forma curta e direta, para analistas de pesquisa, comercial e programação.

DADOS (consulte SEMPRE pelas ferramentas; nunca invente números):
- Kantar IBOPE EasyMedia4 (Rádio Recall), Grande Salvador, 05h–05h, todos os dias.
- Cada BANCO é um trimestre móvel de 3 meses (ex.: jul–set/26), um por mês; nas ferramentas, um banco é indicado pelo mês
  final (jul–set/26 = 2026-09). Trimestres fechados: jan–mar, abr–jun, jul–set, out–dez.
- Bancos disponíveis: {rot_banco(ini)} a {rot_banco(fim)} (Bahia FM e GFM); concorrentes e totais desde {rot_banco(conc_ini) if pd.notna(conc_ini) else '–'}.
- Emissoras e totais: {", ".join(ems)}.
- Demográfico (zonas e perfil): {dem}.
{"- ATENÇÃO: estes são DADOS FICTÍCIOS de demonstração; as concorrentes têm nomes inventados." if fonte.demo else ""}

CONCEITOS: OPM# = ouvintes por minuto (média de ouvintes a cada minuto); SHT% = share, fatia da emissora no total de
ouvintes de rádio; ALCM# = alcance, pessoas diferentes que ouviram no período; TMED# = tempo médio de audição (minutos);
AFIN% = afinidade com a zona (100 = igual à população; acima de 100, a zona pesa mais no público da emissora);
PS% = participação de cada segmento (classe, idade, sexo) no público. O número oficial do ano é a média dos 10 bancos internos
do ano (jan–mar a out–dez). A previsão do BI usa o método CAGR.

COMO RESPONDER:
1. Use as ferramentas para buscar exatamente o que a pergunta pede (pode chamar mais de uma).
2. Comece pela resposta, com os números principais (formato brasileiro: 31.540 ouvintes; 22,4%; banco como jul–set/26).
3. Depois, em 1 a 3 itens curtos, uma LEITURA com insights apoiados nos dados: tendência, posição no ranking, comparação com
   o ano anterior, distância para a previsão do BI, zonas e perfis que puxam o resultado. Não especule causas que os dados
   não mostram; se sugerir uma hipótese, diga que é hipótese.
4. Sem tabelas e sem títulos grandes (o quadro é estreito); use itens com "- " e **negrito** nos números-chave.
5. Se o dado não existe nas ferramentas, diga que o painel não tem essa informação.
6. Fora do tema audiência de rádio/painel, recuse em uma frase e diga o que você consegue responder."""


def descreve_consulta(c):
    nomes = {"serie_bancos": "Série por banco", "ranking": "Ranking", "comparar_periodos": "Comparação de períodos",
             "demografico": "Demográfico", "projecao": "Projeção do ano", "numeros_oficiais": "Números oficiais"}
    a = c.get("args") or {}
    det = " · ".join(f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in a.items() if v not in (None, "", []))
    return f"{nomes.get(c.get('ferramenta'), c.get('ferramenta'))}" + (f" ({det})" if det else "")


# ---------------------------------------------------------------------------------------------- respostas prontas (sem IA)
CONCEITOS = ("• **OPM#**: ouvintes por minuto, a média de pessoas ouvindo a emissora a cada minuto.\n"
             "• **SHT% (share)**: fatia da emissora entre todos os ouvintes de rádio.\n"
             "• **ALCM# (alcance)**: pessoas diferentes que ouviram a emissora no período.\n"
             "• **TMED#**: tempo médio que cada ouvinte passa com a emissora.\n"
             "Cada **banco** é um trimestre móvel de 3 meses, como jul–set/26.")
PROJECAO = ("A projeção trabalha com os **trimestres fechados** da Bahia FM e da GFM:\n"
            "• vários métodos (nível local, AR(1), Holt, ETS, CAGR do BI e a combinação deles), validados em projeções do passado;\n"
            "• o **nowcast** usa o banco móvel mais recente como leitura antecipada do trimestre em curso;\n"
            "• milhares de cenários simulados dão o fechamento do ano, a faixa de 80% e a chance de ficar acima de um patamar.\n"
            "Os detalhes estão na aba *Projeções e cenários*.")
AJUDA = ("Posso responder, por exemplo:\n• *como foi o último banco?*\n• *ranking das emissoras*\n• *quem mais cresceu / caiu?*\n"
         "• *como está a GFM?*\n• *o que é OPM e share?*")
NAO_SEI = ("Ainda não sei responder isso sem a IA. Entendo perguntas sobre o último banco, ranking, crescimento ou queda e cada "
           "emissora. Experimente uma das sugestões.")


def r_emissora(fonte, e):
    s, sh = fonte.serie(e, "opm"), fonte.serie(e, "sht")
    if s.empty:
        return f"Não encontrei dados de **{nome(e)}**."
    f = s.index.max()
    rk = f_ranking(fonte, "opm", f"{f:%Y-%m}", limite=30)["linhas"]
    pos = next((l["posicao"] for l in rk if l["emissora"] == e), None)
    t = (f"**{nome(e)}** em {rot_banco(f)}: **{br(s[f])}** ouvintes por minuto "
         f"({sinal(_var(s, f, 1))} vs banco anterior, {sinal(_var(s, f, 12))} vs ano anterior)")
    if f in sh.index:
        t += f"\n• share **{br(sh[f], 2)}%** ({sinal(_var(sh, f, 12), 2)} p.p. vs ano anterior)"
    if pos and not _e_total(e):
        t += f"\n• **{pos}º lugar** no ranking de OPM#"
    return t


def r_resumo(fonte):
    return "Resumo do último banco:\n" + "\n".join(
        "• " + r_emissora(fonte, e).replace("\n• ", " · ") for e in PROPRIAS if e in fonte.emissoras())


def r_ranking(fonte):
    r = f_ranking(fonte, "opm", limite=5)
    return (f"**Ranking de OPM#** em {r['banco']}:\n" +
            "\n".join(f"• {l['posicao']}º **{nome(l['emissora'])}**: {br(l['valor'])}" for l in r["linhas"]))


def r_variacao(fonte, crescer=True):
    r = f_ranking(fonte, "opm", criterio="var_ano_anterior", ordem="desc" if crescer else "asc", limite=5)
    ls = [l for l in r["linhas"] if (l["var_ano_anterior"] > 0) == crescer]
    if not ls:
        return "Nenhuma emissora " + ("cresceu" if crescer else "caiu") + " em OPM# vs o mesmo banco do ano anterior."
    return (f"Emissoras que **mais {'cresceram' if crescer else 'caíram'}** em OPM# ({r['banco']} vs ano anterior):\n" +
            "\n".join(f"• **{nome(l['emissora'])}**: {sinal(l['var_ano_anterior'])} ({br(l['valor'])})" for l in ls))


def responder(texto, fonte):
    """Pergunta em texto livre -> resposta pronta em markdown simples, sem IA."""
    t = norm(texto)
    if not t:
        return AJUDA
    if re.search(r"\bo que (e|significa|sao)\b|\bsignifica\b|\bdiferenca\b", t) and re.search(r"opm|share|sht|alcance|tmed|banco", t):
        return CONCEITOS
    if re.search(r"\b(como|metodo|metodologia)\b.*\b(projec|calcul|model|feita|funciona)", t):
        return PROJECAO
    e = _acha_emissora(t, fonte)
    if e and not re.search(r"\b(cresc|subi|cai|queda|perd|ranking|lider)", t):
        return r_emissora(fonte, e)
    if re.search(r"\b(cresc\w*|subi\w*|ganh\w*)\b", t):
        return r_variacao(fonte, True)
    if re.search(r"\b(cai\w*|queda|perd\w*|pior\w*)\b", t):
        return r_variacao(fonte, False)
    if re.search(r"\b(ranking|lider\w*|maior\w*|top|primeir\w*)\b", t):
        return r_ranking(fonte)
    if re.search(r"\b(ultimo banco|resumo|como foi|como esta|como estamos|geral)\b", t):
        return r_resumo(fonte)
    if re.search(r"\b(oi|ola|bom dia|boa tarde|boa noite|e ai|opa)\b", t):
        return "Olá! " + AJUDA
    if re.search(r"\b(ajuda|help|o que voce|como usar|pode fazer)\b", t):
        return AJUDA
    if re.search(r"\b(obrigad\w*|valeu|show|otimo|perfeito)\b", t):
        return "Por nada! Se precisar de mais alguma coisa, é só perguntar."
    return NAO_SEI
