"""Importação do calendário editorial existente (Excel .xlsx).

Dois passos, sem guardar o ficheiro no servidor:
1. `analisar` — lê a folha, encontra a linha de cabeçalho, sugere a correspondência
   das colunas e mostra uma pré-visualização com os erros de cada linha;
2. `confirmar` — a pessoa revê/ajusta a correspondência e os valores por omissão;
   as linhas válidas são criadas num lote identificado (para se poder rever).

Regras: conteúdos importados nunca entram como aprovados/publicados — a aprovação
humana é sempre feita no sistema. Estados do Excel além de «revisão» ficam em revisão.
"""
import io
import json
import re
import unicodedata
import uuid
from datetime import date, datetime, time

from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import registar
from app.core.errors import ErroNegocio
from app.modules.equipa.models import Utilizador
from app.modules.marketing.models import Conteudo


def _n(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").strip().lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c)))


CAMPOS = {
    "data_publicacao": ["data", "data de publicacao", "data publicacao", "dia", "date", "quando"],
    "hora_publicacao": ["hora", "horario", "hora de publicacao", "time"],
    "plataforma": ["plataforma", "rede", "rede social", "canal", "redes"],
    "categoria": ["categoria", "pilar", "tipo de conteudo", "linha editorial", "pilar de conteudo"],
    "formato": ["formato", "tipo", "tipo de post", "format"],
    "tema": ["tema", "assunto", "titulo", "ideia", "topico", "conteudo"],
    "objectivo": ["objectivo", "objetivo", "meta", "finalidade"],
    "texto": ["texto", "legenda", "copy", "descricao", "caption"],
    "hashtags": ["hashtags", "hashtag", "tags", "#"],
    "cta": ["cta", "chamada para accao", "chamada para acao", "call to action"],
    "responsavel": ["responsavel", "quem", "autor", "responsavel pela publicacao"],
    "estado": ["estado", "status", "situacao"],
    "notas_producao": ["notas", "observacoes", "obs", "guiao", "imagem", "video", "visual"],
}
ROTULOS = {"data_publicacao": "Data de publicação", "hora_publicacao": "Hora", "plataforma": "Plataforma", "categoria": "Pilar",
           "formato": "Formato", "tema": "Tema", "objectivo": "Objectivo", "texto": "Texto / legenda", "hashtags": "Hashtags",
           "cta": "Chamada para acção", "responsavel": "Responsável", "estado": "Estado", "notas_producao": "Notas / guião"}

SIN_PLATAFORMA = {"instagram": ["instagram", "insta", "ig"], "facebook": ["facebook", "fb", "face"], "tiktok": ["tiktok", "tik tok", "tt"],
                  "whatsapp": ["whatsapp", "whats", "wa", "estado whatsapp", "status"], "outro": ["outro", "outros"]}
SIN_CATEGORIA = {"educacao": ["educacao", "educativo", "educacional", "dica", "dicas", "informativo", "tutorial"],
                 "autoridade": ["autoridade", "especialista", "ciencia", "ingredientes", "mitos", "curiosidades"],
                 "branding": ["branding", "marca", "bastidores", "making of", "processo", "producao", "lifestyle", "evento", "eventos", "feira", "historia"],
                 "prova_social": ["prova social", "testemunho", "testemunhos", "depoimento", "depoimentos", "review", "feedback", "antes e depois", "ugc"],
                 "vendas": ["vendas", "venda", "produto", "produtos", "lancamento", "promocao", "promocoes", "desconto", "oferta", "campanha"]}
SIN_FORMATO = {"post": ["post", "imagem", "foto", "estatico", "feed"], "carrossel": ["carrossel", "carousel", "carrosel"],
               "reel": ["reel", "reels", "video curto"], "story": ["story", "stories", "storie", "estado"],
               "video": ["video", "videos"], "live": ["live", "direto", "directo"], "outro": ["outro"]}
SIN_ESTADO = {"ideia": ["ideia", "por fazer", "a fazer", "pendente", "backlog"], "planeamento": ["planeamento", "planeado", "planejado", "agendar"],
              "criacao": ["criacao", "em criacao", "em producao", "a criar", "em curso", "em andamento"],
              "revisao": ["revisao", "em revisao", "aprovacao", "aprovado", "pronto", "agendado", "publicado", "feito", "concluido"]}


def _sinonimo(valor, tabela: dict) -> str | None:
    v = _n(valor)
    if not v:
        return None
    for chave, lista in tabela.items():
        if v == chave or v in lista:
            return chave
    for chave, lista in tabela.items():
        if any(s in v for s in lista if len(s) > 3):
            return chave
    return None


def _data(valor, ano: int) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})", s)
    if m:
        try:
            return date(ano, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _hora(valor) -> time | None:
    if isinstance(valor, time):
        return valor
    if isinstance(valor, datetime):
        return valor.time()
    m = re.fullmatch(r"(\d{1,2})[:hH](\d{2})?", str(valor or "").strip())
    if m and int(m.group(1)) < 24:
        return time(int(m.group(1)), int(m.group(2) or 0))
    return None


def _abrir(dados: bytes):
    try:
        return load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, OSError, ValueError, Exception) as e:  # noqa: BLE001 — ficheiro do utilizador
        raise ErroNegocio("excel_invalido", "Não foi possível ler o ficheiro Excel. Confirme que é um .xlsx válido.") from e


