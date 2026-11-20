"""API de finanças. Tudo é exclusivo da CEO, excepto propor uma despesa (todas),
em que a colaboradora vê apenas as suas próprias propostas."""
from datetime import date
from decimal import Decimal
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, undefer

from app.core.audit import diferencas, registar
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErroNegocio, conflito, nao_encontrado, proibido
from app.core.permissions import P
from app.core.tempo import agora, formatar_data, hoje
from app.dependencies import Contexto, contexto_actual, requer
from app.modules.financas import service as svc
from app.modules.financas.models import CategoriaFinanceira, DespesaFixa, Lancamento, Orcamento
from app.modules.notificacoes.service import notificar, notificar_ceo
from app.modules.producao.models import FichaTecnica
from app.modules.vendas.service import fkz

router = APIRouter(prefix="/financas", tags=["Finanças"])
DIN = dict(max_digits=14, decimal_places=2)
Forma = Literal["transferencia", "multicaixa_express", "tpa", "numerario", "outro"]

CATEGORIAS_BASE = [  # genéricas (não são dados da Lumara); a CEO acrescenta/ajusta
    ("Matérias-primas", "despesa", "compras_stock", False), ("Embalagens e rótulos", "despesa", "compras_stock", False),
    ("Marketing e publicidade", "despesa", "marketing", False), ("Eventos e feiras", "despesa", "marketing", False),
    ("Salários e pessoal", "despesa", "pessoal", True), ("Renda", "despesa", "operacional", True),
    ("Energia e água", "despesa", "operacional", False), ("Internet e telecomunicações", "despesa", "operacional", True),
    ("Transporte e entregas", "despesa", "transporte", False), ("Impostos e taxas", "despesa", "impostos", False),
    ("Material de escritório e limpeza", "despesa", "operacional", False), ("Equipamentos", "despesa", "investimento", False),
    ("Outras despesas", "despesa", "outra", False), ("Outras receitas", "receita", "outra", False),
]


def garantir_categorias(db: Session) -> None:
    existentes = set(db.scalars(select(CategoriaFinanceira.nome)))
    for nome, tipo, nat, fixa in CATEGORIAS_BASE:
        if nome not in existentes:
            db.add(CategoriaFinanceira(nome=nome, tipo=tipo, natureza=nat, fixa=fixa))
    db.commit()


def codigo(l: Lancamento) -> str:
    return f"{'D' if l.tipo == 'despesa' else 'R'}-{l.numero:04d}"


def lanc_saida(l: Lancamento, db: Session | None = None) -> dict:
    s = {"id": l.id, "numero": l.numero, "codigo": codigo(l), "tipo": l.tipo, "categoria": {"id": l.categoria.id, "nome": l.categoria.nome,
         "natureza": l.categoria.natureza}, "descricao": l.descricao, "valor_kz": str(l.valor_kz), "data_competencia": l.data_competencia,
         "data_vencimento": l.data_vencimento, "estado": l.estado, "data_pagamento": l.data_pagamento, "forma_pagamento": l.forma_pagamento,
         "referencia": l.referencia, "fornecedor": {"id": l.fornecedor.id, "nome": l.fornecedor.nome} if l.fornecedor else None,
         "evento_id": l.evento_id, "campanha_id": l.campanha_id, "justificacao": l.justificacao, "motivo_decisao": l.motivo_decisao,
         "proposto_por": l.proposto_por.nome, "aprovado_em": l.aprovado_em, "documento_nome": l.documento_nome, "is_demo": l.is_demo,
         "vencida": l.estado == "aprovada" and l.data_vencimento is not None and l.data_vencimento < hoje()}
    if db is not None and l.tipo == "despesa" and l.estado in ("proposta", "aprovada"):
        s["excede_orcamento"] = svc.excede_orcamento(db, l.categoria_id, l.data_competencia, l.valor_kz, excluir_id=l.id)
    return s


# --- Categorias ---------------------------------------------------------------------

class CategoriaIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    tipo: Literal["despesa", "receita"]
    natureza: Literal["producao", "embalagem", "marketing", "pessoal", "operacional", "transporte", "impostos", "compras_stock", "investimento", "outra"]
    fixa: bool = False
    activa: bool = True


