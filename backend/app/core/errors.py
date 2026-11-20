"""Erros de domínio com formato único {codigo, mensagem, detalhes?}."""
from fastapi import HTTPException, status


class ErroNegocio(HTTPException):
    def __init__(self, codigo: str, mensagem: str, estado: int = status.HTTP_400_BAD_REQUEST, detalhes=None):
        corpo = {"codigo": codigo, "mensagem": mensagem}
        if detalhes is not None:
            corpo["detalhes"] = detalhes
        super().__init__(status_code=estado, detail=corpo)


def nao_encontrado(entidade: str) -> ErroNegocio:
    return ErroNegocio("nao_encontrado", f"{entidade} não encontrado(a).", status.HTTP_404_NOT_FOUND)


def proibido(mensagem: str = "Não tem permissão para esta acção.") -> ErroNegocio:
    return ErroNegocio("sem_permissao", mensagem, status.HTTP_403_FORBIDDEN)


def conflito(mensagem: str) -> ErroNegocio:
    return ErroNegocio("conflito", mensagem, status.HTTP_409_CONFLICT)
