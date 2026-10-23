# Painel de Audiência · Rádio — documentação técnica

Painel web interno da Rede Bahia com a audiência de rádio (OPM#) da **Bahia FM** e da **GFM 90.1** e das emissoras
concorrentes na Grande Salvador, a partir das exportações do **Kantar IBOPE EasyMedia4 (Rádio Recall)**, com projeção
probabilística do fechamento do ano e exportação de relatórios em PDF.

---

## 1. Visão geral

| Item | Descrição |
|---|---|
| Linguagem | Python 3.12 |
| Framework web | Streamlit 1.65 (aplicação única, sem banco de dados) |
| Gráficos | Plotly (tela) e Matplotlib (PDF) |
| Modelos | pandas, numpy, scipy, statsmodels (projeção e validação) |
| Entrada de dados | planilhas `.xlsx`/`.csv` exportadas do EasyMedia |
| Armazenamento atual | arquivos no próprio repositório (pasta `dados/`, `radio_movel.csv`, `parametros.json`) |
| Hospedagem atual | Streamlit Community Cloud, a partir de repositório privado no GitHub (provisório) |
| Usuários | ~10 pessoas (Pesquisa e Inteligência, Jornalismo, Esporte, Entretenimento) |

A aplicação não depende de serviços externos para funcionar. O único acesso externo, opcional, é a API do GitHub
para gravar os envios feitos pela tela (ver seção 5).

---

## 2. Arquivos

| Arquivo | Função |
|---|---|
| `streamlit_app.py` | Interface: abas Visão geral e Projeções, cabeçalho, filtros, gráficos, rodapé (Atualizar dados, Visualizações, Notas), janela de exportação em PDF |
| `modelos.py` | Leitura das planilhas do EasyMedia, base de trimestres móveis, métodos de projeção, validação (origem móvel) e simulação Monte Carlo |
| `relatorio.py` | Geração do PDF: redesenha os gráficos do Plotly com Matplotlib e monta as páginas (sem navegador nem kaleido) |
| `demo_dados.py` | Gera dados **fictícios** no mesmo formato do EasyMedia (modo demonstração) |
| `parametros.json` | Números oficiais (anual e semestral), previsão do BI, bancos excluídos, data da última atualização |
| `dados/*.xlsx` | Planilhas do EasyMedia: histórico (uma aba por ano), ranking de concorrência, totais de mercado |
| `radio_movel.csv` | Base gravada pelo painel quando há envios pela tela (prevalece sobre `dados/`) |
| `backups/` | Cópia da base anterior a cada mudança (criada pelo painel) |
| `cache_modelos/` | Cache das validações (recriado automaticamente; não versionar) |
| `.streamlit/config.toml` | Tema claro, cor principal, menu do Streamlit escondido, limite de upload |
| `requirements.txt` | Dependências com versões fixas |
| `testes/test_painel.py` | Testes automáticos (pytest) no modo demonstração |
| `.github/workflows/testes.yml` | Roda os testes a cada envio ao GitHub |

---

## 3. Fluxo dos dados

```
EasyMedia (exportação manual)
        │  .xlsx / .csv
        ▼
dados/  ──────────────┐
                      ├──► modelos.ler_arquivo()  ──►  base de trimestres móveis (emissora × banco: OPM#, SHT%, ALCM#, TMED#)
envio pela tela  ─────┘          │                                  │
(⚙ Atualizar dados →             │                                  ├──► gráficos e tabelas (Visão geral)
 radio_movel.csv)                ▼                                  └──► projeção + Monte Carlo (Projeções)
                        parametros.json (oficiais, previsão do BI, excluídos)
```

1. A cada carga, o painel lê **todas** as planilhas de `dados/` e o `radio_movel.csv` (se existir); os envios feitos
   pela tela prevalecem. Bancos marcados como excluídos em `parametros.json` ficam fora.
2. O leitor identifica cada coluna pelo **rótulo da métrica** (OPM#, SHT%, ALCM#, TMED#), não pela posição; aceita o
   período mesclado ou repetido e a linha de métricas acima ou abaixo da linha de períodos.
3. Linhas `TOTAL EMISSORAS/FM/WEB/RADIO` entram como totais de mercado: aparecem nos gráficos, mas ficam fora do
   ranking, das contagens e da projeção.
4. As projeções só usam GFM e Bahia FM. Resultados de validação ficam em cache (`cache_modelos/`) e são refeitos quando
   a base muda.

**Formatos aceitos no envio**: histórico (A = emissora, B = período `SAL - JUN/2026 A AGO/2026`, C = OPM#) e ranking
(linha de períodos, linha de métricas, uma linha por emissora `SAL - NOME`). Valores com `#` são marcados como
amostra pequena.

**Validação do envio** (antes de aplicar): mesmo período com valores diferentes, OPM# maior que o alcance (coluna
trocada), OPM# ≤ 0, share fora de 0–100%, períodos no futuro (bloqueiam até confirmação); emissoras novas com nome
parecido com outra já existente e mudanças acima de 50% em valores já existentes (avisos).

---

## 4. Modos de operação

| Modo | Como ativar | Dados |
|---|---|---|
| Real | padrão | `dados/`, `radio_movel.csv`, `parametros.json` |
| Demonstração | `modo = "demo"` nos Secrets, **ou** variável de ambiente `PAINEL_MODO=demo`, **ou** arquivo vazio `MODO_DEMO` na raiz | gerados por `demo_dados.py` em `demo_runtime/` (fora do Git); nada é gravado no GitHub |

No modo demonstração, o painel mostra a faixa "Ambiente de demonstração" e os PDFs saem com marca-d'água "DADOS
FICTÍCIOS". O código é o mesmo nos dois modos.

---

## 5. Configuração (Secrets do Streamlit ou variáveis do servidor)

```toml
senha_atualizacao = "..."      # senha pedida para aplicar envios e alterações na tela (opcional)
modo = "demo"                  # opcional: liga o modo demonstração

[github]                       # opcional: grava os envios no repositório (necessário só no Streamlit Cloud)
token  = "github_pat_..."      # fine-grained, Contents: Read and write, só neste repositório
repo   = "usuario/repositorio"
branch = "main"
```

Sem o bloco `[github]`, os envios pela tela valem até o app reiniciar (o disco do Streamlit Cloud é temporário). Num
servidor próprio, com disco permanente, o bloco é dispensável.

---

## 6. Executar

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py --server.port 8501            # real
PAINEL_MODO=demo streamlit run streamlit_app.py              # demonstração
pip install pytest==8.3.4 && pytest testes -q                # testes (~30 s)
```

Uso de recursos: ~400–700 MB de memória; a primeira carga calcula as projeções (~10 s num computador comum, mais no
Streamlit Cloud); depois fica em cache e as interações levam < 1 s.

---

## 7. Hospedagem na rede interna (sugestão)

- **Mínimo**: uma VM Linux com Python 3.12, o app rodando como serviço (`systemd`) atrás de um proxy reverso (nginx) com
  HTTPS e o endereço interno. O Streamlit usa **WebSocket**: o proxy precisa repassar `Upgrade`/`Connection`.
- **Acesso restrito**: autenticação no proxy (SSO/Entra ID via oauth2-proxy) ou o login OIDC nativo do Streamlit
  (`st.login`); hoje a única proteção própria do app é a senha de atualização.
- **Dados**: a pasta do app em disco permanente já resolve. Para atualização automática, a leitura pode passar a vir do
  SharePoint (Microsoft Graph) ou de um banco (PostgreSQL); as funções de leitura e gravação estão concentradas em
  `carregar()` e `salvar_base()` no `streamlit_app.py`.
- **Recursos**: 2 vCPU e 2–4 GB de RAM sobram para o volume atual (poucos MB de dados).

---

## 8. Segurança e dados

- Os dados do EasyMedia são de uso interno; o rodapé das exportações do IBOPE restringe compartilhamento e uso em
  sistemas internos e modelos de IA sem anuência — confirmar a cobertura contratual.
- O token do GitHub, se usado, deve ficar só nos Secrets (nunca no repositório).
- O histórico do Git guarda versões anteriores dos dados: um repositório que já teve dados reais não deve ser tornado
  público. A versão de demonstração deve ser publicada a partir de um repositório novo.

---

## 9. Limitações conhecidas

- Alguns recursos visuais (arrastar os quadros de emissoras, animações, clique fora para desmarcar, contagem dos
  números) usam scripts no navegador sobre a página do Streamlit; podem precisar de ajuste numa atualização de versão.
  Por isso as versões estão fixas no `requirements.txt`.
- Dois envios simultâneos pela tela: vale o último.
- A projeção é recalculada a cada mudança da base; com o histórico atual, isso leva alguns segundos.
