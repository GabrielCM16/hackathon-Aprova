# API do Prumo (backend)

Base: `http://localhost:8000` · JSON em UTF-8 · documentação interativa em `/docs`.

O fluxo tem duas fases:

1. **Contexto (antes da reunião).** Os arquivos do cliente (histórico de conversas, PDFs, imagens, planilhas) são
   analisados **uma vez** e viram um `contexto.md` consolidado, um glossário, um checklist e as perguntas rápidas.
2. **Sessão (durante a reunião).** A sessão é ligada a um contexto. O áudio é só transcrito (rota rápida).
   A análise roda em segundo plano a cada ~30s de fala, marca o checklist, sugere perguntas e anota.
   A interface lê o estado por `GET /copiloto` ou recebe tudo ao vivo por `GET /eventos` (SSE).

---

## Como cada parte da tela usa a API

| Tela | Rota |
|---|---|
| Card "Preparação da sessão" + mensagem de abertura | `POST /sessoes` → `preparacao`, ou `GET /sessoes/{id}/preparacao` |
| Modo de escuta (Gravação com aviso / Escuta sem guardar / Modo notas) | `PATCH /sessoes/{id}` `{modo}` |
| Caixa "Participantes informados" + botão **Iniciar reunião** | `POST /sessoes/{id}/iniciar` `{aviso_confirmado: true}` |
| Status no topo (Preparando / Ouvindo / Finalizada) | `copiloto.estado` |
| "Última fala" | `copiloto.ultima_fala` |
| Aba Checklist: barra "4 de 10 · 40%" | `copiloto.progresso` (`respondida`, `total`, `percentual`) |
| Grupo "Confirmados pelo contexto" | itens com `fonte == "contexto"` |
| Grupo "Pendentes de alinhamento" | itens com `status` `pendente` ou `parcial` |
| Código `CHK-05`, título, valor à direita | `codigo`, `titulo`, `resposta` ou `valor_referencia` |
| Expandir item (pergunta, trecho, hora) | `pergunta`, `trecho`, `hora`, `diverge` |
| Marcar item à mão | `PATCH /sessoes/{id}/checklist/{item_id}` |
| Busca no checklist | feita no cliente, sobre `copiloto.checklist` |
| Chips "Rápido: Qual o recuo? …" | `copiloto.perguntas_rapidas` |
| Caixa "Pergunte algo rápido" | `POST /sessoes/{id}/perguntar` |
| Mensagens do Prumo na conversa (pergunte agora, anotações) | `copiloto.sugestao_pergunta_imediata`, `perguntas_sugeridas`, `anotacoes` |
| Encerrar e ata | `POST /sessoes/{id}/finalizar`, `GET /sessoes/{id}/ata` |

---

## 1. Contextos

Na pasta `backend/contextos/<id>/`:

```
meta.json               nome, descrição
arquivos/               originais (pode copiar arquivos direto aqui e chamar /processar)
extracoes/              uma extração por arquivo, feita só quando o arquivo é novo ou mudou
processados.json        hash de cada arquivo já extraído
contexto.md             tudo consolidado (o "txt cheio"); editável à mão
glossario.json          termos com a grafia certa → melhora a transcrição
checklist.json          itens a alinhar
perguntas_rapidas.json  chips de pergunta rápida
```

Formatos aceitos: `.txt .md .csv .json .html .xml .docx .pdf .png .jpg .jpeg .webp .heic .mp3 .wav .m4a .ogg .webm`.
Acima de 18 MB o arquivo vai pela File API do Gemini.

### `GET /contextos`
Lista os contextos.
```json
[{"id": "serra-do-sabia-alvara", "nome": "Alvará de Construção Residencial · Serra do Sabiá",
  "descricao": "...", "criado_em": "2026-10-24T13:53:18", "itens_checklist": 12, "tem_contexto": true}]
```

### `POST /contextos`
```json
{"nome": "Alvará de Construção Residencial · Serra do Sabiá", "descricao": "opcional", "id": "opcional"}
```
O `id` padrão é gerado a partir do nome. Retorna o contexto completo, ou `409` se o id já existir.

### `GET /contextos/{id}`
Contexto completo: `arquivos` (com `processado_em` e `erro`), `contexto`, `glossario`, `checklist` e `perguntas_rapidas`.

### `POST /contextos/{id}/arquivos`
`multipart/form-data` com um ou mais campos `arquivos`. Só salva os arquivos; para analisar, chame `/processar`.

