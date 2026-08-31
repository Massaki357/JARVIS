from . import config, tuya_client

import re
import time
import unicodedata


# Padroniza um texto para facilitar comparações (mesmo approach do
# memory_manager.py): minúsculas, sem acento, sem espaço duplicado.
def _normalizar(texto):
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


# ============================================================
# Descoberta de dispositivos
# ============================================================

_cache_dispositivos = {
    "dados": None,
    "expira_em": 0.0,
}


# Lista os dispositivos vinculados à conta (via app Smart Life),
# consultando a API da Tuya. Cacheia por
# config.DURACAO_CACHE_DISPOSITIVOS_SEGUNDOS para não bater na API a
# cada comando de voz. Se a consulta falhar, devolve o último cache
# válido (mesmo vencido) em vez de uma lista vazia, quando disponível.
def listar_dispositivos(forcar_atualizacao=False):
    agora = time.time()

    if (
        not forcar_atualizacao
        and _cache_dispositivos["dados"] is not None
        and agora < _cache_dispositivos["expira_em"]
    ):
        return _cache_dispositivos["dados"]

    try:
        uid = tuya_client.obter_uid()

        resposta = tuya_client.get(
            f"/v1.0/users/{uid}/devices"
        )

    except Exception as erro:
        print(
            f"[casa_inteligente] Falha ao listar dispositivos: {erro}"
        )

        return _cache_dispositivos["dados"] or []

    if not resposta.get("success"):
        print(
            "[casa_inteligente] Erro ao listar dispositivos: "
            f"{resposta.get('msg')}"
        )

        return _cache_dispositivos["dados"] or []

    dispositivos = [
        {
            "id": dispositivo.get("id"),
            "nome": dispositivo.get("name", ""),
            "categoria": dispositivo.get("category", ""),
            "online": bool(dispositivo.get("online")),
        }
        for dispositivo in (resposta.get("result") or [])
    ]

    _cache_dispositivos["dados"] = dispositivos
    _cache_dispositivos["expira_em"] = (
        agora + config.DURACAO_CACHE_DISPOSITIVOS_SEGUNDOS
    )

    return dispositivos


# Lista os controles remotos já aprendidos sob um hub de
# infravermelho (ver IR Control Hub Open Service).
def listar_controles_remotos_ir(infrared_id):
    try:
        resposta = tuya_client.get(
            f"/v2.0/infrareds/{infrared_id}/remotes"
        )

    except Exception as erro:
        print(
            f"[casa_inteligente] Falha ao listar controles IR: {erro}"
        )

        return []

    if not resposta.get("success"):
        return []

    return [
        {
            "remote_id": remoto.get("remote_id"),
            "nome": remoto.get("remote_name", ""),
            "category_id": remoto.get("category_id"),
        }
        for remoto in (resposta.get("result") or [])
    ]


# Monta a lista "achatada" de tudo que pode ser controlado por nome:
# cada switch/tomada vira um candidato próprio, e cada hub de
# infravermelho se expande em um candidato por controle remoto
# aprendido embaixo dele (em vez do hub em si).
def _listar_candidatos():
    candidatos = []

    for dispositivo in listar_dispositivos():
        if dispositivo["categoria"] == config.CATEGORIA_HUB_INFRAVERMELHO:
            for remoto in listar_controles_remotos_ir(dispositivo["id"]):
                candidatos.append(
                    {
                        "tipo": "infravermelho",
                        "nome": remoto["nome"] or dispositivo["nome"],
                        "infrared_id": dispositivo["id"],
                        "remote_id": remoto["remote_id"],
                        "category_id": remoto["category_id"],
                        "online": dispositivo["online"],
                    }
                )

            continue

        candidatos.append(
            {
                "tipo": "switch",
                "nome": dispositivo["nome"],
                "id": dispositivo["id"],
                "online": dispositivo["online"],
            }
        )

    return candidatos