@router.get("/categorias")
def categorias(ctx: Contexto = Depends(requer(P.DESPESAS_PROPOR)), db: Session = Depends(get_db)):
    q = select(CategoriaFinanceira).order_by(CategoriaFinanceira.tipo, CategoriaFinanceira.nome)
    if not ctx.pode(P.FINANCAS_VER):
        q = q.where(CategoriaFinanceira.tipo == "despesa", CategoriaFinanceira.activa.is_(True))
    return [{"id": c.id, "nome": c.nome, "tipo": c.tipo, "natureza": c.natureza, "fixa": c.fixa, "activa": c.activa} for c in db.scalars(q)]


@router.post("/categorias", status_code=201)
def criar_categoria(dados: CategoriaIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    if db.scalar(select(CategoriaFinanceira).where(CategoriaFinanceira.nome.ilike(dados.nome.strip()))):
        raise conflito("Já existe uma categoria com esse nome.")
    c = CategoriaFinanceira(**dados.model_dump())
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.put("/categorias/{cid}")
def editar_categoria(cid: UUID, dados: CategoriaIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    c = db.get(CategoriaFinanceira, cid)
    if c is None:
        raise nao_encontrado("Categoria")
    for k, v in dados.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return {"id": c.id}


# --- Lançamentos ---------------------------------------------------------------------

class LancamentoIn(BaseModel):
    tipo: Literal["despesa", "receita"] = "despesa"
    categoria_id: UUID
    descricao: str = Field(min_length=3, max_length=300)
    valor_kz: Decimal = Field(gt=0, **DIN)
    data_competencia: date | None = None
    data_vencimento: date | None = None
    fornecedor_id: UUID | None = None
    evento_id: UUID | None = None
    campanha_id: UUID | None = None
    justificacao: str | None = Field(default=None, max_length=3000)
    referencia: str | None = Field(default=None, max_length=120)
    paga: bool = False                     # só CEO: registar já como paga
    data_pagamento: date | None = None
    forma_pagamento: Forma | None = None


def _validar(db: Session, dados: LancamentoIn) -> CategoriaFinanceira:
    c = db.get(CategoriaFinanceira, dados.categoria_id)
    if c is None or not c.activa or c.tipo != dados.tipo:
        raise ErroNegocio("categoria_invalida", "Categoria inexistente, inactiva ou de outro tipo.")
    return c


@router.get("/lancamentos")
def lancamentos(tipo: str | None = None, estado: str | None = None, de: date | None = None, ate: date | None = None,
                categoria_id: UUID | None = None, ctx: Contexto = Depends(requer(P.DESPESAS_PROPOR)), db: Session = Depends(get_db)):
    q = select(Lancamento)
    if not ctx.pode(P.FINANCAS_VER):
        q = q.where(Lancamento.proposto_por_id == ctx.utilizador.id)
    for col, v in ((Lancamento.tipo, tipo), (Lancamento.estado, estado), (Lancamento.categoria_id, categoria_id)):
        if v:
            q = q.where(col == v)
    if de:
        q = q.where(Lancamento.data_competencia >= de)
    if ate:
        q = q.where(Lancamento.data_competencia <= ate)
    return [lanc_saida(l, db) for l in db.scalars(q.order_by(Lancamento.data_competencia.desc(), Lancamento.numero.desc()).limit(500)).unique()]


@router.post("/lancamentos", status_code=201)
def criar(dados: LancamentoIn, ctx: Contexto = Depends(requer(P.DESPESAS_PROPOR)), db: Session = Depends(get_db)):
    ceo = ctx.pode(P.FINANCAS_APROVAR_DESPESAS)
    if not ceo and (dados.tipo != "despesa" or dados.paga):
        raise proibido("Pode apenas propor despesas; a aprovação e o pagamento são decididos pela CEO.")
    _validar(db, dados)
    if dados.paga and not (dados.forma_pagamento and dados.data_pagamento):
        raise ErroNegocio("pagamento_incompleto", "Indique a data e a forma de pagamento.")
    l = Lancamento(**dados.model_dump(exclude={"paga", "data_competencia"}), data_competencia=dados.data_competencia or hoje(),
                   proposto_por_id=ctx.utilizador.id)
    if ceo:
        l.estado, l.aprovado_por_id, l.aprovado_em = ("paga" if dados.paga else "aprovada"), ctx.utilizador.id, agora()
    else:
        l.data_pagamento = l.forma_pagamento = None
    db.add(l)
    db.flush()
    db.refresh(l)
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="lancamento", entidade_id=l.id,
             resumo=f"{'Registou' if ceo else 'Propôs'} {codigo(l)} «{l.descricao}» ({fkz(l.valor_kz)}, {l.categoria.nome})", ip=ctx.ip)
    excesso = svc.excede_orcamento(db, l.categoria_id, l.data_competencia, Decimal(0), excluir_id=None) if l.tipo == "despesa" else None
    if not ceo:
        notificar_ceo(db, "despesa", f"Despesa proposta: {l.descricao}", f"{ctx.utilizador.nome} — {fkz(l.valor_kz)} ({l.categoria.nome})", "/financas")
    elif excesso:
        notificar_ceo(db, "orcamento", f"Orçamento excedido: {l.categoria.nome}", f"Excesso de {fkz(excesso['excesso_kz'])} em {l.data_competencia.strftime('%m/%Y')}.",
                      "/financas", chave_dedup=f"orc:{l.categoria_id}:{l.data_competencia:%Y-%m}:{l.id}")
    db.commit()
    return lanc_saida(l, db)


@router.put("/lancamentos/{lid}")
def editar(lid: UUID, dados: LancamentoIn, ctx: Contexto = Depends(requer(P.DESPESAS_PROPOR)), db: Session = Depends(get_db)):
    l = db.get(Lancamento, lid)
    if l is None or not (ctx.pode(P.FINANCAS_VER) or l.proposto_por_id == ctx.utilizador.id):
        raise nao_encontrado("Lançamento")
    ceo = ctx.pode(P.FINANCAS_APROVAR_DESPESAS)
    if l.estado not in ("proposta", "aprovada") or (not ceo and l.estado != "proposta"):
        raise ErroNegocio("lancamento_fechado", "Este lançamento já não pode ser alterado (anule-o e registe um novo, se necessário).")
    if dados.tipo != l.tipo:
        raise ErroNegocio("tipo_imutavel", "O tipo não pode ser alterado.")
    _validar(db, dados)
    novos = dados.model_dump(exclude={"paga", "data_pagamento", "forma_pagamento", "tipo"})
    novos["data_competencia"] = novos["data_competencia"] or l.data_competencia
    antes = {k: getattr(l, k) for k in novos}
    for k, v in novos.items():
        setattr(l, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="lancamento", entidade_id=l.id,
             resumo=f"Alterou {codigo(l)}", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    return lanc_saida(l, db)


class DecisaoIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=2000)


def _obter(db: Session, lid: UUID) -> Lancamento:
    l = db.scalar(select(Lancamento).where(Lancamento.id == lid).with_for_update(of=Lancamento))
    if l is None:
        raise nao_encontrado("Lançamento")
    return l


@router.post("/lancamentos/{lid}/aprovar")
def aprovar(lid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.FINANCAS_APROVAR_DESPESAS)), db: Session = Depends(get_db)):
    l = _obter(db, lid)
    if l.estado != "proposta":
        raise ErroNegocio("estado_invalido", "Só propostas podem ser aprovadas.")
    l.estado, l.aprovado_por_id, l.aprovado_em, l.motivo_decisao = "aprovada", ctx.utilizador.id, agora(), dados.motivo
    registar(db, utilizador_id=ctx.utilizador.id, accao="aprovar", entidade="lancamento", entidade_id=l.id,
             resumo=f"Aprovou {codigo(l)} «{l.descricao}» ({fkz(l.valor_kz)})", ip=ctx.ip)
    notificar(db, l.proposto_por_id, "despesa", f"Despesa aprovada: {l.descricao}", dados.motivo, "/financas", excepto=ctx.utilizador.id)
    db.commit()
    return lanc_saida(l, db)


