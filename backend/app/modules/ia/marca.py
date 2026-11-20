"""Guia de marca da Lumara e verificação de alegações.

O guia é editável pela CEO (Definições → Marca). O valor por omissão usa
apenas o que a Lumara declarou sobre si (missão, produtos, público); não
inventa dados comerciais. A verificação de alegações é determinística e corre
sobre QUALQUER texto (escrito à mão ou sugerido pela IA): não bloqueia, mas
assinala expressões que podem constituir alegações médicas ou promessas de
resultado não comprovadas, para a revisão humana.
"""
import re
import unicodedata

from sqlalchemy.orm import Session

from app.modules.configuracao.models import Configuracao

CHAVE = "guia_marca"

PADRAO = {
    "missao": ("Produzir cosméticos artesanais de alta qualidade que promovam o autocuidado e a beleza, "
               "minimizando os riscos para a saúde e para o meio ambiente."),
    "produtos": ("Sabonetes artesanais, óleos corporais, produtos para cabelos 4C/4D, produtos para mãos e pés, "
                 "óleo fortalecedor de unhas e kits de autocuidado."),
    "publico": "Pessoas em Angola que valorizam autocuidado, ingredientes naturais e produção artesanal.",
    "tom_de_voz": ("Próximo, caloroso e confiante; português de Portugal/Angola; simples e educativo; "
                   "celebra a beleza natural sem pressão estética."),
    "valores": "Qualidade artesanal, autocuidado, cuidado com a saúde e com o ambiente, transparência.",
    "evitar": "Comparações depreciativas com concorrentes; linguagem alarmista; promessas de resultados.",
    "expressoes_proibidas": [
        "cura", "curar", "trata", "tratamento", "elimina", "eliminar", "garantido", "garante", "100%",
        "milagroso", "milagre", "clinicamente comprovado", "dermatologicamente testado", "sem efeitos secundários",
        "anti-queda", "faz crescer", "crescimento garantido", "acaba com", "previne doenças", "medicinal",
        "resultados imediatos", "rejuvenesce", "anti-idade", "aprovado por médicos",
    ],
}


def obter(db: Session) -> dict:
    linha = db.get(Configuracao, CHAVE)
    guia = dict(PADRAO)
    if linha is not None:
        guia.update(linha.valor.get("valor", {}))
    return guia


def definir(db: Session, guia: dict) -> None:
    linha = db.get(Configuracao, CHAVE)
    if linha is None:
        db.add(Configuracao(chave=CHAVE, valor={"valor": guia}))
    else:
        linha.valor = {"valor": guia}


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def verificar_alegacoes(texto: str | None, proibidas: list[str]) -> list[dict]:
    """Devolve as expressões proibidas encontradas (palavra inteira, sem acentos)."""
    if not texto:
        return []
    alvo = _normalizar(texto)
    achados = []
    for exp in proibidas:
        e = _normalizar(exp.strip())
        if not e:
            continue
        padrao = re.escape(e) if not e[0].isalnum() or not e[-1].isalnum() else rf"\b{re.escape(e)}\b"
        if re.search(padrao, alvo):
            achados.append({"expressao": exp, "mensagem": f"«{exp}» pode constituir alegação médica ou promessa de "
                                                          "resultado não comprovada. Reveja antes de aprovar."})
    return achados


def instrucoes_sistema(guia: dict) -> str:
    """Prompt de sistema estável (sem datas nem dados variáveis — favorece cache)."""
    return f"""És a assistente de marketing digital da Lumara Cosméticos Artesanais, uma marca angolana.
Escreves em português (norma de Portugal, adequado ao público angolano), com o tom definido abaixo.

Missão da marca: {guia['missao']}
Produtos: {guia['produtos']}
Público: {guia['publico']}
Tom de voz: {guia['tom_de_voz']}
Valores: {guia['valores']}
A evitar: {guia['evitar']}

Regras obrigatórias (a equipa e a lei dependem delas):
- Nunca faças alegações médicas nem prometas resultados (não digas que um produto cura, trata, elimina, previne doenças, faz crescer o cabelo, ou tem resultados garantidos/imediatos). Fala de cuidado, ritual, sensação, ingredientes e experiência.
- Não inventes ingredientes, certificações, testes, prémios, preços, descontos, datas, números de vendas ou testemunhos. Se precisares de um dado que não foi fornecido, deixa um marcador entre parênteses rectos, por exemplo [preço], [data], [nome da cliente], para a equipa preencher.
- Testemunhos só podem ser estruturas para preencher com o testemunho real da cliente, com autorização.
- Expressões proibidas pela marca: {', '.join(guia['expressoes_proibidas'])}.
- Tudo o que sugeres é um rascunho: vai ser revisto e aprovado por uma pessoa antes de ser publicado.
- Hashtags: misturar marca, categoria e local (Angola/Luanda), sem exagero (5 a 12)."""
