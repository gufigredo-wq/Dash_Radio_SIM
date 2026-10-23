# Painel de Audiência · Rádio

Audiência (OPM#) da Bahia FM e da GFM 90.1 e das concorrentes na Grande Salvador (Kantar IBOPE EasyMedia4),
com projeção probabilística do fechamento do ano e relatórios em PDF.

- **Visão geral**: cartões do último banco, resumo em frases, evolução, média anual, ranking, curva do ano, mapa de calor
  e comparativo. Mais visualizações em **🧩 Visualizações da tela inicial** (rodapé): share, alcance, tempo médio,
  variação anual, posição no ranking, participação, sazonalidade e tendência estatística (Mann-Kendall).
- **Projeções e cenários**: projeção em leque, distribuição do fechamento, chance por patamar, validação e cenário manual.
- **📄 Exportar PDF** (cabeçalho): escolha de gráficos, tabelas, cartões e resumo; projeções opcionais nas últimas páginas.
- **⚙ Atualizar dados** (rodapé): envio de planilhas do EasyMedia com validação, gerenciamento de bancos, números oficiais.
- **🌙 Modo escuro** no cabeçalho.

## Rodar
```
pip install -r requirements.txt
streamlit run streamlit_app.py                  # dados reais (pasta dados/)
PAINEL_MODO=demo streamlit run streamlit_app.py # demonstração com dados fictícios
pytest testes -q                                # testes automáticos
```
Modo demonstração também com `modo = "demo"` nos Secrets ou com um arquivo vazio `MODO_DEMO` na raiz.

Detalhes técnicos (arquivos, fluxo de dados, configuração, hospedagem interna): `DOCUMENTACAO_TECNICA.md`.