### `DELETE /contextos/{id}/arquivos/{nome}`
Remove o arquivo e a extração dele.

### `POST /contextos/{id}/processar?forcar=false`
Extrai **só os arquivos novos ou alterados** e reconsolida tudo. Com `forcar=true`, refaz todos.
Leva de 10s a 2 min, conforme o tamanho.
```json
{"extraidos": ["01_historico_reunioes.txt"], "erros": {}, "consolidado": true, "itens_checklist": 12, ...}
```
Na consolidação, os itens novos do checklist entram sem duplicar os existentes. Os confirmados ficam no topo e a lista é renumerada (`CHK-01…`).

### `GET /contextos/{id}/contexto` (texto) · `PUT /contextos/{id}/contexto` `{texto}`
Lê ou edita o `contexto.md`.

### `PUT /contextos/{id}/glossario` `{termos: [...]}`
Substitui o glossário, removendo duplicados sem diferenciar maiúsculas.

### `PUT /contextos/{id}/perguntas-rapidas` `{perguntas: [...]}`

### `GET /contextos/{id}/checklist` · `PUT` (substitui tudo) · `POST` (adiciona um)
Item do checklist do contexto:
```json
{
  "id": "a1b2c3d4",
  "codigo": "CHK-08",
  "titulo": "Recuo frontal mínimo da ZR2",
  "pergunta": "Qual é o recuo frontal mínimo na ZR2 na versão publicada da lei?",
  "categoria": "Parâmetros",
  "obrigatoria": true,
  "origem": "ia",
  "valor_referencia": "4,50 m",
  "confirmado_no_contexto": false,
  "resposta_contexto": null
}
```
- `valor_referencia`: o valor que o material indica, mas que ainda precisa ser confirmado com o cliente. É o número cinza da tela.
- `confirmado_no_contexto`: o cliente já confirmou o valor numa reunião anterior. A resposta está em `resposta_contexto`.

---

## 2. Sessões

Na pasta `backend/sessoes/<id>/`: `sessao.json`, `segmentos.jsonl` (fonte da verdade), `transcricao.txt`,
`checklist.json`, `anotacoes.jsonl`, `chat.jsonl`, `analise.json/.md` e `ata.md`.

### `POST /sessoes`
```json
{"contexto_id": "serra-do-sabia-alvara", "titulo": "Alvará de Construção Residencial · Serra do Sabiá",
 "horario": "14:00", "modo": "gravacao", "id": "opcional"}
```
Cria a sessão e copia o checklist do contexto. Os itens confirmados chegam como `respondida`, com `fonte: "contexto"`.
Retorna o estado e a `preparacao`:
```json
{
  "titulo": "Alvará de Construção Residencial · Serra do Sabiá",
  "horario": "14:00",
  "contexto": {"id": "serra-do-sabia-alvara", "nome": "..."},
  "total": 12, "confirmados_contexto": 5, "a_perguntar": 7,
  "modo": "gravacao", "modos": ["gravacao", "sem_guardar", "notas"],
  "aviso_confirmado": false, "estado": "preparando",
  "mensagem": "Reunião de hoje, 14:00: Alvará de ... O checklist tem 12 itens: 5 já estão confirmados pelo contexto do cliente e 7 faltam perguntar."
}
```

**Modos**

| `modo` | Na tela | Comportamento |
|---|---|---|
| `gravacao` | Gravação com aviso | transcreve; guarda o áudio de falhas (e todo o áudio se `SALVAR_AUDIO=1`); gera ata |
| `sem_guardar` | Escuta sem guardar | transcreve e analisa; **nunca grava áudio em disco** (o reprocessamento usa só a memória) |
| `notas` | Modo notas | `/audio` responde `409`; funcionam checklist manual, anotações, chat e ata |

**Estados:** `preparando` → `ouvindo` → `finalizada`.

### `GET /sessoes` · `GET /sessoes/{id}`
Lista os ids das sessões · estado resumido da sessão (meta, contagem de segmentos, progresso).

### `GET /sessoes/{id}/preparacao`
O mesmo objeto `preparacao` acima.

### `PATCH /sessoes/{id}`
```json
{"modo": "sem_guardar", "titulo": "...", "horario": "14:00", "aviso_confirmado": true}
```
Todos os campos são opcionais. O `modo` só pode mudar enquanto a sessão estiver em `preparando`; depois disso, retorna `409`.

### `POST /sessoes/{id}/iniciar` `{aviso_confirmado: true}`
Passa a sessão para `ouvindo`. Exceto no modo `notas`, exige `aviso_confirmado: true`; sem isso, retorna `409`.
Um cliente que não chama esta rota, como a extensão do Chrome, inicia a sessão automaticamente no primeiro áudio.

