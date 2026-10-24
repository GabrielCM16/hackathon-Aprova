"""Prompts e schemas usados com o Gemini. Ajuste aqui o comportamento do copiloto."""
from typing import List, Optional

from google.genai import types
from pydantic import BaseModel

# ---------- Transcrição (por chunk, rápida, texto puro) ----------

TRANSCRICAO = """Você é um transcritor de reuniões em português do Brasil.
Transcreva literalmente a fala deste trecho de áudio, recortado de uma conversa contínua.

Regras:
- Responda SOMENTE com o texto transcrito, sem aspas, rótulos ou comentários.
- O áudio pode começar ou terminar no meio de uma palavra. Não invente o pedaço que falta.
- NÃO repita o texto do contexto anterior; transcreva apenas o que é falado neste áudio.
- Escreva números como dígitos (ex.: "2,25 polegadas", "30 dias", "R$ 1.500").
- Se não houver fala (silêncio, ruído ou só música), responda exatamente: [silencio]
{glossario}{contexto}"""

GLOSSARIO_TRANSCRICAO = """
Nomes e termos que costumam aparecer nesta reunião (use esta grafia quando ouvir algo parecido, mas só se for realmente dito):
{termos}
"""

CONFIG_TRANSCRICAO = types.GenerateContentConfig(temperature=0.0)


# ---------- Contexto: extração de cada arquivo (roda uma vez por arquivo) ----------

class ExtracaoArquivo(BaseModel):
    conteudo: str               # markdown com tudo que importa do arquivo
    termos: List[str]           # nomes próprios, siglas, sistemas, órgãos
    perguntas: List[str]        # perguntas que ainda precisam ser feitas


EXTRACAO = """Você prepara material de apoio para um copiloto de reuniões de implantação de software em prefeituras e órgãos públicos.
O arquivo "{nome}" faz parte do contexto de um cliente/projeto. Ele pode ser uma conversa anterior, documento, edital, planilha, print ou foto.

Extraia:
- conteudo: Markdown fiel e denso com TUDO que pode ser útil numa próxima reunião: quem é quem (nomes, cargos, setores),
  regras de negócio, fluxos, prazos, valores, sistemas atuais, decisões já tomadas, problemas relatados e pendências.
  Não resuma demais; prefira listas. Para imagens, descreva o que aparece de relevante (telas, tabelas, textos).
- termos: nomes próprios, siglas, nomes de sistemas, órgãos, localidades e jargões, com a grafia correta.
- perguntas: dúvidas que ficaram em aberto ou informações que faltam e deveriam ser perguntadas na próxima reunião.

Não invente nada que não esteja no arquivo."""

CONFIG_EXTRACAO = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=ExtracaoArquivo,
    temperature=0.1,
)


# ---------- Contexto: consolidação de todos os arquivos ----------

class ItemSugerido(BaseModel):
    titulo: str                         # rótulo curto (ex.: "Recuo frontal mínimo na ZR2")
    pergunta: str
    categoria: str
    obrigatoria: bool
    valor_referencia: Optional[str]     # valor que o material indica e precisa ser confirmado (ex.: "4,50 m")
    confirmado_no_contexto: bool        # o material já confirma a resposta de forma definitiva
    resposta_contexto: Optional[str]    # a resposta confirmada, se houver


class Consolidacao(BaseModel):
    contexto: str
    glossario: List[str]
    checklist: List[ItemSugerido]
    perguntas_rapidas: List[str]