# Encontra o dispositivo cujo nome mais se aproxima de nome_falado.
# Retorna (candidato, None) se achar exatamente um, ou
# (None, mensagem_de_erro) se não achar nenhum ou achar mais de um —
# pro Jarvis avisar por voz em vez de adivinhar.
def resolver_dispositivo(nome_falado):
    candidatos = _listar_candidatos()

    if not candidatos:
        return None, (
            "Não consegui consultar os dispositivos da casa "
            "inteligente agora."
        )

    alvo = _normalizar(nome_falado)

    # Primeira tentativa: correspondência exata.
    exatos = [
        candidato
        for candidato in candidatos
        if _normalizar(candidato["nome"]) == alvo
    ]

    if len(exatos) == 1:
        return exatos[0], None

    # Segunda tentativa: correspondência parcial, em qualquer direção
    # (nome do dispositivo contém o termo falado, ou vice-versa).
    parciais = [
        candidato
        for candidato in candidatos
        if alvo in _normalizar(candidato["nome"])
        or _normalizar(candidato["nome"]) in alvo
    ]

    if len(parciais) == 1:
        return parciais[0], None

    if len(parciais) > 1:
        nomes = ", ".join(
            candidato["nome"] for candidato in parciais[:5]
        )

        return None, (
            f"Encontrei mais de um dispositivo parecido com "
            f"'{nome_falado}': {nomes}. Qual deles?"
        )

    disponiveis = ", ".join(
        candidato["nome"] for candidato in candidatos[:10]
    )

    return None, (
        f"Não encontrei nenhum dispositivo chamado '{nome_falado}'. "
        f"Dispositivos disponíveis: {disponiveis}."
    )


# ============================================================
# Interruptor / tomada — switches simples, mesmo tratamento pros
# dois (ver DP_CODE_SWITCH_PADRAO em config.py).
# ============================================================

def ligar(device_id, dp_code=None):
    dp_code = dp_code or config.DP_CODE_SWITCH_PADRAO

    sucesso, mensagem = tuya_client.enviar_comando(
        device_id,
        [
            {
                "code": dp_code,
                "value": True,
            }
        ],
    )

    return "Ligado." if sucesso else f"Falha ao ligar: {mensagem}"


def desligar(device_id, dp_code=None):
    dp_code = dp_code or config.DP_CODE_SWITCH_PADRAO

    sucesso, mensagem = tuya_client.enviar_comando(
        device_id,
        [
            {
                "code": dp_code,
                "value": False,
            }
        ],
    )

    return "Desligado." if sucesso else f"Falha ao desligar: {mensagem}"


# ============================================================
# Infravermelho (IR Control Hub Open Service)
# ============================================================
#
# Envia uma tecla já aprendida/associada pelo app Smart Life a um
# controle remoto. Endpoint e formato do corpo confirmados na
# documentação oficial da Tuya (Send Key Command):
#   POST /v2.0/infrareds/{infrared_id}/remotes/{remote_id}/raw/command
#   body: {"category_id": int, "key": str, "key_id": int}
#
# category_id/remote_id vêm de listar_controles_remotos_ir(). Para
# adicionar um comando aprendido novo (ex: "aumentar temperatura"),
# basta chamar enviar_tecla_infravermelho() com o nome de tecla
# correspondente — não precisa mexer no resto deste arquivo.
def enviar_tecla_infravermelho(
    infrared_id,
    remote_id,
    category_id,
    tecla,
    key_id=1,
):
    try:
        resposta = tuya_client.post(
            f"/v2.0/infrareds/{infrared_id}/remotes/{remote_id}"
            "/raw/command",
            {
                "category_id": category_id,
                "key": tecla,
                "key_id": key_id,
            },
        )

    except Exception as erro:
        return False, f"Falha ao falar com a Tuya: {erro}"

    if not resposta.get("success"):
        return False, resposta.get(
            "msg",
            "Erro desconhecido da API da Tuya.",
        )

    return True, "Comando infravermelho enviado com sucesso."


# AVISO: "power_on"/"power_off" são os nomes de tecla mais comuns pra
# ligar/desligar em controles aprendidos via Smart Life, mas isso
# ainda NÃO foi testado contra um dispositivo real (nenhum
# infravermelho pareado até a escrita deste código). Alguns controles
# só têm uma tecla única de "power" (liga/desliga alternado, sem
# estado). Confirme e ajuste os dois nomes abaixo assim que houver um
# controle remoto real pareado pra testar.
TECLA_IR_LIGAR = "power_on"
TECLA_IR_DESLIGAR = "power_off"


def ligar_infravermelho(infrared_id, remote_id, category_id):
    sucesso, mensagem = enviar_tecla_infravermelho(
        infrared_id,
        remote_id,
        category_id,
        TECLA_IR_LIGAR,
    )

    return "Ligado." if sucesso else f"Falha ao ligar: {mensagem}"


def desligar_infravermelho(infrared_id, remote_id, category_id):
    sucesso, mensagem = enviar_tecla_infravermelho(
        infrared_id,
        remote_id,
        category_id,
        TECLA_IR_DESLIGAR,
    )

    return "Desligado." if sucesso else f"Falha ao desligar: {mensagem}"
