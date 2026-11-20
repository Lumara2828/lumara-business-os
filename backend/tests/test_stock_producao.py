from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.tempo import hoje
from app.modules.notificacoes.models import Notificacao


def D(v):
    return Decimal(str(v))


@pytest.fixture
def catalogo(equipa):
    """Matéria-prima, embalagem e produto acabado, com ficha técnica (dados de teste)."""
    luisa, _, diana = equipa
    mk = lambda **k: diana.post("/stock/artigos", k).json()  # noqa: E731
    oleo = mk(codigo="MP-OLEO", nome="Óleo de coco", categoria="materia_prima", unidade="ml", stock_minimo="500")
    frasco = mk(codigo="EMB-30", nome="Frasco 30 ml", categoria="embalagem", unidade="un", stock_minimo="20", controla_lotes=False)
    produto = mk(codigo="PA-OLEO30", nome="Óleo corporal 30 ml", categoria="produto_acabado", unidade="un", stock_minimo="10")
    ficha = diana.post("/producao/fichas", {
        "codigo": "FT-OLEO30", "nome": "Óleo corporal 30 ml", "produto_id": produto["id"], "rendimento": "10",
        "validade_dias": 180, "tempo_producao_min": 60, "instrucoes": "Misturar e envasar.",
        "ingredientes": [{"artigo_id": oleo["id"], "quantidade": "300"}, {"artigo_id": frasco["id"], "quantidade": "10"}],
    })
    assert ficha.status_code == 201, ficha.text
    return {"oleo": oleo, "frasco": frasco, "produto": produto, "ficha": ficha.json()}


def _entrada(p, artigo, qtd, **k):
    r = p.post("/stock/movimentos/entrada", {"artigo_id": artigo["id"], "quantidade": str(qtd), **k})
    assert r.status_code == 201, r.text
    return r.json()


def _disp(p, artigo):
    return D(p.get(f"/stock/artigos/{artigo['id']}").json()["disponivel"])


def test_entradas_saidas_e_fefo(equipa, catalogo):
    luisa, _, diana = equipa
    oleo = catalogo["oleo"]
    _entrada(diana, oleo, 400, validade=(hoje() + timedelta(days=200)).isoformat(), lote_numero="A")
    _entrada(diana, oleo, 300, validade=(hoje() + timedelta(days=20)).isoformat(), lote_numero="B")
    assert _disp(diana, oleo) == 700
    ms = diana.post("/stock/movimentos/saida", {"artigo_id": oleo["id"], "quantidade": "350", "tipo": "saida", "referencia": "teste"}).json()
    # FEFO: primeiro o lote B (expira antes), depois o A
    assert [(m["lote"]["numero"], D(m["quantidade"])) for m in ms] == [("B", -300), ("A", -50)]
    r = diana.post("/stock/movimentos/saida", {"artigo_id": oleo["id"], "quantidade": "1000"})
    assert r.status_code == 400 and r.json()["codigo"] == "stock_insuficiente"
    r = diana.post("/stock/movimentos/saida", {"artigo_id": oleo["id"], "quantidade": "5", "tipo": "perda"})
    assert r.json()["codigo"] == "motivo_obrigatorio"
    assert _disp(diana, oleo) == 350


def test_movimentos_sao_imutaveis(equipa, catalogo, db):
    _, _, diana = equipa
    _entrada(diana, catalogo["frasco"], 50)
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE movimentos_stock SET quantidade = 999"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM movimentos_stock"))
    db.rollback()


def test_inventario_fisico_cria_ajustamento(equipa, catalogo):
    _, _, diana = equipa
    frasco = catalogo["frasco"]
    _entrada(diana, frasco, 50)
    r = diana.post("/stock/movimentos/inventario", {"artigo_id": frasco["id"], "quantidade_contada": "47", "motivo": "Contagem mensal"})
    assert r.status_code == 201 and D(r.json()["diferenca"]) == -3
    assert _disp(diana, frasco) == 47
    hist = diana.get("/stock/movimentos", params={"artigo_id": frasco["id"]}).json()
    assert hist[0]["tipo"] == "inventario" and hist[0]["motivo"] == "Contagem mensal"


