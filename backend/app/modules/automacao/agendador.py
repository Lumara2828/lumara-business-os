"""Automações internas (Fase 6).

Corre em segundo plano no servidor (de 10 em 10 minutos) e também quando
alguém abre as notificações, para não depender de o serviço estar acordado à
hora certa. Cada automação é idempotente (chave de deduplicação por dia,
semana ou mês): correr duas vezes não duplica nada.

Automações:
- alertas: atrasos, stock, validades, conteúdos, encomendas, finanças;
- resumo_semanal: à segunda-feira, a partir das 07:00 (Luanda), cada pessoa
  recebe o resumo da sua semana; a CEO recebe também o da equipa;
- relatorio_mensal: no primeiro dia útil do mês, a CEO é avisada de que o
  relatório do mês anterior está pronto.

Nenhuma automação altera dados de negócio: só cria notificações.
"""
import logging
import threading
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.formato import fkz, fpct  # noqa: F401
from app.core.tempo import agora, formatar_data, hoje, inicio_semana
from app.modules.automacao import alertas
from app.modules.configuracao import service as config
from app.modules.configuracao.models import Configuracao
from app.modules.notificacoes.service import notificar

log = logging.getLogger("lumara.automacao")

INTERVALO = timedelta(minutes=10)
HORA_RESUMO = 7
_CHAVE_ESTADO = "_automacoes"
_TRAVA = 742_006  # pg_advisory_lock: uma só execução de cada vez, mesmo com vários processos

def ausencias(db: Session) -> dict:
    from app.modules.ausencias.service import processar
    return processar(db)


def lembretes_reunioes(db: Session) -> dict:
    from app.modules.agenda.router import lembretes
    return lembretes(db)


def emails(db: Session) -> dict:
    from app.modules.notificacoes.email import processar
    return processar(db)


AUTOMACOES = {
    "alertas": {"nome": "Alertas operacionais", "descricao": "Tarefas em atraso, aprovações paradas, stock abaixo do mínimo, "
                "validades, conteúdos sem aprovação, encomendas atrasadas e cobranças. De 15 em 15 minutos, no máximo.",
                "configuravel": None},
    "ausencias": {"nome": "Ausências e substituições", "descricao": "No início de cada ausência aprovada, as tarefas passam "
                  "para a substituta; no regresso, as que ficaram por concluir voltam à pessoa original.", "configuravel": None},
    "lembretes_reunioes": {"nome": "Lembretes de reuniões", "descricao": "No dia de cada reunião, cada participante recebe um "
                           "lembrete com a hora, o local e a ordem de trabalhos.", "configuravel": None},
    "emails": {"nome": "Avisos por email", "descricao": "Envia por email os avisos urgentes (e o resumo semanal a quem o pediu). "
               "Desligado até a chave do serviço de envio ser configurada no servidor.", "configuravel": None},
    "resumo_semanal": {"nome": "Resumo semanal", "descricao": "À segunda-feira a partir das 07:00: cada pessoa recebe o resumo da sua "
                       "semana (atrasos, prazos, aprovações); a CEO recebe também o da equipa.", "configuravel": "automacao_resumo_semanal"},
    "relatorio_mensal": {"nome": "Relatório mensal da CEO", "descricao": "No início de cada mês, a CEO é avisada de que o relatório do "
                         "mês anterior está pronto para ler e imprimir.", "configuravel": "automacao_relatorio_mensal"},
}


def _estado(db: Session) -> dict:
    linha = db.get(Configuracao, _CHAVE_ESTADO)
    return dict(linha.valor) if linha is not None else {}


def _guardar_estado(db: Session, nome: str, resultado: dict | None, erro: str | None = None) -> None:
    linha = db.get(Configuracao, _CHAVE_ESTADO)
    est = dict(linha.valor) if linha is not None else {}
    est[nome] = {"em": agora().isoformat(), "resultado": resultado, "erro": erro}
    if linha is None:
        db.add(Configuracao(chave=_CHAVE_ESTADO, valor=est))
    else:
        linha.valor = est
    db.commit()


def resumo_semanal(db: Session) -> dict:
    from app.modules.dashboard.metricas import estado_actual, indicadores_periodo
    from app.modules.equipa.models import Utilizador
    from app.core.permissions import P, tem_permissao
    d = hoje()
    seg = inicio_semana(d)
    if d - seg > timedelta(days=1):
        return {"enviados": 0, "motivo": "só à segunda-feira, ou à terça se o servidor esteve parado"}
    if d == seg and agora().hour < HORA_RESUMO:
        return {"enviados": 0, "motivo": f"antes das {HORA_RESUMO}:00"}
    ant_ini, ant_fim = seg - timedelta(days=7), seg - timedelta(days=1)
    n = 0
    for u in db.scalars(select(Utilizador).where(Utilizador.activo.is_(True))):
        e = estado_actual(db, u.id)
        i = indicadores_periodo(db, ant_ini, ant_fim, u.id)
        partes = [f"Em atraso: {e['em_atraso']}.", f"Prazos nos próximos 7 dias: {e['proximos_7_dias']}."]
        if e["aguardar_aprovacao"]:
            partes.append(f"A aguardar aprovação: {e['aguardar_aprovacao']}.")
        if e["bloqueadas"]:
            partes.append(f"Bloqueadas: {e['bloqueadas']}.")
        if i["taxa_cumprimento"] is not None:
            partes.append(f"Semana passada: {fpct(i['taxa_cumprimento'])} no prazo.")
        notificar(db, u.id, "resumo_semanal", f"Resumo da semana de {formatar_data(seg)}", " ".join(partes), "/tarefas",
                  chave_dedup=f"resumo-semana:{u.id}:{seg.isoformat()}")
        n += 1
        if tem_permissao(u.funcao, P.RELATORIOS_EQUIPA):
            eq = estado_actual(db)
            ie = indicadores_periodo(db, ant_ini, ant_fim)
            msg = (f"Equipa: {eq['em_atraso']} em atraso, {eq['bloqueadas']} bloqueada(s), {eq['aguardar_aprovacao']} a aguardar a sua aprovação. "
                   + (f"Cumprimento na semana passada: {fpct(ie['taxa_cumprimento'])}." if ie["taxa_cumprimento"] is not None else ""))
            notificar(db, u.id, "resumo_semanal", "Resumo da equipa — planeamento de segunda-feira", msg.strip(), "/rotina",
                      chave_dedup=f"resumo-equipa:{u.id}:{seg.isoformat()}")
    db.commit()
    return {"enviados": n}


