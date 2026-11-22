"""Consultas de gestão — a base do assistente (Fase 6).

Cada consulta é uma função determinística sobre os dados reais, com as
permissões de quem pergunta: a mesma regra de acesso dos ecrãs. O assistente
de IA só consegue ver o que a pessoa já podia ver — as consultas que a função
dela não permite nem chegam a ser oferecidas ao modelo.

Sem IA configurada, as mesmas consultas funcionam por botões e por palavras-
-chave. Nenhuma consulta altera dados.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import P
from app.core.tempo import FUSO, formatar_data, hoje, inicio_semana
from app.core.formato import fkz, fpct
from app.dependencies import Contexto
from app.modules.configuracao import service as config

LIMITE_LINHAS = 50
ESTADOS_TAREFA = {"nao_iniciada": "Não iniciada", "em_andamento": "Em andamento", "aguardar_aprovacao": "A aguardar aprovação",
                  "bloqueada": "Bloqueada", "concluida": "Concluída"}
ESTADOS_CONTEUDO = {"ideia": "Ideia", "planeamento": "Planeamento", "criacao": "Criação", "revisao": "Revisão", "aprovado": "Aprovado",
                    "agendado": "Agendado", "publicado": "Publicado", "analisado": "Analisado"}


@dataclass
class Resultado:
    resumo: str
    colunas: list[str] = field(default_factory=list)
    linhas: list[list] = field(default_factory=list)
    ligacao: str | None = None

    def para_dict(self) -> dict:
        return {"resumo": self.resumo, "colunas": self.colunas, "linhas": self.linhas[:LIMITE_LINHAS],
                "total_linhas": len(self.linhas), "ligacao": self.ligacao}


@dataclass
class Consulta:
    id: str
    titulo: str
    descricao: str            # usada também como descrição da ferramenta para a IA
    permissoes: tuple[P, ...]  # basta uma
    palavras: tuple[str, ...]
    executar: Callable[[Session, Contexto], Resultado]
    grupo: str = "Geral"

    def disponivel(self, ctx: Contexto) -> bool:
        return not self.permissoes or any(ctx.pode(p) for p in self.permissoes)


def _qtd(v, unidade: str = "") -> str:
    d = Decimal(v).normalize()
    txt = f"{d:f}".replace(".", ",")
    return f"{txt} {unidade}".strip()


# --- Tarefas ----------------------------------------------------------------------

def _tarefas(ctx: Contexto):
    from app.modules.tarefas.models import Tarefa
    from app.modules.tarefas.service import consulta_visivel
    return Tarefa, consulta_visivel(ctx)


def tarefas_atrasadas(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.tarefas.service import codigo
    Tarefa, q = _tarefas(ctx)
    lista = db.scalars(q.where(Tarefa.estado != "concluida", Tarefa.prazo < hoje()).order_by(Tarefa.prazo)).unique().all()
    linhas = [[codigo(t), t.titulo, t.responsavel.nome, formatar_data(t.prazo), (hoje() - t.prazo).days, t.prioridade] for t in lista]
    resumo = "Não há tarefas em atraso." if not lista else f"{len(lista)} tarefa(s) em atraso; a mais antiga tem {linhas[0][4]} dia(s) de atraso."
    return Resultado(resumo, ["Código", "Tarefa", "Responsável", "Prazo", "Dias de atraso", "Prioridade"], linhas, "/tarefas")


def tarefas_semana(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.tarefas.service import codigo
    Tarefa, q = _tarefas(ctx)
    ini = inicio_semana(hoje())
    fim = ini + timedelta(days=6)
    lista = db.scalars(q.where(Tarefa.estado != "concluida", Tarefa.prazo >= ini, Tarefa.prazo <= fim).order_by(Tarefa.prazo)).unique().all()
    linhas = [[codigo(t), t.titulo, t.responsavel.nome, formatar_data(t.prazo), ESTADOS_TAREFA.get(t.estado, t.estado)] for t in lista]
    resumo = f"{len(lista)} tarefa(s) por concluir com prazo entre {formatar_data(ini)} e {formatar_data(fim)}."
    return Resultado(resumo, ["Código", "Tarefa", "Responsável", "Prazo", "Estado"], linhas, "/tarefas")


def tarefas_bloqueadas_aprovacao(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.tarefas.service import codigo
    Tarefa, q = _tarefas(ctx)
    lista = db.scalars(q.where(Tarefa.estado.in_(("bloqueada", "aguardar_aprovacao"))).order_by(Tarefa.prazo)).unique().all()
    linhas = [[codigo(t), t.titulo, t.responsavel.nome, "Bloqueada" if t.estado == "bloqueada" else "A aguardar aprovação",
               t.motivo_bloqueio or "", formatar_data(t.prazo)] for t in lista]
    b = sum(1 for t in lista if t.estado == "bloqueada")
    resumo = f"{b} bloqueada(s) e {len(lista) - b} a aguardar aprovação."
    return Resultado(resumo, ["Código", "Tarefa", "Responsável", "Situação", "Motivo do bloqueio", "Prazo"], linhas, "/tarefas")


def desempenho_equipa(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.dashboard.metricas import indicadores_periodo
    from app.modules.equipa.models import Utilizador
    ini = inicio_semana(hoje())
    fim = ini + timedelta(days=6)
    linhas = []
    for u in db.scalars(select(Utilizador).where(Utilizador.activo.is_(True)).order_by(Utilizador.nome)):
        i = indicadores_periodo(db, ini, fim, u.id)
        taxa = i["taxa_cumprimento"]
        linhas.append([u.nome, i["tarefas_com_prazo"], i["concluidas"], i["em_atraso"], fpct(taxa)])
    return Resultado(f"Execução da semana de {formatar_data(ini)} a {formatar_data(fim)}, por pessoa.",
                     ["Pessoa", "Com prazo na semana", "Concluídas", "Em atraso", "Cumprimento"], linhas, "/rotina")


# --- Produção e stock -------------------------------------------------------------

def o_que_produzir(db: Session, ctx: Contexto) -> Resultado:
    """Produtos acabados: stock disponível vs. mínimo + encomendas em aberto − o que já está em produção."""
    from app.modules.producao.models import FichaTecnica, OrdemProducao
    from app.modules.producao.service import necessidades
    from app.modules.stock import service as stock
    from app.modules.stock.models import Artigo
    from app.modules.vendas.models import Encomenda, LinhaEncomenda

    produtos = db.scalars(select(Artigo).where(Artigo.categoria == "produto_acabado", Artigo.activo.is_(True)).order_by(Artigo.nome)).unique().all()
    saldos = stock.saldos(db, [a.id for a in produtos])
    encomendado = dict(db.execute(
        select(LinhaEncomenda.artigo_id, func.sum(LinhaEncomenda.quantidade)).join(Encomenda)
        .where(Encomenda.estado.in_(("recebida", "em_preparacao"))).group_by(LinhaEncomenda.artigo_id)).all())
    em_producao = dict(db.execute(
        select(OrdemProducao.produto_id, func.sum(OrdemProducao.quantidade_planeada))
        .where(OrdemProducao.estado.in_(("planeada", "em_curso"))).group_by(OrdemProducao.produto_id)).all())
    linhas = []
    for a in produtos:
        disp = saldos.get(a.id, Decimal(0)) - stock_reservado(db, a.id)
        enc = encomendado.get(a.id, Decimal(0))
        prod = em_producao.get(a.id, Decimal(0))
        sugerido = max(Decimal(0), a.stock_minimo + enc - disp - prod)
        if sugerido <= 0:
            continue
        ficha = db.scalars(select(FichaTecnica).where(FichaTecnica.produto_id == a.id, FichaTecnica.activa.is_(True))
                           .order_by(FichaTecnica.versao.desc())).unique().first()
        if ficha is None:
            materiais = "sem ficha técnica activa"
        else:
            faltas = [f"{n['artigo'].nome} (faltam {_qtd(n['falta'], n['artigo'].unidade)})" for n in necessidades(db, ficha, sugerido) if n["falta"] > 0]
            materiais = "; ".join(faltas) if faltas else "materiais disponíveis"
        linhas.append([a.nome, _qtd(disp, a.unidade), _qtd(a.stock_minimo, a.unidade), _qtd(enc, a.unidade),
                       _qtd(prod, a.unidade), _qtd(sugerido, a.unidade), materiais])
    resumo = ("Nenhum produto precisa de produção: o stock cobre o mínimo e as encomendas em aberto."
              if not linhas else f"{len(linhas)} produto(s) a produzir. Sugestão = mínimo + encomendas em aberto − disponível − já em produção.")
    return Resultado(resumo, ["Produto", "Disponível", "Mínimo", "Encomendado (em aberto)", "Já em produção", "Sugestão a produzir",
                              "Materiais"], linhas, "/producao")


def stock_reservado(db: Session, artigo_id) -> Decimal:
    from app.modules.vendas.service import reservado
    return Decimal(reservado(db, artigo_id))


def stock_baixo(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.stock import service as stock
    lista = stock.abaixo_minimo(db)
    linhas = [[a.nome, a.categoria.replace("_", " ").capitalize(), _qtd(q, a.unidade), _qtd(a.stock_minimo, a.unidade), "Ruptura" if q <= 0 else "Abaixo do mínimo"]
              for a, q in lista]
    rupt = sum(1 for _, q in lista if q <= 0)
    resumo = "Todos os artigos estão acima do stock mínimo." if not lista else f"{len(lista)} artigo(s) abaixo do mínimo, {rupt} em ruptura."
    return Resultado(resumo, ["Artigo", "Categoria", "Disponível", "Mínimo", "Situação"], linhas, "/stock")


def validades(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.stock import service as stock
    dias = int(config.obter(db, "dias_alerta_validade"))
    lista = stock.proximos_validade(db, dias)
    linhas = [[l.artigo.nome, l.numero, _qtd(s, l.artigo.unidade), stock.descrever_validade(l)] for l, s in lista]
    exp = sum(1 for l, _ in lista if l.validade < hoje())
    resumo = f"{len(lista)} lote(s) com validade nos próximos {dias} dias ou expirados ({exp} expirado(s))."
    return Resultado(resumo, ["Artigo", "Lote", "Quantidade", "Validade"], linhas, "/stock")


def producao_em_curso(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.producao.models import OrdemProducao
    from app.modules.producao.service import codigo
    lista = db.scalars(select(OrdemProducao).where(OrdemProducao.estado.in_(("planeada", "em_curso"))).order_by(OrdemProducao.data_prevista)).unique().all()
    linhas = [[codigo(o), o.produto.nome, _qtd(o.quantidade_planeada, o.produto.unidade),
               "Planeada" if o.estado == "planeada" else "Em curso", formatar_data(o.data_prevista),
               "Sim" if o.data_prevista < hoje() else "Não"] for o in lista]
    atrasadas = sum(1 for o in lista if o.data_prevista < hoje())
    return Resultado(f"{len(lista)} ordem(ns) planeada(s) ou em curso, {atrasadas} atrasada(s).",
                     ["Ordem", "Produto", "Quantidade", "Estado", "Conclusão prevista", "Atrasada"], linhas, "/producao")


# --- Vendas e clientes ------------------------------------------------------------

def clientes_inactivos(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.vendas.models import Cliente, Encomenda
    dias = int(config.obter(db, "dias_cliente_inactivo"))
    de_ent = func.date(func.timezone(str(FUSO), Encomenda.entregue_em))
    sq = (select(Encomenda.cliente_id, func.max(de_ent).label("ultima"), func.count().label("n"))
          .where(Encomenda.estado == "entregue").group_by(Encomenda.cliente_id).subquery())
    limite = hoje() - timedelta(days=dias)
    linhas_db = db.execute(select(Cliente, sq.c.ultima, sq.c.n).join(sq, sq.c.cliente_id == Cliente.id)
                           .where(Cliente.activo.is_(True), sq.c.ultima < limite).order_by(sq.c.n.desc(), sq.c.ultima)).unique().all()
    linhas = [[c.nome, c.localidade or "", formatar_data(u), (hoje() - u).days, n,
               "Sim" if c.consentimento_marketing else "Não", c.whatsapp or c.telefone or ""] for c, u, n in linhas_db]
    resumo = (f"Nenhuma cliente sem compras há mais de {dias} dias." if not linhas
              else f"{len(linhas)} cliente(s) sem compras há mais de {dias} dias. Só contacte para marketing quem deu consentimento.")
    return Resultado(resumo, ["Cliente", "Localidade", "Última compra", "Dias sem comprar", "N.º de compras", "Consentimento marketing", "Contacto"],
                     linhas, "/vendas")


def encomendas_pendentes(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.vendas.models import Encomenda
    from app.modules.vendas.service import codigo
    lista = db.scalars(select(Encomenda).where(Encomenda.estado.in_(("recebida", "em_preparacao", "pronta")))
                       .order_by(Encomenda.data_prevista.nulls_last(), Encomenda.numero)).unique().all()
    rot = {"recebida": "Recebida", "em_preparacao": "Em preparação", "pronta": "Pronta"}
    linhas = [[codigo(e), e.cliente.nome, rot[e.estado], formatar_data(e.data_prevista) if e.data_prevista else "—",
               "Sim" if e.data_prevista and e.data_prevista < hoje() else "Não",
               "; ".join(f"{_qtd(l.quantidade)} × {l.artigo.nome}" for l in e.linhas)] for e in lista]
    atras = sum(1 for e in lista if e.data_prevista and e.data_prevista < hoje())
    return Resultado(f"{len(lista)} encomenda(s) em aberto, {atras} com entrega atrasada.",
                     ["Encomenda", "Cliente", "Estado", "Entrega prevista", "Atrasada", "Produtos"], linhas, "/vendas")


def por_receber(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.vendas.router import por_receber as pr
    r = pr(db)
    linhas = [[i["codigo"], i["cliente"], fkz(i["em_divida_kz"]), i["dias"], "Sim" if i["atrasado"] else "Não"] for i in r["itens"]]
    atras = sum(1 for i in r["itens"] if i["atrasado"])
    return Resultado(f"Por receber: {fkz(r['total_kz'])} em {len(linhas)} encomenda(s) entregue(s); {atras} além de {r['dias_cobranca']} dias.",
                     ["Encomenda", "Cliente", "Em dívida", "Dias desde a entrega", "Atrasada"], linhas, "/vendas")


def vendas_mes(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.vendas.router import indicadores
    ini = hoje().replace(day=1)
    i = indicadores(db, ini, hoje())
    linhas = [["Facturação líquida", fkz(i["facturacao_liquida_kz"])], ["Recebido", fkz(i["recebido_kz"])],
              ["Encomendas entregues", i["encomendas_entregues"]], ["Encomendas recebidas", i["encomendas_recebidas"]],
              ["Clientes compradoras", i["clientes_compradoras"]], ["Clientes novas", i["clientes_novas"]],
              ["Valor médio por encomenda", fkz(i["ticket_medio_kz"]) if i["ticket_medio_kz"] else "—"]]
    return Resultado(f"Vendas de {formatar_data(ini)} a {formatar_data(hoje())}.", ["Indicador", "Valor"], linhas, "/vendas")


# --- Marketing --------------------------------------------------------------------

def conteudos_semana(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.marketing.models import Conteudo
    ini = inicio_semana(hoje())
    fim = ini + timedelta(days=13)
    lista = db.scalars(select(Conteudo).where(Conteudo.data_publicacao >= ini, Conteudo.data_publicacao <= fim)
                       .order_by(Conteudo.data_publicacao)).unique().all()
    linhas = [[formatar_data(c.data_publicacao), c.plataforma.capitalize(), c.formato.capitalize(), c.tema,
               ESTADOS_CONTEUDO.get(c.estado, c.estado), c.responsavel.nome,
               "Sim" if c.data_publicacao < hoje() and c.estado not in ("publicado", "analisado") else "Não"] for c in lista]
    por_aprovar = sum(1 for c in lista if c.estado == "revisao")
    atras = sum(1 for l in linhas if l[6] == "Sim")
    return Resultado(f"{len(lista)} conteúdo(s) entre {formatar_data(ini)} e {formatar_data(fim)}: {por_aprovar} em revisão, {atras} atrasado(s).",
                     ["Data", "Plataforma", "Formato", "Tema", "Estado", "Responsável", "Atrasado"], linhas, "/marketing")


# --- Finanças (só CEO) ------------------------------------------------------------

def despesas_por_aprovar(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.financas.models import Lancamento
    lista = db.scalars(select(Lancamento).where(Lancamento.estado == "proposta").order_by(Lancamento.criado_em)).unique().all()
    linhas = [[l.descricao, l.categoria.nome, fkz(l.valor_kz), l.proposto_por.nome, formatar_data(l.data_competencia)] for l in lista]
    total = sum((l.valor_kz for l in lista), Decimal(0))
    return Resultado(f"{len(lista)} despesa(s) proposta(s) a aguardar decisão, total {fkz(total)}.",
                     ["Descrição", "Categoria", "Valor", "Proposta por", "Mês de competência"], linhas, "/financas")


def resultado_mes(db: Session, ctx: Contexto) -> Resultado:
    from app.modules.financas.service import resultados
    d = hoje()
    r = resultados(db, d.year, d.month)
    linhas = [["Facturação líquida", fkz(r["facturacao_liquida_kz"])],
              ["Custo dos produtos vendidos", fkz(r["custo_mercadorias_vendidas_kz"])],
              ["Margem bruta", fkz(r["margem_bruta_kz"]) + (f" ({fpct(r['margem_bruta_pct'])})" if r["margem_bruta_pct"] else " (por calcular)")],
              ["Despesas", fkz(r["despesas_total_kz"])], ["Perdas de stock", fkz(r["perdas_stock_kz"])],
              ["Resultado operacional", fkz(r["resultado_kz"])],
              ["Caixa do mês (entradas − saídas)", fkz(r["caixa"]["saldo_kz"])]]
    aviso = "" if r["completo"] else f" Atenção: {r['vendas_sem_custo_registado']} venda(s) sem custo registado — margens por calcular."
    return Resultado(f"Resultado do mês corrente até {formatar_data(d)}.{aviso}", ["Indicador", "Valor"], linhas, "/financas")


CONSULTAS: list[Consulta] = [
    Consulta("tarefas_atrasadas", "Tarefas em atraso", "Tarefas por concluir cujo prazo já passou, com responsável e dias de atraso.",
             (), ("atras", "atraso", "atrasad", "tarefa"), tarefas_atrasadas, "Tarefas"),
    Consulta("tarefas_semana", "Tarefas desta semana", "Tarefas por concluir com prazo nesta semana (segunda a domingo).",
             (), ("tarefas desta semana", "tarefas da semana", "tarefas para esta semana", "prazos"), tarefas_semana, "Tarefas"),
    Consulta("tarefas_bloqueadas", "Bloqueios e aprovações", "Tarefas bloqueadas (com motivo) e tarefas a aguardar aprovação da CEO.",
             (), ("bloque", "aprova", "aguard"), tarefas_bloqueadas_aprovacao, "Tarefas"),
    Consulta("desempenho_equipa", "Execução da equipa", "Tarefas com prazo nesta semana por pessoa: concluídas, em atraso e taxa de cumprimento.",
             (P.RELATORIOS_EQUIPA,), ("equipa", "desempenho", "cumprimento", "pessoa"), desempenho_equipa, "Tarefas"),
    Consulta("o_que_produzir", "O que produzir", "Produtos acabados a produzir: stock disponível face ao mínimo e às encomendas em aberto, "
             "descontando o que já está em produção, e se há materiais para isso.",
             (P.STOCK_VER,), ("produzir", "produção", "producao", "fabricar", "fazer"), o_que_produzir, "Produção e stock"),
    Consulta("producao_em_curso", "Ordens de produção abertas", "Ordens de produção planeadas ou em curso, com data prevista e atrasos.",
             (P.STOCK_VER,), ("ordem", "ordens", "em curso"), producao_em_curso, "Produção e stock"),
    Consulta("stock_baixo", "Stock abaixo do mínimo", "Artigos (matérias-primas, embalagens, produtos) abaixo do stock mínimo ou em ruptura.",
             (P.STOCK_VER,), ("stock", "mínimo", "minimo", "ruptura", "comprar", "falta"), stock_baixo, "Produção e stock"),
    Consulta("validades", "Validades próximas", "Lotes com stock cuja validade termina em breve ou já expirou.",
             (P.STOCK_VER,), ("validade", "expira", "lote"), validades, "Produção e stock"),
    Consulta("encomendas_pendentes", "Encomendas em aberto", "Encomendas recebidas, em preparação ou prontas, com entrega prevista e atrasos.",
             (P.VENDAS_GERIR, P.ENCOMENDAS_PREPARAR), ("encomenda", "entrega", "preparar"), encomendas_pendentes, "Vendas"),
    Consulta("clientes_inactivos", "Clientes inactivas", "Clientes que já compraram mas estão sem comprar há mais dias do que o definido, "
             "indicando se deram consentimento para marketing.", (P.VENDAS_GERIR,), ("inactiv", "cliente", "voltar", "recuperar"), clientes_inactivos, "Vendas"),
    Consulta("por_receber", "Pagamentos por receber", "Encomendas entregues com valor em dívida, há quantos dias e se passou o prazo de cobrança.",
             (P.VENDAS_RELATORIOS,), ("receber", "dívida", "divida", "cobrar", "pagamento"), por_receber, "Vendas"),
    Consulta("vendas_mes", "Vendas do mês", "Indicadores de vendas do mês corrente: facturação, recebido, encomendas, clientes.",
             (P.VENDAS_RELATORIOS,), ("vendas", "vendemos", "facturação", "faturação", "facturamos"), vendas_mes, "Vendas"),
    Consulta("conteudos_semana", "Conteúdos das próximas 2 semanas", "Conteúdos do calendário editorial desta semana e da seguinte, "
             "com estado, responsável e atrasos.", (P.MARKETING_CALENDARIO,), ("conteúdo", "conteudo", "publica", "marketing", "post"),
             conteudos_semana, "Marketing"),
    Consulta("despesas_por_aprovar", "Despesas por aprovar", "Despesas propostas pela equipa a aguardar decisão da CEO.",
             (P.FINANCAS_APROVAR_DESPESAS,), ("despesa", "aprovar despesa"), despesas_por_aprovar, "Finanças"),
    Consulta("resultado_mes", "Resultado do mês", "Facturação, margem bruta, despesas, perdas, resultado operacional e caixa do mês corrente.",
             (P.FINANCAS_VER,), ("resultado", "lucro", "margem", "dinheiro", "caixa"), resultado_mes, "Finanças"),
]

POR_ID = {c.id: c for c in CONSULTAS}


def disponiveis(ctx: Contexto) -> list[Consulta]:
    return [c for c in CONSULTAS if c.disponivel(ctx)]


def correspondencia(texto: str, ctx: Contexto) -> list[Consulta]:
    """Sem IA: escolhe consultas pelas palavras da pergunta (as mais específicas primeiro)."""
    t = texto.lower()
    pontos = []
    for c in disponiveis(ctx):
        p = sum(len(w) for w in c.palavras if w in t)
        if p:
            pontos.append((p, c))
    pontos.sort(key=lambda x: -x[0])
    # Uma segunda consulta só aparece se a pergunta lhe corresponder quase tanto como à primeira.
    return [c for p, c in pontos[:2] if p > 0.8 * pontos[0][0]]
