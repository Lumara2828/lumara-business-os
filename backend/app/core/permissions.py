"""Controlo de acesso por função (RBAC).

A matriz é a fonte única de verdade: o backend verifica-a em cada endpoint
(dependência `requer(...)`) e o frontend recebe-a em GET /auth/me apenas para
mostrar/esconder elementos — esconder no frontend nunca substitui a
verificação no servidor.

Permissões dos módulos das fases seguintes já estão declaradas para que a
matriz completa fique documentada e testada desde o início (ver
docs/04-matriz-permissoes.md); os endpoints correspondentes ainda não existem.
"""
from enum import StrEnum


class Funcao(StrEnum):
    CEO = "ceo"
    MARKETING = "marketing"
    PRODUCAO = "producao"


ROTULOS_FUNCAO = {Funcao.CEO: "CEO", Funcao.MARKETING: "Marketing Digital", Funcao.PRODUCAO: "Produção"}


class P(StrEnum):
    # --- Fase 1 ---
    DASHBOARD_EXECUTIVO = "dashboard.executivo"
    TAREFAS_VER_TODAS = "tarefas.ver_todas"
    TAREFAS_DELEGAR = "tarefas.delegar"          # criar e atribuir a qualquer pessoa
    TAREFAS_CRIAR_PROPRIAS = "tarefas.criar_proprias"
    TAREFAS_APROVAR = "tarefas.aprovar"
    TAREFAS_ELIMINAR = "tarefas.eliminar"
    EXCEPCOES_VER = "excepcoes.ver"
    RELATORIOS_EQUIPA = "relatorios.equipa"
    OCORRENCIAS_REGISTAR = "ocorrencias.registar"
    OCORRENCIAS_GERIR = "ocorrencias.gerir"
    RESPONSABILIDADES_VER = "responsabilidades.ver"
    RESPONSABILIDADES_GERIR = "responsabilidades.gerir"
    ROTINA_PLANEAR = "rotina.planear"
    EQUIPA_GERIR = "equipa.gerir"
    AUDITORIA_VER = "auditoria.ver"
    CONFIGURACAO_GERIR = "configuracao.gerir"
    # --- Fase 2: produção e stock ---
    PRODUCAO_ORDENS = "producao.ordens"
    PRODUCAO_FICHAS_TECNICAS = "producao.fichas_tecnicas"
    STOCK_VER = "stock.ver"                      # consultar quantidades (sem valores)
    STOCK_MOVIMENTAR = "stock.movimentar"
    STOCK_VER_VALOR = "stock.ver_valor"          # custos e valor do inventário (confidencial)
    # --- Fases seguintes (declaradas, sem endpoints ainda) ---
    MARKETING_CALENDARIO = "marketing.calendario"
    MARKETING_APROVAR = "marketing.aprovar_publicacao"
    VENDAS_GERIR = "vendas.gerir"
    FINANCAS_VER = "financas.ver"
    FINANCAS_APROVAR_DESPESAS = "financas.aprovar_despesas"
    PRECOS_ALTERAR = "precos.alterar"
    ESTRATEGIA_METAS = "estrategia.metas"
    PROCEDIMENTOS_VER = "procedimentos.ver"
    PROCEDIMENTOS_APROVAR = "procedimentos.aprovar"


_COMUNS = {
    P.TAREFAS_CRIAR_PROPRIAS,
    P.OCORRENCIAS_REGISTAR,
    P.RESPONSABILIDADES_VER,
    P.PROCEDIMENTOS_VER,
    P.STOCK_VER,
}

MATRIZ: dict[Funcao, frozenset[P]] = {
    Funcao.CEO: frozenset(P),
    Funcao.MARKETING: frozenset(_COMUNS | {P.MARKETING_CALENDARIO, P.VENDAS_GERIR}),
    Funcao.PRODUCAO: frozenset(
        _COMUNS | {P.PRODUCAO_ORDENS, P.PRODUCAO_FICHAS_TECNICAS, P.STOCK_MOVIMENTAR}
    ),
}


def tem_permissao(funcao: str, permissao: P) -> bool:
    return permissao in MATRIZ.get(Funcao(funcao), frozenset())


def permissoes_de(funcao: str) -> list[str]:
    return sorted(p.value for p in MATRIZ.get(Funcao(funcao), frozenset()))
