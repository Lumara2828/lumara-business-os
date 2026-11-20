"""Adaptadores de fornecedores de IA.

A aplicação só conhece a interface `FornecedorIA`; trocar de fornecedor é
acrescentar um adaptador e mudar IA_FORNECEDOR. A chave de API vive apenas no
servidor (variável de ambiente) e nunca é enviada ao navegador.
"""
import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.core.errors import ErroNegocio

log = logging.getLogger("lumara.ia")


@dataclass
class RespostaIA:
    dados: dict | None
    modelo: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    recusada: bool = False
    motivo: str | None = None


class FornecedorIA(Protocol):
    nome: str
    modelo: str

    def configurado(self) -> bool: ...

    def gerar(self, sistema: str, pedido: str, esquema: dict) -> RespostaIA: ...


class SemFornecedor:
    nome = "nenhum"
    modelo = "—"

    def configurado(self) -> bool:
        return False

    def gerar(self, sistema: str, pedido: str, esquema: dict) -> RespostaIA:
        raise ErroNegocio("ia_nao_configurada", "O assistente de IA não está configurado: falta a chave de API no servidor "
                          "(ANTHROPIC_API_KEY). Veja o README.", 503)


# Modelos com reencaminhamento automático no servidor quando o pedido é recusado
# por um classificador de segurança (fallbacks: "default").
_COM_FALLBACK = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-2", "claude-fable-5-1", "claude-sonnet-5-5"}


class AnthropicFornecedor:
    nome = "anthropic"

    def __init__(self, api_key: str | None, modelo: str, esforco: str):
        self.modelo = modelo
        self.esforco = esforco
        self._api_key = api_key
        self._cliente = None

    def configurado(self) -> bool:
        return bool(self._api_key)

    def _client(self):
        if self._cliente is None:
            import anthropic
            self._cliente = anthropic.Anthropic(api_key=self._api_key, timeout=120, max_retries=2)
        return self._cliente

    def gerar(self, sistema: str, pedido: str, esquema: dict) -> RespostaIA:
        import anthropic
        if not self.configurado():
            return SemFornecedor().gerar(sistema, pedido, esquema)
        params = dict(
            model=self.modelo,
            max_tokens=16000,
            # O prompt de sistema (guia de marca) é estável: fica em cache entre pedidos.
            system=[{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.esforco, "format": {"type": "json_schema", "schema": esquema}},
            messages=[{"role": "user", "content": pedido}],
        )
        if self.modelo in _COM_FALLBACK:
            params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        try:
            r = self._client().beta.messages.create(**params)
        except anthropic.AuthenticationError as e:
            log.error("IA: chave inválida (%s)", getattr(e, "request_id", ""))
            raise ErroNegocio("ia_chave_invalida", "A chave de API da IA é inválida. Contacte a administração.", 503) from e
        except anthropic.RateLimitError as e:
            raise ErroNegocio("ia_limite", "O serviço de IA está ocupado. Tente novamente dentro de um minuto.", 503) from e
        except anthropic.BadRequestError as e:
            log.error("IA: pedido inválido: %s", e.message)
            raise ErroNegocio("ia_pedido_invalido", "O serviço de IA rejeitou o pedido.", 502) from e
        except anthropic.APIStatusError as e:
            log.error("IA: erro %s", e.status_code)
            raise ErroNegocio("ia_indisponivel", "O serviço de IA está temporariamente indisponível.", 503) from e
        except anthropic.APIConnectionError as e:
            raise ErroNegocio("ia_sem_ligacao", "Sem ligação ao serviço de IA.", 503) from e

        uso = getattr(r, "usage", None)
        base = dict(modelo=r.model, tokens_entrada=getattr(uso, "input_tokens", None), tokens_saida=getattr(uso, "output_tokens", None))
        if r.stop_reason == "refusal":
            motivo = getattr(getattr(r, "stop_details", None), "explanation", None)
            return RespostaIA(dados=None, recusada=True, motivo=motivo or "Pedido recusado pelo modelo.", **base)
        if r.stop_reason == "max_tokens":
            raise ErroNegocio("ia_resposta_longa", "A resposta da IA ficou incompleta. Peça menos propostas.", 502)
        texto = next((b.text for b in r.content if b.type == "text"), None)
        try:
            dados = json.loads(texto) if texto else None
        except json.JSONDecodeError as e:
            raise ErroNegocio("ia_resposta_invalida", "A IA devolveu uma resposta num formato inesperado.", 502) from e
        return RespostaIA(dados=dados, **base)


def fornecedor_configurado() -> FornecedorIA:
    if settings.ia_fornecedor == "anthropic":
        return AnthropicFornecedor(settings.anthropic_api_key, settings.ia_modelo, settings.ia_esforco)
    return SemFornecedor()


def get_fornecedor() -> FornecedorIA:
    """Dependência FastAPI (substituível nos testes)."""
    return fornecedor_configurado()