def _linhas(wb, folha: str | None) -> tuple[str, list[list]]:
    nomes = wb.sheetnames
    if folha and folha not in nomes:
        raise ErroNegocio("folha_inexistente", f"A folha «{folha}» não existe no ficheiro.")
    escolhida = folha
    if not escolhida:
        escolhida = next((n for n in nomes if wb[n].max_row and wb[n].max_row > 1), nomes[0])
    linhas = [list(r) for r in wb[escolhida].iter_rows(values_only=True, max_row=2000)]
    return escolhida, linhas


def _cabecalho(linhas: list[list]) -> int:
    for i, r in enumerate(linhas[:15]):
        textos = [c for c in r if isinstance(c, str) and c.strip()]
        reconhecidos = sum(1 for c in textos if _sugerir(c))
        if reconhecidos >= 2 or len(textos) >= 4:
            return i
    return 0


def _sugerir(cab) -> str | None:
    h = _n(cab)
    if not h:
        return None
    for campo, sins in CAMPOS.items():
        if h in sins:
            return campo
    for campo, sins in CAMPOS.items():
        if any(s in h for s in sins if len(s) > 3):
            return campo
    return None


def _interpretar(db: Session, linha: list, mapa: dict[str, int], ano: int, padroes: dict, utilizadores: list[Utilizador],
                 por_omissao_id) -> tuple[dict, list[str]]:
    def val(campo):
        i = mapa.get(campo)
        return linha[i] if i is not None and i < len(linha) else None

    erros, d = [], {}
    dt = _data(val("data_publicacao"), ano)
    if dt is None:
        erros.append("Data em falta ou inválida")
    d["data_publicacao"] = dt
    d["hora_publicacao"] = _hora(val("hora_publicacao"))
    for campo, tabela in (("plataforma", SIN_PLATAFORMA), ("categoria", SIN_CATEGORIA), ("formato", SIN_FORMATO)):
        bruto = val(campo)
        v = _sinonimo(bruto, tabela) or padroes.get(campo)
        if v is None:
            erros.append(f"{ROTULOS[campo]}: valor não reconhecido «{bruto}»" if bruto else f"{ROTULOS[campo]} em falta")
        d[campo] = v
    texto = str(val("texto") or "").strip() or None
    tema = str(val("tema") or "").strip()
    if not tema and texto:
        tema = texto[:80] + ("…" if len(texto) > 80 else "")
    if len(tema) < 2:
        erros.append("Tema em falta")
    d.update(tema=tema[:300], texto=texto, objectivo=str(val("objectivo") or "").strip() or None,
             hashtags=str(val("hashtags") or "").strip() or None, cta=(str(val("cta") or "").strip() or None),
             notas_producao=str(val("notas_producao") or "").strip() or None)
    if d["cta"]:
        d["cta"] = d["cta"][:300]
    d["estado"] = _sinonimo(val("estado"), SIN_ESTADO) or "planeamento"
    if d["estado"] == "revisao" and not texto:
        d["estado"] = "criacao"
    nome = _n(val("responsavel"))
    resp = None
    if nome:
        resp = next((u for u in utilizadores if _n(u.nome).split(" ")[0] == nome.split(" ")[0] or nome in _n(u.nome)), None)
        if resp is None:
            erros.append(f"Responsável não encontrada: «{val('responsavel')}» (fica a pessoa que importa)")
    d["responsavel_id"] = resp.id if resp else por_omissao_id
    d["_responsavel"] = resp.nome if resp else None
    return d, erros


AVISOS = ("Responsável não encontrada",)