CONSOLIDACAO = """Abaixo estão extrações de vários arquivos sobre o mesmo cliente/projeto: "{nome}".
{descricao}

Produza:
- contexto: um único documento Markdown consolidado (no máximo ~{max_chars} caracteres), sem duplicações, organizado em seções
  (Cliente e pessoas, Situação atual, Regras de negócio, Decisões já tomadas, Problemas e riscos, Pendências).
  Quando houver informações conflitantes, mantenha a mais recente e registre o conflito.
- glossario: até {max_termos} termos (nomes, siglas, sistemas, lugares) com a grafia correta, os mais importantes primeiro.
- checklist: itens que precisam estar alinhados para configurar o sistema. UM VALOR POR ITEM: nunca agrupe
  (ex.: taxa de ocupação, coeficiente e recuo de uma zona são 3 itens separados). Cada item tem:
  titulo curto em frase normal, sem Title Case (até ~40 caracteres, ex.: "Recuo frontal mínimo na ZR2"),
  pergunta objetiva, categoria curta (ex.: "Parâmetros", "Taxas", "Prazos", "Documentos", "Fluxo", "Responsáveis"),
  obrigatoria=true para o que bloqueia a implantação,
  valor_referencia = só o valor, bem curto, que o material indica mas ainda precisa ser confirmado
  (ex.: "58%", "4,50 m", "R$ 3,85 por m²", "20 dias úteis", "Modelo não prevê"; null se não houver),
  confirmado_no_contexto=true SOMENTE se alguém do cliente confirmou explicitamente aquele valor (ex.: "Confirmado",
  "Sim, sou eu", "Isso mesmo") e nada posterior o colocou em dúvida; aí preencha resposta_contexto, curta
  (ex.: "ZR1, ZR2 e ZC1", "Diretor de Planejamento Urbano").
  NÃO são confirmações: minutas/rascunhos não publicados, tabelas marcadas "confirmar", e-mails com "ainda estou
  confirmando" ou "precisa ser decidido", preferências ("a Renata prefere") e qualquer coisa listada como pendência.
  Esses ficam confirmado_no_contexto=false com o valor em valor_referencia.
  Inclua os itens já confirmados (escopo, documentos, etapas do fluxo, quem assina etc.) para a equipe ver o quadro
  completo, e todos os pendentes. Ordene: confirmados primeiro, depois pendentes por importância.
  NÃO repita itens que já estão no checklist atual.
- perguntas_rapidas: 3 a 6 perguntas bem curtas (até ~25 caracteres) que o implantador pode querer fazer ao copiloto
  durante a reunião (ex.: "Qual o recuo?", "Qual a taxa?", "Qual o prazo?").

CHECKLIST ATUAL:
{checklist_atual}

EXTRAÇÕES:
{extracoes}"""

CONFIG_CONSOLIDACAO = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=Consolidacao,
    temperature=0.2,
)


# ---------- Análise acumulada (a cada ~30s de fala) ----------

class AtualizacaoChecklist(BaseModel):
    id: str
    status: str                 # pendente | parcial | respondida
    resposta: str               # o que foi respondido, em uma frase
    trecho: str                 # citação curta da transcrição que comprova
    hora: Optional[str]         # [HH:MM:SS] do trecho, se houver
    diverge: bool               # a resposta dada contradiz o valor de referência


class Analise(BaseModel):
    resumo: str
    regras_negocio: List[str]
    pendencias: List[str]
    resolvidos: List[str]
    anotacoes: List[str]
    perguntas_sugeridas: List[str]
    sugestao_pergunta_imediata: Optional[str]
    checklist: List[AtualizacaoChecklist]


