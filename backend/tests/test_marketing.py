import io
import json
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook
from sqlalchemy import select, text

from app.core.tempo import hoje
from app.main import app
from app.modules.ia.fornecedores import RespostaIA, get_fornecedor
from app.modules.marketing.models import InteracaoIA
from app.modules.notificacoes.models import Notificacao


def _d(n=3):
    return (hoje() + timedelta(days=n)).isoformat()


def _novo(p, **k):
    corpo = {"data_publicacao": _d(), "plataforma": "instagram", "categoria": "educativo", "formato": "carrossel",
             "tema": "Ritual de cuidado das unhas", **k}
    r = p.post("/marketing/conteudos", corpo)
    assert r.status_code == 201, r.text
    return r.json()


class FornecedorFalso:
    """Só para testes: devolve uma resposta fixa e regista o que recebeu."""
    nome, modelo = "teste", "modelo-teste"

    def __init__(self, dados=None, recusar=False):
        self.dados, self.recusar, self.chamadas = dados, recusar, []

    def configurado(self):
        return True

    def gerar(self, sistema, pedido, esquema):
        self.chamadas.append((sistema, pedido, esquema))
        return RespostaIA(dados=self.dados, modelo=self.modelo, tokens_entrada=1200, tokens_saida=300, recusada=self.recusar)


@pytest.fixture
def ia_falsa():
    f = FornecedorFalso({"propostas": [
        {"titulo": "A", "texto": "Um momento só teu: hidrata as unhas com o nosso óleo.", "cta": "Envia-nos mensagem", "hashtags": ["#Lumara"]},
        {"titulo": "B", "texto": "Este óleo cura unhas fracas em 3 dias!", "cta": "Encomenda já", "hashtags": ["#unhas"]},
    ]})
    app.dependency_overrides[get_fornecedor] = lambda: f
    yield f
    app.dependency_overrides.pop(get_fornecedor, None)


def test_fluxo_aprovacao_humana(equipa, db):
    luisa, maira, diana = equipa
    c = _novo(maira)
    url = f"/marketing/conteudos/{c['id']}"
    assert c["codigo"] == "C-0001" and c["estado"] == "ideia"
    assert maira.post(f"{url}/estado", {"estado": "revisao"}).json()["codigo"] == "texto_em_falta"
    maira.patch(url, {"texto": "Cuida das tuas unhas com calma e carinho."})
    assert maira.post(f"{url}/estado", {"estado": "agendado"}).json()["codigo"] == "sem_aprovacao"
    assert maira.post(f"{url}/estado", {"estado": "aprovado"}).json()["codigo"] == "usar_aprovar"
    assert maira.post(f"{url}/estado", {"estado": "revisao"}).json()["estado"] == "revisao"
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "conteudo_revisao")).first() is not None
    assert maira.post(f"{url}/aprovar", {}).status_code == 403
    assert luisa.post(f"{url}/rejeitar", {}).status_code == 400
    assert luisa.post(f"{url}/rejeitar", {"comentario": "Mais curto"}).json()["estado"] == "criacao"
    maira.post(f"{url}/estado", {"estado": "revisao"})
    a = luisa.post(f"{url}/aprovar", {"comentario": "Boa"}).json()
    assert a["estado"] == "aprovado" and a["aprovado_em"]
    assert maira.post(f"{url}/estado", {"estado": "agendado"}).json()["estado"] == "agendado"
    # Alterar o texto depois de aprovado anula a aprovação
    r = maira.patch(url, {"texto": "Texto novo"}).json()
    assert r["estado"] == "revisao" and r["aprovado_em"] is None
    luisa.post(f"{url}/aprovar", {})
    r = maira.post(f"{url}/estado", {"estado": "publicado", "link_publicacao": "https://instagram.com/p/abc"}).json()
    assert r["estado"] == "publicado" and r["link_publicacao"].startswith("https://")
    assert maira.patch(url, {"texto": "x"}).json()["codigo"] == "conteudo_publicado"
    assert maira.post(f"{url}/estado", {"estado": "analisado"}).json()["codigo"] == "metricas_em_falta"
    m = maira.put(f"{url}/metricas", {"alcance": 1000, "gostos": 80, "comentarios": 10, "partilhas": 5, "guardados": 5}).json()
    assert m["envolvimento_pct"] == 10.0
    assert maira.post(f"{url}/estado", {"estado": "analisado"}).json()["estado"] == "analisado"
    # A base de dados também impede publicar sem aprovação
    with pytest.raises(Exception):
        db.execute(text("UPDATE conteudos SET aprovado_em = NULL WHERE id = :i"), {"i": c["id"]})
        db.commit()
    db.rollback()
    assert diana.get("/marketing/conteudos").status_code == 403