@router.post("/lancamentos/{lid}/rejeitar")
def rejeitar(lid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.FINANCAS_APROVAR_DESPESAS)), db: Session = Depends(get_db)):
    l = _obter(db, lid)
    if l.estado != "proposta":
        raise ErroNegocio("estado_invalido", "Só propostas podem ser rejeitadas.")
    if not (dados.motivo or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo.")
    l.estado, l.motivo_decisao = "rejeitada", dados.motivo.strip()
    registar(db, utilizador_id=ctx.utilizador.id, accao="rejeitar", entidade="lancamento", entidade_id=l.id,
             resumo=f"Rejeitou {codigo(l)}: {dados.motivo.strip()}", ip=ctx.ip)
    notificar(db, l.proposto_por_id, "despesa", f"Despesa não aprovada: {l.descricao}", dados.motivo.strip(), "/financas", excepto=ctx.utilizador.id)
    db.commit()
    return lanc_saida(l, db)


class PagarIn(BaseModel):
    data_pagamento: date | None = None
    forma_pagamento: Forma
    referencia: str | None = Field(default=None, max_length=120)


@router.post("/lancamentos/{lid}/pagar")
def pagar(lid: UUID, dados: PagarIn, ctx: Contexto = Depends(requer(P.FINANCAS_APROVAR_DESPESAS)), db: Session = Depends(get_db)):
    l = _obter(db, lid)
    if l.estado != "aprovada":
        raise ErroNegocio("estado_invalido", "Só lançamentos aprovados podem ser marcados como pagos/recebidos.")
    dp = dados.data_pagamento or hoje()
    if dp > hoje():
        raise ErroNegocio("data_invalida", "A data não pode ser futura.")
    l.estado, l.data_pagamento, l.forma_pagamento = "paga", dp, dados.forma_pagamento
    l.referencia = dados.referencia or l.referencia
    registar(db, utilizador_id=ctx.utilizador.id, accao="pagar", entidade="lancamento", entidade_id=l.id,
             resumo=f"{'Pagou' if l.tipo == 'despesa' else 'Recebeu'} {codigo(l)} ({fkz(l.valor_kz)}, {dados.forma_pagamento})", ip=ctx.ip)
    db.commit()
    return lanc_saida(l, db)


@router.post("/lancamentos/{lid}/anular")
def anular(lid: UUID, dados: DecisaoIn, ctx: Contexto = Depends(requer(P.FINANCAS_APROVAR_DESPESAS)), db: Session = Depends(get_db)):
    l = _obter(db, lid)
    if l.estado in ("rejeitada", "anulada"):
        raise ErroNegocio("estado_invalido", "Já está anulado/rejeitado.")
    if not (dados.motivo or "").strip():
        raise ErroNegocio("motivo_obrigatorio", "Indique o motivo da anulação.")
    antigo = l.estado
    l.estado, l.motivo_decisao = "anulada", dados.motivo.strip()
    registar(db, utilizador_id=ctx.utilizador.id, accao="anular", entidade="lancamento", entidade_id=l.id,
             resumo=f"Anulou {codigo(l)} (estava {antigo}): {dados.motivo.strip()}", alteracoes={"estado": [antigo, "anulada"]}, ip=ctx.ip)
    db.commit()
    return lanc_saida(l, db)


TIPOS_DOC = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


@router.post("/lancamentos/{lid}/documento")
async def documento(lid: UUID, ficheiro: UploadFile = File(...), ctx: Contexto = Depends(requer(P.DESPESAS_PROPOR)), db: Session = Depends(get_db)):
    l = db.get(Lancamento, lid)
    if l is None or not (ctx.pode(P.FINANCAS_VER) or l.proposto_por_id == ctx.utilizador.id):
        raise nao_encontrado("Lançamento")
    tipo = (ficheiro.content_type or "").split(";")[0].strip().lower()
    if tipo not in TIPOS_DOC:
        raise ErroNegocio("tipo_nao_permitido", "Anexe a factura/recibo em PDF ou imagem.")
    limite = settings.anexo_tamanho_maximo_mb * 1024 * 1024
    conteudo = await ficheiro.read(limite + 1)
    if len(conteudo) > limite or not conteudo:
        raise ErroNegocio("ficheiro_invalido", f"Ficheiro vazio ou maior que {settings.anexo_tamanho_maximo_mb} MB.")
    l.documento, l.documento_tipo, l.documento_nome = conteudo, tipo, (ficheiro.filename or "documento")[:255].replace("/", "_")
    registar(db, utilizador_id=ctx.utilizador.id, accao="anexar", entidade="lancamento", entidade_id=l.id, resumo=f"Anexou documento a {codigo(l)}", ip=ctx.ip)
    db.commit()
    return {"documento_nome": l.documento_nome}


@router.get("/lancamentos/{lid}/documento")
def ver_documento(lid: UUID, ctx: Contexto = Depends(requer(P.DESPESAS_PROPOR)), db: Session = Depends(get_db)):
    l = db.scalar(select(Lancamento).options(undefer(Lancamento.documento)).where(Lancamento.id == lid))
    if l is None or l.documento is None or not (ctx.pode(P.FINANCAS_VER) or l.proposto_por_id == ctx.utilizador.id):
        raise nao_encontrado("Documento")
    return Response(content=l.documento, media_type=l.documento_tipo,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(l.documento_nome)}", "X-Content-Type-Options": "nosniff"})


@router.get("/contas-a-pagar")
def contas_a_pagar(ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    itens = [lanc_saida(l) for l in svc.contas_a_pagar(db)]
    return {"total_kz": str(sum((Decimal(i["valor_kz"]) for i in itens), Decimal(0))), "vencidas": sum(1 for i in itens if i["vencida"]), "itens": itens}


# --- Orçamento ------------------------------------------------------------------------

class OrcamentoIn(BaseModel):
    ano: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)
    valores: list[dict] = Field(max_length=100)  # [{"categoria_id": ..., "valor_kz": ... | null}]


@router.get("/orcamento")
def orcamento(ano: int, mes: int = Query(ge=1, le=12), ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    return svc.orcamento_vs_real(db, ano, mes)


@router.put("/orcamento")
def definir_orcamento(dados: OrcamentoIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    for v in dados.valores:
        try:
            cid = UUID(str(v["categoria_id"]))
            valor = None if v.get("valor_kz") in (None, "") else Decimal(str(v["valor_kz"]))
        except (KeyError, ValueError, ArithmeticError) as e:
            raise ErroNegocio("orcamento_invalido", "Valores de orçamento inválidos.") from e
        if valor is not None and valor < 0:
            raise ErroNegocio("orcamento_invalido", "O orçamento não pode ser negativo.")
        existente = db.scalar(select(Orcamento).where(Orcamento.ano == dados.ano, Orcamento.mes == dados.mes, Orcamento.categoria_id == cid))
        if valor is None:
            if existente:
                db.delete(existente)
        elif existente:
            existente.valor_kz = valor
        else:
            db.add(Orcamento(ano=dados.ano, mes=dados.mes, categoria_id=cid, valor_kz=valor))
    registar(db, utilizador_id=ctx.utilizador.id, accao="orcamento", entidade="orcamento", entidade_id=f"{dados.ano}-{dados.mes:02d}",
             resumo=f"Definiu o orçamento de {dados.mes:02d}/{dados.ano}", ip=ctx.ip)
    db.commit()
    return svc.orcamento_vs_real(db, dados.ano, dados.mes)


@router.post("/orcamento/copiar")
def copiar_orcamento(ano: int, mes: int = Query(ge=1, le=12), ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    """Copia o orçamento do mês anterior para o mês indicado (não sobrepõe valores já definidos)."""
    a, m = svc.mes_anterior(ano, mes)
    for o in db.scalars(select(Orcamento).where(Orcamento.ano == a, Orcamento.mes == m)).unique():
        db.execute(insert(Orcamento).values(ano=ano, mes=mes, categoria_id=o.categoria_id, valor_kz=o.valor_kz)
                   .on_conflict_do_nothing(constraint="ux_orcamento_mes_categoria"))
    db.commit()
    return svc.orcamento_vs_real(db, ano, mes)


# --- Despesas fixas ---------------------------------------------------------------------

class FixaIn(BaseModel):
    descricao: str = Field(min_length=3, max_length=200)
    categoria_id: UUID
    valor_kz: Decimal = Field(gt=0, **DIN)
    dia_vencimento: int = Field(ge=1, le=28)
    fornecedor_id: UUID | None = None
    activa: bool = True


def _fixa(f: DespesaFixa) -> dict:
    return {"id": f.id, "descricao": f.descricao, "categoria": {"id": f.categoria.id, "nome": f.categoria.nome}, "valor_kz": str(f.valor_kz),
            "dia_vencimento": f.dia_vencimento, "fornecedor_id": f.fornecedor_id, "activa": f.activa, "is_demo": f.is_demo}


@router.get("/despesas-fixas")
def fixas(ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    return [_fixa(f) for f in db.scalars(select(DespesaFixa).order_by(DespesaFixa.activa.desc(), DespesaFixa.descricao)).unique()]


@router.post("/despesas-fixas", status_code=201)
def criar_fixa(dados: FixaIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    c = db.get(CategoriaFinanceira, dados.categoria_id)
    if c is None or c.tipo != "despesa":
        raise ErroNegocio("categoria_invalida", "Categoria de despesa inválida.")
    f = DespesaFixa(**dados.model_dump())
    db.add(f)
    db.flush()
    registar(db, utilizador_id=ctx.utilizador.id, accao="criar", entidade="despesa_fixa", entidade_id=f.id,
             resumo=f"Criou a despesa fixa «{f.descricao}» ({fkz(f.valor_kz)}/mês)", ip=ctx.ip)
    db.commit()
    db.refresh(f)
    return _fixa(f)


@router.put("/despesas-fixas/{fid}")
def editar_fixa(fid: UUID, dados: FixaIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    f = db.get(DespesaFixa, fid)
    if f is None:
        raise nao_encontrado("Despesa fixa")
    novos = dados.model_dump()
    antes = {k: getattr(f, k) for k in novos}
    for k, v in novos.items():
        setattr(f, k, v)
    registar(db, utilizador_id=ctx.utilizador.id, accao="actualizar", entidade="despesa_fixa", entidade_id=f.id,
             resumo=f"Alterou a despesa fixa «{f.descricao}»", alteracoes=diferencas(antes, novos), ip=ctx.ip)
    db.commit()
    db.refresh(f)
    return _fixa(f)


@router.post("/despesas-fixas/gerar")
def gerar_fixas(ano: int, mes: int = Query(ge=1, le=12), ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    """Cria (aprovados, por pagar) os lançamentos do mês para as despesas fixas activas. Idempotente."""
    ini, _ = svc.mes(ano, mes)
    criadas = 0
    for f in db.scalars(select(DespesaFixa).where(DespesaFixa.activa.is_(True))).unique():
        r = db.execute(insert(Lancamento).values(
            tipo="despesa", categoria_id=f.categoria_id, descricao=f"{f.descricao} ({mes:02d}/{ano})", valor_kz=f.valor_kz,
            data_competencia=ini, data_vencimento=date(ano, mes, f.dia_vencimento), estado="aprovada", fornecedor_id=f.fornecedor_id,
            despesa_fixa_id=f.id, proposto_por_id=ctx.utilizador.id, aprovado_por_id=ctx.utilizador.id, aprovado_em=agora(), is_demo=f.is_demo,
        ).on_conflict_do_nothing(constraint="ux_lancamento_fixa_mes").returning(Lancamento.id)).first()
        criadas += 1 if r else 0
    registar(db, utilizador_id=ctx.utilizador.id, accao="gerar_fixas", entidade="lancamento", entidade_id=f"{ano}-{mes:02d}",
             resumo=f"Gerou {criadas} despesa(s) fixa(s) de {mes:02d}/{ano}", ip=ctx.ip)
    db.commit()
    return {"criadas": criadas}


# --- Custos por produto, resultados, indicadores -------------------------------------------

@router.get("/custos-produtos")
def custos_produtos(ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    from app.modules.configuracao import service as config
    return {"custo_mao_obra_hora_kz": config.obter(db, "custo_mao_obra_hora_kz"), "margem_minima_pct": config.obter(db, "margem_minima_pct"),
            "produtos": svc.ficha_custos(db)}


class OutrosCustosIn(BaseModel):
    outros_custos_unidade_kz: Decimal | None = Field(default=None, ge=0, **DIN)


@router.put("/custos-produtos/{ficha_id}")
def outros_custos(ficha_id: UUID, dados: OutrosCustosIn, ctx: Contexto = Depends(requer(P.FINANCAS_VER)), db: Session = Depends(get_db)):
    f = db.get(FichaTecnica, ficha_id)
    if f is None:
        raise nao_encontrado("Ficha técnica")
    antigo = f.outros_custos_unidade_kz
    f.outros_custos_unidade_kz = dados.outros_custos_unidade_kz
    registar(db, utilizador_id=ctx.utilizador.id, accao="custos", entidade="ficha_tecnica", entidade_id=f.id,
             resumo=f"Outros custos/unidade de {f.produto.nome}: {antigo} → {dados.outros_custos_unidade_kz}", ip=ctx.ip)
    db.commit()
    return {"ok": True}


@router.get("/resultados")
def resultados(ano: int | None = None, mes: int | None = Query(default=None, ge=1, le=12), ctx: Contexto = Depends(requer(P.FINANCAS_VER)),
               db: Session = Depends(get_db)):
    a, m = ano or hoje().year, mes or hoje().month
    actual = svc.resultados(db, a, m)
    pa, pm = svc.mes_anterior(a, m)
    return {"actual": actual, "anterior": svc.resultados(db, pa, pm), "serie": svc.serie_12_meses(db)}
