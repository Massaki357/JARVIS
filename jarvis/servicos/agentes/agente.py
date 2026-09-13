"""
O contrato único de chamada de agente deste projeto.

UM PEDIDO ENTRA (PedidoAgente), UMA RESPOSTA SAI (RespostaAgente), e
executar() nunca levanta exceção. Todo lugar do ALFRED que fala com
uma LLM de texto ou de visão passa por aqui — Groq, Cerebras, OpenAI,
Gemini e Mistral, com ou sem imagem, com ou sem ferramenta, com ou
sem JSON.

O QUE ERA ANTES
===============

Sete implementações da mesma ideia, cada uma com o próprio formato de
entrada, o próprio jeito de ler a saída e a própria lista de erros
tratados:

  - delegacao_ia/provedores.py: requests.post para três provedores +
    um genai.Client para o quarto;
  - roteamento_hierarquico/roteador.py: requests.post com "tools" e
    leitura manual de choices[0].message.tool_calls;
  - identificacao_visual/: um cliente do Gemini e um da Mistral, com
    formatos de imagem diferentes entre si;
  - descricao_visual/cliente_visao.py: os mesmos dois de novo, em
    outro arquivo;
  - memoria_obsidian/consolidacao.py: mais um genai.Client;
  - servicos/visao/localizador_clique.py: mais um, com response_schema.

Todos devolviam (sucesso, texto) — o acerto que esta camada preserva
—, mas nenhum devolvia tokens, latência, chamada de ferramenta ou o
TIPO da falha de forma comparável. Quem quisesse saber "isso foi
limite de uso ou chave errada?" tinha que ler o status HTTP na mão,
em cada arquivo.

O QUE MUDA PARA QUEM CHAMA
==========================

Nada do contrato externo. Cada função pública continua devolvendo
(sucesso, texto) para o cérebro, porque é isso que os pacotes deste
projeto combinaram entre si (docs/INTEGRATION.md). O que muda é o que
existe POR DENTRO: agora dá para saber quantos tokens custou, quanto
demorou, e se vale a pena repetir — de forma igual em todos eles.
"""

import json
import time

from . import erros as classificacao
from . import mensagens as construtor
from . import modelos


class ChamadaFerramenta:
    """
    Uma chamada de ferramenta pedida pelo modelo, já normalizada.

    O LangChain entrega .tool_calls no mesmo formato para todos os
    provedores ({"name", "args", "id", "type"}) — o que antes exigia
    ler choices[0].message.tool_calls e decodificar a string JSON de
    "arguments" na mão.
    """

    def __init__(self, nome, argumentos, identificador=None):
        self.nome = nome
        self.argumentos = argumentos or {}
        self.identificador = identificador

    def __repr__(self):
        return f"ChamadaFerramenta({self.nome!r}, {self.argumentos!r})"


class UsoTokens:
    """
    Consumo de tokens de uma chamada, nos dois vocabulários.

    Os campos em português vêm do usage_metadata padronizado do
    LangChain (igual em todo provedor). O `bruto` é o dicionário de
    uso CRU do provedor, preservado porque
    jarvis/roteamento_hierarquico/medir_custo.py mede cache hit por
    prompt_tokens_details.cached_tokens — um campo que só existe no
    formato da Groq e que o formato padronizado não carrega. Medir
    custo real exige o número real; ver o comentário de
    _tokens_cacheados lá.
    """

    def __init__(self, entrada=0, saida=0, total=0, bruto=None):
        self.entrada = entrada
        self.saida = saida
        self.total = total
        self.bruto = bruto or {}

    def como_dicionario_provedor(self):
        """
        O uso no formato de chave do provedor (prompt_tokens /
        completion_tokens / total_tokens). Devolve o dicionário cru
        quando ele veio, e reconstrói um equivalente quando não veio —
        assim quem lê essas chaves funciona com qualquer provedor.
        """
        if self.bruto:
            return self.bruto

        return {
            "prompt_tokens": self.entrada,
            "completion_tokens": self.saida,
            "total_tokens": self.total,
        }