ANALISE = """Você é um copiloto de reunião de implantação de software para prefeituras e órgãos públicos.
Abaixo estão o contexto do cliente (preparado antes da reunião), o checklist de perguntas, as anotações manuais,
a transcrição acumulada da reunião (pode ter pequenos erros de reconhecimento de voz) e a análise anterior.
Atualize a análise considerando TODA a conversa, consolidando e removendo duplicados:

- resumo: 2 a 4 frases sobre o que está sendo discutido.
- regras_negocio: regras de negócio, prazos, valores, metragens, documentos, fluxos e responsáveis citados. Só o que foi realmente dito.
- pendencias: dúvidas em aberto, informações que faltaram ou ficaram ambíguas.
- resolvidos: itens confirmados/decididos.
- anotacoes: fatos novos importantes que NÃO estavam no contexto, ou que o contradizem (comece com "Diverge do contexto:" nesse caso).
- checklist: para cada item do checklist cuja situação MUDOU com base na transcrição, retorne id, status
  ("respondida" se a resposta está completa, "parcial" se só parte foi respondida), resposta (curta, no formato do
  valor de referência: "5,00 m", "R$ 3,85 por m²", "20 dias úteis a partir de 01/2027"),
  trecho (citação curta), hora e diverge=true se o que foi dito contradiz o valor de referência do item.
  Confirmar o valor de referência ("isso, 4,50 metros") conta como resposta.
  Não inclua itens sem mudança. Nunca marque como respondido algo que não foi dito.
- perguntas_sugeridas: até 3 perguntas, priorizando itens obrigatórios pendentes do checklist e lacunas da conversa.
- sugestao_pergunta_imediata: UMA pergunta curta e objetiva que o implantador deveria fazer agora, ligada ao assunto
  que está sendo falado neste momento. null se não houver.

Se a conversa não for sobre implantação de software, analise mesmo assim, de forma neutra, sem inventar contexto.

CONTEXTO DO CLIENTE:
{contexto}

CHECKLIST (id | status | pergunta | valor de referência | resposta atual):
{checklist}

ANOTAÇÕES MANUAIS:
{anotacoes}

ANÁLISE ANTERIOR:
{anterior}

TRANSCRIÇÃO:
{transcricao}"""

CONFIG_ANALISE = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=Analise,
    temperature=0.2,
)


# ---------- Chat com o copiloto durante a reunião ----------

PERGUNTA = """Você é o copiloto de uma reunião de implantação de software que está acontecendo agora.
Responda à pergunta do implantador de forma curta e direta, usando o contexto do cliente, o checklist e a transcrição.
Cite o horário [HH:MM:SS] quando a resposta vier da transcrição. Se a informação não existir, diga que não foi mencionada.

CONTEXTO DO CLIENTE:
{contexto}

CHECKLIST:
{checklist}

ANOTAÇÕES:
{anotacoes}

TRANSCRIÇÃO:
{transcricao}

PERGUNTA DO IMPLANTADOR:
{pergunta}"""

CONFIG_PERGUNTA = types.GenerateContentConfig(temperature=0.2)

# ---------- Chat sobre o contexto (fora da reunião) ----------

PERGUNTA_CONTEXTO = """Você é o assistente de implantação de software. O material abaixo é sobre a implantação de um produto
em um cliente. Quando o implantador fala "o sistema", "a plataforma" ou "o produto", ele se refere ao produto sendo implantado.
Entenda perguntas informais e com erros de digitação. Responda de forma curta e direta, em português,
usando o contexto consolidado, os documentos e o checklist abaixo; diga de qual documento veio a informação quando souber.
Se algo ainda não foi confirmado com o cliente, avise que está pendente. Só diga que não consta no material
se de fato nenhum trecho abaixo tratar do assunto. Não use markdown com asteriscos.

CONTEXTO CONSOLIDADO:
{contexto}

DOCUMENTOS (extração de cada arquivo):
{documentos}

CHECKLIST:
{checklist}

PERGUNTA DO IMPLANTADOR:
{pergunta}"""


# ---------- Ata final ----------

ATA = """Com base na transcrição completa da reunião, no checklist e nas anotações abaixo, escreva uma ata em Markdown, em português, objetiva e fiel ao que foi dito.

Estrutura:
# Ata de reunião
**Data:** {data}
## Resumo
## Decisões e itens confirmados
## Regras de negócio levantadas
(prazos, valores, documentos, fluxos, responsáveis)
## Checklist
(tabela: pergunta | status | resposta)
## Pendências e dúvidas em aberto
(inclua os itens do checklist que ficaram sem resposta)
## Próximos passos / encaminhamentos
(quem faz o quê, se foi dito)

Não invente informações. Se uma seção não tiver conteúdo, escreva "_Nada registrado._".

CHECKLIST:
{checklist}

ANOTAÇÕES:
{anotacoes}

TRANSCRIÇÃO:
{transcricao}"""

CONFIG_ATA = types.GenerateContentConfig(temperature=0.2)
