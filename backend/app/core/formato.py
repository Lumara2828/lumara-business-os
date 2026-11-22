"""Formato de números para textos gerados no servidor (resumos, notificações,
relatórios). Convenção da Lumara: Kz com ponto nos milhares e vírgula decimal
(36.000,00 Kz); percentagens com vírgula (54,5%)."""
from decimal import ROUND_HALF_UP, Decimal


def fkz(v) -> str:
    q = Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    neg = q < 0
    inteiro, dec = f"{abs(q):.2f}".split(".")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return ("-" if neg else "") + ".".join(grupos) + f",{dec} Kz"


def fpct(v) -> str:
    if v is None:
        return "—"
    d = Decimal(str(v)).normalize()
    return f"{d:f}".replace(".", ",") + "%"
