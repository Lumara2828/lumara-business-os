"""Dados de DEMONSTRAÇÃO — claramente identificados (is_demo=true e prefixo
[DEMO] nos títulos). Não representam dados comerciais ou financeiros reais da
Lumara. Para remover: python -m scripts.seed_demo --limpar

Uso: python -m scripts.seed_demo
"""
import argparse
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import delete, select, update

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
    db.commit()
    print("Dados DEMO criados.")
    for nome, email, funcao, _ in USERS:
        print(f"  {nome:14} {email:24} palavra-passe: {PASSWORD_DEMO}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limpar", action="store_true")
    a = ap.parse_args()
    with SessionLocal() as db:
        limpar(db) if a.limpar else semear(db)
    if a.limpar:
        print("Dados DEMO removidos.")
