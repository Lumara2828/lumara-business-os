"""Integrações externas — adaptadores declarados, NÃO activos.

Nenhuma integração é simulada. Cada entrada indica o que permitirá fazer, que
credenciais/autorizações são necessárias e se estão presentes no servidor.
A activação efectiva (chamadas reais às APIs) está planeada para a Fase 6.
"""
import os

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.permissions import P
from app.dependencies import Contexto, requer

router = APIRouter(prefix="/integracoes", tags=["Integrações"])

INTEGRACOES = [
    {"id": "ia", "nome": "Assistente de IA (Claude, Anthropic)", "fase": 3,
     "permite": "Sugestões de legendas, hashtags, CTA, guiões de Reels, Stories, temas, campanhas e adaptação a plataformas.",
     "requer": ["ANTHROPIC_API_KEY (chave de API da Anthropic, só no servidor)"], "variaveis": ["ANTHROPIC_API_KEY"],
     "documentacao": "https://docs.claude.com/"},
    {"id": "instagram", "nome": "Instagram (Meta Graph API)", "fase": 6,
     "permite": "Publicar conteúdos aprovados e ler métricas (alcance, interacções).",
     "requer": ["Conta profissional do Instagram ligada a uma Página do Facebook", "App Meta aprovada (revisão da Meta)",
                "META_APP_ID, META_APP_SECRET e token de acesso de longa duração"], "variaveis": ["META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"],
     "documentacao": "https://developers.facebook.com/docs/instagram-platform"},
    {"id": "facebook", "nome": "Facebook (Páginas)", "fase": 6, "permite": "Publicar na Página da Lumara e ler métricas.",
     "requer": ["App Meta com permissões pages_manage_posts e pages_read_engagement", "Token de Página"],
     "variaveis": ["META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"], "documentacao": "https://developers.facebook.com/docs/pages-api"},
    {"id": "whatsapp", "nome": "WhatsApp Business (Cloud API)", "fase": 6,
     "permite": "Receber pedidos e enviar mensagens transaccionais a clientes (com consentimento).",
     "requer": ["Conta WhatsApp Business verificada", "Número dedicado", "WHATSAPP_TOKEN e WHATSAPP_PHONE_ID", "Modelos de mensagem aprovados pela Meta"],
     "variaveis": ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"], "documentacao": "https://developers.facebook.com/docs/whatsapp/cloud-api"},
    {"id": "canva", "nome": "Canva (Connect API)", "fase": 6, "permite": "Abrir/criar designs a partir de um conteúdo e anexar o resultado.",
     "requer": ["Integração registada no Canva Developers", "CANVA_CLIENT_ID e CANVA_CLIENT_SECRET", "Autorização OAuth da conta da Lumara"],
     "variaveis": ["CANVA_CLIENT_ID", "CANVA_CLIENT_SECRET"], "documentacao": "https://www.canva.dev/docs/connect/"},
    {"id": "metricool", "nome": "Metricool", "fase": 6, "permite": "Agendamento multi-plataforma e importação de métricas.",
     "requer": ["Plano Metricool com acesso à API", "METRICOOL_API_KEY e ID do perfil"], "variaveis": ["METRICOOL_API_KEY"],
     "documentacao": "https://help.metricool.com/"},
    {"id": "make", "nome": "Make (automação)", "fase": 6, "permite": "Disparar cenários quando um conteúdo é aprovado ou publicado.",
     "requer": ["Cenário Make com webhook", "MAKE_WEBHOOK_URL"], "variaveis": ["MAKE_WEBHOOK_URL"], "documentacao": "https://www.make.com/en/help"},
]


@router.get("")
def listar(ctx: Contexto = Depends(requer(P.MARKETING_CALENDARIO))):
    res = []
    for i in INTEGRACOES:
        presentes = [v for v in i["variaveis"] if (settings.anthropic_api_key if v == "ANTHROPIC_API_KEY" else os.environ.get(v))]
        if i["id"] == "ia":
            estado = "activa" if presentes and settings.ia_fornecedor == "anthropic" else "nao_configurada"
        else:
            estado = "credenciais_presentes_por_activar" if len(presentes) == len(i["variaveis"]) else "nao_configurada"
        res.append({**{k: v for k, v in i.items() if k != "variaveis"}, "estado": estado,
                    "credenciais_presentes": len(presentes), "credenciais_necessarias": len(i["variaveis"])})
    return res
