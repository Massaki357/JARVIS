

# [CURSO] json converte textos JSON em dicionários Python.
# [CURSO] Aqui ele interpreta a resposta estruturada devolvida pelo Gemini.
import json
# [CURSO] os permite acessar variáveis de ambiente.
# [CURSO] O modelo visual pode ser configurado externamente sem alterar este arquivo.
import os

# [CURSO] mss captura a tela com baixo custo e boa velocidade.
import mss
# [CURSO] Pillow transforma a captura bruta em uma imagem
# [CURSO] e permite convertê-la para JPEG em memória.
from PIL import Image
# [CURSO] Cliente oficial usado para chamar o modelo Gemini.
from google import genai
# [CURSO] types fornece estruturas da API,
# [CURSO] como Part e GenerateContentConfig.
from google.genai import types

# [CURSO] Importa a chave configurada no projeto.
from core.config import GEMINI_API_KEY


# [CURSO] Lê o nome do modelo da variável GEMINI_VISION_MODEL.
# [CURSO] Se ela não existir, usa o valor padrão definido abaixo.
MODELO_LOCALIZADOR = os.getenv(
    "GEMINI_VISION_MODEL",
    "gemini-3.1-flash-lite",
)

# [CURSO] Define a confiança mínima aceita.
# [CURSO] Resultados abaixo de 0.78 são recusados para evitar cliques incertos.
CONFIANCA_MINIMA = 0.78

# [CURSO] Lista de ações sensíveis ou destrutivas.
# [CURSO] Se o alvo do clique contiver um desses termos,
# [CURSO] a operação será bloqueada antes mesmo de capturar a tela.
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


# [CURSO] Padroniza um texto para comparação.
# [CURSO] Converte para minúsculas, remove espaços duplicados
# [CURSO] e limpa as extremidades.
def _normalizar(texto):
    # [CURSO] split separa o texto ignorando espaços repetidos.
    # [CURSO] join reconstrói usando somente um espaço entre as palavras.
    return " ".join(str(texto).lower().split()).strip()


# [CURSO] Verifica se o alvo contém algum termo proibido.
def _alvo_bloqueado(alvo):
    # [CURSO] Normaliza o alvo antes da comparação.
    alvo_normalizado = _normalizar(alvo)

    # [CURSO] any retorna True assim que encontrar
    # [CURSO] pelo menos um termo bloqueado dentro do alvo.
    return any(
        termo in alvo_normalizado
        for termo in TERMOS_BLOQUEADOS
    )


# [CURSO] Captura somente o monitor principal
# [CURSO] e devolve a imagem, resolução e posição na área virtual.
def _capturar_tela_principal():
    # [CURSO] Abre o capturador de tela.
    # [CURSO] O bloco with garante o fechamento automático.
    with mss.mss() as sct:
        # [CURSO] No mss, monitors[1] normalmente representa
        # [CURSO] o primeiro monitor físico, considerado o principal.
        monitor = sct.monitors[1]
        # [CURSO] Captura todos os pixels da área do monitor.
        captura = sct.grab(monitor)

        # [CURSO] Converte os bytes RGB do mss em uma imagem Pillow.
        imagem = Image.frombytes(
            "RGB",
            captura.size,
            captura.rgb,
        )

        # [CURSO] io é importado localmente porque só é necessário nesta função.
        import io
        # [CURSO] Cria um arquivo em memória RAM.
        buffer = io.BytesIO()
        # [CURSO] Converte a captura para JPEG.
        # [CURSO] A qualidade 88 reduz tamanho sem perder muita nitidez.
        imagem.save(buffer, format="JPEG", quality=88)

        # [CURSO] Retorna a imagem e os dados necessários
        # [CURSO] para converter coordenadas locais em coordenadas absolutas.
        return {
            "imagem": buffer.getvalue(),
            "largura": captura.width,
            "altura": captura.height,
            "esquerda": monitor["left"],
            "topo": monitor["top"],
        }


# [CURSO] Limpa e interpreta o JSON devolvido pelo modelo.
def _extrair_json(texto):
    # [CURSO] Garante que o valor seja texto e remove espaços externos.
    texto = str(texto or "").strip()

    # [CURSO] Alguns modelos podem envolver o JSON em bloco Markdown.
    # [CURSO] Este trecho remove as linhas com crases antes do json.loads.
    if texto.startswith("```"):
        # [CURSO] Divide a resposta em linhas.
        linhas = texto.splitlines()
        # [CURSO] Mantém somente as linhas que não iniciam
        # [CURSO] ou encerram um bloco de código Markdown.
        linhas = [
            linha
            for linha in linhas
            if not linha.strip().startswith("```")
        ]
        texto = "\n".join(linhas).strip()

    # [CURSO] Converte o texto JSON em um dicionário Python.
    return json.loads(texto)