### `POST /sessoes/{id}/audio` — transcrição
`multipart/form-data`:

| campo | obrigatório | |
|---|---|---|
| `audio_chunk` | sim | webm/opus, wav, ogg ou mp3; até 20 MB |
| `seq` | recomendado | número sequencial do trecho (garante a ordem quando as respostas chegam fora de ordem) |
| `inicio_ms` | recomendado | epoch em ms do início do trecho (vira a hora `[HH:MM:SS]`) |
| `duracao_ms` | recomendado | conta para disparar a análise a cada ~30s de fala |

```json
{"seq": 3, "hora": "14:12:07", "status": "ok", "texto": "o recuo frontal ficou em 5 m, e não 4,5 como estava na minuta."}
```
`status`: `ok` | `silencio` | `falha`. Em caso de falha, o trecho é reprocessado sozinho em segundo plano.
A resposta **não traz a análise**; ela chega por `/copiloto` ou `/eventos`.

**Dicas para a transcrição sair melhor:**
- Corte os trechos nas pausas da fala, entre 4 e 12s. Cortes no meio de palavras geram erros.
- Grave o microfone junto com o áudio da reunião, para as perguntas do implantador também entrarem.
- Mantenha o glossário do contexto bem preenchido: nomes, siglas e sistemas vão direto para o prompt.

### `GET /sessoes/{id}/copiloto` — estado completo da tela
```json
{
  "sessao": "2026-10-26_14-00-00",
  "estado": "ouvindo",
  "modo": "gravacao",
  "contexto": {"id": "serra-do-sabia-alvara", "nome": "..."},
  "atualizado_em": "14:12:40",
  "ultima_fala": {"seq": 3, "hora": "14:12:07", "texto": "..."},
  "perguntas_rapidas": ["Qual o recuo da ZR2?", "Qual a taxa do alvará?", "Qual o prazo de análise?"],
  "resumo": "…",
  "sugestao_pergunta_imediata": "A vistoria VIS-TEC vale para todo projeto acima de 500 m²?",
  "perguntas_sugeridas": ["…", "…"],
  "checklist": [
    {
      "id": "a1b2c3d4", "codigo": "CHK-08", "titulo": "Recuo frontal mínimo da ZR2",
      "pergunta": "…", "categoria": "Parâmetros", "obrigatoria": true,
      "valor_referencia": "4,50 m",
      "status": "respondida",
      "resposta": "5,00 m",
      "fonte": "conversa",
      "diverge": true,
      "trecho": "ficou em 5 m, e não 4,5 como estava na minuta",
      "hora": "14:12:07",
      "manual": false
    }
  ],
  "progresso": {"pendente": 1, "parcial": 0, "respondida": 11, "ignorada": 0, "total": 12,
                "percentual": 92, "confirmados_contexto": 5, "obrigatorias_pendentes": 0},
  "anotacoes": {
    "ia": ["Diverge do contexto: recuo frontal da ZR2 é 5 m na versão publicada (minuta dizia 4,50 m)."],
    "manuais": [{"hora": "14:05:10", "texto": "Juliana pediu treinamento presencial"}]
  },
  "regras_negocio": ["…"], "pendencias": ["…"], "resolvidos": ["…"]
}
```
Campos do item na sessão:
- `status`: `pendente` | `parcial` | `respondida` | `ignorada`.
- `fonte`: quem respondeu (`contexto`, `conversa` ou `manual`); `null` enquanto o item está pendente.
- `diverge`: a resposta dada contradiz o `valor_referencia`. Destaque na tela.
- `manual`: o item foi marcado à mão e a IA não muda mais o status dele.

### `GET /sessoes/{id}/eventos` — ao vivo (Server-Sent Events)
```js
const es = new EventSource(`${API}/sessoes/${id}/eventos`);
es.addEventListener('copiloto', e => render(JSON.parse(e.data)));      // mesmo formato do GET /copiloto
es.addEventListener('transcricao', e => ultimaFala(JSON.parse(e.data))); // {seq, hora, status, texto}
es.addEventListener('finalizado', e => ...);                            // {ata: true}
```
Ao conectar, o primeiro evento já é um `copiloto` completo. O servidor envia um `: ping` a cada 15s para manter a conexão.
`copiloto` também é enviado a cada mudança manual (checklist, anotação, modo ou início).

