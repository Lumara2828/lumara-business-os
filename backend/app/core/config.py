"""Configuração lida de variáveis de ambiente (ver .env.example).

Nenhum segredo tem valor por omissão: SECRET_KEY é obrigatório para a
aplicação arrancar, para nunca correr em produção com um valor de exemplo.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/lumara"
    # Usado para derivar valores internos (não assina tokens — as sessões são
    # opacas e guardadas com hash na base de dados).
    secret_key: str
    # Duração de uma sessão sem actividade (horas) e duração máxima absoluta (dias).
    sessao_inactividade_horas: int = 12
    sessao_duracao_maxima_dias: int = 14
    # Origens autorizadas a chamar a API (separadas por vírgula).
    cors_origens: str = "http://localhost:5173"
    # Fuso horário do negócio (Angola, WAT, UTC+1).
    fuso_horario: str = "Africa/Luanda"
    # Tamanho máximo de um anexo (MB).
    anexo_tamanho_maximo_mb: int = 8
    # Ambiente: "desenvolvimento" | "producao" — em produção os detalhes de
    # erros internos nunca são devolvidos ao cliente.
    ambiente: str = "desenvolvimento"

    # Inteligência artificial (Fase 3). Sem chave, o assistente responde "não configurado"
    # — nunca simula respostas. A chave só existe no servidor.
    ia_fornecedor: str = "anthropic"            # "anthropic" | "nenhum"
    anthropic_api_key: str | None = None
    ia_modelo: str = "claude-opus-5-5"          # alternativas mais económicas: claude-sonnet-5-5, claude-haiku-5-5
    ia_esforco: str = "medium"                  # low | medium | high
    ia_limite_pedidos_hora: int = 30            # por utilizadora, para controlo de custos

    @property
    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origens.split(",") if o.strip()]


settings = Settings()
