"""Dados de DEMONSTRAÇÃO — claramente identificados (is_demo=true e prefixo
[DEMO] nos títulos). Não representam dados comerciais ou financeiros reais da
Lumara. Para remover: python -m scripts.seed_demo --limpar

Uso: python -m scripts.seed_demo
"""
import argparse
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import delete, select, text, update

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.tempo import FUSO, hoje, inicio_semana
from app.modules.equipa.models import Sessao, Utilizador
from app.modules.notificacoes.models import Notificacao
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.responsabilidades.models import ActividadeRecorrente, RegraDecisao
from app.modules.tarefas.models import CategoriaTarefa, ComentarioTarefa, Tarefa
from scripts.base import garantir_base

PASSWORD_DEMO = "Lumara-Demo-2026"
USERS = [
    ("Luísa (DEMO)", "luisa@demo.lumara.ao", "ceo", "CEO e proprietária"),
    ("Maira (DEMO)", "maira@demo.lumara.ao", "marketing", "Marketing Digital"),
    ("Diana (DEMO)", "diana@demo.lumara.ao", "producao", "Produção"),
]


def quando(d, h=15):
    return datetime.combine(d, time(h, 0), tzinfo=FUSO).astimezone(timezone.utc)


def limpar(db):
    demo_ids = list(db.scalars(select(Utilizador.id).where(Utilizador.is_demo.is_(True))))
    # Movimentos de stock são imutáveis; remover os DEMO é uma operação administrativa explícita
    # (o trigger é suspenso só dentro desta transacção e reactivado no fim).
    db.execute(text("ALTER TABLE movimentos_stock DISABLE TRIGGER movimentos_stock_imutavel"))
    db.execute(text("ALTER TABLE pagamentos DISABLE TRIGGER pagamentos_imutavel"))
    db.execute(text("DELETE FROM pagamentos WHERE encomenda_id IN (SELECT id FROM encomendas WHERE is_demo)"))
    db.execute(text("ALTER TABLE pagamentos ENABLE TRIGGER pagamentos_imutavel"))
    db.execute(text("DELETE FROM movimentos_stock WHERE encomenda_id IN (SELECT id FROM encomendas WHERE is_demo)"))
    db.execute(text("UPDATE ordens_producao SET lote_id = NULL, tarefa_id = NULL WHERE is_demo"))
    db.execute(text("DELETE FROM nao_conformidades WHERE ordem_id IN (SELECT id FROM ordens_producao WHERE is_demo)"))
    db.execute(text("DELETE FROM movimentos_stock WHERE artigo_id IN (SELECT id FROM artigos WHERE is_demo)"))
    db.execute(text("ALTER TABLE movimentos_stock ENABLE TRIGGER movimentos_stock_imutavel"))
    db.execute(text("DELETE FROM encomendas WHERE is_demo"))
    db.execute(text("DELETE FROM eventos WHERE is_demo"))
    db.execute(text("DELETE FROM clientes WHERE is_demo"))
    db.execute(text("DELETE FROM precos WHERE is_demo"))
    db.execute(text("DELETE FROM lotes WHERE artigo_id IN (SELECT id FROM artigos WHERE is_demo)"))
    db.execute(text("DELETE FROM ordens_producao WHERE is_demo"))
    db.execute(text("DELETE FROM ficha_ingredientes WHERE ficha_id IN (SELECT id FROM fichas_tecnicas WHERE is_demo)"))
    db.execute(text("DELETE FROM fichas_tecnicas WHERE is_demo"))
    db.execute(text("DELETE FROM artigos WHERE is_demo"))
    db.execute(text("DELETE FROM fornecedores WHERE is_demo"))
    db.execute(text("DELETE FROM conteudos WHERE is_demo"))
    db.execute(text("DELETE FROM campanhas WHERE is_demo"))
    db.execute(delete(Ocorrencia).where(Ocorrencia.is_demo.is_(True)))
    db.execute(delete(Tarefa).where(Tarefa.is_demo.is_(True)))
    db.execute(delete(ActividadeRecorrente).where(ActividadeRecorrente.is_demo.is_(True)))
    db.execute(delete(RegraDecisao).where(RegraDecisao.is_demo.is_(True)))
    if demo_ids:
        db.execute(delete(Notificacao).where(Notificacao.utilizador_id.in_(demo_ids)))
        db.execute(delete(Sessao).where(Sessao.utilizador_id.in_(demo_ids)))
        # Utilizadoras DEMO com histórico de auditoria ficam desactivadas (o histórico é imutável).
        db.execute(update(Utilizador).where(Utilizador.id.in_(demo_ids)).values(activo=False))
        for uid in demo_ids:
            try:
                with db.begin_nested():
                    db.execute(delete(Utilizador).where(Utilizador.id == uid))
            except Exception:  # noqa: BLE001 — referenciada no registo de actividade
                pass
    db.commit()