def relatorio_mensal(db: Session) -> dict:
    from app.modules.equipa.models import Utilizador
    from app.modules.financas.service import mes_anterior
    from app.modules.relatorios.service import nome_mes
    d = hoje()
    if d.day > 7:
        return {"enviados": 0, "motivo": "só na primeira semana do mês"}
    a, m = mes_anterior(d.year, d.month)
    n = 0
    for uid in db.scalars(select(Utilizador.id).where(Utilizador.funcao == "ceo", Utilizador.activo.is_(True))):
        notificar(db, uid, "relatorio_mensal", f"Relatório mensal de {nome_mes(a, m)} pronto",
                  "Tarefas, vendas, produção, stock, marketing, finanças e ocorrências do mês, com comparação ao mês anterior.",
                  f"/relatorio?ano={a}&mes={m}", chave_dedup=f"relatorio-mensal:{a}-{m:02d}:{uid}")
        n += 1
    db.commit()
    return {"enviados": n}


def _activa(db: Session, nome: str) -> bool:
    chave = AUTOMACOES[nome]["configuravel"]
    return chave is None or bool(config.obter(db, chave))


def executar(db: Session, forcar: bool = False) -> dict:
    """Corre as automações activas. Com `forcar`, ignora o intervalo mínimo dos alertas."""
    from app.core.database import engine
    with engine.connect() as trava:
        if not trava.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": _TRAVA}):
            return {"ocupado": True}
        try:
            return _executar(db, forcar)
        finally:
            trava.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _TRAVA})
            trava.commit()


def _executar(db: Session, forcar: bool) -> dict:
    feitos = {}
    for nome, fn in (("alertas", alertas.verificar if forcar else _alertas_se_necessario),
                     ("ausencias", ausencias), ("lembretes_reunioes", lembretes_reunioes), ("resumo_semanal", resumo_semanal), ("relatorio_mensal", relatorio_mensal), ("emails", emails)):
        if not _activa(db, nome):
            continue
        try:
            r = fn(db)
            feitos[nome] = r
            if r is not None:
                _guardar_estado(db, nome, r)
        except Exception as e:  # uma automação com erro não impede as outras
            db.rollback()
            log.exception("Automação %s falhou", nome)
            _guardar_estado(db, nome, None, str(e)[:300])
            feitos[nome] = {"erro": str(e)[:300]}
    return feitos


def _alertas_se_necessario(db: Session) -> dict | None:
    linha = db.get(Configuracao, "_ultima_verificacao_alertas")
    if linha is not None:
        from datetime import datetime
        if agora() - datetime.fromisoformat(linha.valor["valor"]) < alertas.INTERVALO_MINIMO:
            return None
    return alertas.verificar(db)


def executar_se_necessario(db: Session) -> None:
    est = _estado(db)
    ultima = est.get("_ultima_volta")
    from datetime import datetime
    if ultima and agora() - datetime.fromisoformat(ultima) < INTERVALO:
        return
    executar(db)
    linha = db.get(Configuracao, _CHAVE_ESTADO)
    if linha is not None:
        linha.valor = {**linha.valor, "_ultima_volta": agora().isoformat()}
    else:
        db.add(Configuracao(chave=_CHAVE_ESTADO, valor={"_ultima_volta": agora().isoformat()}))
    db.commit()


def estado(db: Session) -> list[dict]:
    est = _estado(db)
    return [{"id": k, **{c: v for c, v in a.items()}, "activa": _activa(db, k),
             "ultima_execucao": est.get(k, {}).get("em"), "ultimo_resultado": est.get(k, {}).get("resultado"),
             "ultimo_erro": est.get(k, {}).get("erro")} for k, a in AUTOMACOES.items()]


class _Ciclo(threading.Thread):
    """Ciclo em segundo plano. Desligado nos testes (AUTOMACOES_EM_FUNDO=0)."""

    def __init__(self):
        super().__init__(daemon=True, name="automacoes")
        self.parar = threading.Event()

    def run(self):
        from app.core.database import SessionLocal
        espera = 60  # a primeira volta espera que o servidor arranque
        while not self.parar.wait(espera):
            espera = INTERVALO.total_seconds()
            try:
                with SessionLocal() as db:
                    executar_se_necessario(db)
            except Exception:
                log.exception("Ciclo de automações falhou")


_ciclo: _Ciclo | None = None


def iniciar_ciclo() -> None:
    global _ciclo
    if _ciclo is None:
        _ciclo = _Ciclo()
        _ciclo.start()


def parar_ciclo() -> None:
    if _ciclo is not None:
        _ciclo.parar.set()