class PoliticaRepeticao:
    """
    Quantas vezes repetir, e por qual motivo.

    São ORÇAMENTOS SEPARADOS por tipo de falha, e isso não é
    preciosismo: o roteamento hierárquico já tinha descoberto, na
    prática, que somar os dois num contador só faz um limite de uso
    consumir as tentativas reservadas para o outro caso. Ver
    jarvis/roteamento_hierarquico/config.py.

    O padrão é NÃO repetir nada (tudo em 1). Repetir é sempre uma
    decisão explícita de quem chama, porque quem chama é quem sabe se
    tem um usuário esperando a resposta falada ou uma tela dizendo
    "consultando o modelo...".
    """

    def __init__(
        self,
        tentativas=1,
        tentativas_limite=1,
        tentativas_ferramenta_indevida=1,
        espera_base=1.0,
        espera_maxima=5.0,
        rotulo="agentes",
    ):
        self.tentativas = max(1, tentativas)
        self.tentativas_limite = max(1, tentativas_limite)
        self.tentativas_ferramenta_indevida = max(
            1, tentativas_ferramenta_indevida
        )
        self.espera_base = espera_base
        self.espera_maxima = espera_maxima

        # Só aparece nos prints de diagnóstico, para dizer QUEM estava
        # repetindo quando a linha aparecer no painel de console.
        self.rotulo = rotulo


class PedidoAgente:
    """
    Tudo o que vai PARA o agente, num objeto só.

    provedor / modelo / api_key
        Quem responde. O provedor é um nome de
        modelos.PROVEDORES_SUPORTADOS; a chave vem SEMPRE do config.py
        de quem chama, nunca é lida aqui — cada pacote continua dono
        das próprias variáveis de .env, como sempre foi.

    texto / instrucao_sistema / historico / imagem
        A conversa. historico é a lista de {"role", "content"} que o
        projeto já usava; imagem são os bytes JPEG em memória.

    ferramentas / forcar_ferramenta
        Esquemas de tool (ver ferramentas.obter_esquemas). Sem elas,
        nenhuma ferramenta é declarada ao modelo — o que é o caso da
        maioria das chamadas daqui.

    json_esperado / esquema_resposta
        Modo JSON do provedor, e opcionalmente o esquema exato.
        Nenhum dos dois substitui validar em código o que voltou: o
        modo JSON garante SINTAXE, nunca conteúdo — nenhum provedor
        promete que um nome de ferramenta citado lá dentro existe
        neste projeto.

    temperatura / timeout
        timeout em SEGUNDOS, sempre. Um dos motivos desta camada
        existir é que os clientes do Gemini contavam em milissegundos
        e os de requests em segundos, no mesmo projeto.
    """

    def __init__(
        self,
        provedor,
        modelo,
        api_key,
        texto=None,
        instrucao_sistema=None,
        historico=None,
        imagem=None,
        mime_imagem=construtor.MIME_PADRAO,
        ferramentas=None,
        forcar_ferramenta=None,
        json_esperado=False,
        esquema_resposta=None,
        temperatura=None,
        timeout=None,
    ):
        self.provedor = provedor
        self.modelo = modelo
        self.api_key = api_key
        self.texto = texto
        self.instrucao_sistema = instrucao_sistema
        self.historico = historico
        self.imagem = imagem
        self.mime_imagem = mime_imagem
        self.ferramentas = ferramentas
        self.forcar_ferramenta = forcar_ferramenta
        self.json_esperado = json_esperado
        self.esquema_resposta = esquema_resposta
        self.temperatura = temperatura
        self.timeout = timeout

    def sem_historico(self):
        """
        Uma cópia deste pedido sem o histórico da conversa.

        Existe para o plano B do roteamento hierárquico: o 400 de "o
        modelo chamou uma ferramenta que ninguém declarou" acontece
        muito mais COM histórico (medido: 0 em 8 sem nenhum turno
        anterior, de 1 a 3 em cada 6 com um turno de assistente
        antes), então a última cartada de lá é refazer a etapa sem
        ele. Perder contexto é muito melhor do que perder o turno.
        """
        return PedidoAgente(
            self.provedor,
            self.modelo,
            self.api_key,
            texto=self.texto,
            instrucao_sistema=self.instrucao_sistema,
            historico=None,
            imagem=self.imagem,
            mime_imagem=self.mime_imagem,
            ferramentas=self.ferramentas,
            forcar_ferramenta=self.forcar_ferramenta,
            json_esperado=self.json_esperado,
            esquema_resposta=self.esquema_resposta,
            temperatura=self.temperatura,
            timeout=self.timeout,
        )