def semear(db):
    garantir_base(db)
    if db.scalar(select(Utilizador).where(Utilizador.email == USERS[0][1], Utilizador.activo.is_(True))):
        print("Os dados DEMO já existem. Use --limpar para os remover primeiro.")
        return
    u = {}
    for nome, email, funcao, cargo in USERS:
        existente = db.scalar(select(Utilizador).where(Utilizador.email == email))
        if existente:
            existente.activo = True
            existente.password_hash = hash_password(PASSWORD_DEMO)
            u[funcao] = existente
        else:
            u[funcao] = Utilizador(nome=nome, email=email, funcao=funcao, cargo=cargo, is_demo=True,
                                   password_hash=hash_password(PASSWORD_DEMO))
            db.add(u[funcao])
    db.flush()
    cat = {c.nome: c.id for c in db.scalars(select(CategoriaTarefa))}
    ceo, mai, dia = u["ceo"].id, u["marketing"].id, u["producao"].id
    d = hoje()
    seg = inicio_semana(d)

    actividades = [
        ("Publicar conteúdos do calendário editorial", "marketing", mai, "Conteúdos e redes sociais", "semanal", 4,
         "POP-MKT-01", "Publicações feitas vs. planeadas na semana", False),
        ("Relatório semanal de marketing", "marketing", mai, "Conteúdos e redes sociais", "semanal", 4, None,
         "Relatório entregue até sexta-feira", True),
        ("Responder a mensagens de potenciais clientes", "marketing", mai, "Atendimento", "diaria", 0, "POP-ATD-01",
         "Mensagens respondidas em menos de 24 h", False),
        ("Contagem de matérias-primas e embalagens", "producao", dia, "Matérias-primas e embalagens", "semanal", 0,
         "POP-STK-01", "Contagem registada e necessidades comunicadas", False),
        ("Registo de lotes e validades da produção", "producao", dia, "Qualidade", "semanal", 4, None, None, False),
        ("Revisão semanal de resultados", "gestao", ceo, "Gestão e estratégia", "semanal", 4, None,
         "Relatório semanal fechado", False),
    ]
    for nome, area, resp, catn, freq, dia_p, pop, ind, aprov in actividades:
        db.add(ActividadeRecorrente(nome=f"[DEMO] {nome}", area=area, responsavel_id=resp, categoria_id=cat.get(catn),
                                    frequencia=freq, dia_prazo=dia_p, procedimento_ref=pop, indicador=ind,
                                    requer_aprovacao=aprov, is_demo=True))

    regras = [
        ("Publicar conteúdo já aprovado no calendário editorial", "marketing", "autonoma", "marketing", None),
        ("Responder a clientes com informação de produto e preços em vigor", "vendas", "autonoma", "marketing", None),
        ("Rejeitar um lote com não conformidade", "producao", "informar_ceo", "producao", None),
        ("Planear a produção semanal a partir das encomendas", "producao", "autonoma", "producao", None),
        ("Compra de matérias-primas acima do limite", "stock", "aprovacao_ceo", "producao", None),
        ("Alterar preços de venda", "vendas", "aprovacao_ceo", "ceo", None),
        ("Criar promoção ou desconto", "marketing", "aprovacao_ceo", "marketing", None),
        ("Aprovar despesas e investimentos", "financas", "aprovacao_ceo", "ceo", None),
    ]
    for decisao, area, nivel, funcao, lim in regras:
        db.add(RegraDecisao(decisao=f"[DEMO] {decisao}", area=area, nivel=nivel, funcao_responsavel=funcao,
                            limite_valor_kz=lim, is_demo=True,
                            observacoes="Exemplo de demonstração — rever e definir limites reais." if nivel == "aprovacao_ceo" else None))

    def tarefa(titulo, resp, catn, prazo, estado="nao_iniciada", prio="media", aprov=False, concl=None, motivo=None,
               criada=None, desc=None, resultado=None):
        t = Tarefa(titulo=f"[DEMO] {titulo}", descricao=desc, responsavel_id=resp, criado_por_id=ceo, categoria_id=cat.get(catn),
                   prazo=prazo, data_inicio=min(prazo, (criada or prazo - timedelta(days=5))), prioridade=prio, estado=estado,
                   requer_aprovacao=aprov, motivo_bloqueio=motivo, resultado_esperado=resultado, is_demo=True,
                   concluida_em=quando(concl) if concl else None,
                   submetida_em=quando(d - timedelta(days=3)) if estado == "aguardar_aprovacao" else None)
        if criada:
            t.criada_em = quando(criada, 9)
        db.add(t)
        return t

    # Histórico concluído nas últimas semanas (alimenta gráficos e taxas).
    for i in range(1, 7):
        s = seg - timedelta(weeks=i)
        tarefa(f"Publicações da semana {s.isocalendar().week}", mai, "Conteúdos e redes sociais", s + timedelta(days=4),
               "concluida", concl=s + timedelta(days=4 if i % 3 else 5), criada=s)
        tarefa(f"Contagem semanal de stock (sem. {s.isocalendar().week})", dia, "Matérias-primas e embalagens", s + timedelta(days=1),
               "concluida", concl=s + timedelta(days=1), criada=s)
        if i % 2 == 0:
            tarefa(f"Revisão de resultados (sem. {s.isocalendar().week})", ceo, "Gestão e estratégia", s + timedelta(days=4),
                   "concluida", concl=s + timedelta(days=4), criada=s)

    tarefa("Fotografar a nova linha para cabelos 4C/4D", mai, "Conteúdos e redes sociais", d - timedelta(days=3), "em_andamento",
           "alta", aprov=True, criada=d - timedelta(days=9), desc="Sessão fotográfica em fundo natural (bege/verde).",
           resultado="10 fotografias editadas prontas a publicar")
    tarefa("Guião para Reel de bastidores da produção", mai, "Conteúdos e redes sociais", d + timedelta(days=1),
           "aguardar_aprovacao", "media", aprov=True, criada=d - timedelta(days=6))
    tarefa("Plano de publicações da próxima quinzena", mai, "Conteúdos e redes sociais", d + timedelta(days=4), "nao_iniciada",
           "alta", aprov=True, criada=d - timedelta(days=1))
    tarefa("Produzir lote de sabonetes artesanais", dia, "Produção", d + timedelta(days=2), "em_andamento", "alta",
           criada=d - timedelta(days=4), resultado="Quantidade produzida registada e lote etiquetado")
    tarefa("Registar validades dos óleos corporais em armazém", dia, "Qualidade", d - timedelta(days=1), "nao_iniciada", "media",
           criada=d - timedelta(days=7))
    tarefa("Encomendar frascos para óleo fortalecedor de unhas", dia, "Matérias-primas e embalagens", d - timedelta(days=4),
           "bloqueada", "critica", motivo="A aguardar decisão da CEO sobre o fornecedor e o orçamento.", criada=d - timedelta(days=10))
    tarefa("Preparar kits de autocuidado para encomendas", dia, "Encomendas", d, "nao_iniciada", "alta", criada=d - timedelta(days=2))
    tarefa("Definir metas do próximo trimestre", ceo, "Gestão e estratégia", d + timedelta(days=8), "nao_iniciada", "alta",
           criada=d - timedelta(days=1))
    db.flush()

    db.add(Ocorrencia(tipo="necessidade_material", gravidade="alta", titulo="[DEMO] Frascos de 30 ml quase esgotados",
                      descricao="Restam poucas unidades; necessário para o óleo fortalecedor de unhas.", reportada_por_id=dia, is_demo=True))
    db.add(Ocorrencia(tipo="reclamacao_cliente", gravidade="media", titulo="[DEMO] Cliente reportou atraso na entrega",
                      descricao="Mensagem recebida pelo Instagram.", reportada_por_id=mai, is_demo=True))
    db.flush()
    t = db.scalar(select(Tarefa).where(Tarefa.titulo.like("[DEMO] Guião%")))
    db.add(ComentarioTarefa(tarefa_id=t.id, autor_id=mai, tipo="submissao", texto="Guião pronto, segue em anexo para revisão."))
    db.flush()
    semear_producao(db, u["producao"], u["ceo"])
    semear_marketing(db, u["marketing"], u["ceo"])
    semear_vendas(db, u["marketing"], u["producao"], u["ceo"])
    db.commit()
    print("Dados DEMO criados.")
    for nome, email, funcao, _ in USERS:
        print(f"  {nome:14} {email:24} palavra-passe: {PASSWORD_DEMO}")


