from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.equipa.models import Utilizador
from app.modules.notificacoes.models import Notificacao


def notificar(
    db: Session,
    utilizador_id,
    tipo: str,
    titulo: str,
    mensagem: str | None = None,
    ligacao: str | None = None,
    chave_dedup: str | None = None,
    excepto=None,
) -> None:
    """Cria uma notificação (não notifica quem fez a acção: `excepto`).
    Com `chave_dedup`, uma segunda notificação igual é ignorada."""
    if utilizador_id is None or utilizador_id == excepto:
        return
    valores = dict(utilizador_id=utilizador_id, tipo=tipo, titulo=titulo[:200], mensagem=mensagem,
                   ligacao=ligacao, chave_dedup=chave_dedup)
    if chave_dedup:
        db.execute(insert(Notificacao).values(**valores).on_conflict_do_nothing(index_elements=["chave_dedup"]))
    else:
        db.add(Notificacao(**valores))


def ids_ceo(db: Session) -> list:
    return list(db.scalars(select(Utilizador.id).where(Utilizador.funcao == "ceo", Utilizador.activo.is_(True))))


def notificar_ceo(db: Session, tipo: str, titulo: str, mensagem: str | None = None, ligacao: str | None = None,
                  chave_dedup: str | None = None, excepto=None) -> None:
    for uid in ids_ceo(db):
        notificar(db, uid, tipo, titulo, mensagem, ligacao,
                  f"{chave_dedup}:{uid}" if chave_dedup else None, excepto=excepto)
