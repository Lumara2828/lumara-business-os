"""Melhoria nº 3: avisos por email.

Só os tipos urgentes (e o resumo semanal, para quem o quiser) saem por email. Nada é enviado
sem a chave do serviço de envio (Resend) configurada no servidor; contas DEMO nunca recebem.
O envio corre na automação, fora dos pedidos, com até 3 tentativas.
"""
import html
import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tempo import agora
from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.models import Notificacao

log = logging.getLogger(__name__)

URGENTES = {"tarefa_atrasada", "aprovacao_parada", "tarefa_bloqueada", "ruptura_stock", "conta_vencida",
            "nao_conformidade", "substituicao"}
RESUMO = {"resumo_semanal"}
MAX_TENTATIVAS = 3
POR_VOLTA = 20  # a volta também pode correr ao abrir as notificações: manter curta


def para_email(tipo: str) -> bool:
    return settings.email_configurado and (tipo in URGENTES or tipo in RESUMO)


def quer(u: Utilizador, tipo: str) -> bool:
    if not u.activo or u.is_demo or u.email_avisos == "nenhum":
        return False
    return tipo in URGENTES or (tipo in RESUMO and u.email_avisos == "urgentes_resumo")


def enviar(para: str, assunto: str, texto: str, corpo_html: str) -> None:
    """Envia um email pelo Resend. Substituível nos testes."""
    r = httpx.post("https://api.resend.com/emails", timeout=15,
                   headers={"Authorization": f"Bearer {settings.email_api_key}"},
                   json={"from": settings.email_remetente, "to": [para], "subject": assunto, "text": texto, "html": corpo_html})
    r.raise_for_status()


def _conteudo(n: Notificacao) -> tuple[str, str, str]:
    link = f"{settings.app_url.rstrip('/')}{n.ligacao}" if settings.app_url and n.ligacao else None
    texto = "\n\n".join(x for x in (n.titulo, n.mensagem, f"Abrir: {link}" if link else None,
                                    "— Lumara Business OS. Pode desligar estes avisos em Definições.") if x)
    h = f"<p><strong>{html.escape(n.titulo)}</strong></p>"
    if n.mensagem:
        h += f"<p>{html.escape(n.mensagem).replace(chr(10), '<br>')}</p>"
    if link:
        h += f'<p><a href="{html.escape(link, quote=True)}">Abrir no Lumara Business OS</a></p>'
    h += '<p style="color:#666;font-size:12px">Lumara Business OS. Pode desligar estes avisos em Definições.</p>'
    return f"[Lumara] {n.titulo}", texto, h


def processar(db: Session) -> dict:
    if not settings.email_configurado:
        return {"desligado": True}
    fila = db.scalars(select(Notificacao).where(Notificacao.email_estado == "pendente", Notificacao.criada_em >= agora() - timedelta(days=1))
                      .order_by(Notificacao.criada_em).limit(POR_VOLTA).with_for_update(skip_locked=True)).all()
    enviados = ignorados = falhados = 0
    for n in fila:
        u = db.get(Utilizador, n.utilizador_id)
        if u is None or not quer(u, n.tipo):
            n.email_estado = "ignorado"
            ignorados += 1
            continue
        try:
            enviar(u.email, *_conteudo(n))
            n.email_estado, n.email_enviado_em = "enviado", agora()
            enviados += 1
        except Exception as e:  # noqa: BLE001 — falha de rede ou do serviço: tenta de novo na próxima volta
            n.email_tentativas += 1
            if n.email_tentativas >= MAX_TENTATIVAS:
                n.email_estado = "erro"
            falhados += 1
            log.warning("Email não enviado (%s): %s", n.tipo, str(e)[:200])
    db.commit()
    return {"enviados": enviados, "ignorados": ignorados, "falhados": falhados}