class RespostaAgente:
    """
    Tudo o que volta DO agente, num objeto só — inclusive quando deu
    errado. Nunca é uma exceção.

    sucesso    -> bool
    texto      -> a resposta em texto (vazio quando o modelo só pediu
                  uma ferramenta)
    dados      -> o dict já decodificado, quando foi pedido JSON
    chamadas   -> lista de ChamadaFerramenta
    uso        -> UsoTokens
    latencia_segundos, provedor, modelo
    erro       -> mensagem legível da falha (vazia em caso de sucesso)
    tipo_erro  -> uma das constantes de erros.py, para decidir se vale
                  repetir SEM reler status HTTP em lugar nenhum
    excecao    -> a exceção original que causou a falha, guardada para
                  os casos em que o tipo não basta e é preciso olhar a
                  resposta HTTP de novo (ver cabecalho_do_erro)
    """

    def __init__(
        self,
        sucesso,
        texto="",
        dados=None,
        chamadas=None,
        uso=None,
        latencia_segundos=0.0,
        provedor="",
        modelo="",
        erro="",
        tipo_erro="",
        excecao=None,
    ):
        self.sucesso = sucesso
        self.texto = texto or ""
        self.dados = dados
        self.chamadas = chamadas or []
        self.uso = uso or UsoTokens()
        self.latencia_segundos = latencia_segundos
        self.provedor = provedor
        self.modelo = modelo
        self.erro = erro
        self.tipo_erro = tipo_erro
        self.excecao = excecao

    def cabecalho_do_erro(self, nome):
        """
        Um cabeçalho HTTP da resposta que falhou, quando o SDK o
        preservou. Devolve None se a falha não tinha resposta ou se o
        cabeçalho não veio.

        Serve para o punhado de casos em que tipo_erro não é fino o
        bastante — hoje, os DOIS 429 diferentes da Mistral, que só se
        distinguem pelo x-ratelimit-limit-req-minute. Ver
        jarvis/pacotes/identificacao_visual/mistral_vision_client.py.
        """
        return classificacao.cabecalho(self.excecao, nome)

    @property
    def usou_ferramenta(self):
        return bool(self.chamadas)

    def primeira_chamada(self):
        """
        No máximo UMA chamada de ferramenta por turno — mesma
        suposição de "uma ação por pedido" usada em todo o projeto.
        Se o modelo devolver mais de uma, só a primeira vale.
        """
        return self.chamadas[0] if self.chamadas else None

    def como_tupla(self):
        """
        (sucesso, texto_ou_erro) — o formato que TODO pacote deste
        projeto já usava antes desta camada. Existe para a migração
        não precisar reescrever o contrato de ninguém.
        """
        return (True, self.texto) if self.sucesso else (False, self.erro)


