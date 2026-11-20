"""Limite de pedidos por IP (memória do processo — correcto para um único
worker; com várias réplicas usar storage_uri partilhado, ex.: Redis)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
