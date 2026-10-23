import glob
import json
import os
import re
import shutil
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

os.chdir(os.path.dirname(os.path.abspath(__file__)))   # caminhos relativos à pasta do app (Colab e Streamlit Cloud)
import modelos as M  # noqa: E402

st.set_page_config(page_title="Painel de Audiência · Rádio", page_icon="📻", layout="wide",
                   initial_sidebar_state="collapsed")

# ============================================================ identidade visual (mesma do painel de homicídios)
AZUL, LARANJA, AQUA, AMARELO, MAGENTA, VERDE, VIOLETA, VERMELHO = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
# modo claro / escuro: escolhido no botão do cabeçalho (o navegador lembra a escolha). O tema do Streamlit fica sempre
# claro (config.toml) e o modo escuro é desenhado pelo próprio painel, então funciona igual em qualquer lugar.
if "tema_escuro" not in st.session_state:
    st.session_state["tema_escuro"] = st.query_params.get("tema") == "escuro"
ESCURO = bool(st.session_state["tema_escuro"])


def _troca_tema():
    novo = not st.session_state.get("tema_escuro", False)
    st.session_state["tema_escuro"] = novo
    st.query_params["tema"] = "escuro" if novo else "claro"     # o link da página guarda o modo
_PAL_CLARO = dict(FUNDO="#f2f4f9", CARTAO="#ffffff", BORDA="#e3e7f0", BORDA_IN="#d6d4d1", CAMPO="#fafaf9", LINHA="#f0efec",
                REALCE="#f3f6fd", TOPO="#001564", AVISO_BG="#fff8e6", AVISO_BD="#f3dca0", SOMBRA=".06", SOMBRA2=".10",
                SOBE="#0a7a0a", DESCE="#b42318", TINTA="#1f1f1e", TINTA2="#52514e", CINZA="#8a8984", CINZA_CLARO="#c9c8c3",
                GRADE="#ecebe8", EIXO="#d6d4d1", ZERO="#b9b7b2", FAIXA="rgba(138,137,132,.16)", HACHURA="rgba(31,31,30,.55)",
                SEQ=["#eef5fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
                DIV=["#b42318", "#f6d5d1", "#ffffff", "#cde2fb", "#1c5cab"])
_PAL_ESCURO = dict(FUNDO="#0b1120", CARTAO="#131c31", BORDA="#22304d", BORDA_IN="#2b3a5c", CAMPO="#18223a", LINHA="#1c2740",
                   REALCE="#1a2a4a", TOPO="#001564", AVISO_BG="#2e2610", AVISO_BD="#5c4a1a", SOMBRA=".35", SOMBRA2=".5",
                   SOBE="#4cd08a", DESCE="#ff7a6b", TINTA="#e8edf7", TINTA2="#aab6cf", CINZA="#7f8aa3", CINZA_CLARO="#3a4664",
                   GRADE="#1f2a42", EIXO="#2e3b58", ZERO="#4a5878", FAIXA="rgba(160,175,210,.14)", HACHURA="rgba(0,0,0,.5)",
                   SEQ=["#142038", "#1b3563", "#23508f", "#2f6fc0", "#5a98e6", "#a9cdf7"],
                   DIV=["#ff6b5e", "#5a2a2e", "#131c31", "#24476f", "#6aa6f0"])
_PAL = _PAL_ESCURO if ESCURO else _PAL_CLARO
globals().update({k: v for k, v in _PAL.items() if k not in ("SEQ", "DIV")})
SEQ = [[x, c] for x, c in zip([0, .15, .35, .55, .75, 1], _PAL["SEQ"])]
COR = {"Bahia FM": AZUL, "GFM": LARANJA}
NOME = {"Bahia FM": "Bahia FM", "GFM": "GFM 90.1"}
FONTE_TXT = "Inter, Segoe UI, Helvetica Neue, Arial, sans-serif"
MESES = "jan fev mar abr mai jun jul ago set out nov dez".split()
TRIM_NOME = {1: "jan–mar", 2: "abr–jun", 3: "jul–set", 4: "out–dez"}

st.markdown(f"""<style>
html, body, [class*="css"], .stApp {{font-family:{FONTE_TXT};}}
.stApp {{background:{FUNDO};}}
header[data-testid="stHeader"] {{background:transparent; height:0;}}
.block-container {{padding:0 1.6rem 2rem; max-width:1500px;}}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {{display:none;}}
.bi-top {{background:{TOPO}; color:#fff; margin:0 -1.6rem 0; padding:14px 1.6rem 12px; display:flex;
          align-items:center; justify-content:space-between; border-bottom:3px solid {AZUL};}}
.bi-top h1 {{font-size:1.15rem; font-weight:600; margin:0; padding:0; color:#fff; letter-spacing:.2px;}}
.bi-top .sub {{font-size:.78rem; color:#c3c2b7; margin-top:2px;}}
.bi-top .meta {{font-size:.74rem; color:#c3c2b7; text-align:right; line-height:1.5;}}
.bi-top .meta b {{color:#fff; font-weight:600;}}
.stTabs [data-baseweb="tab-list"] {{gap:0; background:{CARTAO}; margin:0 -1.6rem 14px; padding:0 1.6rem;
                                    border-bottom:1px solid #e1dfdd;}}
.stTabs [data-baseweb="tab"] {{height:42px; padding:0 18px; font-size:.86rem; color:{TINTA2}; border-radius:0;}}
.stTabs [aria-selected="true"] {{color:{TINTA}; font-weight:600;}}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{display:none;}}
/* abas fixas: a aba aberta ganha um sublinhado azul ([role=tab] = versões novas do Streamlit) */
.stTabs [role="tablist"] {{gap:0 !important;}}
.stTabs [role="tab"] {{padding:0 16px !important; white-space:nowrap;}}
.stTabs [role="tab"][aria-selected="true"] {{box-shadow:inset 0 -3px 0 {AZUL};}}
.stTabs .react-aria-SelectionIndicator {{display:none;}}
/* notas metodológicas recolhidas no rodapé */
.st-key-notas [data-testid="stExpander"] details {{border:0; background:transparent;}}
.st-key-notas [data-testid="stExpander"] summary {{padding:4px 0; font-size:.74rem; color:{CINZA};}}
.st-key-notas [data-testid="stExpander"] summary p {{font-size:.74rem; color:{CINZA};}}
.st-key-notas [data-testid="stExpanderDetails"] {{font-size:.82rem; color:{TINTA2};}}
[class*="st-key-card"] {{background:{CARTAO}; border:1px solid {BORDA} !important; border-radius:4px !important;
    box-shadow:0 1px 2px rgba(0,0,0,{SOMBRA}); transition:box-shadow .15s; padding:12px 14px 6px !important;}}
[class*="st-key-card"]:hover {{box-shadow:0 4px 12px rgba(0,0,0,{SOMBRA2});}}
[class*="st-key-card"] [data-testid="stTextInputRootElement"], [class*="st-key-card"] [data-testid="stNumberInputContainer"] {{border:1px solid {BORDA_IN} !important; border-radius:6px; background:{CAMPO} !important;}}
[class*="st-key-card"] [data-testid="stTextInputRootElement"] input, [class*="st-key-card"] [data-testid="stNumberInputContainer"] input {{background:{CAMPO} !important; color:{TINTA};}}
[data-testid="stToolbar"], [data-testid="stDecoration"] {{display:none !important;}}
.rk {{width:100%; border-collapse:collapse; font-size:.8rem; font-variant-numeric:tabular-nums;}}
.rk th {{text-align:left; font-size:.68rem; text-transform:uppercase; letter-spacing:.5px; color:{TINTA2};
         font-weight:600; padding:4px 6px; border-bottom:1px solid {BORDA};}}
.rk td {{padding:6px 6px; border-bottom:1px solid {LINHA}; color:{TINTA}; white-space:nowrap;}}
.rk td.n {{text-align:right;}} .rk tr:hover td {{background:{REALCE};}}
.rk tr.hl td {{background:{REALCE}; font-weight:600;}}
.rk .bar {{height:8px; border-radius:0 4px 4px 0; min-width:2px;}}
.vt {{font-size:.88rem; font-weight:600; color:{TINTA}; margin:0 0 1px;}}
.vs {{font-size:.74rem; color:{CINZA}; margin:0 0 4px;}}
[data-testid="stWidgetLabel"] p {{font-size:.74rem !important; font-weight:600; color:{TINTA2}; text-transform:uppercase; letter-spacing:.5px;}}
.kpis {{display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin:2px 0 12px;}}
.kpi {{background:{CARTAO}; border:1px solid {BORDA}; border-radius:4px; padding:10px 14px 9px; border-top:3px solid var(--c);
       box-shadow:0 1px 2px rgba(0,0,0,{SOMBRA});}}
.kpi .t {{font-size:.7rem; text-transform:uppercase; letter-spacing:.5px; color:{TINTA2}; font-weight:600; line-height:1.35;}}
.kpi .v {{font-size:1.65rem; font-weight:600; color:{TINTA}; line-height:1.25; margin-top:2px; font-variant-numeric:tabular-nums;}}
.kpi .d {{font-size:.74rem; color:{CINZA}; line-height:1.4;}}
.kpi .up {{color:{SOBE}; font-weight:600;}} .kpi .down {{color:{DESCE}; font-weight:600;}}
.xf {{font-size:.78rem; color:{TINTA2}; background:{CARTAO}; border:1px dashed {AZUL}; border-radius:4px; padding:6px 10px;}}
.xf b {{color:{AZUL};}}
.aviso {{font-size:.8rem; color:{TINTA2}; background:{AVISO_BG}; border:1px solid {AVISO_BD}; border-radius:4px; padding:7px 11px; margin-bottom:10px;}}
.metodo {{font-size:.78rem; color:{TINTA2}; background:{CARTAO}; border:1px solid {BORDA}; border-left:3px solid {AZUL};
          border-radius:4px; padding:7px 11px; margin:-2px 0 12px;}}
.rodape {{font-size:.72rem; color:{CINZA}; margin-top:6px; line-height:1.5;}}
@media (max-width:700px) {{ .bi-top {{flex-direction:column; align-items:flex-start; gap:6px;}} .bi-top .meta {{text-align:left;}} }}
</style>""", unsafe_allow_html=True)


LOGO_B64 = "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"

st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
[data-testid="stElementContainer"]:has(style), [data-testid="stElementContainer"]:has(iframe[height="1"]),
[data-testid="stElementContainer"]:has(iframe[data-testid="stIFrame"]) {{display:none;}}
@keyframes subir {{ from {{opacity:0; transform:translateY(10px);}} to {{opacity:1; transform:none;}} }}
@keyframes brilho {{ 0% {{background-position:-200% 0;}} 100% {{background-position:200% 0;}} }}
@keyframes pulso {{ 0%,100% {{opacity:.55;}} 50% {{opacity:1;}} }}
.stApp {{background:
    radial-gradient(1200px 500px at 85% -10%, rgba(42,120,214,.10), transparent 60%),
    radial-gradient(900px 400px at -10% 10%, rgba(0,21,100,.07), transparent 60%), {FUNDO};}}
/* cabeçalho Rede Bahia */
.bi-top {{position:relative; overflow:hidden; border-bottom:0; padding:14px 1.6rem 14px;
    background:linear-gradient(110deg, #001564 0%, #062a8c 55%, #0b3fae 100%);
    box-shadow:0 8px 24px rgba(0,21,100,.18);}}
.bi-top::before {{content:""; position:absolute; inset:0; pointer-events:none;
    background:linear-gradient(105deg, transparent 35%, rgba(255,255,255,.10) 50%, transparent 65%);
    background-size:200% 100%; animation:brilho 7s ease-in-out infinite;}}
.bi-top::after {{content:""; position:absolute; left:0; right:0; bottom:0; height:3px;
    background:linear-gradient(90deg, #00c2ff, #2a78d6, #7b5cff, #00c2ff); background-size:200% 100%;
    animation:brilho 6s linear infinite;}}
.bi-top .marca {{display:flex; align-items:center; gap:14px; position:relative; z-index:1;}}
.bi-top .logo {{height:44px; width:auto; display:block; filter:drop-shadow(0 2px 6px rgba(0,0,0,.25));}}
.bi-top .sep {{width:1px; height:36px; background:rgba(255,255,255,.25);}}
.bi-top h1 {{font-weight:700; letter-spacing:.1px;}}
.bi-top .sub, .bi-top .meta {{color:#b9c6ea; position:relative; z-index:1;}}
/* abas com efeito vidro */
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {{background:rgba(255,255,255,.72) !important;
    backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); border-bottom:1px solid {BORDA} !important;}}
.stTabs [role="tab"] {{border-radius:8px 8px 0 0;}}
.stTabs [role="tab"]:hover {{background:rgba(42,120,214,.06);}}
.stTabs [role="tab"][aria-selected="true"] {{box-shadow:inset 0 -3px 0 #2a78d6;}}
/* cartões */
[class*="st-key-card"] {{border-radius:14px !important; border:1px solid rgba(16,24,64,.07) !important; position:relative;
    box-shadow:0 1px 2px rgba(16,24,64,.04), 0 8px 24px rgba(16,24,64,.05);
    transition:box-shadow .25s ease, transform .25s ease, border-color .25s ease;
    animation:subir .55s cubic-bezier(.2,.7,.2,1) both;}}
[class*="st-key-card"]:hover {{transform:translateY(-2px); border-color:rgba(42,120,214,.25) !important;
    box-shadow:0 2px 4px rgba(16,24,64,.05), 0 14px 32px rgba(16,24,64,.09);}}
.vt {{font-size:.9rem; font-weight:600; letter-spacing:.1px;}}
/* KPIs */
.kpi {{border-radius:12px; border:1px solid rgba(16,24,64,.07); border-top:0; position:relative; overflow:hidden;
    box-shadow:0 1px 2px rgba(16,24,64,.04), 0 6px 18px rgba(16,24,64,.05);
    transition:transform .25s ease, box-shadow .25s ease; animation:subir .5s cubic-bezier(.2,.7,.2,1) both;}}
.kpi::before {{content:""; position:absolute; left:0; right:0; top:0; height:3px;
    background:linear-gradient(90deg, var(--c), color-mix(in srgb, var(--c) 35%, #ffffff));}}
.kpi:hover {{transform:translateY(-3px); box-shadow:0 4px 10px rgba(16,24,64,.06), 0 16px 32px rgba(16,24,64,.10);}}
.kpi .v {{font-weight:700; letter-spacing:-.4px;}}
.kpis .kpi:nth-child(1) {{animation-delay:.02s;}} .kpis .kpi:nth-child(2) {{animation-delay:.06s;}}
.kpis .kpi:nth-child(3) {{animation-delay:.10s;}} .kpis .kpi:nth-child(4) {{animation-delay:.14s;}}
.kpis .kpi:nth-child(5) {{animation-delay:.18s;}} .kpis .kpi:nth-child(6) {{animation-delay:.22s;}}
.kpis .kpi:nth-child(7) {{animation-delay:.26s;}} .kpis .kpi:nth-child(8) {{animation-delay:.30s;}}
/* campos e botões */
[data-baseweb="select"] > div, [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{border-radius:10px !important;
    transition:box-shadow .2s, border-color .2s;}}
[data-baseweb="select"] > div:hover {{box-shadow:0 0 0 3px rgba(42,120,214,.10);}}
.stButton button, .stDownloadButton button {{border-radius:10px; transition:transform .15s, box-shadow .2s, background .2s;}}
.stButton button:hover, .stDownloadButton button:hover {{transform:translateY(-1px); box-shadow:0 6px 14px rgba(42,120,214,.18);}}
[data-testid="stSegmentedControl"] button {{transition:all .2s;}}
/* botão de expandir no canto dos cartões */
.st-key-exp_calor, .st-key-exp_curva {{position:absolute !important; top:8px; right:10px; width:auto !important; z-index:3;}}
.st-key-exp_calor button, .st-key-exp_curva button {{min-height:0; height:30px; width:30px; padding:0; border-radius:9px;
    border:1px solid rgba(16,24,64,.10); background:rgba(255,255,255,.9); color:#2a78d6;}}
.st-key-exp_calor button:hover, .st-key-exp_curva button:hover {{background:#2a78d6; color:#fff; transform:scale(1.06);}}
/* janela expandida */
[data-testid="stDialog"] [role="dialog"] {{border-radius:18px; box-shadow:0 30px 80px rgba(0,21,100,.25);}}
.mini {{display:grid; grid-template-columns:repeat(auto-fit, minmax(150px,1fr)); gap:8px; margin:4px 0 10px;}}
.mini div {{background:linear-gradient(180deg,#f7f9ff,#eef3fd); border:1px solid rgba(42,120,214,.12); border-radius:10px;
    padding:8px 11px; font-size:.72rem; color:{TINTA2}; animation:subir .45s both;}}
.mini b {{display:block; font-size:1.05rem; color:{TINTA}; margin-top:2px; font-variant-numeric:tabular-nums;}}
.vivo {{display:inline-block; width:7px; height:7px; border-radius:50%; background:#00c2ff; margin-right:6px;
    box-shadow:0 0 0 0 rgba(0,194,255,.6); animation:pulso 1.8s ease-in-out infinite; vertical-align:middle;}}
/* ---------- animações dos gráficos ---------- */
@keyframes barY {{ from {{transform:scaleY(0);}} to {{transform:scaleY(1);}} }}
@keyframes barX {{ from {{transform:scaleX(0);}} to {{transform:scaleX(1);}} }}
@keyframes desenha {{ from {{stroke-dashoffset:4000;}} to {{stroke-dashoffset:0;}} }}
@keyframes surge {{ from {{opacity:0;}} to {{opacity:1;}} }}
@keyframes surgeZoom {{ from {{opacity:0; transform:scale(.97);}} to {{opacity:1; transform:none;}} }}
@keyframes larg {{ from {{width:0;}} }}
.js-plotly-plot .barlayer .point path {{transform-box:fill-box; transform-origin:50% 100%;
    animation:barY .75s cubic-bezier(.2,.85,.25,1) backwards; animation-delay:var(--d, 0ms);}}
.st-key-v_barras .js-plotly-plot .barlayer .point path, .st-key-v_cmp .js-plotly-plot .barlayer .point path {{
    transform-origin:0% 50%; animation-name:barX;}}
.js-plotly-plot .barlayer .point text, .js-plotly-plot .barlayer .bartext {{animation:surge .45s ease backwards;
    animation-delay:calc(var(--d, 0ms) + 420ms);}}
.js-plotly-plot .scatterlayer .js-line {{stroke-dasharray:4000; animation:desenha 1.4s cubic-bezier(.45,.05,.25,1) backwards;}}
.js-plotly-plot .scatterlayer .js-fill {{animation:surge .9s ease backwards;}}
.js-plotly-plot .scatterlayer .points path, .js-plotly-plot .scatterlayer .textpoint {{animation:surge .5s ease backwards; animation-delay:.75s;}}
.js-plotly-plot .heatmaplayer image {{animation:surgeZoom .8s cubic-bezier(.2,.8,.2,1) backwards; transform-box:fill-box; transform-origin:center;}}
.js-plotly-plot .heatmaplayer text {{animation:surge .5s ease backwards; animation-delay:.5s;}}
/* o gráfico cresce suavemente quando muda de altura (ex.: mais bancos no período) */
.js-plotly-plot .svg-container {{transition:height .6s cubic-bezier(.2,.8,.2,1); overflow:hidden;}}
/* tabelas: linhas entram em sequência e as barrinhas crescem */
.rk tr {{animation:subir .45s cubic-bezier(.2,.8,.2,1) backwards;}}
.rk tr:nth-child(2) {{animation-delay:.03s;}} .rk tr:nth-child(3) {{animation-delay:.06s;}} .rk tr:nth-child(4) {{animation-delay:.09s;}}
.rk tr:nth-child(5) {{animation-delay:.12s;}} .rk tr:nth-child(6) {{animation-delay:.15s;}} .rk tr:nth-child(7) {{animation-delay:.18s;}}
.rk tr:nth-child(8) {{animation-delay:.21s;}} .rk tr:nth-child(9) {{animation-delay:.24s;}} .rk tr:nth-child(10) {{animation-delay:.27s;}}
.rk tr:nth-child(n+11) {{animation-delay:.3s;}}
.rk .bar {{animation:larg .9s cubic-bezier(.2,.8,.2,1) backwards; animation-delay:.25s;}}
.kpi .v {{transition:color .3s;}}
.kpi .v.contando {{color:#2a78d6;}}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{animation:none !important; transition:none !important;}} }}
/* o cabeçalho do próprio Streamlit (invisível, mas no Streamlit Cloud fica por cima do canto superior direito)
   não pode capturar os cliques: o nosso cabeçalho fica acima dele */
header[data-testid="stHeader"] {{pointer-events:none !important; height:0 !important; min-height:0 !important; background:transparent !important;}}
header[data-testid="stHeader"] * {{pointer-events:none !important;}}
[data-testid="stMain"], [data-testid="stAppViewContainer"] {{overflow-x:hidden;}}
/* cabeçalho (faixa azul com logo, datas e botão do modo escuro) */
.st-key-topo {{z-index:1000100 !important; position:relative; overflow:hidden; width:100vw !important; max-width:none !important;
    margin:0 0 0 calc(50% - 50vw) !important; box-sizing:border-box; gap:0;
    padding:12px max(1.6rem, calc(50vw - 750px + 1.6rem)) 13px !important;
    background:linear-gradient(110deg, #001564 0%, #062a8c 55%, #0b3fae 100%); box-shadow:0 8px 24px rgba(0,21,100,.18);}}
.st-key-topo::before {{content:""; position:absolute; inset:0; pointer-events:none;
    background:linear-gradient(105deg, transparent 35%, rgba(255,255,255,.10) 50%, transparent 65%);
    background-size:200% 100%; animation:brilho 7s ease-in-out infinite;}}
.st-key-topo::after {{content:""; position:absolute; left:0; right:0; bottom:0; height:3px;
    background:linear-gradient(90deg, #00c2ff, #2a78d6, #7b5cff, #00c2ff); background-size:200% 100%; animation:brilho 6s linear infinite;}}
.st-key-topo [data-testid="stHorizontalBlock"] {{position:relative; z-index:1;}}
.st-key-topo .marca {{display:flex; align-items:center; gap:14px;}}
.st-key-topo .logo {{height:44px; width:auto; display:block; filter:drop-shadow(0 2px 6px rgba(0,0,0,.25));}}
.st-key-topo .sep {{width:1px; height:36px; background:rgba(255,255,255,.25);}}
.st-key-topo h1 {{font-size:1.15rem; font-weight:700; margin:0; padding:0; color:#fff !important; letter-spacing:.1px;}}
.st-key-topo .sub {{font-size:.78rem; color:#b9c6ea !important; margin-top:2px;}}
.st-key-topo .meta {{font-size:.74rem; color:#b9c6ea !important; text-align:right; line-height:1.5;}}
.st-key-topo .meta b {{color:#fff !important; font-weight:600;}}
.st-key-topo [data-testid="stMarkdownContainer"] p {{margin:0;}}
.demo {{margin:10px 0 2px; padding:8px 14px; border-radius:10px; font-size:.8rem; color:#6b4e00; border:1px solid #f0c24b;
    background:repeating-linear-gradient(135deg, #fff6d6 0 14px, #fff0bf 14px 28px);}}
.demo b {{color:#4a3600;}}
.st-key-tema_btn, .st-key-pdf_btn {{display:flex; justify-content:flex-end;}}
.st-key-pdf_btn button {{background:rgba(255,255,255,.08) !important; color:#dbe4ff !important; border:1px solid rgba(255,255,255,.3) !important;
    border-radius:999px !important; padding:5px 15px !important; min-height:0 !important; white-space:nowrap; box-shadow:none !important;}}
.st-key-pdf_btn button:hover {{background:rgba(255,255,255,.18) !important; border-color:rgba(255,255,255,.55) !important;}}
.st-key-pdf_btn button p {{color:#dbe4ff !important; font-size:.78rem;}}
.st-key-tema_btn button {{background:rgba(255,255,255,.08) !important; color:#dbe4ff !important; border:1px solid rgba(255,255,255,.3) !important;
    border-radius:999px !important; padding:5px 15px !important; min-height:0 !important; font-size:.78rem; white-space:nowrap;
    box-shadow:none !important;}}
.st-key-tema_btn button:hover {{background:rgba(255,255,255,.18) !important; border-color:rgba(255,255,255,.55) !important;}}
.st-key-tema_btn button p {{color:#dbe4ff !important; font-size:.78rem;}}
@media (max-width:700px) {{ .st-key-topo .meta {{text-align:left;}} }}
.trocando-tema .stApp, .trocando-tema [class*="st-key-card"], .trocando-tema .kpi {{transition:background-color .5s ease, border-color .5s ease, color .5s ease !important;}}
.bi-top .lado {{display:flex; align-items:center; gap:18px; position:relative; z-index:1;}}
.tema-btn {{font:500 .76rem {FONTE_TXT}; color:#dbe4ff; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.28);
    border-radius:999px; padding:6px 14px; cursor:pointer; white-space:nowrap; transition:background .2s, border-color .2s, transform .15s;}}
.tema-btn:hover {{background:rgba(255,255,255,.18); border-color:rgba(255,255,255,.5); transform:translateY(-1px);}}
@media (max-width:700px) {{ .bi-top .lado {{width:100%; justify-content:space-between;}} }}
""" + (f"""
/* ---------- modo escuro ---------- */
.stApp {{background:radial-gradient(1200px 520px at 85% -10%, rgba(42,120,214,.16), transparent 60%),
    radial-gradient(900px 420px at -10% 10%, rgba(0,60,200,.12), transparent 60%), {FUNDO} !important;}}
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {{background:rgba(19,28,49,.78) !important;}}
.stTabs [role="tab"]:hover {{background:rgba(90,152,230,.10);}}
.stTabs [role="tab"][aria-selected="true"] {{box-shadow:inset 0 -3px 0 #5a98e6 !important;}}
[class*="st-key-card"] {{border-color:rgba(255,255,255,.06) !important; box-shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 28px rgba(0,0,0,.28);}}
[class*="st-key-card"]:hover {{border-color:rgba(90,152,230,.35) !important; box-shadow:0 2px 6px rgba(0,0,0,.45), 0 16px 36px rgba(0,0,0,.4);}}
.kpi {{border-color:rgba(255,255,255,.06); box-shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 22px rgba(0,0,0,.3);}}
.kpi::before {{background:linear-gradient(90deg, var(--c), color-mix(in srgb, var(--c) 30%, {CARTAO}));}}
.kpi .v.contando {{color:#6aa6f0;}}
.mini div {{background:linear-gradient(180deg,#17223b,#131c31); border-color:rgba(90,152,230,.18);}}
.st-key-exp_calor button, .st-key-exp_curva button {{background:rgba(19,28,49,.9); border-color:rgba(255,255,255,.14); color:#8fb8f0;}}
.st-key-exp_calor button:hover, .st-key-exp_curva button:hover {{background:#2a78d6; color:#fff;}}
[data-testid="stDialog"] [role="dialog"] {{box-shadow:0 30px 80px rgba(0,0,0,.6);}}
.stButton button:hover, .stDownloadButton button:hover {{box-shadow:0 6px 16px rgba(42,120,214,.30);}}
.xf {{border-color:#3d6fb8;}}
/* gráficos mais vivos no fundo escuro: leve brilho nas linhas e cores um pouco mais saturadas */
.js-plotly-plot .scatterlayer .js-line {{filter:drop-shadow(0 0 3px rgba(255,255,255,.22));}}
.js-plotly-plot .barlayer .point path {{filter:saturate(1.1) brightness(1.06);}}
.js-plotly-plot .scatterlayer .points path {{filter:drop-shadow(0 0 2px rgba(255,255,255,.3));}}
/* componentes do próprio Streamlit (o tema dele fica claro; aqui eles ganham as cores escuras) */
.stApp, .stApp p, .stApp li, .stApp label, .stMarkdown, [data-testid="stMarkdownContainer"],
[data-testid="stCaptionContainer"], [data-testid="stExpander"] summary, .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{color:{TINTA};}}
[data-testid="stWidgetLabel"] p {{color:{TINTA2} !important;}}
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="input"] > div, [data-baseweb="base-input"],
.stTextInput input, .stNumberInput input, [data-baseweb="textarea"] textarea {{background:{CAMPO} !important; color:{TINTA} !important;
    border-color:{BORDA_IN} !important;}}
[data-baseweb="select"] input, [data-baseweb="select"] span, [data-baseweb="select"] div {{color:{TINTA};}}
[data-baseweb="select"] svg, [data-testid="stNumberInput"] svg {{fill:{TINTA2}; color:{TINTA2};}}
[data-baseweb="popover"] > div, [data-baseweb="popover"] ul, [data-baseweb="menu"], [role="listbox"] {{background:{CARTAO} !important; color:{TINTA} !important;}}
[data-baseweb="popover"] li, [role="option"] {{color:{TINTA} !important; background:transparent;}}
[data-baseweb="popover"] li:hover, [role="option"]:hover, [role="option"][aria-selected="true"], [role="option"][data-focused] {{background:{REALCE} !important;}}
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"],
[data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"] {{background:{CAMPO} !important;
    border-color:{BORDA_IN} !important; color:{TINTA};}}
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input, [data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {{background:transparent !important; color:{TINTA} !important;}}
[data-testid="stSelectbox"] [role="group"] *, [data-testid="stNumberInputContainer"] * {{color:{TINTA};}}
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg {{color:{TINTA2}; fill:{TINTA2};}}
[data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"] {{background:{CARTAO} !important;
    color:{TINTA} !important; border:1px solid {BORDA}; box-shadow:0 12px 32px rgba(0,0,0,.45);}}
[data-testid="stSelectboxVirtualDropdown"] *, [data-testid="stMultiSelectDropdown"] * {{color:{TINTA};}}
[data-testid="stNumberInput"] button {{background:{CAMPO}; color:{TINTA2}; border-color:{BORDA_IN};}}
.stButton button[kind="secondary"], .stDownloadButton button, [data-testid="stBaseButton-secondary"] {{background:{CAMPO}; color:{TINTA};
    border-color:{BORDA_IN};}}
[data-testid="stButtonGroup"] button {{background:{CAMPO}; color:{TINTA2}; border-color:{BORDA_IN};}}
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[kind*="Active"] {{background:rgba(42,120,214,.22); color:#cfe2ff; border-color:#3d6fb8;}}
[data-testid="stExpander"] details {{background:transparent; border-color:{BORDA};}}
[data-testid="stDialog"] [role="dialog"] {{background:{CARTAO} !important; color:{TINTA};}}
[data-testid="stDialog"] [role="dialog"] button[aria-label="Close"] svg {{fill:{TINTA2};}}
[data-testid="stFileUploaderDropzone"] {{background:{CAMPO}; border-color:{BORDA_IN}; color:{TINTA2};}}
[data-testid="stFileUploaderDropzone"] span, [data-testid="stFileUploaderDropzone"] small {{color:{TINTA2};}}
[data-testid="stAlert"] {{color:{TINTA};}}
[data-testid="stAlert"] p {{color:{TINTA} !important;}}
[data-testid="stTooltipIcon"] svg, [data-testid="stTooltipHoverTarget"] svg {{color:{CINZA}; stroke:{CINZA};}}
[data-testid="stSliderTickBar"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{color:{CINZA};}}
/* tabelas do Streamlit (desenhadas em canvas): inversão de cores para combinar com o fundo escuro */
[data-testid="stDataFrame"] canvas, [data-testid="stDataFrameResizable"] canvas {{filter:invert(.9) hue-rotate(180deg) brightness(1.05);}}
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {{border-radius:10px; overflow:hidden;}}
""" if ESCURO else "") + """</style>""", unsafe_allow_html=True)


# ============================================================ dados
def _assinatura_dados():
    """Muda sempre que um arquivo de dados ou o código de leitura muda: invalida o cache do carregamento."""
    arqs = ["radio_movel.csv", "parametros.json", "modelos.py"] + glob.glob(os.path.join("dados", "*"))
    return tuple(sorted((a, os.path.getmtime(a), os.path.getsize(a)) for a in arqs if os.path.exists(a)))


def chave_banco(fim, emissora="*"):
    """Chave de um banco na lista de excluídos: 'AAAA-MM|Emissora' ('*' = todas as emissoras daquele banco)."""
    return f"{pd.Timestamp(fim):%Y-%m}|{emissora}"


def aplicar_exclusoes(d, excluidos):
    if not excluidos or d.empty:
        return d
    ex = set(excluidos)
    mes = pd.to_datetime(d["fim"]).dt.strftime("%Y-%m")
    fora = (mes + "|*").isin(ex) | (mes + "|" + d["emissora"].astype(str)).isin(ex)
    return d[~fora].reset_index(drop=True)


def arquivos_fixos():
    return sorted(a for a in glob.glob(os.path.join("dados", "*.xlsx")) + glob.glob(os.path.join("dados", "*.csv"))
                  if not os.path.basename(a).startswith("~$"))


@st.cache_data
def carregar(versao=None, assinatura=None):
    """Base = planilhas do EasyMedia em dados/ + radio_movel.csv (envios feitos pela aba Atualizar dados, que prevalecem).
    Bancos excluídos pelo painel (lista "excluidos" em parametros.json) ficam fora do que o painel mostra."""
    d = pd.DataFrame(columns=M.COLUNAS)
    for arq in arquivos_fixos():
        d = M.mesclar(d, M.ler_arquivo(arq))[0]
    if os.path.exists("radio_movel.csv"):
        d = M.mesclar(d, pd.read_csv("radio_movel.csv", parse_dates=["inicio", "fim"]))[0]
    par = json.load(open("parametros.json", encoding="utf-8")) if os.path.exists("parametros.json") else {}
    d = d.reindex(columns=list(dict.fromkeys(list(d.columns) + M.COLUNAS)))      # garante as colunas novas (share, amostra…)
    d["amostra_baixa"] = d["amostra_baixa"].fillna(False).astype(bool)
    for c in ("opm", "sht", "alcance"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    # o painel usa a base sem os excluídos; a base completa é o que se grava (para poder restaurar depois)
    return aplicar_exclusoes(d, par.get("excluidos", [])), par, d


def segredo(chave, padrao=None):
    """Lê st.secrets sem quebrar quando não há arquivo de segredos (Colab)."""
    try:
        return st.secrets.get(chave, padrao)
    except Exception:
        return padrao


def github_salvar(caminho, conteudo, msg):
    """Grava um arquivo no repositório do GitHub (Streamlit Cloud). Precisa de [github] token/repo/branch em secrets."""
    cfg = segredo("github")
    if not cfg or not cfg.get("token") or not cfg.get("repo"):
        return None
    import base64
    import requests
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{caminho}"
    h = {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/vnd.github+json"}
    ramo = cfg.get("branch", "main")
    try:
        r = requests.get(url, headers=h, params={"ref": ramo}, timeout=20)
        corpo = {"message": msg, "content": base64.b64encode(conteudo).decode(), "branch": ramo}
        if r.status_code == 200:
            corpo["sha"] = r.json()["sha"]
        r = requests.put(url, headers=h, json=corpo, timeout=30)
        return r.status_code in (200, 201)
    except Exception:
        return False


MOVEL, PAR, BASE = carregar("v3-bancos", _assinatura_dados())
EMISSORAS = [e for e in ["Bahia FM", "GFM"] if e in MOVEL["emissora"].unique()]
# concorrência: todas as outras emissoras da base, da maior para a menor audiência no último banco
_ult = MOVEL.sort_values("fim").groupby("emissora")["opm"].last()
# totais de mercado (Total emissoras, Total FM, Total web): aparecem na seleção e nos gráficos,
# mas não são emissoras: ficam fora do ranking, das contagens de concorrência e da projeção
TOTAIS = [t for t in dict.fromkeys(M.TOTAIS.values()) if t in _ult.index]
CONCORRENTES = [e for e in _ult.sort_values(ascending=False).index if e not in EMISSORAS and e not in TOTAIS]
TODAS = sorted(EMISSORAS + CONCORRENTES, key=lambda e: -_ult.get(e, 0)) + TOTAIS
EXTERNAS = CONCORRENTES + TOTAIS          # séries que só existem a partir de 2024 (ranking e painel do EasyMedia)
INICIO_CONC = MOVEL.loc[MOVEL["emissora"].isin(EXTERNAS), "fim"].min() if EXTERNAS else None
# cores: as 4 do slide "Evolução trimestral" (GFM, Bahia FM, Piatã, Itapoan) + Salvador FM do trilho de audiência;
# as demais emissoras têm cores próprias, escolhidas para ficarem distintas entre si (distância OKLab ≥ 9 entre quaisquer duas)
COR_FIXA = {"GFM": "#384d74", "Bahia FM": "#ff3399", "Piatã FM": "#7030a0", "Itapoan FM": "#92d050", "Salvador FM": "#00b0f0",
            "A Tarde FM": "#e0a100", "Sociedade FM": "#c0504d", "Baiana FM": "#ff7f0e", "Metrópole FM": "#008080",
            "Educadora FM": "#7b4a12", "Rede Aleluia": "#2ca02c", "NovaBrasil FM": "#4b6cf0", "Band FM": "#d4a5e8",
            "Antena 1": "#2b2b2b", "88.3 FM": "#7a1f3d", "Metropolitana FM": "#5ec4b6", "Sociedade AM": "#f7b6a8",
            "Popular FM": "#9e9a2a", "Total emissoras": "#3b3f4a", "Total FM": "#5b7a99", "Total web": "#00a3c4",
            "Total rádio": "#a0522d"}
if ESCURO:      # tons escuros demais para o fundo escuro: mesma família, mais claros
    COR_FIXA.update({"GFM": "#7b9ad8", "Antena 1": "#9aa3b5", "Total emissoras": "#a3acc0", "88.3 FM": "#c2557f",
                     "Educadora FM": "#c48a4a", "Piatã FM": "#9b5fd0"})
_RESERVA = ["#1f77b4", "#e377c2", "#8c564b", "#bcbd22", "#17becf", "#aec7e8"]   # emissoras novas que vierem em planilhas futuras
COR = {}
for e in TODAS:
    COR[e] = COR_FIXA.get(e) or _RESERVA[len([x for x in COR if x not in COR_FIXA]) % len(_RESERVA)]


def _vivo(hexcor):
    """Versão mais viva da cor para o fundo escuro: mais clara (luminosidade ≥ 58%) e mais saturada, sem virar neon."""
    import colorsys
    r, g, b = [int(hexcor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = min(max(l, .58), .72) if not (.42 <= h <= .53) else min(max(l, .46), .6)   # verde-água/ciano: menos claro
    s = max(s, min(.88, s * 1.2 + .05)) if s > .08 else s
    return "#%02x%02x%02x" % tuple(round(x * 255) for x in colorsys.hls_to_rgb(h, l, s))



if ESCURO:      # no fundo escuro, todas as séries ficam mais vivas
    COR = {e: _vivo(c) for e, c in COR.items()}
    AZUL, LARANJA = _vivo(AZUL), _vivo(LARANJA)


def _texto_sobre(hexcor):
    """Branco ou tinta escura, o que tiver mais contraste com a cor da barra."""
    r, g, b = [int(hexcor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lum = sum(w * (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for w, c in zip((0.2126, 0.7152, 0.0722), (r, g, b)))
    return "#ffffff" if (1.05 / (lum + 0.05)) >= ((lum + 0.05) / 0.0625) else "#1f1f1e"


COR_TEXTO = {e: _texto_sobre(COR[e]) for e in TODAS}


def _cmap(cores):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("painel", cores)
NOME = {e: e for e in TODAS}
NOME.update({"GFM": "GFM 90.1", "Bahia FM": "Bahia FM"})
OFICIAL = PAR.get("oficial", {})
PREV_BI = PAR.get("previsao_bi", {})
Q = {e: M.fechados(MOVEL, e) for e in EMISSORAS}
K_ANO = M.fator_conversao(Q, OFICIAL, "ano")
K_SEM = M.fator_conversao(Q, OFICIAL, "semestre")


def br(v, casas=0):
    if v is None or pd.isna(v):
        return "–"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v, casas=1, sinal=False):
    if v is None or pd.isna(v):
        return "–"
    return ("+" if sinal and v > 0 else "") + br(v * 100, casas) + "%"


def fmt_p(p):
    if p < .05:
        return "<5%"
    if p > .95:
        return ">95%"
    return f"≈{int(5 * round(20 * p))}%"


def freq(p):
    if p < .05:
        return "menos de 1 em 20"
    if p > .95:
        return "mais de 19 em 20"
    if p <= .5:
        return f"1 em {max(2, round(1 / p))}"
    n = max(2, round(1 / (1 - p)))
    return f"{n - 1} em {n}"


def rot_movel(fim):
    fim = pd.Timestamp(fim)
    return f"{MESES[(fim.month - 3) % 12]}–{MESES[fim.month - 1]}/{str(fim.year)[2:]}"


def rot_ini(m):
    """Rótulo do trimestre móvel pelo mês inicial (como nas abas da planilha)."""
    return f"{MESES[m - 1]}–{MESES[(m + 1) % 12]}"


def rot_trim(t):
    t = pd.Period(t, "Q")
    return f"{t.year}T{t.quarter}"


def layout(fig, h=290, legenda=False):
    fig.update_layout(template="none", height=h, margin=dict(l=6, r=10, t=6 if not legenda else 30, b=6),
                      paper_bgcolor=CARTAO, plot_bgcolor=CARTAO, separators=",.",
                      font=dict(family=FONTE_TXT, size=12, color=TINTA2), showlegend=legenda,
                      legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", font=dict(size=11), title_text=""),
                      hoverlabel=dict(bgcolor=CARTAO, bordercolor=BORDA, font=dict(family=FONTE_TXT, size=12, color=TINTA)),
                      bargap=0.28, barcornerradius=4, clickmode="event+select", dragmode=False,
                      transition=dict(duration=450, easing="cubic-in-out"))
    fig.update_xaxes(showgrid=False, linecolor=EIXO, ticks="", tickfont=dict(size=11), automargin=True, title_text="")
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, linecolor="rgba(0,0,0,0)", tickfont=dict(size=11), automargin=True,
                     title_text="", tickformat=",.0f")
    return fig


CFG = {"displayModeBar": False}
_n_card = [0]


def cartao(titulo, sub="", nota=False):
    """Cartão com título e, se houver, um subtítulo cinza curto (o essencial para ler o quadro)."""
    _n_card[0] += 1
    st.session_state["_card_titulo"], st.session_state["_card_sub"] = _sem_tags(titulo), _sem_tags(sub)
    c = st.container(border=True, key=f"card{_n_card[0]}")
    c.markdown(f'<div class="vt">{titulo}</div>' + (f'<div class="vs">{sub}</div>' if sub else ""), unsafe_allow_html=True)
    return c


def _sem_tags(t):
    import re
    return re.sub(r"<[^>]+>", "", str(t)).replace('"', "")


def kpis(lista):
    if isinstance(st.session_state.get("_kpis_run"), list):
        st.session_state["_kpis_run"].append({"aba": st.session_state.get("_aba_atual", ""),
                                              "cartoes": [(_sem_tags(t), _sem_tags(v), _sem_tags(d), c) for t, v, d, c in lista]})
    st.markdown('<div class="kpis">' + "".join(
        f'<div class="kpi" style="--c:{c}"><div class="t" title="{t}">{t}</div><div class="v">{v}</div>'
        f'<div class="d" title="{_sem_tags(dsc)}">{dsc}</div></div>' for t, v, dsc, c in lista) + "</div>", unsafe_allow_html=True)


def delta_html(atual, anterior):
    if anterior is None or pd.isna(anterior) or not anterior or atual is None or pd.isna(atual):
        return ""
    v = atual / anterior - 1
    cls, seta = ("up", "▲") if v > 0 else ("down", "▼")
    return f'<span class="{cls}">{seta} {pct(abs(v))}</span>'


def selecao(chave, dims):
    ev = st.session_state.get(chave)
    try:
        pts = ev["selection"]["points"] if ev else []
    except (KeyError, TypeError):
        pts = []
    out = []
    for p in pts:
        cd = p.get("customdata")
        if cd is None:
            continue
        cd = cd if isinstance(cd, (list, tuple)) else [cd]
        out.append({d: (int(v) if d == "ano" else v) for d, v in zip(dims, cd) if v is not None})
    return out


def media_bancos(e):
    """Média dos bancos internos de cada ano (jan–mar ... out–dez): é a regra do número oficial anual.
    size = nº de bancos disponíveis (10 = ano completo)."""
    s = M.movel_serie(MOVEL, e)
    s = s[s.index.month >= 3]
    return pd.DataFrame({"ano": s.index.year, "v": s.values}).groupby("ano")["v"].agg(["mean", "size"])


def rot_banco(fim):
    """Rótulo no padrão do slide: JUN/2026 A AGO/2026."""
    fim = pd.Timestamp(fim); ini = fim - pd.DateOffset(months=2)
    return f"{MESES[ini.month - 1].upper()}/{ini.year} A {MESES[fim.month - 1].upper()}/{fim.year}"


def media_anual(q):
    """Média dos trimestres fechados por ano (n = nº de trimestres disponíveis)."""
    d = pd.DataFrame({"ano": q.index.year, "v": q.values})
    return d.groupby("ano")["v"].agg(["mean", "size"])


# ============================================================ barra de título
ult_mov = MOVEL["fim"].max()
ult_fech = max(q.index.max() for q in Q.values())
with st.container(key="topo"):
    _c = st.columns([5.6, 2.5, 1.15, 1.15], vertical_alignment="center", gap="small")
    _c[0].markdown(f"""<div class="marca"><img class="logo" alt="Rede Bahia" src="data:image/png;base64,{LOGO_B64}">
<div class="sep"></div><div><h1>Painel de Audiência · Rádio</h1>
<div class="sub">Bahia FM e GFM 90.1 · OPM# 05h–05h · todos os dias · Grande Salvador · Kantar IBOPE EasyMedia4 (Rádio Recall)</div></div></div>""",
                   unsafe_allow_html=True)
    _c[1].markdown(f"""<div class="meta"><span class="vivo"></span>Série <b>{rot_movel(MOVEL['fim'].min())} → {rot_movel(ult_mov)}</b><br>
Último trimestre fechado: <b>{rot_trim(ult_fech)} ({TRIM_NOME[ult_fech.quarter]})</b></div>""", unsafe_allow_html=True)
    _c[2].button("📄 Exportar PDF", key="pdf_btn", on_click=lambda: st.session_state.update(_abrir_pdf=True))
    _c[3].button("☀️ Modo claro" if ESCURO else "🌙 Modo escuro", key="tema_btn", on_click=_troca_tema)
if PAR.get("demo"):
    st.markdown('<div class="demo">🧪 <b>Ambiente de demonstração.</b> Todos os números deste painel são <b>fictícios</b>, gerados '
                'só para testar e apresentar as funcionalidades. Eles não representam a audiência real e as concorrentes têm nomes '
                'inventados.</div>', unsafe_allow_html=True)
if getattr(st, "_plotly_versao", 0) < 2:
    # (1) no modo escuro, os gráficos usam só as cores do painel (sem o tema claro do Streamlit por cima);
    # (2) cada gráfico desenhado fica registrado na sessão, com o título do cartão, para o relatório em PDF.
    # Tudo é lido da sessão de cada pessoa, então uma não afeta a outra.
    st._plotly_original = getattr(st, "_plotly_original", st.plotly_chart)

    def _plotly_tema(fig, *a, **k):
        ss_ = st.session_state
        if ss_.get("tema_escuro"):
            k.setdefault("theme", None)
        chave = str(k.get("key", ""))
        if chave and not chave.startswith("dlg_") and isinstance(ss_.get("_graf_run"), list):
            ss_["_graf_run"].append({"chave": chave, "titulo": ss_.get("_card_titulo", ""), "sub": ss_.get("_card_sub", ""),
                                     "aba": ss_.get("_aba_atual", ""), "fig": fig})
        return st._plotly_original(fig, *a, **k)
    st.plotly_chart = _plotly_tema
    st._plotly_versao = 2
st.session_state["_graf_run"] = []
st.session_state["_kpis_run"] = []

# ---- visualizações da tela inicial: as padrão já vêm marcadas; as extras entram pelo rodapé (🧩 Visualizações)
VIS_PADRAO = {"evolucao": "Evolução por período (barras)", "anual": "Média anual", "ranking": "Ranking do período",
              "curva": "Curva do ano", "calor": "Mapa de calor", "comparativo": "Comparativo em linhas"}
VIS_EXTRA = {"share": "Share (SHT%) por banco", "alcance": "Alcance (ALCM#) por banco", "tmed": "Tempo médio de audição (TMED#)",
             "yoy": "Variação vs mesmo banco do ano anterior", "posicao": "Posição no ranking ao longo do tempo",
             "participacao": "Participação entre as emissoras selecionadas", "sazonal": "Sazonalidade por banco (caixas)"}
VIS_TODAS = {**VIS_PADRAO, **VIS_EXTRA}
if "vis_sel" not in st.session_state:
    _q = st.query_params.get("vis")
    st.session_state["vis_sel"] = [v for v in _q.split(",") if v in VIS_TODAS] if _q else list(VIS_PADRAO)


def mostra(codigo):
    return codigo in st.session_state.get("vis_sel", list(VIS_PADRAO))


def _guarda_vis():
    sel = st.session_state.get("vis_w") or []
    st.session_state["vis_sel"] = list(sel)
    if sorted(sel) == sorted(VIS_PADRAO):
        st.query_params.pop("vis", None)
    else:
        st.query_params["vis"] = ",".join(sel)      # recebe "escuro"/"claro" do botão (escondido)

_EFEITOS_JS = r"""
(function () {
  const P = window, D = document;
  if (P.__efeitosPainel) return;
  P.__efeitosPainel = true;
  // 0) modo claro/escuro: o botão é do próprio Streamlit; aqui o navegador só lembra a última escolha
  D.addEventListener("click", ev => {
    const b = ev.target.closest(".st-key-tema_btn button");
    if (b) { try { P.localStorage.setItem("painelTema", b.textContent.includes("escuro") ? "escuro" : "claro"); } catch (e) {} }
  }, true);
  (function lembra(n) {
    const b = D.querySelector(".st-key-tema_btn button");
    if (!b) { if (n < 60) setTimeout(() => lembra(n + 1), 200); return; }
    let salvo = null;
    try { salvo = P.localStorage.getItem("painelTema"); } catch (e) { return; }
    const atual = b.textContent.includes("escuro") ? "claro" : "escuro";
    if (salvo && salvo !== atual && !/[?&]tema=/.test(P.location.search)) b.click();
  })(0);
  // 1) barras novas entram em sequência: atraso por série e por posição
  function escalona(raiz) {
    raiz.querySelectorAll(".js-plotly-plot .barlayer .trace").forEach((tr, k) => {
      tr.querySelectorAll(".point").forEach((g, i) => {
        if (!g.dataset.anim) { g.dataset.anim = 1; g.style.setProperty("--d", Math.min(k * 110 + i * 22, 900) + "ms"); }
      });
    });
  }
  // 2) números dos cartões contam até o valor (e de um valor ao outro quando o filtro muda)
  const ultimo = {};
  function parse(t) {
    const m = t.trim().match(/^([+\-−]?)([\d.]+)(?:,(\d+))?(.*)$/);
    if (!m || /\d/.test(m[4])) return null;       // datas e textos como 30/09/2026 não contam
    const casas = m[3] ? m[3].length : 0;
    const v = parseFloat(m[2].replace(/\./g, "") + (m[3] ? "." + m[3] : ""));
    return {sinal: m[1], v: (m[1] === "-" || m[1] === "−") ? -v : v, casas, suf: m[4], mil: m[2].includes(".") || v >= 1000};
  }
  function fmt(x, n) {
    const neg = x < 0, a = Math.abs(x);
    let [i, d] = a.toFixed(n.casas).split(".");
    if (n.mil || a >= 1000) i = i.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const s = neg ? (n.sinal === "−" ? "−" : "-") : (n.sinal === "+" ? "+" : "");
    return s + i + (d ? "," + d : "") + n.suf;
  }
  function conta(el) {
    if (el.dataset.contado === el.textContent) return;
    const alvo = el.textContent, n = parse(alvo);
    const chave = (el.closest(".kpi")?.querySelector(".t")?.textContent || "") + "|" + n?.suf;
    if (!n) { el.dataset.contado = alvo; return; }
    const de = ultimo[chave] !== undefined ? ultimo[chave] : 0;
    ultimo[chave] = n.v;
    if (de === n.v) { el.dataset.contado = alvo; return; }
    const t0 = performance.now(), dur = 900;
    el.classList.add("contando");
    function passo(t) {
      const f = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - f, 3);
      el.textContent = f < 1 ? fmt(de + (n.v - de) * e, n) : alvo;
      el.dataset.contado = el.textContent;
      if (f < 1) requestAnimationFrame(passo); else el.classList.remove("contando");
    }
    requestAnimationFrame(passo);
  }
  function varre(raiz) {
    escalona(raiz);
    raiz.querySelectorAll(".kpi .v").forEach(conta);
  }
  new MutationObserver(ms => {
    for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) varre(n.closest ? (n.closest(".js-plotly-plot") || n) : n);
    ms.forEach(m => { if (m.type === "characterData" && m.target.parentElement?.matches(".kpi .v")) conta(m.target.parentElement); });
  }).observe(D.body, {childList: true, subtree: true, characterData: true});
  varre(D);
})();
"""

paginas = st.tabs(["Visão geral", "Projeções e cenários"])

if "nonce" not in st.session_state:
    st.session_state.nonce = 0
N = st.session_state.nonce


# =================================================================================== PÁGINA 1
def _periodos(ems, serie, inicio):
    d = MOVEL[MOVEL["emissora"].isin(ems) & (MOVEL["fim"] >= inicio)]
    conc = [e for e in ems if e in EXTERNAS]
    if conc:   # com concorrentes, só os bancos que existem no ranking de concorrência (o ranking não traz nov–jan nem dez–fev)
        d = d[d["fim"].isin(MOVEL.loc[MOVEL["emissora"].isin(conc), "fim"])]
    fins = sorted(d["fim"].unique())
    if serie.startswith("Banco"):
        return [pd.Timestamp(x) for x in fins]
    if serie.startswith("Trimestre"):
        return [pd.Timestamp(x) for x in fins if pd.Timestamp(x).month % 3 == 0]
    return sorted({pd.Timestamp(x).year for x in fins})


def _rot_periodo(x, serie):
    if serie.startswith("Ano"):
        return str(x)
    return rot_banco(x)


def _valores(e, serie, periodos):
    """Valor de cada período para a emissora e (NaN se não houver), + share e marca de amostra pequena."""
    d = MOVEL[MOVEL["emissora"] == e].set_index("fim").sort_index()
    if serie.startswith("Ano"):
        mb = media_bancos(e)
        v = [mb["mean"].get(a, np.nan) for a in periodos]
        n = [int(mb["size"].get(a, 0)) for a in periodos]
        return np.array(v, float), [np.nan] * len(v), [False] * len(v), n
    v = d["opm"].reindex(periodos).values.astype(float)
    sh = d["sht"].reindex(periodos).values.astype(float) if "sht" in d else np.full(len(periodos), np.nan)
    bx = d["amostra_baixa"].reindex(periodos).fillna(False).astype(bool).values if "amostra_baixa" in d else np.zeros(len(periodos), bool)
    return v, sh, bx, [3] * len(v)


def _ranking(fim):
    d = MOVEL[(MOVEL["fim"] == fim) & ~MOVEL["emissora"].isin(TOTAIS)][["emissora", "opm", "sht", "amostra_baixa"]].sort_values("opm", ascending=False).reset_index(drop=True)
    d.index = d.index + 1
    return d


_ARRASTE_JS = r"""
(function () {
  const P = window, D = document;        // roda dentro da página do painel (injetado pelo iframe abaixo)
  if (P.__arrasteTags) return;            // instala uma vez só por página
  P.__arrasteTags = true;
  const css = D.createElement("style");
  css.textContent = `
    .st-key-p1_em [data-tag], .st-key-p1_em [data-baseweb="tag"] {cursor:grab; touch-action:none; user-select:none;}
    .arraste-fantasma {position:fixed; z-index:99999; pointer-events:none; opacity:.9; transform:rotate(-2deg);
                       box-shadow:0 6px 16px rgba(0,0,0,.25); cursor:grabbing;}
    .arraste-marca {position:fixed; z-index:99998; width:3px; border-radius:2px; background:#1c5cab; pointer-events:none;}
    .st-key-p1_ordem_txt {position:absolute !important; left:-9999px; height:0; overflow:hidden;}`;
  D.head.appendChild(css);
  const tags = () => [...D.querySelectorAll(".st-key-p1_em [data-tag], .st-key-p1_em [data-baseweb='tag']")];
  const rotulo = t => (t.getAttribute("aria-label") || t.textContent || "").trim();
  let ini = null, arr = null, fant = null, marca = null, destino = null;

  function onde(x, y) {                   // posição de inserção pela linha e pelo meio de cada quadro
    const ts = tags(); let pos = ts.length;
    for (let i = 0; i < ts.length; i++) {
      const r = ts[i].getBoundingClientRect();
      if (y < r.top - 4) { pos = i; break; }
      if (y <= r.bottom + 4 && x < r.left + r.width / 2) { pos = i; break; }
    }
    return pos;
  }
  function mostraMarca(pos) {
    const ts = tags(); if (!ts.length) return;
    const ref = pos < ts.length ? ts[pos].getBoundingClientRect() : ts[ts.length - 1].getBoundingClientRect();
    const x = pos < ts.length ? ref.left - 4 : ref.right + 2;
    Object.assign(marca.style, {left: x + "px", top: ref.top + "px", height: ref.height + "px"});
  }
  function enviar(ordem) {
    const inp = D.querySelector(".st-key-p1_ordem_txt input"); if (!inp) return;
    const set = Object.getOwnPropertyDescriptor(P.HTMLInputElement.prototype, "value").set;
    inp.focus();
    set.call(inp, JSON.stringify({o: ordem, t: Date.now()}));
    inp.dispatchEvent(new P.Event("input", {bubbles: true}));
    inp.dispatchEvent(new P.KeyboardEvent("keydown", {key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true}));
    inp.blur();
  }
  D.addEventListener("pointerdown", ev => {
    const t = ev.target.closest(".st-key-p1_em [data-tag], .st-key-p1_em [data-baseweb='tag']");
    if (!t || ev.button !== 0 || ev.target.closest("button, [role='presentation']")) return;
    ev.preventDefault(); ev.stopPropagation();
    ini = {x: ev.clientX, y: ev.clientY, tag: t, i: tags().indexOf(t)};
  }, true);
  D.addEventListener("mousedown", ev => {          // não abre a lista ao pegar um quadro
    if (ev.target.closest(".st-key-p1_em [data-tag], .st-key-p1_em [data-baseweb='tag']") &&
        !ev.target.closest("button, [role='presentation']")) { ev.preventDefault(); ev.stopPropagation(); }
  }, true);
  D.addEventListener("pointermove", ev => {
    if (!ini) return;
    if (!arr) {
      if (Math.hypot(ev.clientX - ini.x, ev.clientY - ini.y) < 5) return;
      arr = ini; const r = arr.tag.getBoundingClientRect();
      fant = arr.tag.cloneNode(true); fant.classList.add("arraste-fantasma");
      Object.assign(fant.style, {width: r.width + "px", height: r.height + "px", left: r.left + "px", top: r.top + "px"});
      arr.dx = ev.clientX - r.left; arr.dy = ev.clientY - r.top;
      marca = D.createElement("div"); marca.className = "arraste-marca";
      D.body.append(fant, marca); arr.tag.style.opacity = ".35";
    }
    fant.style.left = (ev.clientX - arr.dx) + "px"; fant.style.top = (ev.clientY - arr.dy) + "px";
    destino = onde(ev.clientX, ev.clientY); mostraMarca(destino);
  }, true);
  function fim() {
    if (arr) {
      const ts = tags(), nomes = ts.map(rotulo), de = arr.i;
      let para = destino == null ? de : destino;
      arr.tag.style.opacity = ""; fant.remove(); marca.remove();
      if (para > de) para -= 1;
      if (para !== de && de >= 0) {
        const [m] = nomes.splice(de, 1); nomes.splice(para, 0, m); enviar(nomes);
      }
    }
    ini = arr = fant = marca = destino = null;
  }
  D.addEventListener("pointerup", fim, true);
  D.addEventListener("pointercancel", fim, true);
})();
"""


def _rodar_js(html):
    """Roda um trecho de HTML/JS invisível (iframe de altura zero). Usa st.iframe nas versões novas do Streamlit,
    onde components.html foi descontinuado, e components.html nas antigas."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=1)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=0)


_rodar_js("<script>const D = window.parent.document; if (!window.parent.__efeitosPainel) { const s = D.createElement('script'); "
          "s.textContent = " + json.dumps(_EFEITOS_JS) + "; D.head.appendChild(s); }</script>")


def ordem_do_arraste():
    """Lê a nova ordem enviada pelo arraste dos quadros (campo escondido) e aplica na seleção antes de ela ser desenhada."""
    txt = st.session_state.get("p1_ordem_txt", "")
    if txt and txt != st.session_state.get("_p1_ordem_lida"):
        st.session_state["_p1_ordem_lida"] = txt
        try:
            por_nome = {NOME.get(e, e): e for e in TODAS}
            nova = [por_nome[n] for n in json.loads(txt)["o"] if n in por_nome]
            if sorted(nova) == sorted(st.session_state.get("p1_em", [])):
                st.session_state["p1_em"] = nova
        except (ValueError, KeyError, TypeError):
            pass


def arrastar_selecionados(chave):
    """Permite arrastar os quadros azuis do próprio campo de seleção para mudar a ordem das emissoras nos gráficos.
    O arraste é feito no navegador; a ordem nova volta ao Python por um campo de texto escondido."""
    st.text_input("ordem", key="p1_ordem_txt", label_visibility="collapsed")
    _rodar_js("""<script>
    const D = window.parent.document;
    if (!window.parent.__arrasteTags) {
      const s = D.createElement("script");
      s.textContent = """ + json.dumps(_ARRASTE_JS) + """;
      D.head.appendChild(s);
    }
    </script>""")


def cartao_media(e, s, ano, nb, cor):
    """Média do ano até o último banco disponível, comparada com a média dos MESMOS bancos do ano anterior
    (jan–mar a jul–set de 2026 vs jan–mar a jul–set de 2025), para não misturar ano parcial com ano completo."""
    meses = sorted(m for m in s.index[(s.index.year == ano) & (s.index.month >= 3)].month)
    atual = s[(s.index.year == ano) & s.index.month.isin(meses)]
    antes = s[(s.index.year == ano - 1) & s.index.month.isin(meses)]
    ini, fim = pd.Timestamp(ano, meses[0], 1), pd.Timestamp(ano, meses[-1], 1)
    faixa = f"{rot_movel(ini)[:7]} a {rot_movel(fim)[:7]}"            # ex.: jan–mar a jul–set
    titulo = f"{NOME[e]} · média {ano}" + ("" if nb >= 10 else f" ({faixa})")
    parcial = nb < 10
    if len(antes) == len(atual) and len(antes):
        comp = (f"{delta_html(atual.mean(), antes.mean())} vs {br(antes.mean())}, "
                + (f"média parcial de {ano - 1} (mesmo período)" if parcial else f"média de {ano - 1}"))
    else:
        comp = f"sem o mesmo período de {ano - 1} para comparar"
    sub = (f"média parcial de {ano}" if parcial else f"média de {ano}") + " · " + comp
    return (titulo, br(atual.mean()), sub, cor)


def limpar_com_clique_fora(chave):
    """Com um ano destacado, qualquer clique na página fora das barras do gráfico `chave` desfaz a seleção
    (dispara o mesmo evento de "desmarcar" do Plotly, que o Streamlit já trata)."""
    _rodar_js(f"""<script>
    (function () {{
      const P = window.parent, D = P.document, eu = window.frameElement;
      if (P.__limpaSel) D.removeEventListener("click", P.__limpaSel, true);
      P.__limpaSel = function (ev) {{
        if (!eu || !eu.isConnected) {{ D.removeEventListener("click", P.__limpaSel, true); return; }}
        const gd = D.querySelector(".st-key-{chave} .js-plotly-plot");
        if (!gd) return;
        const x = ev.clientX, y = ev.clientY;
        const naBarra = [...gd.querySelectorAll("g.point path")].some(b => {{
          const r = b.getBoundingClientRect(); return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom; }});
        if (naBarra) return;
        D.removeEventListener("click", P.__limpaSel, true);
        gd.emit("plotly_deselect", null);
      }};
      D.addEventListener("click", P.__limpaSel, true);
    }})();
    </script>""")



# =================================================================================== mapa de calor e curva do ano (com janela expandida)
def tabela_detalhe(em, base, medida_k):
    """Tabela ano × banco (ou trimestre) da emissora: OPM#, variação vs mesmo período do ano anterior ou vs período anterior."""
    s = M.movel_serie(MOVEL, em)
    if base == "Trimestre móvel":
        ini = s.index - pd.DateOffset(months=2)
        d3 = pd.DataFrame({"Ano": ini.year, "c": ini.month, "v": s.values})
        tab = d3.pivot_table(index="Ano", columns="c", values="v").reindex(columns=range(1, 13))
        nomes_col = [rot_ini(m) for m in range(1, 13)]
    else:
        f_ = s[s.index.month.isin([3, 6, 9, 12])]
        q_full = pd.Series(f_.values, index=pd.PeriodIndex(f_.index, freq="Q"))
        d3 = pd.DataFrame({"Ano": q_full.index.year, "c": q_full.index.quarter, "v": q_full.values})
        tab = d3.pivot_table(index="Ano", columns="c", values="v").reindex(columns=range(1, 5))
        nomes_col = [f"T{k} ({TRIM_NOME[k]})" for k in range(1, 5)]
    if medida_k == "ano":
        tab = (tab / tab.shift(1) - 1) * 100
    elif medida_k == "periodo":
        flat = tab.stack(future_stack=True)
        tab = ((flat / flat.shift(1) - 1) * 100).unstack()
    tab.columns = nomes_col
    return tab.sort_index(ascending=False)


def rot_medida(base, medida_k):
    un = "banco" if base == "Trimestre móvel" else "trimestre"
    return {"OPM#": "OPM#", "ano": f"Variação vs mesmo {un} do ano anterior", "periodo": f"Variação vs {un} anterior"}[medida_k]


DIVERG = ([[0, "#ff6b5e"], [.35, "#6b2f33"], [.5, "#131c31"], [.65, "#24476f"], [1, "#6aa6f0"]] if ESCURO else
          [[0, "#b42318"], [.35, "#f4b6ae"], [.5, "#f6f7fb"], [.65, "#a9c8f2"], [1, "#1c5cab"]])


def fig_calor(tab, medida_k, h, texto=False, desde=None):
    t = tab if desde is None else tab[tab.index >= desde]
    t = t.sort_index()
    z = t.values.astype(float)
    if medida_k == "OPM#":
        kw = dict(colorscale=SEQ, colorbar=dict(thickness=10, outlinewidth=0, tickfont=dict(size=10), tickformat=",.0f"),
                  hovertemplate="<b>%{y}</b> · %{x}<br>%{z:,.0f} OPM<extra></extra>")
        txt = [[("" if pd.isna(v) else br(v)) for v in r] for r in z]
    else:
        lim = float(np.nanpercentile(np.abs(z), 95)) if np.isfinite(z).any() else 10
        kw = dict(colorscale=DIVERG, zmid=0, zmin=-lim, zmax=lim,
                  colorbar=dict(thickness=10, outlinewidth=0, tickfont=dict(size=10), ticksuffix="%"),
                  hovertemplate="<b>%{y}</b> · %{x}<br>%{z:+.1f}%<extra></extra>")
        txt = [[("" if pd.isna(v) else f"{v:+.1f}%".replace(".", ",")) for v in r] for r in z]
    fig = go.Figure(go.Heatmap(z=z, x=list(t.columns), y=[str(a) for a in t.index], xgap=2, ygap=2,
                               text=txt if texto else None, texttemplate="%{text}" if texto else None,
                               textfont=dict(size=10), **kw))
    layout(fig, h).update_yaxes(autorange="reversed", tickformat="", dtick=1, tickfont=dict(size=10))
    fig.update_xaxes(tickangle=0, tickfont=dict(size=10))
    return fig


CORES_ANOS = ["#52514e", "#7b5cff", "#00a3a3", "#eb6834", "#c0392b", "#8a8984", "#2e7d32", "#b07d00"]


def fig_curva(em, anos, banda, h, sel_click=None):
    s = M.movel_serie(MOVEL, em)
    dfm = pd.DataFrame({"v": s.values, "ano_ini": (s.index - pd.DateOffset(months=2)).year,
                        "m_ini": (s.index - pd.DateOffset(months=2)).month})
    ano_atual = int(dfm["ano_ini"].max())
    xs = [rot_ini(m) for m in range(1, 13)]
    fig = go.Figure()
    if banda:
        ant = dfm[(dfm["ano_ini"] < ano_atual)].pivot_table(index="m_ini", columns="ano_ini", values="v")
        ant = ant[[c for c in ant.columns if c not in (2020, 2021)]] if ant.shape[1] > 3 else ant
        if ant.shape[1]:
            lo, hi = ant.min(axis=1).reindex(range(1, 13)), ant.max(axis=1).reindex(range(1, 13))
            fig.add_scatter(x=xs, y=hi.values, mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False)
            fig.add_scatter(x=xs, y=lo.values, mode="lines", line=dict(width=0), fill="tonexty", fillcolor=FAIXA,
                            name="mín–máx anteriores (sem 2020–21)", hoverinfo="skip")
            fig.add_scatter(x=xs, y=ant.median(axis=1).reindex(range(1, 13)).values, mode="lines", name="mediana anteriores",
                            line=dict(color=CINZA, width=1.2, dash="dot"), hovertemplate="mediana anteriores · %{x}<br>%{y:,.0f}<extra></extra>")
    outros = [a for a in anos if a != ano_atual]
    for k, a in enumerate(sorted(outros, reverse=True) + ([ano_atual] if ano_atual in anos else [])):
        cor = COR[em] if a == ano_atual else CORES_ANOS[k % len(CORES_ANOS)]
        est = dict(color=cor, width=2.6) if a == ano_atual else dict(color=cor, width=1.8, dash="dash" if k == 0 else "dot")
        g = dfm[dfm["ano_ini"] == a].set_index("m_ini")["v"].reindex(range(1, 13))
        fig.add_scatter(x=xs, y=g.values, mode="lines+markers", name=str(a), line=est,
                        marker=dict(size=7 if a == ano_atual else 5, color=cor, line=dict(color=CARTAO, width=1.5)),
                        hovertemplate=f"<b>{a}</b> · " + "%{x}<br>%{y:,.0f} OPM<extra></extra>")
    layout(fig, h, legenda=True)
    return fig, dfm, ano_atual


def _guarda(dest, origem):
    st.session_state[dest] = st.session_state[origem]


def _dialogo(titulo):
    import inspect
    kw = {"width": "large"}
    if "on_dismiss" in inspect.signature(st.dialog).parameters:
        kw["on_dismiss"] = "rerun"            # ao fechar, o painel volta com os filtros escolhidos
    return st.dialog(titulo, **kw)


def _estado_padrao(em_foco, ano_atual):
    ss = st.session_state
    if ss.get("_foco_ult") != em_foco:         # trocar a emissora em foco leva os dois quadros junto
        ss["_foco_ult"] = em_foco
        ss["hm_em"] = em_foco
        ss["cv_em"] = em_foco
        ss.pop("cv_anos", None)
    ss.setdefault("hm_base", "Trimestre móvel")
    ss.setdefault("hm_med", "OPM#")
    ss.setdefault("cv_banda", True)
    if ss.get("hm_em") not in TODAS:
        ss["hm_em"] = em_foco
    if ss.get("cv_em") not in TODAS:
        ss["cv_em"] = em_foco


@_dialogo("Mapa de calor · detalhes")
def janela_calor():
    ss = st.session_state
    c = st.columns(3)
    c[0].selectbox("Emissora", TODAS, index=TODAS.index(ss["hm_em"]), format_func=NOME.get, key="hm_em_w",
                   on_change=_guarda, args=("hm_em", "hm_em_w"))
    bases = ["Trimestre móvel", "Trimestre fechado"]
    c[1].selectbox("Base", bases, index=bases.index(ss["hm_base"]), key="hm_base_w", on_change=_guarda, args=("hm_base", "hm_base_w"))
    meds = ["OPM#", "ano", "periodo"]
    c[2].selectbox("Mostrar", meds, index=meds.index(ss["hm_med"]), format_func=lambda m: rot_medida(ss["hm_base"], m),
                   key="hm_med_w", on_change=_guarda, args=("hm_med", "hm_med_w"))
    em, base, med = ss["hm_em"], ss["hm_base"], ss["hm_med"]
    tab = tabela_detalhe(em, base, med)
    bruto = tabela_detalhe(em, base, "OPM#")
    flat = bruto.stack().dropna()
    if len(flat):
        (a_max, c_max), (a_min, c_min) = flat.idxmax(), flat.idxmin()
        ultimo_ano = int(bruto.dropna(how="all").index.max())
        m_ult = bruto.loc[ultimo_ano].dropna()
        cols_ok = m_ult.index
        m_ant = bruto.loc[ultimo_ano - 1, cols_ok].mean() if ultimo_ano - 1 in bruto.index else np.nan
        st.markdown(f"""<div class="mini">
            <div>Maior da série<b>{br(flat.max())}</b>{c_max}/{a_max}</div>
            <div>Menor da série<b>{br(flat.min())}</b>{c_min}/{a_min}</div>
            <div>Média de {ultimo_ano} ({len(m_ult)} {'bancos' if base == 'Trimestre móvel' else 'trimestres'})<b>{br(m_ult.mean())}</b>
                {pct(m_ult.mean() / m_ant - 1, 1, True) + f' vs mesmo período de {ultimo_ano - 1}' if pd.notna(m_ant) else ''}</div>
            <div>Períodos na série<b>{len(flat)}</b>desde {int(bruto.dropna(how='all').index.min())}</div></div>""",
                    unsafe_allow_html=True)
    st.plotly_chart(fig_calor(tab, med, 34 * len(tab) + 70, texto=True), config=CFG, key="dlg_calor")
    b = st.columns([1.2, 1.6, 1])
    b[0].download_button("⬇️ Exportar tabela (CSV)", tab.to_csv(sep=";", decimal=",").encode("utf-8-sig"),
                         f"audiencia_{em.replace(' ', '_')}.csv", "text/csv", key="dlg_dl_tab")
    b[1].download_button("⬇️ Exportar base completa (CSV, formato longo)",
                         MOVEL.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"), "audiencia_radio_movel.csv",
                         "text/csv", key="dlg_dl_base")
    if b[2].button("Minimizar", icon=":material/close_fullscreen:", key="min_calor", type="primary"):
        st.rerun()


@_dialogo("Curva do ano · detalhes")
def janela_curva():
    ss = st.session_state
    s = M.movel_serie(MOVEL, ss["cv_em"])
    anos_disp = sorted({int(a) for a in (s.index - pd.DateOffset(months=2)).year}, reverse=True)
    atual = anos_disp[0]
    c = st.columns([1.2, 2.4, 1.2])
    c[0].selectbox("Emissora", TODAS, index=TODAS.index(ss["cv_em"]), format_func=NOME.get, key="cv_em_w",
                   on_change=_guarda, args=("cv_em", "cv_em_w"))
    padrao = [a for a in ss.get("cv_anos", [atual, atual - 1]) if a in anos_disp] or [atual]
    c[1].multiselect("Anos", anos_disp, default=padrao, key="cv_anos_w", on_change=_guarda, args=("cv_anos", "cv_anos_w"))
    c[2].toggle("Faixa dos anos anteriores", value=ss["cv_banda"], key="cv_banda_w", on_change=_guarda, args=("cv_banda", "cv_banda_w"))
    anos = ss.get("cv_anos", padrao) or padrao
    fig, dfm, ano_atual = fig_curva(ss["cv_em"], anos, ss["cv_banda"], 430)
    st.plotly_chart(fig, config=CFG, key="dlg_curva")
    piv = dfm[dfm["ano_ini"].isin(anos)].pivot_table(index="ano_ini", columns="m_ini", values="v").reindex(columns=range(1, 13))
    piv = piv.sort_index(ascending=False)
    if len(piv):
        cur = piv.loc[ano_atual].dropna() if ano_atual in piv.index else pd.Series(dtype=float)
        mini = ""
        if len(cur):
            mini += (f"<div>Melhor banco de {ano_atual}<b>{br(cur.max())}</b>{rot_ini(int(cur.idxmax()))}</div>"
                     f"<div>Pior banco de {ano_atual}<b>{br(cur.min())}</b>{rot_ini(int(cur.idxmin()))}</div>")
            for a in [x for x in piv.index if x != ano_atual][:2]:
                ant = piv.loc[a, cur.index].mean()
                mini += (f"<div>{ano_atual} vs {a} (mesmos bancos)<b>{pct(cur.mean() / ant - 1, 1, True)}</b>"
                         f"{br(cur.mean())} vs {br(ant)}</div>")
        st.markdown(f'<div class="mini">{mini}</div>', unsafe_allow_html=True)
        t = piv.copy()
        t.columns = [rot_ini(m) for m in t.columns]
        t["média"] = piv.mean(axis=1)
        with st.expander("Tabela com os valores", expanded=False):
            st.dataframe(t.map(lambda v: "" if pd.isna(v) else br(v)), width="stretch")
    if st.button("Minimizar", icon=":material/close_fullscreen:", key="min_curva", type="primary"):
        st.rerun()


def _fins_do_periodo(serie, periodos):
    """Bancos (trimestres móveis) que cobrem o período escolhido no topo, em qualquer série."""
    if serie.startswith("Ano"):
        anos = set(periodos)
        return sorted(f for f in MOVEL["fim"].unique() if pd.Timestamp(f).year in anos)
    return [pd.Timestamp(x) for x in periodos]


def _min_tmed(t):
    try:
        h, m, s_ = [int(x) for x in str(t).split(":")[:3]]
        return h * 60 + m + s_ / 60
    except (ValueError, TypeError):
        return np.nan


def extras_visao(ems, serie, periodos, p0, p1, em_foco):
    """Visualizações extras escolhidas no rodapé (🧩), duas por linha."""
    pedidas = [c for c in VIS_EXTRA if mostra(c)]
    if not pedidas:
        return
    fins = _fins_do_periodo(serie, periodos)
    rot = [rot_movel(f) for f in fins]
    faixa_txt = f"{rot[0]} a {rot[-1]}" if rot else ""
    d = MOVEL[MOVEL["emissora"].isin(ems) & MOVEL["fim"].isin(fins)]

    def linhas(coluna, titulo, sub, chave, conv=None, fmt=",.1f", suf=""):
        with cartao(titulo, sub):
            fig = go.Figure()
            for e in ems:
                g = d[d["emissora"] == e].set_index("fim")[coluna].reindex(fins)
                v = g.map(conv) if conv else pd.to_numeric(g, errors="coerce")
                if v.notna().sum() == 0:
                    continue
                fig.add_scatter(x=rot, y=v.values, name=NOME.get(e, e), mode="lines+markers", connectgaps=False,
                                line=dict(color=COR.get(e, CINZA), width=2.4), marker=dict(size=6),
                                hovertemplate=f"<b>{NOME.get(e, e)}</b> · %{{x}}<br>%{{y:{fmt}}}{suf}<extra></extra>")
            if not fig.data:
                st.markdown(f'<div class="vs">Sem dados de {titulo.split(" ")[0].lower()} para as emissoras e o período escolhidos '
                            '(o EasyMedia traz essa métrica a partir de 2024).</div>', unsafe_allow_html=True)
                return
            layout(fig, 300, legenda=True)
            fig.update_xaxes(tickangle=-45 if len(rot) > 8 else 0, tickfont=dict(size=10))
            st.plotly_chart(fig, config=CFG, key=chave)

    def share():
        linhas("sht", "Share (SHT%) por banco", f"participação na audiência total do rádio · {faixa_txt}", "v_x_share", suf="%")

    def alcance():
        linhas("alcance", "Alcance (ALCM#) por banco", f"ouvintes alcançados no período · {faixa_txt}", "v_x_alcance", fmt=",.0f")

    def tmed():
        linhas("tmed", "Tempo médio de audição (TMED#)", f"minutos por ouvinte · {faixa_txt}", "v_x_tmed", conv=_min_tmed, suf=" min")

    def yoy():
        with cartao("Variação vs mesmo banco do ano anterior", f"OPM# · {faixa_txt}"):
            fig = go.Figure()
            for e in ems:
                s_ = M.movel_serie(MOVEL, e)
                v = [(s_.get(f) / s_.get(f - pd.DateOffset(years=1)) - 1) * 100
                     if pd.notna(s_.get(f)) and pd.notna(s_.get(f - pd.DateOffset(years=1))) else np.nan for f in fins]
                fig.add_bar(x=rot, y=v, name=NOME.get(e, e), marker_color=COR.get(e, CINZA),
                            customdata=[rot_movel(f - pd.DateOffset(years=1)) for f in fins],
                            hovertemplate=f"<b>{NOME.get(e, e)}</b> · %{{x}}<br>%{{y:+.1f}}% vs %{{customdata}}<extra></extra>")
            layout(fig, 300, legenda=True).update_layout(barmode="group")
            fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=ZERO)
            fig.update_xaxes(tickangle=-45 if len(rot) > 8 else 0, tickfont=dict(size=10))
            st.plotly_chart(fig, config=CFG, key="v_x_yoy")

    def posicao():
        with cartao("Posição no ranking ao longo do tempo", f"entre todas as emissoras medidas · {faixa_txt}"):
            fig = go.Figure()
            pos = {e: [] for e in ems}
            for f in fins:
                rk = _ranking(f)
                lugar = {r.emissora: k for k, r in rk.iterrows()}
                for e in ems:
                    pos[e].append(lugar.get(e, np.nan))
            for e in ems:
                if all(pd.isna(x) for x in pos[e]):
                    continue
                fig.add_scatter(x=rot, y=pos[e], name=NOME.get(e, e), mode="lines+markers",
                                line=dict(color=COR.get(e, CINZA), width=2.6, shape="spline", smoothing=.6), marker=dict(size=8),
                                hovertemplate=f"<b>{NOME.get(e, e)}</b> · %{{x}}<br>%{{y}}º lugar<extra></extra>")
            layout(fig, 300, legenda=True)
            fig.update_yaxes(autorange="reversed", dtick=1, tickformat="d", ticksuffix="º", title_text="")
            fig.update_xaxes(tickangle=-45 if len(rot) > 8 else 0, tickfont=dict(size=10))
            st.plotly_chart(fig, config=CFG, key="v_x_posicao")

    def participacao():
        with cartao("Participação entre as emissoras selecionadas", f"% do OPM# somado das selecionadas · {faixa_txt}"):
            piv = d.pivot_table(index="fim", columns="emissora", values="opm").reindex(fins)
            piv = piv[[e for e in ems if e in piv.columns and e not in TOTAIS]]
            tot = piv.sum(axis=1, min_count=1)
            fig = go.Figure()
            for e in piv.columns:
                fig.add_bar(x=rot, y=(piv[e] / tot * 100).values, name=NOME.get(e, e), marker_color=COR.get(e, CINZA),
                            hovertemplate=f"<b>{NOME.get(e, e)}</b> · %{{x}}<br>%{{y:.1f}}% do total das selecionadas<extra></extra>")
            layout(fig, 300, legenda=True).update_layout(barmode="stack", bargap=.15)
            fig.update_yaxes(ticksuffix="%", range=[0, 100])
            fig.update_xaxes(tickangle=-45 if len(rot) > 8 else 0, tickfont=dict(size=10))
            st.plotly_chart(fig, config=CFG, key="v_x_participacao")

    def sazonal():
        s_ = M.movel_serie(MOVEL, em_foco)
        ini = s_.index - pd.DateOffset(months=2)
        with cartao(f"Sazonalidade por banco · {NOME.get(em_foco, em_foco)}",
                    f"OPM# de cada banco nos anos de {ini.year.min()} a {ini.year.max()} · ◆ = {ini.year.max()}"):
            fig = go.Figure()
            fig.add_box(x=[rot_ini(m) for m in ini.month], y=s_.values, name=NOME.get(em_foco, em_foco),
                        marker_color=COR.get(em_foco, AZUL), boxmean=True, showlegend=False,
                        hovertemplate="%{x}: %{y:,.0f}<extra></extra>")
            atual = s_[ini.year == ini.year.max()]
            ini_a = atual.index - pd.DateOffset(months=2)
            fig.add_scatter(x=[rot_ini(m) for m in ini_a.month], y=atual.values, mode="markers", name=str(ini.year.max()),
                            marker=dict(symbol="diamond", size=10, color=TINTA, line=dict(color=CARTAO, width=1)),
                            hovertemplate=f"{ini.year.max()} · %{{x}}: %{{y:,.0f}}<extra></extra>")
            layout(fig, 300, legenda=True)
            fig.update_xaxes(categoryorder="array", categoryarray=[rot_ini(m) for m in range(1, 13)])
            st.plotly_chart(fig, config=CFG, key="v_x_sazonal")

    funcs = {"share": share, "alcance": alcance, "tmed": tmed, "yoy": yoy, "posicao": posicao,
             "participacao": participacao, "sazonal": sazonal}
    for k in range(0, len(pedidas), 2):
        par = pedidas[k:k + 2]
        cols = st.columns(2) if len(par) == 2 else [st.container()]
        for col, cod in zip(cols, par):
            with col:
                funcs[cod]()


def _dupla(a, b, larg=(1.15, 1)):
    """Duas posições lado a lado; se só uma das duas for mostrada, ela ocupa a linha toda."""
    if a and b:
        c = st.columns(list(larg))
        return c[0], c[1]
    return st.container(), st.container()


def pagina1():
    padrao = [e for e in ["GFM", "Bahia FM", "Piatã FM", "Itapoan FM"] if e in TODAS]
    if len(padrao) < 4:          # sem as concorrentes de sempre (ex.: dados de demonstração): as duas maiores entram no lugar
        padrao += [e for e in CONCORRENTES if e not in padrao][:4 - len(padrao)]
    f = st.columns([2.7, 1.5, 2.1, 1.2])
    if "p1_em" not in st.session_state:
        st.session_state["p1_em"] = padrao
    ordem_do_arraste()
    ems = f[0].multiselect("Emissoras", TODAS, format_func=NOME.get, placeholder="Escolha as emissoras",
                           key="p1_em", help="GFM e Bahia FM têm histórico desde 2016. As concorrentes e os totais (emissoras, FM e web) vêm do "
                                "EasyMedia, a partir de 2024. Os totais servem só para consulta: não entram no ranking nem na projeção.") or padrao
    arrastar_selecionados("p1_em")
    serie = f[1].selectbox("Série", ["Banco (trimestre móvel)", "Trimestre fechado", "Ano (média dos bancos)"], key="p1_serie",
                           help="Banco = trimestre móvel (jan–mar, fev–abr…); vizinhos têm 2 de 3 meses em comum. Trimestre fechado = jan–mar, "
                                "abr–jun, jul–set, out–dez. Ano = média dos 10 bancos do ano (jan–mar a out–dez), que reproduz o número oficial.")
    tem_conc = any(e in EXTERNAS for e in ems)
    inicio = INICIO_CONC if (tem_conc and INICIO_CONC is not None) else pd.Timestamp("2016-01-01")
    pers = _periodos(ems, serie, inicio)
    if not pers:
        st.warning("Sem dados para as emissoras escolhidas.")
        return
    n_pad = {"B": 13, "T": 8, "A": len(pers)}[serie[0]]
    ini_pad = pers[max(0, len(pers) - n_pad)]
    p0, p1 = f[2].select_slider("Período", options=pers, value=(ini_pad, pers[-1]), format_func=lambda x: _rot_periodo(x, serie),
                                key=f"p1_per_{serie[0]}_{tem_conc}")
    modo = f[3].segmented_control("Barras", ["Empilhadas", "Lado a lado"], default="Empilhadas", key="p1_modo") or "Empilhadas"
    periodos = [x for x in pers if p0 <= x <= p1]
    st.session_state["_filtros_txt"] = (f"Emissoras: {', '.join(NOME.get(e, e) for e in ems)} · Série: {serie.lower()} · "
                                        f"Período: {_rot_periodo(p0, serie)} a {_rot_periodo(p1, serie)}")

    sel_ano = [p["ano"] for p in selecao(f"v_anual_{N}", ["ano"])]
    sel_ano = sel_ano[0] if sel_ano else None

    # ---- KPIs (emissoras próprias selecionadas) + posição no ranking do último banco
    ult = MOVEL["fim"].max()
    rk = _ranking(ult)
    lista = []
    for e in [x for x in ems if x in EMISSORAS] or EMISSORAS:
        s = M.movel_serie(MOVEL, e)
        t = s.index.max()
        t_ant, t_aa = t - pd.DateOffset(months=1), t - pd.DateOffset(years=1)
        ant, aa = s.get(t_ant), s.get(t_aa)
        mb = media_bancos(e)
        ano = int(mb.index.max()); nb = int(mb.loc[ano, "size"])
        lista += [(f"{NOME[e]} · {rot_movel(t)}", br(s[t]),
                   (f"{delta_html(s[t], ant)} vs banco anterior ({rot_movel(t_ant)})" if ant else f"banco anterior ({rot_movel(t_ant)}) sem dado"), COR[e]),
                  (f"{NOME[e]} · {rot_movel(t)} vs {rot_movel(t_aa)}", pct(s[t] / aa - 1, sinal=True) if aa else "–",
                   (f"mesmo banco do ano anterior · {br(s[t])} vs {br(aa)} ({'+' if s[t] - aa > 0 else ''}{br(s[t] - aa)} ouvintes)"
                    if aa else f"mesmo banco do ano anterior ({rot_movel(t_aa)}) sem dado"), COR[e])]
        if len(rk) > 2 and e in rk["emissora"].values:
            pos = int(rk.index[rk["emissora"] == e][0])
            if pos == 1:
                dsc = f"{br(rk.loc[1, 'opm'] - rk.loc[2, 'opm'])} à frente de {NOME.get(rk.loc[2, 'emissora'], rk.loc[2, 'emissora'])}"
            else:
                dsc = f"{br(rk.loc[pos - 1, 'opm'] - s[t])} atrás de {NOME.get(rk.loc[pos - 1, 'emissora'], rk.loc[pos - 1, 'emissora'])}"
            lista.append((f"{NOME[e]} · ranking {rot_movel(ult)}", f"{pos}º", f"de {len(rk)} · {dsc}", COR[e]))
        lista.append(cartao_media(e, s, ano, nb, COR[e]))
    kpis(lista)

    if mostra("evolucao"):
        # ---- gráfico principal: barras horizontais por período (padrão do slide "Evolução trimestral")
        nome_serie = {"B": "banco", "T": "trimestre fechado", "A": "ano"}[serie[0]]
        with cartao(f"Evolução por {nome_serie} · audiência",
                    f"OPM# · 05h–05h · " + (f"{p0} a {p1}" if serie.startswith("Ano") else f"{rot_movel(p0)} a {rot_movel(p1)}")):
            rotulos = [_rot_periodo(x, serie) for x in periodos]
            fig = go.Figure()
            for e in ems:
                v, sh, bx, nb = _valores(e, serie, periodos)
                if np.all(np.isnan(v)):
                    continue
                rot_e = [r + ("*" if serie.startswith("Ano") and n < 10 else "") for r, n in zip(rotulos, nb)]
                extra = [("sem dado neste período" if pd.isna(x0) else " · ".join(t for t in [f"share {br(x, 2)}%" if pd.notna(x) else "",
                                                                                 "amostra pequena (#)" if b else ""] if t))
                         for x0, x, b in zip(v, sh, bx)]
                vazio = np.isnan(v)
                v = np.where(vazio, 0.0, v)          # NaN quebra o empilhamento do Plotly: período sem dado vira segmento de largura zero
                fig.add_bar(y=rotulos, x=v, orientation="h", name=NOME[e], marker=dict(color=COR[e], line=dict(color=CARTAO, width=1),
                            pattern=dict(shape=["/" if b else "" for b in bx], fgcolor=HACHURA, fgopacity=0.6, size=5, solidity=0.35, fillmode="overlay")),
                            text=["" if z else br(x) for x, z in zip(v, vazio)],
                            textposition="inside" if modo == "Empilhadas" else "outside", insidetextanchor="middle", cliponaxis=False,
                            textfont=dict(color=COR_TEXTO[e] if modo == "Empilhadas" else TINTA2, size=11 if modo == "Empilhadas" else 10),
                            customdata=np.c_[rot_e, extra],
                            hovertemplate="<b>" + NOME[e] + "</b> · %{customdata[0]}<br>%{x:,.0f} OPM<br>%{customdata[1]}<extra></extra>")
            alto = 34 * len(periodos) + 70 if modo == "Empilhadas" else (17 * len(ems) + 16) * len(periodos) + 70
            layout(fig, max(300, alto), legenda=True).update_layout(barmode="stack" if modo == "Empilhadas" else "group", bargap=0.22,
                                                                    uniformtext=dict(minsize=9, mode="hide"), margin=dict(l=6, r=50, t=34, b=6),
                                                                    legend_traceorder="normal")
            fig.update_yaxes(categoryorder="array", categoryarray=rotulos, autorange="reversed", gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11, color=TINTA))
            fig.update_xaxes(showticklabels=False, showgrid=False)
            st.plotly_chart(fig, config=CFG, key="v_barras")

    # ---- linha 2: média anual | ranking do último período escolhido (cada um pode ser tirado no rodapé)
    _ca, _cr = _dupla(mostra("anual"), mostra("ranking"))
    if mostra("anual"):
        with _ca:
            with cartao("Média anual", "clique num ano para destacar na curva"):
                fig = go.Figure()
                a_ini = pd.Timestamp(inicio).year if tem_conc else 2017
                for e in ems:
                    mb = media_bancos(e)
                    mb = mb[mb.index >= a_ini]
                    if mb.empty:
                        continue
                    rot = [f"{a}" + ("*" if n < 10 else "") for a, n in zip(mb.index, mb["size"])]
                    yoy = mb["mean"] / mb["mean"].shift(1) - 1
                    op = [1 if (sel_ano is None or a == sel_ano) else .35 for a in mb.index]
                    fig.add_bar(x=[str(a) for a in mb.index], y=mb["mean"], name=NOME[e], marker=dict(color=COR[e], opacity=op), customdata=mb.index,
                                text=[pct(v, 0, True) if pd.notna(v) else "" for v in yoy], textposition="none",
                                hovertext=rot, hovertemplate="<b>" + NOME[e] + " · %{hovertext}</b><br>%{y:,.0f} OPM<br>vs média do ano anterior: %{text}<extra></extra>")
                layout(fig, 330, legenda=len(ems) > 1).update_layout(barmode="group", bargroupgap=0.08)
                fig.update_xaxes(type="category")
                st.plotly_chart(fig, config=CFG, on_select="rerun", selection_mode="points", key=f"v_anual_{N}")
                if sel_ano:
                    limpar_com_clique_fora(f"v_anual_{N}")
    if mostra("ranking"):
        with _cr:
            fim_rk = p1 if not serie.startswith("Ano") else MOVEL["fim"].max()
            rk2 = _ranking(fim_rk)
            f_ant, f_aa = fim_rk - pd.DateOffset(months=1), fim_rk - pd.DateOffset(years=1)
            with cartao(f"Ranking · {rot_movel(fim_rk)}"):
                antes = MOVEL[MOVEL["fim"] == f_ant].set_index("emissora")["opm"]
                ano_ant = MOVEL[MOVEL["fim"] == f_aa].set_index("emissora")["opm"]
                mx = rk2["opm"].max() if len(rk2) else 1

                def _d(v):
                    if pd.isna(v):
                        return f'<td class="n" style="color:{CINZA}">–</td>'
                    return f'<td class="n" style="color:{SOBE if v > 0 else DESCE}">{("+" if v > 0 else "") + br(v)}</td>'
                linhas = ""
                for pos, r in rk2.head(12).iterrows():
                    linhas += (f'<tr{" class=hl" if r.emissora in ems else ""}><td>{pos}º</td><td><span style="color:{COR.get(r.emissora, CINZA)}">■</span> '
                               f'{NOME.get(r.emissora, r.emissora)}{" #" if r.amostra_baixa else ""}</td><td class="n">{br(r.opm)}</td>'
                               + _d(r.opm - antes.get(r.emissora, np.nan)) + _d(r.opm - ano_ant.get(r.emissora, np.nan)) +
                               f'<td style="width:24%"><div class="bar" style="width:{r.opm / mx * 100:.1f}%; background:{COR.get(r.emissora, CINZA)}"></div></td></tr>')
                st.markdown(f'<table class="rk"><tr><th></th><th>Emissora</th><th style="text-align:right">OPM#</th>'
                            f'<th style="text-align:right">Δ banco ant.<br>{rot_movel(f_ant)}</th>'
                            f'<th style="text-align:right">Δ ano ant.<br>{rot_movel(f_aa)}</th><th></th></tr>'
                            f'{linhas}</table>', unsafe_allow_html=True)

    # ---- linha 3: curva do ano | mapa de calor (emissora em foco)
    if mostra("curva") or mostra("calor") or mostra("sazonal"):
        em_foco = st.segmented_control("Emissora em foco nos gráficos abaixo", ems, default=ems[0], format_func=NOME.get,
                                       key=f"p1_foco_{'_'.join(ems)}") or ems[0]
    else:
        em_foco = ems[0]
    s = M.movel_serie(MOVEL, em_foco)
    dfm = pd.DataFrame({"v": s.values})
    dfm["ano_ini"] = (s.index - pd.DateOffset(months=2)).year
    dfm["m_ini"] = (s.index - pd.DateOffset(months=2)).month
    ano_atual = int(dfm["ano_ini"].max())
    _estado_padrao(em_foco, ano_atual)
    ss = st.session_state
    _cc, _cm = _dupla(mostra("curva"), mostra("calor"))
    if mostra("curva"):
        with _cc:
            if sel_ano and sel_ano != ano_atual:          # clique na média anual tem prioridade
                anos_c = [ano_atual, sel_ano]
            else:
                anos_c = ss.get("cv_anos") or [ano_atual, ano_atual - 1]
            rot_anos = " vs ".join(str(a) for a in sorted(anos_c, reverse=True))
            with cartao(f"Curva do ano · {NOME[ss['cv_em']]}", rot_anos):
                if st.button("", icon=":material/open_in_full:", key="exp_curva", help="Expandir: mais anos, faixa e detalhes"):
                    janela_curva()
                fig, _, _ = fig_curva(ss["cv_em"], anos_c, ss["cv_banda"], 300)
                st.plotly_chart(fig, config=CFG, key="v_curva")
    if mostra("calor"):
        with _cm:
            with cartao(f"Mapa de calor · {NOME[ss['hm_em']]}",
                        f"{ss['hm_base'].lower()} · {rot_medida(ss['hm_base'], ss['hm_med']).lower()}"):
                if st.button("", icon=":material/open_in_full:", key="exp_calor", help="Expandir: filtros, valores e exportação"):
                    janela_calor()
                tab = tabela_detalhe(ss["hm_em"], ss["hm_base"], ss["hm_med"])
                st.plotly_chart(fig_calor(tab, ss["hm_med"], 300, desde=2017 if ss["hm_em"] in EMISSORAS else None),
                                config=CFG, key="v_calor")

    if mostra("comparativo"):
        # ---- linha 4: comparativo em linhas (mesma série e período do gráfico de barras)
        with cartao("Comparativo · audiência",
                    f"OPM# · " + (f"{p0} a {p1}" if serie.startswith("Ano") else f"{rot_movel(p0)} a {rot_movel(p1)}")):
            eh_ano, eh_banco = serie.startswith("Ano"), serie.startswith("Banco")
            rot_x = [str(x) if eh_ano else (rot_movel(x) if eh_banco else rot_trim(x)) for x in periodos]
            un = "ano" if eh_ano else ("banco" if eh_banco else "trimestre")
            fig = go.Figure()
            for e in ems:
                v = _valores(e, serie, periodos)[0]
                if np.all(np.isnan(v)):
                    continue
                todos = dict(zip(pers, _valores(e, serie, pers)[0]))
                if eh_ano:
                    ant = [todos.get(x - 1, np.nan) for x in periodos]
                    aa = [np.nan] * len(periodos)
                else:
                    passo = pd.DateOffset(months=1 if eh_banco else 3)
                    ant = [todos.get(x - passo, np.nan) for x in periodos]
                    aa = [todos.get(x - pd.DateOffset(years=1), np.nan) for x in periodos]

                def _var(a, b, rotulo):
                    return "" if pd.isna(a) or pd.isna(b) or not b else f"<br>{pct(a / b - 1, 1, True)} vs {rotulo}"
                info = [_var(a, b, f"{un} anterior") + _var(a, c, f"mesmo {un} do ano anterior") for a, b, c in zip(v, ant, aa)]
                if eh_ano:   # ano em andamento: avisa que a média ainda é parcial
                    nbs = _valores(e, serie, periodos)[3]
                    info = [t + (f"<br>média parcial ({n} de 10 bancos)" if n < 10 else "") for t, n in zip(info, nbs)]
                ult = int(np.where(~np.isnan(v))[0][-1])
                fig.add_scatter(x=rot_x, y=v, name=NOME[e], mode="lines+markers+text", connectgaps=False,
                                line=dict(color=COR[e], width=2.5), marker=dict(size=6, color=COR[e]),
                                text=[br(x) if k == ult else "" for k, x in enumerate(v)], textposition="middle right",
                                textfont=dict(size=11, color=COR[e]), customdata=info,
                                hovertemplate="<b>" + NOME[e] + " · %{x}</b><br>%{y:,.0f} OPM%{customdata}<extra></extra>")
            layout(fig, 320, legenda=len(ems) > 1)
            fig.update_xaxes(tickangle=-45 if len(periodos) > 8 else 0, tickfont=dict(size=10), range=[-0.3, len(periodos) - 0.35])
            st.plotly_chart(fig, config=CFG, key="v_linhas")
        st.markdown('<div class="rodape">OPM# = ouvintes por minuto (média), 05h–05h, todos os dias, ambos os sexos, Grande Salvador · Kantar IBOPE EasyMedia4. '
                    'Ano = média dos 10 bancos internos (jan–mar a out–dez), regra que reproduz o número oficial. # = amostra pequena no EasyMedia '
                    '(leia com cautela). Nas barras empilhadas, o comprimento total não tem significado: compare os segmentos.</div>', unsafe_allow_html=True)

    extras_visao(ems, serie, periodos, p0, p1, em_foco)

with paginas[0]:
    st.session_state["_aba_atual"] = "Visão geral"
    pagina1()


# =================================================================================== PÁGINA 2
@st.cache_data(show_spinner=False)
def rodar_projecao(e, metodo, ate, h, usar_now, vies, valor_now=None):
    return M.projetar(MOVEL, e, metodo, ate, h, usar_now=usar_now, corrigir_vies=vies, valor_now=valor_now)


@st.cache_data(show_spinner=False)
def rodar_comparacao(e, ate, usar_now):
    return M.comparar_metodos(MOVEL, e, ate, H=4, usar_now=usar_now)


def fechamentos(p, n_sim):
    """Distribuição do fechamento (ano e 2º semestre) para cada ano coberto: realizados + simulados × fator oficial."""
    rng = np.random.default_rng(7)
    k_ano = rng.normal(K_ANO[0], K_ANO[1], n_sim)
    k_sem = rng.normal(K_SEM[0], K_SEM[1], n_sim)
    out = {}
    for a in sorted({t.year for t in p["futuros"]}):
        cols = []
        for i in (1, 2, 3, 4):
            t = pd.Period(f"{a}Q{i}", "Q")
            if t in p["q"].index:
                cols.append(np.full(n_sim, p["q"][t]))
            elif t in p["futuros"]:
                cols.append(p["sim"][:, list(p["futuros"]).index(t)])
        if len(cols) == 4:
            out[a] = dict(ano=np.mean(cols, axis=0) * k_ano, sem2=np.mean(cols[2:], axis=0) * k_sem,
                          realizados=[t for t in p["q"].index if t.year == a])
    return out


def pagina2():
    f = st.columns([1.1, 1.9, 1.15, 1.7, 1.05, 1.05])
    e = f[0].selectbox("Emissora", EMISSORAS, format_func=NOME.get, key="p2_em")
    metodo = f[1].selectbox("Método", list(M.METODOS), key="p2_met")
    fech_disp = [t for t in Q[e].index if t >= pd.Period("2022Q2", "Q")]
    ate = f[3].select_slider("Projetar a partir de", options=fech_disp, value=fech_disp[-1], format_func=rot_trim, key="p2_ate",
                             help="Último trimestre fechado usado. Escolha um trimestre passado para ver como a projeção teria se saído "
                                  "(o painel usa só o que se sabia na época).")
    fim_opts = [t for t in pd.period_range(ate + 1, periods=6, freq="Q") if t.quarter == 4 or t == ate + 6]
    fim_opts = sorted({t for t in fim_opts})
    padrao = next((i for i, t in enumerate(fim_opts) if t.year == (ate + 1).year), 0)
    ate_fim = f[2].selectbox("Projetar até", fim_opts, index=padrao, format_func=rot_trim, key=f"p2_fim_{ate}")
    h = int((ate_fim - ate).n)
    usar_now = f[4].toggle("Nowcast", value=True, key="p2_now",
                           help="Usa o trimestre móvel mais recente (que já cobre 2 dos 3 meses do trimestre em curso) como leitura do trimestre em curso.")
    vies = f[5].toggle("Corrigir viés", value=False, key="p2_vies",
                       help="Soma ao centro o erro médio da validação. Se o método vinha errando para cima (queda não antecipada), puxa a projeção para baixo.")
    st.markdown(f'<div class="metodo"><b>{metodo}:</b> {M.DESCRICAO[metodo]}</div>', unsafe_allow_html=True)

    with st.spinner("Rodando a validação do método com origem móvel (só na primeira vez de cada combinação)…"):
        p = rodar_projecao(e, metodo, str(ate), h, usar_now, vies)
    n_sim = p["sim"].shape[0]
    FE = fechamentos(p, n_sim)
    simulando_passado = ate < Q[e].index.max()
    if simulando_passado:
        st.markdown(f'<div class="aviso">⏪ Simulando o passado: projeção feita com dados até <b>{rot_trim(ate)}</b>'
                    f'{" + nowcast " + rot_movel(M.mes_nowcast(ate + 1)) if p["nowcast"] else ""}. Os pontos pretos mostram o que de fato aconteceu.</div>',
                    unsafe_allow_html=True)
    if usar_now and not p["nowcast"]:
        st.markdown(f'<div class="aviso">Sem nowcast: o trimestre móvel {rot_movel(M.mes_nowcast(ate + 1))} ainda não está na planilha.</div>',
                    unsafe_allow_html=True)

    anos_f = list(FE)
    ano_alvo = anos_f[0] if anos_f else None
    if len(anos_f) > 1:
        ano_alvo = st.radio("Ano do fechamento", anos_f, horizontal=True, key="p2_ano_alvo")
    ref_bi = PREV_BI.get(e, {}).get("ano") if ano_alvo == 2026 else None
    ofic_ant = OFICIAL.get(e, {}).get(str(ano_alvo - 1)) if ano_alvo else None
    ma_ant = media_anual(Q[e])["mean"].get(ano_alvo - 1) if ano_alvo else None
    ref_ant = ofic_ant or (ma_ant * K_ANO[0] if ma_ant else None)
    padrao_pat = int(round((ref_bi or ref_ant or p["centro"].mean()) / 100) * 100)

    # ---- KPIs
    sim = p["sim"]
    lista = []
    for i in range(min(2, h)):
        t = p["futuros"][i]
        l8, h8 = np.percentile(sim[:, i], [10, 90])
        nome = "nowcast" if (i == 0 and p["nowcast"]) else "projeção"
        lista.append((f"{rot_trim(t)} ({TRIM_NOME[t.quarter]}) · {nome}", br(p["centro"][i]), f"80%: {br(l8)}–{br(h8)}", COR[e]))
    c_pat = st.columns([1.3, 4.7])
    pat = c_pat[0].number_input(f"Patamar anual {ano_alvo or ''} (OPM#)", min_value=0, value=padrao_pat, step=500,
                                key=f"p2_pat_{e}_{ano_alvo}",
                                help="Valor de referência para calcular a chance de o fechamento do ano ficar acima dele "
                                     "(ex.: previsão do BI, meta comercial, resultado do ano anterior).")
    refs = []
    if ref_bi:
        refs.append(f"previsão BI (CAGR) = {br(ref_bi)}")
    if ofic_ant:
        refs.append(f"oficial {ano_alvo - 1} = {br(ofic_ant)}")
    c_pat[1].markdown(f'<div class="vs" style="margin-top:30px">Referências: {" · ".join(refs) if refs else "—"}</div>', unsafe_allow_html=True)
    if ano_alvo:
        v = FE[ano_alvo]["ano"]
        med = np.median(v)
        l8, h8 = np.percentile(v, [10, 90])
        pr = float(np.mean(v >= pat))
        real_of = OFICIAL.get(e, {}).get(str(ano_alvo))
        lista.append((f"Fechamento {ano_alvo}", br(med), f"80%: {br(l8)}–{br(h8)}" + (f" · oficial: {br(real_of)}" if real_of else ""), VIOLETA))
        if ref_ant:
            lista.append((f"vs {ano_alvo - 1}", pct(med / ref_ant - 1, sinal=True), f"{'oficial' if ofic_ant else 'média'} {ano_alvo - 1} = {br(ref_ant)}", VIOLETA))
        lista.append((f"Chance de ≥ {br(pat)}", fmt_p(pr), freq(pr) + " cenários", AMARELO if .2 <= pr < .8 else (VERDE if pr >= .8 else VERMELHO)))
        real = [p["q"][t] for t in FE[ano_alvo]["realizados"]]
        n_rest = 4 - len(real)
        if n_rest:
            nec = (pat / K_ANO[0] * 4 - sum(real)) / n_rest
            fut_idx = [i for i, t in enumerate(p["futuros"]) if t.year == ano_alvo]
            lista.append(("Média necessária", br(nec), f"nos {n_rest} trimestres restantes · projeção {br(p['centro'][fut_idx].mean())}", AMARELO))
    val = p["validacao"]
    if len(val):
        lista.append(("Erro típico (h=1–2)", pct(val[val["h"] <= 2]["MAPE"].mean()),
                      f"MAPE na validação · {p['n_origens']} origens", CINZA))
    kpis(lista)

    # ---- linha 1: leque | distribuição
    l1 = st.columns([1.6, 1])
    with l1[0]:
        with cartao(f"Projeção em leque · {NOME[e]}", "faixas de 50%, 80% e 95%"):
            q_hist = p["q_all"][p["q_all"].index >= ate - 11]
            q_ate = q_hist[q_hist.index <= ate]
            q_dep = q_hist[q_hist.index > ate]
            dt = lambda idx: pd.PeriodIndex(idx, freq="Q").to_timestamp(how="end").normalize().to_period("M").to_timestamp()
            s_h = p["s_all"][(p["s_all"].index >= dt(q_hist.index[:1])[0]) & (p["s_all"].index <= p["s"].index.max())]
            fig = go.Figure()
            fig.add_scatter(x=s_h.index, y=s_h.values, mode="lines", name="Trimestre móvel", line=dict(color=COR[e], width=1),
                            opacity=.45, text=[rot_movel(i) for i in s_h.index],
                            hovertemplate="móvel %{text}<br>%{y:,.0f}<extra></extra>")
            xf = dt(p["futuros"])
            x0 = dt(q_ate.index[-1:])
            for (lo, hi), al, rot in [((2.5, 97.5), .13, "95%"), ((10, 90), .22, "80%"), ((25, 75), .36, "50%")]:
                pl, ph = np.percentile(sim, [lo, hi], axis=0)
                xx = list(x0) + list(xf)
                fig.add_scatter(x=xx, y=[q_ate.iloc[-1]] + list(ph), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False)
                fig.add_scatter(x=xx, y=[q_ate.iloc[-1]] + list(pl), mode="lines", line=dict(width=0), fill="tonexty",
                                fillcolor=f"rgba({int(COR[e][1:3], 16)},{int(COR[e][3:5], 16)},{int(COR[e][5:], 16)},{al})", name=f"Faixa {rot}",
                                hoverinfo="skip")
            fig.add_scatter(x=dt(q_ate.index), y=q_ate.values, mode="lines+markers", name="Realizado (trimestre fechado)",
                            line=dict(color=COR[e], width=2.4), marker=dict(size=8, color=COR[e], line=dict(color=CARTAO, width=2)),
                            text=[f"{rot_trim(i)} ({TRIM_NOME[i.quarter]})" for i in q_ate.index],
                            hovertemplate="<b>%{text}</b><br>%{y:,.0f} OPM<extra></extra>")
            p25, p75 = np.percentile(sim, [25, 75], axis=0)
            l8, h8 = np.percentile(sim, [10, 90], axis=0)
            fig.add_scatter(x=list(x0) + list(xf), y=[q_ate.iloc[-1]] + list(p["centro"]), mode="lines+markers", name="Projeção",
                            line=dict(color=TINTA, width=2, dash="dash"), marker=dict(size=8, color=CARTAO, line=dict(color=TINTA, width=2)),
                            customdata=np.c_[[0] + list(l8), [0] + list(h8), [0] + list(p25), [0] + list(p75)],
                            text=["último fechado"] + [f"{rot_trim(t)} ({TRIM_NOME[t.quarter]})" for t in p["futuros"]],
                            hovertemplate="<b>%{text}</b><br>%{y:,.0f} OPM<br>50%: %{customdata[2]:,.0f}–%{customdata[3]:,.0f}"
                                          "<br>80%: %{customdata[0]:,.0f}–%{customdata[1]:,.0f}<extra></extra>")
            for xi, v in zip(xf, p["centro"]):
                fig.add_annotation(x=xi, y=v, text=f"<b>{br(v)}</b>", showarrow=False, yshift=14, font=dict(color=TINTA, size=11))
            if len(q_dep):
                fig.add_scatter(x=dt(q_dep.index), y=q_dep.values, mode="markers", name="Realizado depois do corte",
                                marker=dict(size=9, color=TINTA, symbol="diamond"),
                                text=[rot_trim(i) for i in q_dep.index], hovertemplate="<b>%{text}</b> (realizado)<br>%{y:,.0f}<extra></extra>")
            if ano_alvo:
                fig.add_hline(y=pat, line=dict(color=TINTA2, width=1, dash="dot"),
                              annotation_text=f"patamar anual {br(pat)}", annotation_position="top left",
                              annotation_font=dict(size=10, color=TINTA2))
            layout(fig, 380, legenda=True).update_layout(hovermode="closest", margin=dict(r=20))
            fig.update_xaxes(tickformat="%b/%y")
            st.plotly_chart(fig, config=CFG, key="v_leque")
    with l1[1]:
        if ano_alvo:
            v = FE[ano_alvo]["ano"]
            pr = float(np.mean(v >= pat))
            with cartao(f"Fechamento {ano_alvo}: distribuição", f"{br(n_sim)} cenários"):
                cont, bordas = np.histogram(v, bins=70, range=tuple(np.percentile(v, [0.3, 99.7])))
                centros = (bordas[:-1] + bordas[1:]) / 2
                cores = [COR[e] if c >= pat else CINZA_CLARO for c in centros]
                fig = go.Figure(go.Bar(x=centros, y=cont / cont.sum() * 100, marker=dict(color=cores, cornerradius=0),
                                       hovertemplate="~%{x:,.0f} OPM<br>%{y:.1f}% dos cenários<extra></extra>"))
                fig.add_vline(x=pat, line=dict(color=TINTA, width=1.5, dash="dash"))
                fig.add_annotation(x=pat, y=1, yref="paper", text=f"patamar {br(pat)}<br><b>chance {fmt_p(pr)}</b>", showarrow=False,
                                   xanchor="left" if pat < np.median(v) else "right", xshift=6 if pat < np.median(v) else -6,
                                   yanchor="top", font=dict(size=11, color=TINTA), align="left")
                med = np.median(v)
                fig.add_vline(x=med, line=dict(color=TINTA2, width=1))
                fig.add_annotation(x=med, y=0, yref="paper", text=f"mediana {br(med)}", showarrow=False, yanchor="bottom", yshift=-2,
                                   xanchor="left", xshift=4, font=dict(size=10, color=TINTA2))
                layout(fig, 380).update_layout(bargap=0.04)
                fig.update_xaxes(tickformat=",.0f")
                fig.update_yaxes(showticklabels=False, showgrid=False)
                st.plotly_chart(fig, config=CFG, key="v_dist")

    # ---- linha 2: patamares | validação
    l2 = st.columns([1, 1.25])
    with l2[0]:
        if ano_alvo:
            v = FE[ano_alvo]["ano"]
            with cartao(f"Chance por patamar · {ano_alvo}"):
                c = round(np.median(v) / 500) * 500
                linhas = ""
                for g in c + 500 * np.arange(-4, 5):
                    pr = float(np.mean(v >= g))
                    hl = " class=hl" if abs(g - pat) < 250 else ""
                    linhas += (f'<tr{hl}><td>{br(g)}</td><td class="n">{fmt_p(pr)}</td><td>{freq(pr)}</td>'
                               f'<td style="width:38%"><div class="bar" style="width:{pr * 100:.1f}%; background:{COR[e]}"></div></td></tr>')
                st.markdown(f'<table class="rk"><tr><th>Patamar (OPM#)</th><th style="text-align:right">Chance</th><th>Frequência</th><th></th></tr>'
                            f'{linhas}</table>', unsafe_allow_html=True)
    with l2[1]:
        with cartao("Validação do método", f"erro médio por horizonte · {p['n_origens']} origens"):
            ing = rodar_projecao(e, "Ingênuo (repete o último)", str(ate), h, usar_now, False)["validacao"]
            fig = go.Figure()
            if len(val):
                for nome_m, vv, cor in [(metodo, val, COR[e]), ("Ingênuo (repete o último)", ing, CINZA_CLARO)]:
                    if nome_m == metodo and metodo.startswith("Ingênuo"):
                        continue
                    rot = [("h=1 (nowcast)" if (k == 1 and p["nowcast"]) else f"h={k}") for k in vv["h"]]
                    fig.add_bar(x=rot, y=vv["MAE"], name=nome_m.split(" (")[0], marker_color=cor,
                                customdata=np.c_[vv["MAPE"] * 100, vv["vies"], vv["n"]],
                                hovertemplate="<b>" + nome_m + " · %{x}</b><br>MAE %{y:,.0f} OPM (%{customdata[0]:.1f}%)"
                                              "<br>viés %{customdata[1]:+,.0f} · n=%{customdata[2]}<extra></extra>")
            layout(fig, 300, legenda=True).update_layout(barmode="group", bargroupgap=0.08)
            st.plotly_chart(fig, config=CFG, key="v_val")
            if len(val):
                vm = val["vies"].mean()
                st.markdown(f'<div class="vs">Viés médio {br(vm)} OPM ({"projeção acima do realizado" if vm < 0 else "projeção abaixo do realizado"}). '
                            f'Fator de alargamento das faixas: {br(p["fator"], 2)}.</div>', unsafe_allow_html=True)

    # ---- linha 3: comparação de métodos | cenário manual
    l3 = st.columns([1.25, 1])
    with l3[0]:
        with cartao("Comparação de métodos", f"MAPE · dados até {rot_trim(ate)}"):
            with st.spinner("Validando todos os métodos…"):
                cmp_ = rodar_comparacao(e, str(ate), False)
            if len(cmp_):
                cmp_ = cmp_.sort_values("MAPE", ascending=False)
                cores = [COR[e] if m == metodo else (CINZA if m.startswith("Ingênuo") else CINZA_CLARO) for m in cmp_["metodo"]]
                fig = go.Figure(go.Bar(x=cmp_["MAPE"] * 100, y=cmp_["metodo"], orientation="h", marker_color=cores,
                                       text=[f"{br(v * 100, 1)}%" for v in cmp_["MAPE"]], textposition="outside", cliponaxis=False,
                                       textfont=dict(color=TINTA2, size=11), customdata=np.c_[cmp_["MAE"], cmp_["vies"]],
                                       hovertemplate="<b>%{y}</b><br>MAPE %{x:.1f}% · MAE %{customdata[0]:,.0f}<br>viés %{customdata[1]:+,.0f}<extra></extra>"))
                layout(fig, 300).update_xaxes(showticklabels=False, range=[0, cmp_["MAPE"].max() * 100 * 1.2])
                st.plotly_chart(fig, config=CFG, key="v_cmp")
    with l3[1]:
        with cartao("Cenário manual", "digite os trimestres que faltam"):
            if ano_alvo:
                fut = [(i, t) for i, t in enumerate(p["futuros"]) if t.year == ano_alvo]
                real = [p["q"][t] for t in FE[ano_alvo]["realizados"]]
                cols = st.columns(max(1, len(fut)))
                manual = []
                for (i, t), c in zip(fut, cols):
                    manual.append(c.number_input(f"{rot_trim(t)} ({TRIM_NOME[t.quarter]})", min_value=0,
                                                 value=int(round(p["centro"][i], -1)), step=250, key=f"man_{e}_{metodo}_{ate}_{t}"))
                if fut:
                    ano_m = (sum(real) + sum(manual)) / 4 * K_ANO[0]
                    s2_m = np.mean(([p["q"][t] for t in FE[ano_alvo]["realizados"] if t.quarter >= 3] + manual)[-2:]) * K_SEM[0]
                    v = FE[ano_alvo]["ano"]
                    pos = float(np.mean(v <= ano_m))
                    kpis([(f"Fechamento {ano_alvo} no cenário", br(ano_m), f"{'≥' if ano_m >= pat else '<'} patamar {br(pat)} · "
                           f"{'acima' if pos > .5 else 'abaixo'} de {pct(pos if pos > .5 else 1 - pos, 0)} dos cenários", VIOLETA),
                          (f"2º semestre {ano_alvo}", br(s2_m), f"vs BI {br(PREV_BI.get(e, {}).get('S2'))}" if ano_alvo == 2026 and PREV_BI.get(e) else "média T3–T4 × fator", VIOLETA)])
                    st.markdown(f'<div class="vs">Realizado em {ano_alvo}: {", ".join(f"{rot_trim(t)} = {br(p["q"][t])}" for t in FE[ano_alvo]["realizados"]) or "—"}. '
                                f'Fechamento = média dos 4 trimestres × fator oficial ({br(K_ANO[0], 4)}).</div>', unsafe_allow_html=True)
                else:
                    st.info("Todos os trimestres deste ano já foram realizados.")

    # ---- tabela da projeção
    with cartao("Tabela da projeção", "centro e percentis"):
        lin = []
        for i, t in enumerate(p["futuros"]):
            q_ = np.percentile(sim[:, i], [2.5, 10, 25, 50, 75, 90, 97.5])
            real_t = p["q_all"].get(t)
            lin.append({"Período": f"{rot_trim(t)} ({TRIM_NOME[t.quarter]})",
                        "Fonte": "nowcast (trimestre móvel)" if (i == 0 and p["nowcast"]) else metodo,
                        "Projeção": br(p["centro"][i]), "50%": f"{br(q_[2])}–{br(q_[4])}", "80%": f"{br(q_[1])}–{br(q_[5])}",
                        "95%": f"{br(q_[0])}–{br(q_[6])}", "Realizado": br(real_t) if pd.notna(real_t) else ""})
        for a, d in FE.items():
            for nome, vv, chave in [(f"2º semestre {a}", d["sem2"], f"2S{str(a)[2:]}"), (f"Ano {a}", d["ano"], str(a))]:
                q_ = np.percentile(vv, [2.5, 10, 25, 50, 75, 90, 97.5])
                lin.append({"Período": nome, "Fonte": "simulação × fator oficial", "Projeção": br(q_[3]),
                            "50%": f"{br(q_[2])}–{br(q_[4])}", "80%": f"{br(q_[1])}–{br(q_[5])}", "95%": f"{br(q_[0])}–{br(q_[6])}",
                            "Realizado": (br(OFICIAL.get(e, {}).get(chave)) + " (oficial)") if OFICIAL.get(e, {}).get(chave) else ""})
        tab = pd.DataFrame(lin)
        if not simulando_passado:
            tab = tab.drop(columns="Realizado")
        st.dataframe(tab, hide_index=True, width="stretch")
        st.download_button("⬇️ Exportar projeção (CSV)", tab.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"),
                           f"projecao_{e.replace(' ', '_')}_{rot_trim(ate)}.csv", "text/csv")
    st.markdown('<div class="rodape">Modelagem só com trimestres fechados (sem sobreposição). Margens vêm dos erros reais de uma validação '
                'com origem móvel (30 origens, sem os casos da pandemia), simulados com t multivariada (6 g.l.) e alargadas pelo fator que '
                'calibra a faixa de 80%. Fechamento = média dos trimestres × fator de conversão para o número oficial (com a incerteza do fator). '
                'Probabilidades arredondadas a 5 p.p.: leia como ordem de grandeza.</div>', unsafe_allow_html=True)


with paginas[1]:
    st.session_state["_aba_atual"] = "Projeções e cenários"
    pagina2()
st.session_state["_aba_atual"] = ""


# =================================================================================== PÁGINA 4 · atualizar dados
def _grava_parametros(par, msg="Atualiza parâmetros pelo painel"):
    json.dump(par, open("parametros.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = github_salvar("parametros.json", json.dumps(par, ensure_ascii=False, indent=1).encode("utf-8"), msg)
    if ok is False:
        st.session_state["msg_erro"] = "Não consegui gravar no GitHub (confira o token em Secrets). A alteração vale só até o app reiniciar."
    pp = par.get("pasta_persistente")
    if pp:
        os.makedirs(pp, exist_ok=True)
        json.dump({"oficial": par.get("oficial"), "previsao_bi": par.get("previsao_bi")},
                  open(os.path.join(pp, "parametros_editados.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _recarrega(msg):
    shutil.rmtree(M.PASTA_CACHE, ignore_errors=True)          # validações refeitas com os dados novos
    st.cache_data.clear()
    st.session_state["msg_ok"] = msg
    st.session_state["up_nonce"] = st.session_state.get("up_nonce", 0) + 1
    st.rerun()


def salvar_base(nova, descricao, excluidos=None):
    """Grava a base (todas as colunas: OPM#, share, alcance, tempo médio, amostra e origem) e guarda a versão anterior,
    também no GitHub quando configurado. `excluidos` (se dado) substitui a lista de bancos excluídos."""
    os.makedirs("backups", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if os.path.exists("radio_movel.csv"):
        bk = os.path.join("backups", f"radio_movel_{ts}.csv")
        shutil.copy("radio_movel.csv", bk)
        github_salvar(f"backups/radio_movel_{ts}.csv", open(bk, "rb").read(), f"Backup da base antes de: {descricao}")
    cols = [c for c in M.COLUNAS if c in nova.columns]
    # o que vem das planilhas fixas de dados/ não é regravado: é lido delas a cada carga, então uma planilha
    # corrigida direto no GitHub passa a valer sem ser encoberta por uma cópia antiga
    fixos = {os.path.basename(a) for a in arquivos_fixos()}
    if "origem" in nova.columns:
        nova = nova[~nova["origem"].map(lambda o: pd.notna(o) and str(o).split(":")[0] in fixos)]
    nova = nova[cols].sort_values(["emissora", "fim"])
    nova.to_csv("radio_movel.csv", index=False)
    par = json.load(open("parametros.json", encoding="utf-8"))
    par["dados"] = {"descricao": descricao, "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M")}
    if excluidos is not None:
        par["excluidos"] = sorted(set(excluidos))
    ok = github_salvar("radio_movel.csv", nova.to_csv(index=False).encode("utf-8"), f"Atualiza base de audiência: {descricao}")
    if ok is False:
        st.session_state["msg_erro"] = "Não consegui gravar no GitHub (confira o token em Secrets). A base vale só até o app reiniciar."
    _grava_parametros(par, f"Atualiza parâmetros: {descricao}")
    if par.get("pasta_persistente"):
        nova.to_csv(os.path.join(par["pasta_persistente"], "radio_base.csv"), index=False)


def _senha_ok(chave):
    senha = PAR.get("senha") or segredo("senha_atualizacao", "") or ""
    if not senha:
        return True
    return st.session_state.get(chave, "") == senha


def _arquivo_origem(o):
    return str(o).split(":")[0] if pd.notna(o) else "(sem origem)"


def gerenciar_bancos(tem_senha):
    """Lista os bancos (trimestres móveis) e os arquivos enviados, com exclusão e restauração."""
    fixos = {os.path.basename(a) for a in arquivos_fixos()}
    excl = sorted(PAR.get("excluidos", []))
    with cartao("3 · Gerenciar bancos",
                "Cada banco é um trimestre móvel do EasyMedia. Exclua um banco inteiro ou só uma emissora, remova um envio "
                "feito pelo painel e restaure o que foi excluído. A versão anterior da base fica guardada a cada mudança.", nota=True):
        abas = st.tabs(["Bancos", "Arquivos enviados", f"Excluídos ({len(excl)})"])

        # ---------------------------------------------------------------- por banco
        with abas[0]:
            d = MOVEL.copy()
            d["arquivo"] = d["origem"].map(_arquivo_origem)
            g = d.groupby("fim")
            n_em = d[~d["emissora"].isin(TOTAIS)].groupby("fim").size()
            tab = pd.DataFrame({"Banco": [rot_banco(f) for f in g.size().index], "Emissoras": n_em.reindex(g.size().index).fillna(0).astype(int).values,
                                "Arquivo": g["arquivo"].agg(lambda x: ", ".join(sorted(set(x)))).values}, index=g.size().index)
            alertas = pd.Series("", index=tab.index)
            for e in EMISSORAS:
                se = M.movel_serie(MOVEL, e)
                tab[f"{NOME[e]} OPM#"] = se.reindex(tab.index).map(lambda v: "" if pd.isna(v) else br(v)).values
                var = se / se.shift(1) - 1
                for f, v in var.items():
                    if pd.notna(v) and abs(v) > 0.5:
                        alertas[f] += f"{NOME[e]} {pct(v, 0, True)} vs banco anterior · "
            tab["Conferir"] = alertas.str.rstrip(" ·").map(lambda t: f"⚠️ {t}" if t else "")
            tab = tab.sort_index(ascending=False)
            fins = list(tab.index)
            if tab["Conferir"].ne("").any():
                st.markdown('<div class="aviso">⚠️ Há bancos com salto acima de 50% sobre o anterior: costuma ser coluna trocada '
                            '(ex.: alcance lido como OPM#). Confira e, se for o caso, exclua e envie de novo.</div>', unsafe_allow_html=True)
            st.dataframe(tab.reset_index(drop=True), hide_index=True, width="stretch", height=min(42 + 35 * len(tab), 380))
            c = st.columns([1.6, 1])
            sel = c[0].multiselect("Bancos", fins, format_func=rot_banco, placeholder="Escolha um ou mais bancos",
                                   key=f"bk_sel_{st.session_state.get('up_nonce', 0)}")
            alvo = c[1].selectbox("Emissoras", ["Todas as emissoras do banco"] + TODAS, format_func=lambda x: NOME.get(x, x),
                                  key="bk_alvo")
            if tem_senha:
                st.text_input("Senha", type="password", key="pw_bkx")
            if st.button("Excluir selecionados", disabled=not sel, key="bt_bkx"):
                if not _senha_ok("pw_bkx"):
                    st.error("Senha incorreta.")
                else:
                    todas = alvo.startswith("Todas")
                    novos = {chave_banco(f) if todas else chave_banco(f, alvo) for f in sel}
                    quem = "todas as emissoras" if todas else NOME.get(alvo, alvo)
                    salvar_base(BASE, f"excluídos {', '.join(rot_banco(f) for f in sel)} ({quem})", set(excl) | novos)
                    _recarrega(f"Excluído: {', '.join(rot_banco(f) for f in sel)} · {quem}. Dá para restaurar na aba Excluídos.")

        # ---------------------------------------------------------------- por arquivo enviado
        with abas[1]:
            d = MOVEL.copy()
            d["arquivo"] = d["origem"].map(_arquivo_origem)
            g = d.groupby("arquivo")
            arqs = pd.DataFrame({"Arquivo": g.size().index,
                                 "Fonte": ["planilha fixa (dados/)" if a in fixos else "enviado pelo painel" for a in g.size().index],
                                 "Bancos": g["fim"].agg(lambda x: f"{rot_movel(x.min())} → {rot_movel(x.max())} ({x.nunique()})").values,
                                 "Emissoras": g["emissora"].nunique().values, "Linhas": g.size().values})
            st.dataframe(arqs, hide_index=True, width="stretch", height=min(42 + 35 * len(arqs), 300))
            st.markdown('<div class="vs">A tabela mostra de onde vem cada valor que está na base agora: se um envio posterior '
                        'corrigiu um banco, o banco passa a contar no arquivo novo.</div>', unsafe_allow_html=True)
            a = st.selectbox("Arquivo", list(arqs["Arquivo"]), key="arq_sel")
            if a in fixos:
                st.markdown('<div class="vs">Planilha fixa da pasta <b>dados/</b>: remover aqui esconde os bancos dela (vão para Excluídos). '
                            'Para apagar de vez, remova o arquivo da pasta no GitHub.</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="vs">Remover tira da base os valores deste envio. Se a planilha fixa de <b>dados/</b> tiver o mesmo '
                            'banco, o valor dela volta a valer.</div>', unsafe_allow_html=True)
            if tem_senha:
                st.text_input("Senha", type="password", key="pw_arq")
            if st.button("Remover este arquivo", key="bt_arq"):
                if not _senha_ok("pw_arq"):
                    st.error("Senha incorreta.")
                else:
                    meus = d["arquivo"] == a
                    if a in fixos:
                        novos = {chave_banco(f, e) for f, e in zip(d.loc[meus, "fim"], d.loc[meus, "emissora"])}
                        salvar_base(BASE, f"removida a planilha {a}", set(excl) | novos)
                    else:
                        salvar_base(BASE[BASE["origem"].map(_arquivo_origem) != a], f"removido o envio {a}")
                    _recarrega(f"{a}: {int(meus.sum())} valores removidos da base.")

        # ---------------------------------------------------------------- excluídos
        with abas[2]:
            if not excl:
                st.markdown('<div class="vs">Nenhum banco excluído.</div>', unsafe_allow_html=True)
            else:
                rot = lambda k: f"{rot_banco(pd.Timestamp(k.split('|')[0] + '-01'))} · " + \
                    ("todas as emissoras" if k.endswith("|*") else NOME.get(k.split("|", 1)[1], k.split("|", 1)[1]))
                volta = st.multiselect("Restaurar", excl, format_func=rot, key="ex_sel",
                                       placeholder="Escolha o que deve voltar para a base")
                c = st.columns(2)
                if tem_senha:
                    st.text_input("Senha", type="password", key="pw_ex")
                if c[0].button("Restaurar selecionados", disabled=not volta, key="bt_ex"):
                    if not _senha_ok("pw_ex"):
                        st.error("Senha incorreta.")
                    else:
                        salvar_base(BASE, f"restaurados {len(volta)} bancos excluídos", set(excl) - set(volta))
                        _recarrega(f"{len(volta)} item(ns) restaurado(s).")
                if c[1].button("Restaurar todos", key="bt_ex_all"):
                    if not _senha_ok("pw_ex"):
                        st.error("Senha incorreta.")
                    else:
                        salvar_base(BASE, "restaurados todos os bancos excluídos", set())
                        _recarrega("Todos os bancos excluídos foram restaurados.")


def pagina_atualizar():
    if st.session_state.get("msg_ok"):
        st.success(st.session_state.pop("msg_ok"))
    if st.session_state.get("msg_erro"):
        st.error(st.session_state.pop("msg_erro"))
    meta = PAR.get("dados", {})
    lista = []
    for e in EMISSORAS:
        s = M.movel_serie(MOVEL, e)
        lista.append((f"{NOME[e]} · última leitura", rot_movel(s.index.max()), f"{len(s)} trimestres móveis desde {rot_movel(s.index.min())}", COR[e]))
    if CONCORRENTES:
        sc = MOVEL[MOVEL["emissora"].isin(CONCORRENTES)]
        lista.append(("Concorrência", f"{len(CONCORRENTES)} emissoras", f"{rot_movel(sc['fim'].min())} → {rot_movel(sc['fim'].max())}", CINZA))
    lista.append(("Última atualização", meta.get("atualizado_em", "–"), meta.get("descricao", ""), CINZA))
    gh = (segredo("github") or {}).get("repo")
    lista.append(("Onde fica salvo", "GitHub" if gh else ("Drive" if PAR.get("pasta_persistente") else "Só nesta sessão"),
                  gh or PAR.get("pasta_persistente") or "perde-se quando o app reinicia", CINZA))
    kpis(lista)
    if not gh and not PAR.get("pasta_persistente"):
        st.warning("**Os envios feitos aqui não ficam salvos.** Sem o bloco `[github]` em Settings → Secrets, a base atualizada "
                   "vale só até o app reiniciar (o Streamlit Cloud reinicia ao ficar parado e a cada mudança no código). "
                   "Configure o token do GitHub (veja o secrets_exemplo.toml) ou suba as planilhas na pasta `dados/` do repositório.")
    tem_senha = bool(PAR.get("senha") or segredo("senha_atualizacao"))

    l = st.columns([1.35, 1])
    with l[0]:
        with cartao("1 · Enviar dados novos do EasyMedia",
                    "Histórico (.xlsx com uma aba por ano), ranking de concorrência (.xlsx) ou CSV do EasyMedia. Pode ser só o período novo: o painel junta com a base.", nota=True):
            ups = st.file_uploader("Arquivos", type=["xlsx", "csv"], accept_multiple_files=True,
                                   key=f"up_{st.session_state.get('up_nonce', 0)}", label_visibility="collapsed")
            if not ups:
                st.markdown('<div class="vs">Formatos aceitos: <b>histórico</b> (coluna A = emissora, B = período <i>SAL - JUN/2026 A AGO/2026</i>, '
                            'C = OPM#) e <b>ranking de concorrência</b> (uma linha de períodos, abaixo OPM# / SHT% / ALCM# / TMED# e uma linha por '
                            'emissora). Valores com # são marcados como amostra pequena.</div>', unsafe_allow_html=True)
            else:
                lidos = []
                for u in ups:
                    try:
                        d = M.ler_arquivo(u, u.name)
                    except Exception as ex:
                        st.error(f"Não consegui ler {u.name}: {ex}")
                        continue
                    lidos.append(d)
                    st.markdown(f'<div class="vs">📄 <b>{u.name}</b>: {len(d)} linhas reconhecidas'
                                + (f' · {", ".join(NOME.get(x, x) for x in d["emissora"].unique())} · '
                                   f'{rot_movel(d["fim"].min())} → {rot_movel(d["fim"].max())}' if len(d) else "") + "</div>",
                                unsafe_allow_html=True)
                novo = pd.concat(lidos, ignore_index=True).drop_duplicates(["emissora", "fim"], keep="last") if lidos else pd.DataFrame()
                if novo.empty:
                    st.error("Nenhuma linha no formato do EasyMedia foi encontrada nos arquivos enviados.")
                else:
                    modo = st.radio("Como aplicar", ["Juntar com a base atual (recomendado)", "Substituir a base inteira"],
                                    horizontal=True, key="up_modo")
                    juntar = modo.startswith("Juntar")
                    n, a = M.mesclar(MOVEL, novo)[1:]          # o que muda no que o painel mostra
                    m = M.mesclar(BASE, novo)[0] if juntar else novo.copy()   # o que se grava (inclui os excluídos)
                    sai = len(MOVEL) - len(m.merge(MOVEL[["emissora", "fim"]], on=["emissora", "fim"])) if not juntar else 0
                    kk = [("Períodos novos", br(len(n)), ", ".join(sorted({rot_movel(x) for x in n["fim"]}))[:60] or "nenhum", VERDE if len(n) else CINZA),
                          ("Valores alterados", br(len(a)), "o arquivo novo prevalece", AMARELO if len(a) else CINZA)]
                    if not juntar:
                        kk.append(("Removidos", br(sai), "períodos que não estão no arquivo", VERMELHO if sai else CINZA))
                    kpis(kk)
                    # checagens
                    avisos = []
                    for e in [x for x in m["emissora"].unique() if x in EMISSORAS]:
                        s = m[m["emissora"] == e].set_index("fim")["opm"].sort_index()
                        meses = pd.date_range(s.index.min(), s.index.max(), freq="MS")
                        falta = [rot_movel(x) for x in meses if x not in s.index and x != pd.Timestamp("2016-09-01")]
                        if falta:
                            avisos.append(f"{NOME.get(e, e)}: faltam {', '.join(falta[:6])}{'…' if len(falta) > 6 else ''}")
                        ss = s[s.index.isin(n["fim"][n["emissora"] == e])] if len(n) else s.iloc[:0]
                        for t, v in ss.items():
                            ant = s.get(t - pd.DateOffset(months=1))
                            if ant and abs(v / ant - 1) > .15:
                                avisos.append(f"{NOME.get(e, e)} {rot_movel(t)}: salto de {pct(v / ant - 1, 1, True)} sobre o banco anterior ({rot_movel(t - pd.DateOffset(months=1))}) — confira")
                    if len(n) and n["emissora"].isin(EMISSORAS).any() and n.loc[n["emissora"].isin(EMISSORAS), "emissora"].nunique() < len(EMISSORAS):
                        avisos.append("O arquivo só traz períodos novos de uma emissora.")
                    for av in avisos:
                        st.markdown(f'<div class="aviso">⚠️ {av}</div>', unsafe_allow_html=True)
                    if len(n) or len(a):
                        tab = pd.concat([n.assign(opm_antes=np.nan, tipo="novo"), a.assign(tipo="alterado")], ignore_index=True)
                        tab = pd.DataFrame({"Emissora": tab["emissora"].map(lambda x: NOME.get(x, x)), "Período": tab["fim"].map(rot_movel),
                                            "Antes": tab["opm_antes"].map(lambda v: "" if pd.isna(v) else br(v)),
                                            "Agora": tab["opm"].map(br), "": tab["tipo"]})
                        st.dataframe(tab, hide_index=True, width="stretch", height=min(40 + 35 * len(tab), 320))
                    if tem_senha:
                        st.text_input("Senha", type="password", key="pw_up")
                    pode = (len(n) or len(a) or not juntar)
                    if st.button("Aplicar atualização", type="primary", disabled=not pode, key="bt_up"):
                        if not _senha_ok("pw_up"):
                            st.error("Senha incorreta.")
                        else:
                            excl = set(PAR.get("excluidos", []))
                            if juntar:   # o que foi reenviado volta a valer, mesmo que o banco tivesse sido excluído
                                excl -= {chave_banco(f, e) for f, e in zip(novo["fim"], novo["emissora"])}
                                excl -= {chave_banco(f) for f in novo["fim"]}
                            else:        # substituir: o que não está no arquivo sai (inclusive o que vem das planilhas de dados/)
                                ficam = {chave_banco(f, e) for f, e in zip(novo["fim"], novo["emissora"])}
                                excl = (excl - ficam - {chave_banco(f) for f in novo["fim"]}) | \
                                       ({chave_banco(f, e) for f, e in zip(MOVEL["fim"], MOVEL["emissora"])} - ficam)
                            salvar_base(m, f"upload: {', '.join(u.name for u in ups)}", excl)
                            _recarrega(f"Base atualizada: {len(n)} períodos novos e {len(a)} valores alterados. "
                                       "As projeções e validações foram refeitas com os dados novos.")
                    if not pode:
                        st.markdown('<div class="vs">Nada para atualizar: a base já tem esses valores.</div>', unsafe_allow_html=True)
    with l[1]:
        with cartao("Versões anteriores", "Cada atualização guarda uma cópia da base anterior", nota=True):
            bks = sorted(glob.glob(os.path.join("backups", "radio_movel_*.csv")), reverse=True)
            if not bks:
                st.markdown('<div class="vs">Nenhuma versão anterior ainda.</div>', unsafe_allow_html=True)
            else:
                fmt_bk = lambda f: datetime.strptime(os.path.basename(f)[12:27], "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
                bk = st.selectbox("Versão", bks, format_func=fmt_bk, key="bk_sel")
                if tem_senha:
                    st.text_input("Senha", type="password", key="pw_bk")
                if st.button("Restaurar esta versão", key="bt_bk"):
                    if not _senha_ok("pw_bk"):
                        st.error("Senha incorreta.")
                    else:
                        salvar_base(pd.read_csv(bk, parse_dates=["inicio", "fim"]), f"restaurada a versão de {fmt_bk(bk)}")
                        _recarrega(f"Versão de {fmt_bk(bk)} restaurada.")
            st.download_button("⬇️ Baixar a base atual (CSV)", MOVEL.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig"),
                               "audiencia_radio_base.csv", "text/csv", key="dl_base")

    gerenciar_bancos(tem_senha)

    with cartao("2 · Números oficiais e previsão do BI",
                "Edite e salve. Os oficiais entram no fator de conversão do fechamento; use chaves como 2026, 1S26 e 2S26.", nota=True):
        c = st.columns([1.3, 1])
        of = pd.DataFrame([(e, k, v) for e, d in OFICIAL.items() for k, v in d.items()], columns=["Emissora", "Período", "OPM# oficial"])
        ed = c[0].data_editor(of, num_rows="dynamic", hide_index=True, width="stretch", key=f"ed_of_{st.session_state.get('up_nonce', 0)}",
                              column_config={"Emissora": st.column_config.SelectboxColumn(options=EMISSORAS, required=True),
                                             "Período": st.column_config.TextColumn(help="Ano (2026) ou semestre (1S26, 2S26)", required=True),
                                             "OPM# oficial": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True)})
        bi = pd.DataFrame([(e, d.get("S1"), d.get("S2"), d.get("ano")) for e, d in PREV_BI.items()],
                          columns=["Emissora", "1º semestre", "2º semestre", "Ano"])
        ed_bi = c[1].data_editor(bi, hide_index=True, width="stretch", key=f"ed_bi_{st.session_state.get('up_nonce', 0)}",
                                 column_config={k: st.column_config.NumberColumn(min_value=0, step=100, format="%d")
                                                for k in ["1º semestre", "2º semestre", "Ano"]})
        c[1].markdown('<div class="vs">Previsão do BI usada como referência e patamar padrão de 2026.</div>', unsafe_allow_html=True)
        if tem_senha:
            st.text_input("Senha", type="password", key="pw_of")
        if st.button("Salvar números", key="bt_of"):
            if not _senha_ok("pw_of"):
                st.error("Senha incorreta.")
            else:
                ed = ed.dropna()
                ruim = [p for p in ed["Período"].astype(str) if not re.fullmatch(r"\d{4}|[12]S\d{2}", p.strip())]
                if ruim:
                    st.error(f"Período inválido: {', '.join(ruim)}. Use 2026, 1S26 ou 2S26.")
                else:
                    par = json.load(open("parametros.json", encoding="utf-8"))
                    par["oficial"] = {e: {str(r["Período"]).strip(): int(r["OPM# oficial"]) for _, r in ed[ed["Emissora"] == e].iterrows()}
                                      for e in EMISSORAS}
                    par["previsao_bi"] = {r["Emissora"]: {"S1": int(r["1º semestre"]), "S2": int(r["2º semestre"]), "ano": int(r["Ano"])}
                                          for _, r in ed_bi.dropna().iterrows()}
                    _grava_parametros(par)
                    _recarrega("Números oficiais e previsão do BI salvos.")
    st.markdown('<div class="rodape">A atualização vale para todo mundo que estiver com o link aberto (basta recarregar a página). '
                'Sem a pasta do Drive configurada, ela dura enquanto a sessão do Colab estiver aberta: para a próxima sessão, '
                'baixe a base ou deixe a planilha nova no lugar da antiga.</div>', unsafe_allow_html=True)


# =================================================================================== relatório em PDF
st.session_state["_graf"] = st.session_state.get("_graf_run", [])
st.session_state["_kpis"] = st.session_state.get("_kpis_run", [])


@_dialogo("Exportar relatório em PDF")
def janela_pdf():
    import relatorio
    ss = st.session_state
    graf, kps = ss.get("_graf", []), ss.get("_kpis", [])
    titulo = st.text_input("Título do relatório", value="Painel de Audiência · Rádio", key="pdf_titulo")
    st.markdown('<div class="vs">Escolha o que entra no relatório. Os gráficos saem com os filtros que estão na tela agora.</div>',
                unsafe_allow_html=True)
    def _itens(aba, padrao, pref):
        """Caixas de seleção dos cartões e gráficos de uma aba. Devolve (gráficos marcados, cartões marcados)."""
        itens = [g for g in graf if g["aba"] == aba]
        blocos = [k for k in kps if k["aba"] == aba]
        gs, cs = [], []
        if blocos and st.checkbox("Cartões de indicadores", value=padrao, key=f"{pref}_k"):
            for b in blocos:
                cs += b["cartoes"]
        cols = st.columns(2)
        vistos = set()
        for i, g in enumerate(itens):
            if g["chave"] in vistos:
                continue
            vistos.add(g["chave"])
            if cols[i % 2].checkbox(g["titulo"] or g["chave"], value=padrao, key=f"{pref}_g_{g['chave']}"):
                gs.append(g)
        return gs, cs

    st.markdown("**Visão geral**")
    escolhidos, cartoes = _itens("Visão geral", True, "pdf_vg")
    proj_g, proj_c = [], []
    if any(g["aba"] == "Projeções e cenários" for g in graf):
        st.markdown("**Projeções e cenários**")
        if st.toggle("Incluir as projeções no relatório (entram nas últimas páginas)", value=False, key="pdf_proj"):
            proj_g, proj_c = _itens("Projeções e cenários", True, "pdf_pj")
    c = st.columns([1.2, 1.4, 2])
    if c[0].button("Gerar PDF", type="primary", key="pdf_gerar", disabled=not (escolhidos or cartoes or proj_g or proj_c)):
        with st.spinner("Montando o relatório…"):
            ss["_pdf_bytes"] = relatorio.gera_pdf(
                [(g["titulo"], g["sub"], g["fig"]) for g in escolhidos], cartoes=cartoes, titulo=titulo,
                final={"titulo": "Projeções e cenários", "cartoes": proj_c,
                       "graficos": [(g["titulo"], g["sub"], g["fig"]) for g in proj_g]} if (proj_g or proj_c) else None,
                subtitulo="Bahia FM e GFM 90.1 · OPM# 05h–05h · todos os dias · Grande Salvador · Kantar IBOPE EasyMedia4 (Rádio Recall)",
                logo_b64=LOGO_B64, filtros=(("DEMONSTRAÇÃO · DADOS FICTÍCIOS · " if PAR.get("demo") else "") + ss.get("_filtros_txt", "")),
                marca="DADOS FICTÍCIOS" if PAR.get("demo") else None,
                fonte="Fonte: Kantar IBOPE EasyMedia4 (Rádio Recall) · relatório gerado pelo Painel de Audiência")
    if ss.get("_pdf_bytes"):
        c[1].download_button("⬇️ Baixar PDF", ss["_pdf_bytes"], file_name=f"painel_radio_{datetime.now():%Y%m%d_%H%M}.pdf",
                             mime="application/pdf", key="pdf_baixar", type="primary")
        c[2].markdown(f'<div class="vs" style="margin-top:8px">{len(escolhidos) + len(proj_g)} gráfico(s) · '
                      f'{len(cartoes) + len(proj_c)} cartão(ões)' + (" · projeções no fim" if (proj_g or proj_c) else "") + '</div>',
                      unsafe_allow_html=True)


if st.session_state.pop("_abrir_pdf", False):
    st.session_state.pop("_pdf_bytes", None)
    janela_pdf()

VERSAO_PAINEL = "21/10/2026 · v9 (modo demonstração)"
_rodape = st.container(key="notas")
with _rodape, st.expander("🧩 Visualizações da tela inicial"):
    st.markdown('<div class="vs">Marque o que deve aparecer na Visão geral. As padrão já vêm marcadas; para tirar uma '
                'visualização, basta desmarcar. A escolha fica no link da página.</div>', unsafe_allow_html=True)
    _ops = list(VIS_TODAS)
    st.pills("Visualizações", _ops, selection_mode="multi", default=st.session_state["vis_sel"], key="vis_w",
             format_func=lambda c: ("★ " if c in VIS_PADRAO else "＋ ") + VIS_TODAS[c], on_change=_guarda_vis,
             label_visibility="collapsed")
    c_ = st.columns([1, 1, 4])
    if c_[0].button("Voltar ao padrão", key="vis_padrao"):
        st.session_state["vis_sel"] = list(VIS_PADRAO)
        st.session_state.pop("vis_w", None)
        st.query_params.pop("vis", None)
        st.rerun()
    st.markdown('<div class="vs">★ padrão · ＋ visualização extra</div>', unsafe_allow_html=True)

_rodape.markdown(f'<div class="vs" style="margin:2px 0 0">Versão do painel: {VERSAO_PAINEL} · Streamlit {st.__version__}</div>',
                 unsafe_allow_html=True)
with _rodape, st.expander("⚙ Atualizar dados"):
    pagina_atualizar()

with _rodape, st.expander("ⓘ Notas metodológicas"):
    st.markdown(f"""
#### Fonte
**Kantar IBOPE EasyMedia4 · Rádio Recall** — OPM# (ouvintes por minuto, em números absolutos), 05h–05h, todos os dias, ambos os sexos,
Grande Salvador. Planilha *Histórico Audiência Rádio 2016 a 2026* (GFM e Bahia FM, uma aba por ano) e ranking
*Concorrência 05h às 05h* (todas as emissoras medidas, de 2024 em diante, com OPM#, share, alcance e tempo médio).

**Atenção à faixa horária:** o painel usa **05h–05h** (dia inteiro). Os slides de análise trimestral usam **05h–00h**, por isso os números
não batem com os do slide (ex.: GFM jun–ago/26 = 27.119 aqui e 32.985 no slide). As cores das emissoras seguem o slide.
Valores com **#** no EasyMedia têm amostra pequena e aparecem hachurados nas barras.

#### Como ler
- **Trimestre móvel:** cada valor do EasyMedia cobre 3 meses (jan–mar, fev–abr, mar–mai…). Dois valores vizinhos têm 2 meses em comum,
  então a série mensal é suave por construção e uma variação de um mês para o outro reflete só 1/3 de dado novo.
- **Trimestre fechado:** os móveis que terminam em mar, jun, set e dez (T1 a T4). Não têm sobreposição e são a base das projeções.
- **Média anual** neste painel = média dos 4 trimestres fechados. O número oficial do ano é processado à parte e difere dela;
  o fator médio oficial ÷ média é **{br(K_ANO[0], 4)}** (desvio {br(K_ANO[1], 4)}, {K_ANO[2]} pares ano × emissora).

#### Projeções
- **Combinação (padrão):** média de 4 modelos (média dos últimos 4 trimestres, suavização exponencial simples, AR(1) com dummy de pandemia
  e nível local com dummy de pandemia). Foi o método escolhido no estudo de projeção V3 (28/09/2026).
- **Nowcast:** o trimestre móvel que termina no mês anterior ao fim do trimestre em curso (ex.: jun–ago para jul–set) já contém 2 dos 3 meses.
  Ele entra como leitura do trimestre em curso, e os trimestres seguintes são projetados a partir dele.
- **Faixas (50%, 80%, 95%):** vêm dos **erros reais** do método numa validação com origem móvel (até 30 origens, sem projeções feitas durante a
  pandemia ou para dentro dela), simulados com uma t multivariada (6 g.l.) que preserva a correlação entre horizontes. A dispersão é alargada
  pelo fator que faz a faixa de 80% cobrir 80% na validação (entre 1,0 e 1,5).
- **Fechamento do ano:** média dos trimestres (realizados + simulados) × fator de conversão sorteado com a média e o desvio observados.
- **Projetar a partir de:** escolha um trimestre passado para ver como a projeção teria se saído. O painel usa só o que se sabia na época,
  inclusive na validação.
- **Comparação de métodos:** MAPE nas mesmas origens, h = 1 a 4, sem nowcast. O ingênuo (repete o último) é a régua: um método útil deve errar menos.

#### Como atualizar os dados
- **Pelo painel (mais rápido):** **⚙ Atualizar dados** (no rodapé da página) → envie a planilha nova do EasyMedia (.xlsx inteiro ou só o CSV do ano corrente) →
  confira os períodos novos e os valores alterados → **Aplicar atualização**. O link continua o mesmo; quem estiver com ele aberto só recarrega.
  Cada atualização guarda a versão anterior, que pode ser restaurada.
- **Pelo notebook:** troque a planilha na pasta do Colab (ou na pasta do Drive) e rode a célula de novo.
- **Entre sessões do Colab:** defina `PASTA_DRIVE` na célula. A base atualizada e os números oficiais editados ficam no Drive
  e são carregados sozinhos na próxima vez.

#### Cuidados
- Poucas origens de validação (e as de horizontes vizinhos se sobrepõem): leia as probabilidades como ordem de grandeza (arredondadas a 5 p.p.).
- A validação cobre um período de queda: todos os métodos tendem a projetar acima do realizado. Use **Corrigir viés** como limite pessimista.
- 2016 fica fora da modelagem porque falta o jul–set/2016. A pandemia (2020T2–2021T2) entra como dummy ou é excluída da base.
- OPM é absoluto: se a Kantar atualizar o universo, o nível muda sem mudança real de audiência.
- A previsão do Power BI (CAGR 2023–2025) é uma extrapolação, não uma meta. Na validação anual do estudo, ela errou cerca do dobro da Combinação.
""")