### `PATCH /sessoes/{id}/checklist/{item_id}`
```json
{"status": "respondida", "resposta": "5,00 m"}
```
Os dois campos são opcionais. Depois de marcado à mão, a IA não muda mais o item.
Voltar o item para `pendente` devolve o controle para a IA. Retorna `404` para item inexistente e `422` para status inválido.

### `POST /sessoes/{id}/checklist` `{pergunta, titulo?, categoria?, obrigatoria?}`
Adiciona um item só nesta sessão.

### `GET /sessoes/{id}/anotacoes` · `POST /sessoes/{id}/anotacoes` `{texto}`
Lê ou adiciona anotações manuais. Elas também entram na análise e na ata.

### `POST /sessoes/{id}/perguntar` `{texto}`
Chat com o copiloto, que usa o contexto, o checklist, as anotações e a transcrição.
```json
{"hora": "14:13:02", "pergunta": "Qual o recuo?", "resposta": "O recuo frontal mínimo na ZR2 é de 5 metros [14:12:07].", "modelo": "gemini-3.5-flash"}
```
Retorna `503` se nenhum modelo do Gemini responder.

### `POST /sessoes/{id}/analisar`
Força uma análise agora, sem esperar os 30s, e retorna o `copiloto`.

### `POST /sessoes/{id}/finalizar`
Espera a análise em andamento, faz a análise final, gera o `ata.md` (com a tabela do checklist) e marca a sessão como `finalizada`.
```json
{"pasta": "...", "ata": true, "falhas_pendentes": 0, "analise": {...}, "copiloto": {...}}
```

### `GET /sessoes/{id}/transcricao` (texto) · `GET /sessoes/{id}/ata` (markdown)

### `POST /sessoes/{id}/reprocessar`
Retranscreve os trechos que ficaram em `falhas/`, por exemplo depois de reiniciar o backend.

### `POST /processar-audio` (legado)
É a rota antiga da extensão do Chrome. Recebe os mesmos campos de `/audio` mais `sessao` e devolve a transcrição junto com a última análise.

---

## Exemplo de teste: MeuLab · IFPR Cascavel

Os arquivos ficam em `backend/exemplos/meulab/` (dados fictícios; os `.md` fazem o papel dos PDFs):

| arquivo | conteúdo |
|---|---|
| `01_proposta_tecnica_MeuLab.md` | proposta PT-2026-031: módulos, fases, perfis, 6 laboratórios preliminares |
| `02_ata_kickoff_IFPR.md` | kickoff de 10/10: decisões confirmadas e o que ficou sem fechamento |
| `03_inventario_almoxarifado_quimica.csv` | inventário do almoxarifado, com estoques mínimos faltando |
| `04_email_tecnico_almoxarifado.txt` | e-mail do técnico: processo atual, tempos de preparo estimados, resíduos |
| `_curadoria.json` | checklist, glossário e perguntas rápidas aplicados depois do processamento |

Para carregar, com o backend rodando:
```
python exemplos/carregar_exemplo.py http://localhost:8000
```
Resultado: o contexto `meulab-ifpr-cascavel` com 14 itens.
- **Confirmados pelo contexto:** laboratórios do piloto, perfis, login e quem movimenta o estoque.
- **Pendentes:** antecedência, tempo de preparo, aprovação, bloqueios de TCC, reagendamento, estoque mínimo, resíduos, Anatomia, integração e Fase 2.

O arquivo `exemplos/roteiros/meulab_reuniao2.txt` traz falas para simular a reunião.
Nele, o tempo de preparo de prática simples é 40 min (a referência dizia 30), o que deve gerar `diverge: true`.

---

## Configuração (`.env`)

| variável | padrão | |
|---|---|---|
| `GEMINI_API_KEY` | — | obrigatória |
| `PORTA` | 8000 | |
| `MODELOS_TRANSCRICAO` / `MODELOS_ANALISE` | flash, flash-lite, flash-lite-latest | ordem de fallback |
| `ANALISAR_A_CADA_S` | 30 | segundos de fala entre análises automáticas |
| `CONTEXTO_ANALISE_CHARS` | 12000 | quanto do `contexto.md` entra no prompt ao vivo |
| `GLOSSARIO_MAX_TERMOS` | 80 | termos enviados ao prompt da transcrição |
| `CONSOLIDACAO_ORIGINAL_CHARS` | 120000 | até esse total, os textos originais entram na consolidação |
| `SALVAR_AUDIO` | 0 | `1` guarda todo o áudio (só no modo `gravacao`) |