def test_alertas_de_alegacoes(equipa):
    _, maira, _ = equipa
    c = _novo(maira, texto="O nosso óleo cura a queda de cabelo com resultados imediatos.")
    exprs = {a["expressao"] for a in c["alertas"]}
    assert {"cura", "resultados imediatos"} <= exprs
    assert _novo(maira, texto="Um ritual de cuidado para ti.")["alertas"] == []


def test_assistente_ia(equipa, ia_falsa, db):
    luisa, maira, diana = equipa
    c = _novo(maira)
    r = maira.post("/ia/marketing", {"tipo": "legendas", "conteudo_id": c["id"], "contexto": {"produto": "Óleo fortalecedor de unhas"}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["propostas"]) == 2 and "aprovação" in d["aviso"]
    assert d["propostas"][0]["alertas"] == [] and d["propostas"][1]["alertas"][0]["expressao"] == "cura"
    sistema, pedido, esquema = ia_falsa.chamadas[0]
    assert "Nunca faças alegações médicas" in sistema and "Óleo fortalecedor" in pedido and "Ritual de cuidado" in pedido
    assert esquema["additionalProperties"] is False
    # A IA não grava nada: o conteúdo continua sem texto
    assert maira.get(f"/marketing/conteudos/{c['id']}").json()["texto"] is None
    reg = db.scalars(select(InteracaoIA)).all()
    assert len(reg) == 1 and reg[0].tokens_entrada == 1200
    assert diana.post("/ia/marketing", {"tipo": "temas"}).status_code == 403
    assert maira.post("/ia/marketing", {"tipo": "adaptar"}).json()["codigo"] == "texto_em_falta"
    assert luisa.get("/ia/interacoes").json()["mes"]["pedidos"] == 1


def test_ia_recusa_e_nao_configurada(equipa):
    _, maira, _ = equipa
    app.dependency_overrides[get_fornecedor] = lambda: FornecedorFalso(recusar=True)
    try:
        assert maira.post("/ia/marketing", {"tipo": "temas"}).json()["codigo"] == "ia_recusou"
    finally:
        app.dependency_overrides.pop(get_fornecedor, None)
    # Sem chave configurada: resposta clara, sem simular
    r = maira.post("/ia/marketing", {"tipo": "temas"})
    assert r.status_code == 503 and r.json()["codigo"] == "ia_nao_configurada"
    assert maira.get("/ia/estado").json()["configurado"] is False


def test_guia_de_marca_so_ceo(equipa):
    luisa, maira, _ = equipa
    guia = luisa.get("/ia/marca").json()
    guia["expressoes_proibidas"] = guia["expressoes_proibidas"] + ["imbatível"]
    assert maira.put("/ia/marca", guia).status_code == 403
    assert luisa.put("/ia/marca", guia).status_code == 200
    assert _novo(maira, texto="Um preço imbatível!")["alertas"][0]["expressao"] == "imbatível"


def _excel(linhas, cabecalho=("Data", "Rede", "Pilar", "Formato", "Tema", "Legenda", "Responsável", "Status")):
    wb = Workbook()
    ws = wb.active
    ws.title = "Dezembro"
    ws.append(["Calendário de conteúdos — Dezembro"])
    ws.append([])
    ws.append(list(cabecalho))
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_importacao_excel(equipa):
    luisa, maira, _ = equipa
    xlsx = _excel([
        [datetime(2026, 12, 1), "Insta", "Educação", "Carrossel", "Como hidratar cabelos 4C", "", "Maira", "Por fazer"],
        ["03/12/2026", "FB", "Depoimento", "Reel", "", "Testemunho da cliente [nome]", "Desconhecida", "Publicado"],
        ["05/12", "Instagram", "Produto", "Stories", "Kits de Natal", "", "", "em produção"],
        ["data errada", "Snapchat", "???", "Post", "Linha inválida", "", "", ""],
    ])
    ficheiro = {"ficheiro": ("calendario.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    a = maira.post("/marketing/importar/analisar", files=ficheiro, data={"ano": "2026"}).json()
    assert a["linha_cabecalho"] == 3 and a["total_linhas"] == 4
    mapa = {c["campo_sugerido"]: c["indice"] for c in a["colunas"] if c["campo_sugerido"]}
    assert set(mapa) == {"data_publicacao", "plataforma", "categoria", "formato", "tema", "texto", "responsavel", "estado"}
    assert a["previsualizacao"][3]["erros"]
    r = maira.post("/marketing/importar/confirmar", files=ficheiro, data={"mapeamento": json.dumps(mapa), "ano": "2026"})
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["criados"] == 3 and [i["linha"] for i in res["ignoradas"]] == [7]
    lista = {c["tema"]: c for c in maira.get("/marketing/conteudos", params={"de": "2026-12-01", "ate": "2026-12-31"}).json()}
    assert lista["Como hidratar cabelos 4C"]["plataforma"] == "instagram" and lista["Como hidratar cabelos 4C"]["categoria"] == "educativo"
    t = lista["Testemunho da cliente [nome]"]
    assert t["estado"] == "revisao" and t["aprovado_em"] is None and t["categoria"] == "testemunhos"  # nunca entra aprovado
    assert lista["Kits de Natal"]["data_publicacao"] == "2026-12-05" and lista["Kits de Natal"]["estado"] == "criacao"
    assert all(c["origem"] == "importacao" for c in lista.values())
    r = maira.post("/marketing/importar/analisar", files={"ficheiro": ("x.csv", b"a,b", "text/csv")})
    assert r.json()["codigo"] == "formato_invalido"
    assert maira.get("/marketing/importar/modelo").status_code == 200


def test_campanhas_e_orcamento_confidencial(equipa):
    luisa, maira, _ = equipa
    corpo = {"nome": "Natal Lumara", "objectivo": "Vender kits de autocuidado", "data_inicio": _d(1), "data_fim": _d(20), "canais": ["instagram"]}
    assert maira.post("/marketing/campanhas", {**corpo, "orcamento_kz": "50000"}).status_code == 403
    k = maira.post("/marketing/campanhas", corpo).json()
    assert k["estado"] == "proposta" and k["orcamento_kz"] is None
    assert maira.post(f"/marketing/campanhas/{k['id']}/estado", {"estado": "activa"}).json()["codigo"] == "sem_aprovacao"
    assert maira.post(f"/marketing/campanhas/{k['id']}/estado", {"estado": "aprovada"}).status_code == 403
    exc = luisa.get("/excepcoes").json()["seccoes"]
    assert [x["nome"] for x in exc["campanhas_aprovacao"]] == ["Natal Lumara"]
    luisa.put(f"/marketing/campanhas/{k['id']}", {**corpo, "orcamento_kz": "50000"})
    assert luisa.post(f"/marketing/campanhas/{k['id']}/estado", {"estado": "aprovada"}).json()["orcamento_kz"] == "50000.00"
    assert maira.get("/marketing/campanhas").json()[0]["orcamento_kz"] is None
    assert maira.post(f"/marketing/campanhas/{k['id']}/estado", {"estado": "activa"}).json()["estado"] == "activa"
    _novo(maira, campanha_id=k["id"])
    assert maira.get("/marketing/campanhas").json()[0]["conteudos"] == 1


def test_desempenho_e_dashboard(equipa, db):
    luisa, maira, _ = equipa
    a = _novo(maira, texto="Texto A")
    b = _novo(maira, texto="Texto B", plataforma="facebook")
    for c in (a, b):
        maira.post(f"/marketing/conteudos/{c['id']}/estado", {"estado": "revisao"})
    luisa.post(f"/marketing/conteudos/{a['id']}/aprovar", {})
    maira.post(f"/marketing/conteudos/{a['id']}/estado", {"estado": "publicado"})
    maira.put(f"/marketing/conteudos/{a['id']}/metricas", {"alcance": 500, "gostos": 50})
    d = maira.get("/marketing/desempenho", params={"de": hoje().isoformat(), "ate": _d(30)}).json()
    assert d["planeados"] == 2 and d["publicados"] == 1 and d["em_revisao"] == 1 and d["alcance_total"] == 500
    assert d["por_categoria"]["educativo"]["envolvimento_pct"] == 10.0
    exc = luisa.get("/excepcoes").json()["seccoes"]
    assert [x["tema"] for x in exc["conteudos_aprovacao"]] == ["Ritual de cuidado das unhas"]
    dash = luisa.get("/dashboard/executivo").json()
    assert dash["marketing"]["em_revisao"] == 1
    assert any("conteúdo(s) de marketing" in x for x in dash["resumo"]["intervencao_ceo"])
    # Conteúdo com data passada e não publicado → alerta à responsável
    db.execute(text("UPDATE conteudos SET data_publicacao = CURRENT_DATE - 2 WHERE id = :i"), {"i": b["id"]})
    db.commit()
    from app.modules.automacao.alertas import verificar_conteudos
    verificar_conteudos(db)
    db.commit()
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "conteudo_atraso")).first() is not None


def test_integracoes_sem_simulacao(equipa):
    luisa, _, diana = equipa
    lista = {i["id"]: i for i in luisa.get("/integracoes").json()}
    assert set(lista) == {"ia", "instagram", "facebook", "whatsapp", "canva", "metricool", "make"}
    assert lista["instagram"]["estado"] == "nao_configurada" and lista["ia"]["estado"] == "nao_configurada"
    assert diana.get("/integracoes").status_code == 403