def analisar(db: Session, dados: bytes, folha: str | None, ano: int) -> dict:
    wb = _abrir(dados)
    nome, linhas = _linhas(wb, folha)
    if not linhas:
        raise ErroNegocio("folha_vazia", "A folha está vazia.")
    ic = _cabecalho(linhas)
    cab = linhas[ic]
    colunas, usados = [], set()
    for i, h in enumerate(cab):
        if h is None or str(h).strip() == "":
            continue
        s = _sugerir(h)
        if s in usados:
            s = None
        if s:
            usados.add(s)
        colunas.append({"indice": i, "cabecalho": str(h), "campo_sugerido": s})
    mapa = {c["campo_sugerido"]: c["indice"] for c in colunas if c["campo_sugerido"]}
    utilizadores = list(db.scalars(select(Utilizador).where(Utilizador.activo.is_(True))))
    corpo = [r for r in linhas[ic + 1:] if any(v not in (None, "") for v in r)]
    previa = []
    for n, r in enumerate(corpo[:15]):
        d, erros = _interpretar(db, r, mapa, ano, {}, utilizadores, None)
        previa.append({"linha": ic + 2 + n, "valores": {k: (v.isoformat() if isinstance(v, (date, time)) else v)
                                                       for k, v in d.items() if k not in ("responsavel_id",)}, "erros": erros})
    return {"folhas": wb.sheetnames, "folha": nome, "linha_cabecalho": ic + 1, "colunas": colunas, "total_linhas": len(corpo),
            "campos": ROTULOS, "obrigatorios": ["data_publicacao", "tema/texto", "plataforma", "categoria", "formato"],
            "previsualizacao": previa}


def confirmar(db: Session, ctx, dados: bytes, mapeamento_json: str, folha: str | None, ano: int, padroes_json: str) -> dict:
    try:
        mapa = {k: int(v) for k, v in json.loads(mapeamento_json).items() if v is not None and v != ""}
        padroes = {k: v for k, v in json.loads(padroes_json or "{}").items() if v}
    except (ValueError, TypeError, AttributeError) as e:
        raise ErroNegocio("mapeamento_invalido", "Correspondência de colunas inválida.") from e
    desconhecidos = set(mapa) - set(CAMPOS)
    if desconhecidos:
        raise ErroNegocio("mapeamento_invalido", f"Campos desconhecidos: {', '.join(sorted(desconhecidos))}.")
    if "data_publicacao" not in mapa or not ({"tema", "texto"} & mapa.keys()):
        raise ErroNegocio("mapeamento_incompleto", "Indique pelo menos as colunas de data e de tema (ou texto).")
    for campo, valores in (("plataforma", SIN_PLATAFORMA), ("categoria", SIN_CATEGORIA), ("formato", SIN_FORMATO)):
        if campo in padroes and padroes[campo] not in valores:
            raise ErroNegocio("padrao_invalido", f"Valor por omissão inválido para {ROTULOS[campo]}.")
    wb = _abrir(dados)
    _, linhas = _linhas(wb, folha)
    ic = _cabecalho(linhas)
    utilizadores = list(db.scalars(select(Utilizador).where(Utilizador.activo.is_(True))))
    lote = f"IMP-{datetime.now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:4]}"
    criados, ignoradas = 0, []
    for n, r in enumerate(linhas[ic + 1:]):
        if not any(v not in (None, "") for v in r):
            continue
        d, erros = _interpretar(db, r, mapa, ano, padroes, utilizadores, ctx.utilizador.id)
        bloqueantes = [e for e in erros if not e.startswith(AVISOS)]
        if bloqueantes:
            ignoradas.append({"linha": ic + 2 + n, "erros": bloqueantes})
            continue
        d.pop("_responsavel")
        db.add(Conteudo(**d, origem="importacao", lote_importacao=lote, criado_por_id=ctx.utilizador.id))
        criados += 1
    if criados == 0:
        raise ErroNegocio("nada_importado", "Nenhuma linha válida para importar.", detalhes=ignoradas[:50])
    registar(db, utilizador_id=ctx.utilizador.id, accao="importar", entidade="calendario", entidade_id=lote,
             resumo=f"Importou {criados} conteúdo(s) do Excel (lote {lote}); {len(ignoradas)} linha(s) ignorada(s)", ip=ctx.ip)
    db.commit()
    return {"lote": lote, "criados": criados, "ignoradas": ignoradas}


def modelo_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Calendário"
    ws.append(["Data", "Hora", "Plataforma", "Categoria", "Formato", "Tema", "Objectivo", "Legenda", "Hashtags", "CTA", "Responsável", "Estado", "Notas"])
    ws.append(["01/12/2026", "18:00", "Instagram", "Educativo", "Carrossel", "Exemplo — apagar esta linha", "Educar sobre o ritual de cuidado",
               "", "", "", "Maira", "Planeamento", ""])
    for col, larg in zip("ABCDEFGHIJKLM", (12, 7, 12, 13, 11, 40, 30, 50, 30, 25, 14, 13, 30)):
        ws.column_dimensions[col].width = larg
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