def semear_producao(db, diana, luisa):
    """Fase 2 — artigos, lotes, ficha técnica e ordens DEMO. Sem custos: os custos
    reais são introduzidos pela CEO (não se inventam dados financeiros)."""
    from decimal import Decimal as D
    from app.dependencies import Contexto
    from app.modules.producao import service as prod
    from app.modules.producao.models import FichaIngrediente, FichaTecnica, OrdemProducao
    from app.modules.stock import service as stock
    from app.modules.stock.models import Artigo, Fornecedor

    ctx = Contexto(utilizador=diana, sessao=None, ip=None)
    d = hoje()
    forn = Fornecedor(nome="[DEMO] Fornecedor de óleos vegetais", is_demo=True)
    forn2 = Fornecedor(nome="[DEMO] Fornecedor de embalagens", is_demo=True)
    db.add_all([forn, forn2])
    db.flush()
    art = {}
    for cod, nome, cat, un, minimo, f, lotes in [
        ("MP-COCO", "Óleo de coco virgem", "materia_prima", "ml", 2000, forn, True),
        ("MP-RICINO", "Óleo de rícino", "materia_prima", "ml", 1000, forn, True),
        ("MP-KARITE", "Manteiga de karité", "materia_prima", "g", 1000, forn, True),
        ("MP-ESS-LAV", "Óleo essencial de lavanda", "materia_prima", "ml", 50, forn, True),
        ("EMB-FR30", "Frasco âmbar 30 ml com conta-gotas", "embalagem", "un", 50, forn2, False),
        ("EMB-ROT", "Rótulo Lumara", "embalagem", "un", 100, forn2, False),
        ("PA-UNHAS30", "Óleo fortalecedor de unhas 30 ml", "produto_acabado", "un", 20, None, True),
        ("PA-CORPO100", "Óleo corporal 100 ml", "produto_acabado", "un", 15, None, True),
    ]:
        a = Artigo(codigo=f"DEMO-{cod}", nome=f"[DEMO] {nome}", categoria=cat, unidade=un, stock_minimo=D(minimo),
                   fornecedor_id=f.id if f else None, controla_lotes=lotes, is_demo=True)
        db.add(a)
        art[cod] = a
    db.flush()
    E = stock.DadosEntrada
    stock.registar_entrada(db, ctx, art["MP-COCO"].id, E(D(5000), validade=d + timedelta(days=300), data_movimento=d - timedelta(days=20)), is_demo=True)
    stock.registar_entrada(db, ctx, art["MP-RICINO"].id, E(D(800), validade=d + timedelta(days=25), data_movimento=d - timedelta(days=40)), is_demo=True)
    stock.registar_entrada(db, ctx, art["MP-KARITE"].id, E(D(3000), validade=d + timedelta(days=200), data_movimento=d - timedelta(days=15)), is_demo=True)
    stock.registar_entrada(db, ctx, art["MP-ESS-LAV"].id, E(D(200), validade=d + timedelta(days=400), data_movimento=d - timedelta(days=30)), is_demo=True)
    stock.registar_entrada(db, ctx, art["EMB-FR30"].id, E(D(60), data_movimento=d - timedelta(days=30)), is_demo=True)
    stock.registar_entrada(db, ctx, art["EMB-ROT"].id, E(D(500), data_movimento=d - timedelta(days=30)), is_demo=True)

    ficha = FichaTecnica(codigo="DEMO-FT-UNHAS30", versao=1, produto_id=art["PA-UNHAS30"].id,
                         nome="[DEMO] Óleo fortalecedor de unhas 30 ml", rendimento=D(10), tempo_producao_min=90, validade_dias=365,
                         instrucoes="1. Higienizar bancada e utensílios.\n2. Pesar os óleos.\n3. Misturar e juntar o óleo essencial.\n"
                                    "4. Envasar, fechar e rotular.\n5. Registar lote e validade.",
                         requisitos_qualidade="Aspecto límpido, sem partículas; frasco bem vedado; rótulo com lote e validade.",
                         is_demo=True)
    ficha.ingredientes = [FichaIngrediente(artigo_id=art["MP-RICINO"].id, quantidade=D(150), ordem=0),
                          FichaIngrediente(artigo_id=art["MP-COCO"].id, quantidade=D(140), ordem=1),
                          FichaIngrediente(artigo_id=art["MP-ESS-LAV"].id, quantidade=D(10), ordem=2),
                          FichaIngrediente(artigo_id=art["EMB-FR30"].id, quantidade=D(10), ordem=3),
                          FichaIngrediente(artigo_id=art["EMB-ROT"].id, quantidade=D(10), ordem=4)]
    db.add(ficha)
    db.flush()
    feita = OrdemProducao(ficha_id=ficha.id, produto_id=ficha.produto_id, quantidade_planeada=D(30), responsavel_id=diana.id,
                          data_inicio=d - timedelta(days=6), data_prevista=d - timedelta(days=5), criado_por_id=luisa.id, is_demo=True)
    db.add(feita)
    db.flush()
    db.refresh(feita)
    prod.concluir(db, ctx, feita, D(28), numero_lote=None, validade=None, notas="Duas unidades com vedação defeituosa.")
    db.add(OrdemProducao(ficha_id=ficha.id, produto_id=ficha.produto_id, quantidade_planeada=D(20), responsavel_id=diana.id,
                         data_inicio=d, data_prevista=d + timedelta(days=2), criado_por_id=luisa.id, is_demo=True))
    db.flush()