def test_custos_confidenciais(equipa, catalogo):
    luisa, maira, diana = equipa
    oleo = catalogo["oleo"]
    _entrada(diana, oleo, 1000, custo_unitario="2")
    _entrada(luisa, oleo, 1000, custo_unitario="4")
    assert D(luisa.get(f"/stock/artigos/{oleo['id']}").json()["custo_unitario"]) == 3  # média ponderada
    assert diana.get(f"/stock/artigos/{oleo['id']}").json()["custo_unitario"] is None
    assert maira.get("/stock/artigos").status_code == 200  # consulta quantidades
    assert "valor_inventario" not in diana.get("/stock/relatorios").json()
    assert D(luisa.get("/stock/relatorios").json()["valor_inventario"]["total"]) == 6000
    assert maira.post("/stock/movimentos/entrada", {"artigo_id": oleo["id"], "quantidade": "1"}).status_code == 403
    r = diana.post("/stock/artigos", {"codigo": "X1", "nome": "Com custo", "categoria": "embalagem", "unidade": "un",
                                      "stock_minimo": "0", "custo_unitario": "5"})
    assert r.status_code == 403


def test_ordem_de_producao_completa(equipa, catalogo, db):
    luisa, _, diana = equipa
    oleo, frasco, produto, ficha = catalogo["oleo"], catalogo["frasco"], catalogo["produto"], catalogo["ficha"]
    _entrada(luisa, oleo, 1000, custo_unitario="2", lote_numero="MP-1", validade=(hoje() + timedelta(days=365)).isoformat())
    _entrada(luisa, frasco, 25, custo_unitario="50")
    nec = diana.get(f"/producao/fichas/{ficha['id']}/necessidades", params={"quantidade": 40}).json()
    assert not nec["pode_produzir"]  # 40 un precisam de 1200 ml de óleo e 40 frascos
    o = diana.post("/producao/ordens", {"ficha_id": ficha["id"], "quantidade_planeada": "20", "data_inicio": hoje().isoformat(),
                                        "data_prevista": (hoje() + timedelta(days=2)).isoformat()}).json()
    assert o["codigo"] == "OP-0001" and o["tarefa_id"] and o["faltas"] == []
    assert diana.post(f"/producao/ordens/{o['id']}/iniciar").json()["estado"] == "em_curso"
    r = diana.post(f"/producao/ordens/{o['id']}/concluir", {"quantidade_produzida": "19"})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["estado"] == "concluida" and c["lote"]["numero"].startswith("L") and c["rendimento_pct"] == "95.0"
    assert c["lote"]["validade"] == (hoje() + timedelta(days=180)).isoformat()
    # Consumo segundo a ficha (sobre a quantidade planeada): 600 ml óleo, 20 frascos
    assert _disp(diana, oleo) == 400 and _disp(diana, frasco) == 5 and _disp(diana, produto) == 19
    # Custo: (600×2 + 20×50) = 2200 Kz → só a CEO vê
    assert D(luisa.get(f"/producao/ordens/{o['id']}").json()["custo_materiais"]) == 2200
    assert diana.get(f"/producao/ordens/{o['id']}").json()["custo_materiais"] is None
    assert D(luisa.get(f"/stock/artigos/{produto['id']}").json()["custo_unitario"]) == D("115.7895")
    # Rastreabilidade do lote produzido
    rast = diana.get(f"/stock/lotes/{c['lote']['id']}/rastreabilidade").json()
    assert rast["origem"]["ordem"]["codigo"] == "OP-0001"
    assert {m["artigo"]["nome"] for m in rast["origem"]["materiais"]} == {"Óleo de coco", "Frasco 30 ml"}
    # Tarefa ligada concluída automaticamente
    assert diana.get(f"/tarefas/{o['tarefa_id']}").json()["estado"] == "concluida"
    assert diana.post(f"/producao/ordens/{o['id']}/concluir", {"quantidade_produzida": "1"}).status_code == 400
    # Frascos abaixo do mínimo (5 < 20) → alerta à produção
    alerta = db.scalars(select(Notificacao).where(Notificacao.tipo == "stock_minimo")).all()
    assert any("Frasco" in n.titulo for n in alerta)


