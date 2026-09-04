# Sistema de perfis do jarvis — camada de dados.
#
# Um PERFIL é um cenário de uso: um prompt de sistema próprio mais um
# subconjunto das ferramentas do projeto. Trocar de perfil troca o
# comportamento da PRÓXIMA chamada; nunca o de uma chamada em
# andamento.
#
# Em disco (ver armazenamento.py para o formato completo):
#
#     dados/perfis/
#       indice.json              índice leve, DERIVADO das pastas
#       completo/                perfil padrão (jarvis completo)
#         perfil.json
#         sistema.md
#       <slug>/                  qualquer outro perfil, mesma forma
#
# A pasta de cada perfil é autocontida e é a fonte da verdade. O
# indice.json existe só para o select da interface abrir rápido, e é
# regravado a cada criação, edição e exclusão — nunca editado à mão.
#
# Este pacote NÃO é um pacote de tool: não expõe
# obter_function_declarations()/despachar() e não entra em
# PACOTES_REGISTRADOS. É infraestrutura de núcleo, como
# jarvis/nucleo/prompts/ e jarvis/nucleo/preferencias.py.
#
# O código mora aqui (jarvis/nucleo/perfis/) e os dados moram em
# dados/perfis/ de propósito — um slug de perfil é texto vindo do
# usuário e do modelo, e misturar as duas coisas na mesma pasta faria
# um perfil chamado "armazenamento" colidir com um módulo Python.
from .armazenamento import (
    CHAVE_PERFIL_ATIVO,
    NOME_PADRAO,
    SLUG_PADRAO,
    TODAS_AS_FERRAMENTAS,
    apagar_perfil,
    caminho_do_indice,
    caminho_do_perfil,
    carregar_perfil,
    criar_perfil,
    definir_perfil_ativo,
    editar_perfil,
    existe,
    ferramentas_editaveis,
    ferramentas_efetivas,
    gerar_slug,
    listar_perfis,
    normalizar_ferramentas,
    perfil_ativo,
    reconstruir_indice,
    slug_disponivel,
    texto_sistema,
)
from .geracao import (
    gerar_sugestao,
    interpretar_resposta,
    montar_catalogo_para_prompt,
    montar_pedido,
)
from .sensiveis import (
    FERRAMENTAS_SENSIVEIS,
    GRUPOS_SENSIVEIS,
    e_sensivel,
    motivo_de,
    separar,
    verificar_classificacao,
)
from .catalogo_ferramentas import (
    FERRAMENTAS_SEMPRE_ATIVAS,
    catalogo_completo,
    nomes_disponiveis,
    resumo_de,
    verificar_catalogo,
)
from .migracao import garantir_perfil_padrao

__all__ = [
    "verificar_classificacao",
    "separar",
    "motivo_de",
    "montar_pedido",
    "montar_catalogo_para_prompt",
    "interpretar_resposta",
    "gerar_sugestao",
    "e_sensivel",
    "GRUPOS_SENSIVEIS",
    "FERRAMENTAS_SENSIVEIS",
    "CHAVE_PERFIL_ATIVO",
    "FERRAMENTAS_SEMPRE_ATIVAS",
    "NOME_PADRAO",
    "SLUG_PADRAO",
    "TODAS_AS_FERRAMENTAS",
    "apagar_perfil",
    "caminho_do_indice",
    "caminho_do_perfil",
    "carregar_perfil",
    "catalogo_completo",
    "criar_perfil",
    "definir_perfil_ativo",
    "editar_perfil",
    "existe",
    "ferramentas_editaveis",
    "ferramentas_efetivas",
    "garantir_perfil_padrao",
    "gerar_slug",
    "listar_perfis",
    "nomes_disponiveis",
    "normalizar_ferramentas",
    "perfil_ativo",
    "reconstruir_indice",
    "resumo_de",
    "slug_disponivel",
    "texto_sistema",
    "verificar_catalogo",
]
