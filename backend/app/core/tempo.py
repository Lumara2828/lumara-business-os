"""Datas e horas no fuso do negócio (Africa/Luanda)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings

FUSO = ZoneInfo(settings.fuso_horario)


def agora() -> datetime:
    return datetime.now(timezone.utc)


def hoje() -> date:
    return datetime.now(FUSO).date()


def inicio_semana(d: date) -> date:
    """Segunda-feira da semana de `d`."""
    return d - timedelta(days=d.weekday())


def formatar_data(d: date | datetime | None) -> str:
    """DD/MM/AAAA — formato usado em todos os textos gerados pelo servidor."""
    if d is None:
        return "—"
    if isinstance(d, datetime):
        d = d.astimezone(FUSO).date()
    return d.strftime("%d/%m/%Y")


def periodo(tipo: str, referencia: date) -> tuple[date, date]:
    """Intervalo [inicio, fim] (inclusivo) de um mês, trimestre ou ano."""
    if tipo == "mes":
        inicio = referencia.replace(day=1)
        prox = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
        return inicio, prox - timedelta(days=1)
    if tipo == "trimestre":
        m = 3 * ((referencia.month - 1) // 3) + 1
        inicio = referencia.replace(month=m, day=1)
        fim_mes = m + 2
        prox = date(referencia.year + (1 if fim_mes == 12 else 0), 1 if fim_mes == 12 else fim_mes + 1, 1)
        return inicio, prox - timedelta(days=1)
    if tipo == "ano":
        return date(referencia.year, 1, 1), date(referencia.year, 12, 31)
    raise ValueError("Período inválido: use mes, trimestre ou ano.")


def periodo_anterior(tipo: str, inicio: date) -> tuple[date, date]:
    return periodo(tipo, inicio - timedelta(days=1))
