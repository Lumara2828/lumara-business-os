"""Palavras-passe (bcrypt) e tokens de sessão opacos.

Sessões: o cliente recebe um token aleatório de 256 bits; a base de dados só
guarda o SHA-256 desse token. Um token roubado da base de dados não serve
para autenticar, e qualquer sessão pode ser revogada de imediato (logout,
desactivação de utilizadora, mudança de palavra-passe).
"""
import hashlib
import secrets

import bcrypt

# Hash fixo usado quando o email não existe, para o tempo de resposta do login
# não revelar que emails têm conta.
_HASH_FICTICIO = bcrypt.hashpw(b"nao-e-uma-password-real", bcrypt.gensalt(rounds=12)).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode()


def verificar_password(password: str, password_hash: str | None) -> bool:
    alvo = password_hash or _HASH_FICTICIO
    ok = bcrypt.checkpw(password.encode("utf-8")[:72], alvo.encode())
    return ok and password_hash is not None


def novo_token_sessao() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validar_forca_password(password: str) -> str | None:
    """Devolve mensagem de erro, ou None se a palavra-passe for aceitável."""
    if len(password) < 10:
        return "A palavra-passe deve ter pelo menos 10 caracteres."
    if password.lower() == password or password.upper() == password:
        return "A palavra-passe deve combinar letras maiúsculas e minúsculas."
    if not any(c.isdigit() for c in password):
        return "A palavra-passe deve incluir pelo menos um número."
    return None
