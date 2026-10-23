# Painel de Audiência · Rádio (Bahia FM e GFM 90.1)

Painel Streamlit com histórico, projeções e cenários da audiência (OPM# 05h–05h, Grande Salvador, Kantar IBOPE EasyMedia4).

## Estrutura
```
streamlit_app.py      # o painel
modelos.py            # leitura dos dados, modelos, validação e simulação
parametros.json       # números oficiais e previsão do BI (editáveis no painel)
dados/                # planilhas do EasyMedia: histórico (GFM e Bahia FM) e ranking de concorrência (.xlsx ou .csv)
requirements.txt
.streamlit/config.toml
```

## Atualizar os dados
- **Pelo painel:** aba *Atualizar dados* → enviar a planilha ou o CSV → *Aplicar atualização*.
  Com o `[github]` configurado em Secrets, a base é gravada no repositório (`radio_movel.csv`) e não se perde.
- **Pelo GitHub:** substituir as planilhas em `dados/` (Add file → Upload files). O app recarrega sozinho.
- O ranking de concorrência (formato largo, com OPM#, SHT%, ALCM# e TMED# por banco) também atualiza GFM e Bahia FM.
  Cada coluna é lida pelo rótulo da métrica: o período pode vir só na 1ª coluna do bloco (como no EasyMedia) ou repetido
  em todas, e a linha de métricas pode ficar acima ou abaixo da linha de períodos. A linha TOTAL RADIO é ignorada.
- **Gerenciar bancos** (aba *Atualizar dados*, cartão 3): excluir um banco inteiro ou só uma emissora, remover um arquivo
  enviado e restaurar o que foi excluído. Bancos com salto acima de 50% sobre o anterior aparecem marcados para conferência.
  Os excluídos ficam em `parametros.json` (`excluidos`) e cada mudança guarda a base anterior em `backups/`.
- Precedência: os envios feitos pelo painel (`radio_movel.csv`) prevalecem sobre as planilhas de `dados/`, que completam o resto.

## Rodar localmente
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```
