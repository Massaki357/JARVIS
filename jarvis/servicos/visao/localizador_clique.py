import json
import os

import mss
from PIL import Image
from jarvis.servicos import agentes

from jarvis.nucleo.config import GEMINI_API_KEY
from jarvis.nucleo import modelos


MODELO_LOCALIZADOR = modelos.modelo("subagentes.localizador_clique")

TIMEOUT_SEGUNDOS = 20

CONFIANCA_MINIMA = 0.78

TERMOS_BLOQUEADOS = (
    "excluir",
    "apagar",
    "deletar",
    "remover permanentemente",
    "esvaziar lixeira",
    "formatar",
    "comprar",
    "finalizar compra",
    "pagar",
    "confirmar pagamento",
    "transferir",
    "enviar dinheiro",
    "instalar",
    "desinstalar",
    "executar como administrador",
)


def _normalizar(texto):
    return " ".join(str(texto).lower().split()).strip()


def _alvo_bloqueado(alvo):
    alvo_normalizado = _normalizar(alvo)

    return any(
        termo in alvo_normalizado
        for termo in TERMOS_BLOQUEADOS
    )


def _capturar_tela_principal():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        captura = sct.grab(monitor)

        imagem = Image.frombytes(
            "RGB",
            captura.size,
            captura.rgb,
        )

        import io
        buffer = io.BytesIO()
        imagem.save(buffer, format="JPEG", quality=88)

        return {
            "imagem": buffer.getvalue(),
            "largura": captura.width,
            "altura": captura.height,
            "esquerda": monitor["left"],
            "topo": monitor["top"],
        }


def _extrair_json(texto):
    texto = str(texto or "").strip()

    if texto.startswith("```"):
        linhas = texto.splitlines()
        linhas = [
            linha
            for linha in linhas
            if not linha.strip().startswith("```")
        ]
        texto = "\n".join(linhas).strip()

    return json.loads(texto)


def localizar_elemento_na_tela(alvo):
    alvo = " ".join(str(alvo).split()).strip()

    if not alvo:
        return {
            "sucesso": False,
            "mensagem": "O alvo do clique não foi informado.",
        }

    if _alvo_bloqueado(alvo):
        return {
            "sucesso": False,
            "mensagem": (
                "Esse clique foi bloqueado por segurança. "
                "Nenhuma ação foi executada."
            ),
        }

    if not GEMINI_API_KEY:
        return {
            "sucesso": False,
            "mensagem": "GEMINI_API_KEY não encontrada.",
        }

    captura = _capturar_tela_principal()

    esquema = {
        "type": "object",
        "properties": {
            "encontrado": {"type": "boolean"},
            "x": {"type": "integer", "minimum": 0, "maximum": 1000},
            "y": {"type": "integer", "minimum": 0, "maximum": 1000},
            "confianca": {"type": "number", "minimum": 0, "maximum": 1},
            "descricao": {"type": "string"},
        },
        "required": [
            "encontrado",
            "x",
            "y",
            "confianca",
            "descricao",
        ],
    }

    prompt = (
        "Você é um localizador visual de interface de computador. "
        "Encontre na captura de tela o elemento solicitado pelo usuário. "
        "Retorne o centro clicável do elemento. "
        "Use coordenadas normalizadas: x=0 é a borda esquerda, x=1000 a direita; "
        "y=0 é o topo e y=1000 a borda inferior. "
        "Se houver mais de um elemento parecido, escolha somente quando a descrição "
        "do usuário permitir distinguir claramente. Caso contrário, marque encontrado=false. "
        "Não invente coordenadas e não escolha elementos parcialmente escondidos. "
        f"Elemento solicitado: {alvo}"
    )

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor="gemini",
            modelo=MODELO_LOCALIZADOR,
            api_key=GEMINI_API_KEY,
            texto=prompt,
            imagem=captura["imagem"],
            esquema_resposta=esquema,
            temperatura=0,
            timeout=TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="localizador_clique"),
    )

    if not resposta.sucesso:
        return {
            "sucesso": False,
            "mensagem": (
                "Não consegui consultar o modelo visual agora. "
                "Nenhum clique foi executado."
            ),
        }

    dados = resposta.dados

    if not isinstance(dados, dict):
        try:
            dados = _extrair_json(resposta.texto)

        except (ValueError, TypeError):
            dados = None

    if not isinstance(dados, dict):
        return {
            "sucesso": False,
            "mensagem": (
                "A resposta do modelo visual veio em formato "
                "inesperado. Nenhum clique foi executado."
            ),
        }

    encontrado = bool(dados.get("encontrado", False))
    confianca = float(dados.get("confianca", 0.0))

    if not encontrado:
        return {
            "sucesso": False,
            "mensagem": (
                "Não consegui localizar esse elemento com segurança. "
                "Nenhum clique foi executado."
            ),
        }

    if confianca < CONFIANCA_MINIMA:
        return {
            "sucesso": False,
            "mensagem": (
                "A localização visual ficou incerta. "
                "Nenhum clique foi executado."
            ),
        }

    x_normalizado = max(0, min(1000, int(dados["x"])))
    y_normalizado = max(0, min(1000, int(dados["y"])))

    x_local = round(
        (x_normalizado / 1000)
        * (captura["largura"] - 1)
    )

    y_local = round(
        (y_normalizado / 1000)
        * (captura["altura"] - 1)
    )

    return {
        "sucesso": True,
        "x": captura["esquerda"] + x_local,
        "y": captura["topo"] + y_local,
        "confianca": confianca,
        "descricao": str(dados.get("descricao", alvo)),
        "mensagem": "Elemento localizado.",
    }