def semear_marketing(db, maira, luisa):
    """Fase 3 — conteúdos e campanha DEMO em vários estados do fluxo. Sem métricas inventadas."""
    from app.core.tempo import agora
    from app.modules.marketing.models import Campanha, Conteudo
    d = hoje()
    camp = Campanha(nome="[DEMO] Kits de autocuidado para as festas", objectivo="Dar a conhecer os kits de autocuidado como presente.",
                    publico_alvo="Clientes actuais e seguidoras em Luanda", mensagem_chave="Oferecer cuidado é oferecer tempo para si.",
                    canais=["instagram", "whatsapp"], data_inicio=d + timedelta(days=5), data_fim=d + timedelta(days=30),
                    responsavel_id=maira.id, criado_por_id=maira.id, is_demo=True)
    db.add(camp)
    db.flush()
    itens = [
        (-6, "instagram", "educativo", "carrossel", "Como hidratar cabelos 4C/4D no calor", "publicado",
         "Cabelos 4C e 4D pedem hidratação com calma e camadas. Guarda este passo a passo para o teu próximo dia de cuidado. 🌿",
         "#Lumara #Cabelos4C #CuidadoNatural #Luanda", "Guarda para não esquecer"),
        (-2, "instagram", "bastidores", "reel", "Um dia na produção dos sabonetes artesanais", "aprovado",
         "Do corte ao embrulho: cada sabonete passa pelas nossas mãos. Vem ver como nasce o teu ritual.", "#Lumara #FeitoAMao #Angola", "Envia-nos mensagem para encomendar"),
        (1, "instagram", "produto", "post", "Óleo fortalecedor de unhas — ritual de 2 minutos", "revisao",
         "Um momento só teu: 2 minutos para cuidar das unhas antes de dormir. [preço] · encomendas por mensagem.", "#Lumara #Unhas #Autocuidado", "Encomenda por mensagem"),
        (3, "facebook", "testemunhos", "post", "Testemunho de cliente sobre o óleo corporal", "criacao",
         "[testemunho real da cliente, com autorização] — [nome da cliente]", None, None),
        (6, "whatsapp", "promocoes", "story", "Anúncio dos kits de festas", "planeamento", None, None, None),
        (9, "instagram", "educativo", "reel", "Mãos e pés: rotina de cuidado semanal", "ideia", None, None, None),
    ]
    for dias, plat, cat, fmt, tema, estado, texto, tags, cta in itens:
        c = Conteudo(data_publicacao=d + timedelta(days=dias), plataforma=plat, categoria=cat, formato=fmt, tema=f"[DEMO] {tema}",
                     texto=texto, hashtags=tags, cta=cta, estado=estado, responsavel_id=maira.id, criado_por_id=maira.id, is_demo=True,
                     campanha_id=camp.id if cat == "promocoes" else None)
        if estado in ("aprovado", "publicado"):
            c.aprovado_em, c.aprovado_por_id, c.submetido_em = agora(), luisa.id, agora()
        if estado == "revisao":
            c.submetido_em = agora()
        if estado == "publicado":
            c.publicado_em = agora()
        db.add(c)
    db.flush()


