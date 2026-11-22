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
    "limite_desconto_pct": {"valor": 10, "descricao": "Desconto máximo (%) sem aprovação da CEO"},
    "dias_cobranca": {"valor": 7, "descricao": "Dias após a entrega até alertar pagamento em falta"},
    "dias_cliente_inactivo": {"valor": 90, "descricao": "Dias sem comprar para considerar uma cliente inactiva"},
    "custo_mao_obra_hora_kz": {"valor": None, "descricao": "Custo de mão-de-obra directa por hora (Kz) — para a ficha de custos"},
    "meta_facturacao_mensal_kz": {"valor": None, "descricao": "Meta de facturação mensal (Kz)"},
    "margem_minima_pct": {"valor": None, "descricao": "Margem bruta mínima por produto (%) — abaixo disto é assinalado"},
    "margem_alvo_pct": {"valor": 50, "descricao": "Margem-alvo para o preço sugerido (%) — margem bruta sobre o preço de venda"},
    "cambio_kz_eur": {"valor": None, "descricao": "Câmbio para compras importadas (Kz por euro)"},
    "iva_importacao_pct": {"valor": None, "descricao": "IVA sobre compras importadas (%)"},
    "frete_importacao_kz_kg": {"valor": None, "descricao": "Frete de importação por kg (Kz)"},
    "automacao_resumo_semanal": {"valor": 1, "descricao": "Enviar o resumo semanal à segunda-feira (1 = sim, 0 = não)"},
    "automacao_relatorio_mensal": {"valor": 1, "descricao": "Avisar a CEO do relatório mensal no início do mês (1 = sim, 0 = não)"},
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