def _texto_da_mensagem(mensagem):
    """
    O texto de uma AIMessage, seja qual for a forma do conteúdo.

    O conteúdo pode vir como string ou como lista de blocos
    (multimodal, raciocínio, ferramenta). Ler .content direto e supor
    string quebraria em silêncio justamente nos provedores que mandam
    blocos.
    """
    texto = getattr(mensagem, "text", None)

    # .text é PROPRIEDADE nas versões atuais do langchain-core, e o
    # valor devolvido ainda é chamável por compatibilidade — chamá-lo
    # emite LangChainDeprecationWarning a cada resposta. Testar string
    # primeiro é o que evita o aviso sem quebrar quem ainda entregue
    # um método de verdade.
    if isinstance(texto, str):
        return texto.strip()

    if callable(texto):
        try:
            texto = texto()

        except Exception:
            texto = None

        if isinstance(texto, str):
            return texto.strip()

    conteudo = getattr(mensagem, "content", "")

    if isinstance(conteudo, str):
        return conteudo.strip()

    if isinstance(conteudo, list):
        partes = []

        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)

            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(bloco.get("text") or "")

        return "".join(partes).strip()

    return ""


def _uso_da_mensagem(mensagem):
    padronizado = getattr(mensagem, "usage_metadata", None) or {}
    metadados = getattr(mensagem, "response_metadata", None) or {}

    # O nome do campo de uso cru muda por provedor: "token_usage" nos
    # compatíveis com OpenAI, "usage_metadata" no Gemini.
    bruto = metadados.get("token_usage") or metadados.get("usage_metadata")

    return UsoTokens(
        entrada=padronizado.get("input_tokens", 0),
        saida=padronizado.get("output_tokens", 0),
        total=padronizado.get("total_tokens", 0),
        bruto=bruto if isinstance(bruto, dict) else None,
    )


def _chamadas_da_mensagem(mensagem):
    chamadas = []

    for bruta in getattr(mensagem, "tool_calls", None) or []:
        if isinstance(bruta, dict):
            chamadas.append(
                ChamadaFerramenta(
                    bruta.get("name"),
                    bruta.get("args"),
                    bruta.get("id"),
                )
            )

    return chamadas


def _decodificar_json(texto):
    """
    O dict de uma resposta em modo JSON. Devolve None se não der —
    quem chama valida o que veio de qualquer jeito, e uma resposta
    ilegível nunca pode virar exceção aqui.
    """
    if not texto:
        return None

    try:
        dados = json.loads(texto)

    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    return dados if isinstance(dados, dict) else None


def _preparar_modelo(pedido):
    """
    O modelo com tudo o que este pedido exige já ligado: ferramentas,
    modo JSON e esquema de resposta.

    O response_format no estilo da OpenAI é o MESMO nos cinco
    provedores — o langchain-google-genai o traduz sozinho para o
    response_mime_type/response_json_schema do Gemini (confirmado
    lendo o código do pacote instalado, não suposto). É por isso que
    aqui não existe um "if provedor == gemini".
    """
    modelo = modelos.criar_modelo(
        pedido.provedor,
        pedido.modelo,
        pedido.api_key,
        temperatura=pedido.temperatura,
        timeout=pedido.timeout,
    )

    if pedido.ferramentas:
        modelo = modelo.bind_tools(
            pedido.ferramentas,
            tool_choice=pedido.forcar_ferramenta or "auto",
        )

    if pedido.esquema_resposta:
        modelo = modelo.bind(
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "resposta",
                    "schema": pedido.esquema_resposta,
                },
            }
        )

    elif pedido.json_esperado:
        modelo = modelo.bind(response_format={"type": "json_object"})

    # As esquisitices de cada provedor, declaradas em modelos.py — é o
    # que mantém este arquivo sem nenhum "if provedor == ...".
    invocacao = modelos.argumentos_de_invocacao(pedido.provedor)

    if invocacao:
        modelo = modelo.bind(**invocacao)

    return modelo