def semear_vendas(db, maira, diana, luisa):
    """Fase 4 — clientes, preços FICTÍCIOS de demonstração, encomendas e uma feira (tudo DEMO)."""
    from decimal import Decimal as D
    from app.dependencies import Contexto
    from app.modules.eventos.models import Evento, EventoProduto, EventoTarefa
    from app.modules.stock.models import Artigo
    from app.modules.vendas import service as vs
    from app.modules.vendas.models import Cliente, Encomenda, Preco

    ctx_m = Contexto(utilizador=maira, sessao=None, ip=None)
    ctx_d = Contexto(utilizador=diana, sessao=None, ip=None)
    d = hoje()
    prods = {a.codigo: a for a in db.scalars(select(Artigo).where(Artigo.is_demo.is_(True), Artigo.categoria == "produto_acabado"))}
    unhas, corpo = prods["DEMO-PA-UNHAS30"], prods["DEMO-PA-CORPO100"]
    for a, p in ((unhas, "4500"), (corpo, "7000")):
        db.add(Preco(artigo_id=a.id, preco_kz=D(p), vigente_desde=d - timedelta(days=60), definido_por_id=luisa.id, is_demo=True,
                     motivo="[DEMO] Preço fictício de demonstração — substituir pelo preço real"))
    db.flush()
    cli = []
    for nome, tel, loc, origem, cons in (("Cliente A (DEMO)", "923000101", "Luanda", "instagram", True),
                                         ("Cliente B (DEMO)", "923000102", "Talatona", "whatsapp", True),
                                         ("Cliente C (DEMO)", "923000103", "Viana", "feira", False)):
        c = Cliente(nome=nome, whatsapp=tel, localidade=loc, origem=origem, consentimento_marketing=cons, is_demo=True, criado_por_id=maira.id)
        db.add(c)
        cli.append(c)
    db.flush()

    def enc(cliente, qtd, estado, dias_prev, pago=None, desconto="0"):
        e = Encomenda(cliente_id=cliente.id, data_encomenda=d - timedelta(days=3), canal="whatsapp", responsavel_id=maira.id,
                      criado_por_id=maira.id, data_prevista=d + timedelta(days=dias_prev), is_demo=True)
        vs.aplicar_linhas(db, ctx_m, e, [vs.LinhaIn(artigo_id=unhas.id, quantidade=D(qtd))], D(desconto), D(0))
        db.add(e)
        db.flush()
        db.refresh(e)
        if estado in ("pronta", "entregue"):
            vs.mudar_estado(db, ctx_d, e, "pronta")
        if estado == "entregue":
            vs.mudar_estado(db, ctx_d, e, "entregue")
        if pago:
            vs.registar_pagamento(db, ctx_m, e, D(pago), d, "multicaixa_express", None, None, is_demo=True)
        return e

    enc(cli[0], 2, "entregue", -1, pago="9000")
    enc(cli[1], 3, "entregue", -2, pago="5000")
    enc(cli[0], 1, "pronta", 1)
    enc(cli[2], 2, "recebida", 3, desconto="2000")
    ev = Evento(nome="[DEMO] Feira de artesanato de Dezembro", data_inicio=d + timedelta(days=12), data_fim=d + timedelta(days=13),
                local="Luanda (local a confirmar)", objectivo="Vender kits e captar novas clientes.", responsavel_id=maira.id,
                criado_por_id=maira.id, is_demo=True)
    ev.checklist = [EventoTarefa(texto=t, ordem=n) for n, t in enumerate(
        ["Confirmar inscrição e localização da banca", "Preparar produtos e etiquetas de preço", "Levar TPA/terminal e troco"])]
    ev.produtos = [EventoProduto(artigo_id=unhas.id, quantidade_planeada=D(10))]
    db.add(ev)
    db.flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limpar", action="store_true")
    a = ap.parse_args()
    with SessionLocal() as db:
        limpar(db) if a.limpar else semear(db)
    if a.limpar:
        print("Dados DEMO removidos.")