# [CURSO] Função principal do localizador visual.
# [CURSO] Valida o pedido, captura a tela, consulta o Gemini,
# [CURSO] verifica a confiança e converte as coordenadas.
def localizar_elemento_na_tela(alvo):
    """
    Localiza um elemento na tela e retorna coordenadas absolutas.

    O modelo devolve x e y normalizados de 0 a 1000, o que evita
    dependência direta da resolução da imagem.
    """

    # [CURSO] Limpa espaços duplicados do alvo solicitado.
    alvo = " ".join(str(alvo).split()).strip()

    # [CURSO] Impede a execução sem uma descrição do elemento.
    if not alvo:
        # [CURSO] Retorna a imagem e os dados necessários
        # [CURSO] para converter coordenadas locais em coordenadas absolutas.
        return {
            "sucesso": False,
            "mensagem": "O alvo do clique não foi informado.",
        }

    # [CURSO] Bloqueia pedidos considerados sensíveis.
    if _alvo_bloqueado(alvo):
        # [CURSO] Retorna a imagem e os dados necessários
        # [CURSO] para converter coordenadas locais em coordenadas absolutas.
        return {
            "sucesso": False,
            "mensagem": (
                "Esse clique foi bloqueado por segurança. "
                "Nenhuma ação foi executada."
            ),
        }

    # [CURSO] Impede a chamada da API quando a chave não está disponível.
    if not GEMINI_API_KEY:
        # [CURSO] Retorna a imagem e os dados necessários
        # [CURSO] para converter coordenadas locais em coordenadas absolutas.
        return {
            "sucesso": False,
            "mensagem": "GEMINI_API_KEY não encontrada.",
        }

    # [CURSO] Captura o monitor principal e guarda
    # [CURSO] imagem, tamanho e deslocamento.
    captura = _capturar_tela_principal()

    # [CURSO] Define o formato obrigatório da resposta JSON.
    # [CURSO] Isso reduz respostas livres e facilita a validação.
    esquema = {
        "type": "object",
        # [CURSO] Declara cada campo que o modelo deve retornar.
        "properties": {
            # [CURSO] Indica se o elemento foi realmente localizado.
            "encontrado": {"type": "boolean"},
            # [CURSO] Coordenada horizontal normalizada entre 0 e 1000.
            "x": {"type": "integer", "minimum": 0, "maximum": 1000},
            # [CURSO] Coordenada vertical normalizada entre 0 e 1000.
            "y": {"type": "integer", "minimum": 0, "maximum": 1000},
            # [CURSO] Grau de confiança entre 0 e 1.
            "confianca": {"type": "number", "minimum": 0, "maximum": 1},
            # [CURSO] Descrição textual do elemento identificado.
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

    # [CURSO] Instrução enviada ao modelo visual.
    # [CURSO] Ela exige o centro clicável e coordenadas normalizadas.
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

    # [CURSO] Cria o cliente autenticado do Gemini.
    client = genai.Client(api_key=GEMINI_API_KEY)

    # [CURSO] Envia o prompt e a imagem para o modelo.
    resposta = client.models.generate_content(
        model=MODELO_LOCALIZADOR,
        # [CURSO] A requisição contém texto e imagem no mesmo pedido.
        contents=[
            prompt,
            # [CURSO] Converte os bytes JPEG em uma parte multimodal.
            types.Part.from_bytes(
                data=captura["imagem"],
                mime_type="image/jpeg",
            ),
        ],
        # [CURSO] Configura resposta determinística e estruturada.
        config=types.GenerateContentConfig(
            # [CURSO] Temperature 0 reduz variações e criatividade.
            temperature=0,
            # [CURSO] Solicita que a resposta seja JSON.
            response_mime_type="application/json",
            # [CURSO] Obriga a resposta a seguir o esquema definido.
            response_schema=esquema,
        ),
    )

    # [CURSO] Converte a resposta textual em dicionário.
    dados = _extrair_json(resposta.text)

    # [CURSO] Lê com segurança o indicador de localização.
    encontrado = bool(dados.get("encontrado", False))
    # [CURSO] Lê e converte a confiança para float.
    confianca = float(dados.get("confianca", 0.0))

    # [CURSO] Recusa a ação se o modelo informou que não encontrou.
    if not encontrado:
        # [CURSO] Retorna a imagem e os dados necessários
        # [CURSO] para converter coordenadas locais em coordenadas absolutas.
        return {
            "sucesso": False,
            "mensagem": (
                "Não consegui localizar esse elemento com segurança. "
                "Nenhum clique foi executado."
            ),
        }

    # [CURSO] Recusa resultados abaixo da confiança mínima.
    if confianca < CONFIANCA_MINIMA:
        # [CURSO] Retorna a imagem e os dados necessários
        # [CURSO] para converter coordenadas locais em coordenadas absolutas.
        return {
            "sucesso": False,
            "mensagem": (
                "A localização visual ficou incerta. "
                "Nenhum clique foi executado."
            ),
        }

    # [CURSO] Converte x para inteiro e limita à faixa segura.
    x_normalizado = max(0, min(1000, int(dados["x"])))
    # [CURSO] Converte y para inteiro e limita à faixa segura.
    y_normalizado = max(0, min(1000, int(dados["y"])))

    # [CURSO] Converte x de 0–1000 para pixels reais da captura.
    x_local = round(
        (x_normalizado / 1000)
        * (captura["largura"] - 1)
    )

    # [CURSO] Converte y de 0–1000 para pixels reais da captura.
    y_local = round(
        (y_normalizado / 1000)
        * (captura["altura"] - 1)
    )

    return {
        "sucesso": True,
        # [CURSO] Soma o deslocamento horizontal do monitor,
        # [CURSO] produzindo uma coordenada absoluta do Windows.
        "x": captura["esquerda"] + x_local,
        # [CURSO] Soma o deslocamento vertical do monitor.
        "y": captura["topo"] + y_local,
        "confianca": confianca,
        "descricao": str(dados.get("descricao", alvo)),
        "mensagem": "Elemento localizado.",
    }