"""Parâmetros configuráveis com valores por omissão documentados.

Nenhum valor comercial ou financeiro da Lumara é assumido: as metas começam
com valores neutros de gestão de tarefas e a CEO ajusta-os em Definições.
"""
from sqlalchemy.orm import Session

from app.modules.configuracao.models import Configuracao

PADRAO: dict[str, dict] = {
    # Meta de cumprimento de prazos da equipa (%) — usada no dashboard.
    "meta_cumprimento_prazos": {"valor": 85, "descricao": "Meta de tarefas concluídas dentro do prazo (%)"},
    # Dias de atraso a partir dos quais a CEO é alertada (antes disso, só a responsável).
    "dias_atraso_alerta_ceo": {"valor": 2, "descricao": "Dias de atraso até a CEO ser alertada"},
    # Dias a aguardar aprovação até gerar excepção.
    "dias_aprovacao_pendente": {"valor": 2, "descricao": "Dias a aguardar aprovação até gerar alerta"},
    "dia_planeamento": {"valor": 0, "descricao": "Dia do planeamento semanal (0 = segunda-feira)"},
    "dia_revisao": {"valor": 4, "descricao": "Dia da revisão semanal (4 = sexta-feira)"},
    "dias_alerta_validade": {"valor": 30, "descricao": "Dias antes da validade para alertar sobre lotes em stock"},
    "moeda": {"valor": "AOA", "descricao": "Moeda base (Kwanza)"},
}


def obter(db: Session, chave: str):
    linha = db.get(Configuracao, chave)
    if linha is not None:
        return linha.valor.get("valor")
    return PADRAO[chave]["valor"]


def listar(db: Session) -> list[dict]:
    guardadas = {c.chave: c.valor.get("valor") for c in db.query(Configuracao).all()}
    return [
        {"chave": k, "valor": guardadas.get(k, v["valor"]), "descricao": v["descricao"]}
        for k, v in PADRAO.items()
    ]


def definir(db: Session, chave: str, valor) -> None:
    linha = db.get(Configuracao, chave)
    if linha is None:
        db.add(Configuracao(chave=chave, valor={"valor": valor}))
    else:
        linha.valor = {"valor": valor}