def test_conclusao_sem_materiais_nao_mexe_no_stock(equipa, catalogo):
    _, _, diana = equipa
    _entrada(diana, catalogo["oleo"], 1000)
    o = diana.post("/producao/ordens", {"ficha_id": catalogo["ficha"]["id"], "quantidade_planeada": "10",
                                        "data_inicio": hoje().isoformat(), "data_prevista": hoje().isoformat()}).json()
    assert [f["artigo"] for f in o["faltas"]] == ["Frasco 30 ml"]
    r = diana.post(f"/producao/ordens/{o['id']}/concluir", {"quantidade_produzida": "10"})
    assert r.status_code == 400 and r.json()["codigo"] == "materiais_insuficientes"
    assert _disp(diana, catalogo["oleo"]) == 1000  # nada foi consumido
    assert diana.post(f"/producao/ordens/{o['id']}/cancelar", {"motivo": "Sem frascos"}).json()["estado"] == "cancelada"


def test_ficha_usada_gera_nova_versao(equipa, catalogo):
    _, _, diana = equipa
    ficha = catalogo["ficha"]
    diana.post("/producao/ordens", {"ficha_id": ficha["id"], "quantidade_planeada": "10", "data_inicio": hoje().isoformat(),
                                    "data_prevista": hoje().isoformat(), "criar_tarefa": False})
    corpo = {"codigo": "FT-OLEO30", "nome": "Óleo corporal 30 ml (nova)", "produto_id": catalogo["produto"]["id"], "rendimento": "12",
             "ingredientes": [{"artigo_id": catalogo["oleo"]["id"], "quantidade": "320"}]}
    r = diana.put(f"/producao/fichas/{ficha['id']}", corpo).json()
    assert r["versao"] == 2 and r["id"] != ficha["id"]
    activas = diana.get("/producao/fichas").json()
    assert [(f["codigo"], f["versao"]) for f in activas] == [("FT-OLEO30", 2)]


def test_nao_conformidade_vai_para_excepcoes(equipa, catalogo, db):
    luisa, maira, diana = equipa
    o = diana.post("/producao/ordens", {"ficha_id": catalogo["ficha"]["id"], "quantidade_planeada": "10",
                                        "data_inicio": hoje().isoformat(), "data_prevista": hoje().isoformat()}).json()
    r = diana.post("/producao/nao-conformidades", {"ordem_id": o["id"], "descricao": "Cor alterada", "gravidade": "alta"})
    assert r.status_code == 201
    exc = luisa.get("/excepcoes").json()["seccoes"]
    assert any("Não conformidade" in x["titulo"] for x in exc["problemas_producao"])
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "nao_conformidade")).first() is not None
    assert maira.post("/producao/nao-conformidades", {"ordem_id": o["id"], "descricao": "x y z", "gravidade": "baixa"}).status_code == 403
    nid = r.json()["id"]
    diana.post(f"/producao/nao-conformidades/{nid}/resolver", {"accao_correctiva": "Lote separado e reanalisado"})
    assert luisa.get("/excepcoes").json()["seccoes"]["problemas_producao"] == []


def test_validade_e_ruptura_nos_relatorios_e_dashboard(equipa, catalogo, db):
    luisa, _, diana = equipa
    _entrada(diana, catalogo["oleo"], 100, validade=(hoje() + timedelta(days=10)).isoformat())
    rel = diana.get("/stock/relatorios").json()
    assert [l["artigo"]["nome"] for l in rel["proximos_validade"]] == ["Óleo de coco"]
    assert {a["nome"] for a in rel["a_comprar"]} == {"Óleo de coco", "Frasco 30 ml"}
    assert [a["nome"] for a in rel["a_produzir"]] == ["Óleo corporal 30 ml"]
    assert {a["nome"] for a in rel["rupturas"]} == {"Frasco 30 ml", "Óleo corporal 30 ml"}
    # lote expirado com stock entra nas excepções e no resumo
    db.execute(text("UPDATE lotes SET validade = CURRENT_DATE - 1, data_producao = CURRENT_DATE - 30"))
    db.commit()
    exc = luisa.get("/excepcoes").json()["seccoes"]
    assert len(exc["lotes_expirados"]) == 1
    assert {a["nome"] for a in exc["stock_critico"]} >= {"Frasco 30 ml", "Óleo corporal 30 ml"}
    dash = luisa.get("/dashboard/executivo").json()
    assert dash["stock"]["lotes_expirados"] == 1 and dash["stock"]["rupturas"] == 2
    assert any("expirado" in x for x in dash["resumo"]["intervencao_ceo"])