def executar(pedido, politica=None):
    """
    Executa um PedidoAgente e devolve uma RespostaAgente. NUNCA
    levanta exceção — nem de rede, nem de configuração, nem de
    formato.

    BLOQUEIA: é uma requisição HTTP. Quem chama de dentro de um loop
    de asyncio precisa de asyncio.to_thread, e quem chama da thread
    da GUI congela a janela — as duas coisas já valiam para o código
    que existia antes desta camada.
    """
    politica = politica or PoliticaRepeticao()
    inicio = time.monotonic()

    try:
        modelo = _preparar_modelo(pedido)

        lista_mensagens = construtor.montar(
            texto_usuario=pedido.texto,
            instrucao_sistema=pedido.instrucao_sistema,
            historico=pedido.historico,
            imagem=pedido.imagem,
            mime_imagem=pedido.mime_imagem,
        )

    except Exception as erro:
        # Falha de MONTAGEM (provedor desconhecido, pacote do provedor
        # não instalado, chave ausente, nenhuma mensagem). Nada foi
        # para a rede, então não há o que repetir.
        return RespostaAgente(
            False,
            provedor=pedido.provedor,
            modelo=pedido.modelo,
            erro=classificacao.descrever(erro),
            tipo_erro=classificacao.classificar(erro),
            excecao=erro,
            latencia_segundos=time.monotonic() - inicio,
        )

    # Orçamentos INDEPENDENTES, um por motivo de falha — ver
    # PoliticaRepeticao.
    gastas_geral = 0
    gastas_limite = 0
    gastas_ferramenta = 0

    ultimo_erro = "Falha desconhecida ao consultar o provedor."
    ultimo_tipo = classificacao.DESCONHECIDO
    ultima_excecao = None

    while True:
        try:
            mensagem = modelo.invoke(lista_mensagens)

        except Exception as erro:
            tipo = classificacao.classificar(erro)
            ultimo_erro = classificacao.descrever(erro)
            ultimo_tipo = tipo
            ultima_excecao = erro

            if tipo == classificacao.LIMITE:
                gastas_limite += 1

                if gastas_limite >= politica.tentativas_limite:
                    break

                espera = classificacao.espera_sugerida(
                    erro,
                    gastas_limite - 1,
                    politica.espera_base,
                    politica.espera_maxima,
                )

                print(
                    f"[{politica.rotulo}] Limite de uso do provedor "
                    f"'{pedido.provedor}' (tentativa {gastas_limite}/"
                    f"{politica.tentativas_limite}); repetindo em "
                    f"{espera:.1f}s."
                )

                time.sleep(espera)

                continue

            if tipo == classificacao.FERRAMENTA_INDEVIDA:
                gastas_ferramenta += 1

                if (
                    gastas_ferramenta
                    >= politica.tentativas_ferramenta_indevida
                ):
                    break

                print(
                    f"[{politica.rotulo}] O modelo tentou chamar uma "
                    "ferramenta numa etapa que não declara nenhuma "
                    f"(tentativa {gastas_ferramenta}/"
                    f"{politica.tentativas_ferramenta_indevida}); "
                    "repetindo."
                )

                # Sem espera: não é limite de uso, é a amostragem do
                # modelo. Dormir aqui só atrasaria a resposta.
                continue

            gastas_geral += 1

            if gastas_geral >= politica.tentativas:
                break

            espera = min(
                politica.espera_base * (2 ** (gastas_geral - 1)),
                politica.espera_maxima,
            )

            print(
                f"[{politica.rotulo}] Falha ao consultar "
                f"'{pedido.provedor}' (tentativa {gastas_geral}/"
                f"{politica.tentativas}): {ultimo_erro[:120]}"
            )

            time.sleep(espera)

            continue

        texto = _texto_da_mensagem(mensagem)
        chamadas = _chamadas_da_mensagem(mensagem)

        dados = None

        if pedido.json_esperado or pedido.esquema_resposta:
            dados = _decodificar_json(texto)

        return RespostaAgente(
            True,
            texto=texto,
            dados=dados,
            chamadas=chamadas,
            uso=_uso_da_mensagem(mensagem),
            latencia_segundos=time.monotonic() - inicio,
            provedor=pedido.provedor,
            modelo=pedido.modelo,
        )

    return RespostaAgente(
        False,
        provedor=pedido.provedor,
        modelo=pedido.modelo,
        erro=ultimo_erro,
        tipo_erro=ultimo_tipo,
        excecao=ultima_excecao,
        latencia_segundos=time.monotonic() - inicio,
    )
