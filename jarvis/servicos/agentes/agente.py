import json
import time

from . import erros as classificacao
from . import mensagens as construtor
from . import modelos


class ChamadaFerramenta:
    def __init__(self, nome, argumentos, identificador=None):
        self.nome = nome
        self.argumentos = argumentos or {}
        self.identificador = identificador

    def __repr__(self):
        return f"ChamadaFerramenta({self.nome!r}, {self.argumentos!r})"


class UsoTokens:
    def __init__(self, entrada=0, saida=0, total=0, bruto=None):
        self.entrada = entrada
        self.saida = saida
        self.total = total
        # medir_custo.py lê prompt_tokens_details.cached_tokens deste formato cru.
        self.bruto = bruto or {}

    def como_dicionario_provedor(self):
        if self.bruto:
            return self.bruto

        return {
            "prompt_tokens": self.entrada,
            "completion_tokens": self.saida,
            "total_tokens": self.total,
        }


# Orçamentos separados por tipo de falha: um 429 não gasta as tentativas do 400.
class PoliticaRepeticao:
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

        self.rotulo = rotulo


class PedidoAgente:
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
        return classificacao.cabecalho(self.excecao, nome)

    @property
    def usou_ferramenta(self):
        return bool(self.chamadas)

    def primeira_chamada(self):
        return self.chamadas[0] if self.chamadas else None

    def como_tupla(self):
        return (True, self.texto) if self.sucesso else (False, self.erro)


def _texto_da_mensagem(mensagem):
    texto = getattr(mensagem, "text", None)

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
    if not texto:
        return None

    try:
        dados = json.loads(texto)

    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    return dados if isinstance(dados, dict) else None


def _preparar_modelo(pedido):
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

    invocacao = modelos.argumentos_de_invocacao(pedido.provedor)

    if invocacao:
        modelo = modelo.bind(**invocacao)

    return modelo


def executar(pedido, politica=None):
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
        return RespostaAgente(
            False,
            provedor=pedido.provedor,
            modelo=pedido.modelo,
            erro=classificacao.descrever(erro),
            tipo_erro=classificacao.classificar(erro),
            excecao=erro,
            latencia_segundos=time.monotonic() - inicio,
        )

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
