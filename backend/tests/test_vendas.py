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
def loja(equipa):
    """Dois produtos acabados com stock em lotes e preço definido (dados de teste)."""
    luisa, maira, diana = equipa
    prods = {}
    for cod, nome, qtd, val in (("PA-UNHAS", "Óleo de unhas", 20, 300), ("PA-SAB", "Sabonete artesanal", 5, 200)):
        a = diana.post("/stock/artigos", {"codigo": cod, "nome": nome, "categoria": "produto_acabado", "unidade": "un", "stock_minimo": "2"}).json()
        diana.post("/stock/movimentos/entrada", {"artigo_id": a["id"], "quantidade": str(qtd), "lote_numero": f"L-{cod}-A",
                                                 "validade": (hoje() + timedelta(days=val)).isoformat()})
        prods[cod] = a
    luisa.put(f"/stock/artigos/{prods['PA-UNHAS']['id']}", {**{k: prods['PA-UNHAS'][k] for k in ("codigo", "nome", "categoria", "unidade", "stock_minimo")},
                                                         "custo_unitario": "1500"})
    assert luisa.post("/vendas/precos", {"artigo_id": prods["PA-UNHAS"]["id"], "preco_kz": "5000"}).status_code == 201
    assert luisa.post("/vendas/precos", {"artigo_id": prods["PA-SAB"]["id"], "preco_kz": "2500"}).status_code == 201
    cliente = maira.post("/vendas/clientes", {"nome": "Ana Teste", "whatsapp": "923 000 111", "localidade": "Luanda",
                                              "consentimento_marketing": True}).json()
    return {"unhas": prods["PA-UNHAS"], "sabao": prods["PA-SAB"], "cliente": cliente}


def _enc(p, loja, linhas, **k):
    r = p.post("/vendas/encomendas", {"cliente_id": loja["cliente"]["id"], "canal": "whatsapp",
                                      "linhas": [{"artigo_id": a["id"], "quantidade": str(q)} for a, q in linhas], **k})
    return r


def _disp(p, a):
    return D(p.get(f"/stock/artigos/{a['id']}").json()["disponivel"])


def test_precos_so_ceo_e_margem_so_ceo(equipa, loja):
    luisa, maira, diana = equipa
    assert maira.post("/vendas/precos", {"artigo_id": loja["unhas"]["id"], "preco_kz": "1"}).status_code == 403
    pl = {p["artigo"]["codigo"]: p for p in luisa.get("/vendas/precos").json()}
    assert pl["PA-UNHAS"]["preco_kz"] == "5000.00" and pl["PA-UNHAS"]["margem_bruta_pct"] == "70.0"  # (5000-1500)/5000
    pm = {p["artigo"]["codigo"]: p for p in maira.get("/vendas/precos").json()}
    assert pm["PA-UNHAS"]["preco_kz"] == "5000.00" and pm["PA-UNHAS"]["margem_bruta_pct"] is None and pm["PA-UNHAS"]["custo_unitario"] is None
    assert diana.get("/vendas/precos").status_code == 403


def test_ciclo_completo_encomenda(equipa, loja, db):
    luisa, maira, diana = equipa
    r = _enc(maira, loja, [(loja["unhas"], 3), (loja["sabao"], 2)], taxa_entrega_kz="1000", tipo_entrega="entrega",
             morada_entrega="Talatona", data_prevista=(hoje() + timedelta(days=2)).isoformat())
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["codigo"] == "E-0001" and e["total_kz"] == "21000.00"  # 15000 + 5000 + 1000
    assert e["estado_pagamento"] == "pendente"
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "encomenda")).first() is not None  # Diana avisada
    url = f"/vendas/encomendas/{e['id']}"
    # Diana prepara e não vê valores
    vista = diana.get(url).json()
    assert "total_kz" not in vista and "preco_unitario_kz" not in vista["linhas"][0]
    assert diana.post(f"{url}/estado", {"estado": "em_preparacao"}).json()["estado"] == "em_preparacao"
    assert diana.post(f"{url}/estado", {"estado": "pronta"}).json()["estado"] == "pronta"
    # Facturação ≠ recebimento: entregue sem pagamento
    assert diana.post(f"{url}/estado", {"estado": "entregue"}).json()["estado"] == "entregue"
    assert _disp(diana, loja["unhas"]) == 17 and _disp(diana, loja["sabao"]) == 3
    det = maira.get(url).json()
    assert {(l["artigo"], l["lote"]) for l in det["lotes_entregues"]} == {("Óleo de unhas", "L-PA-UNHAS-A"), ("Sabonete artesanal", "L-PA-SAB-A")}
    rel = luisa.get("/vendas/relatorios", params={"de": hoje().isoformat(), "ate": hoje().isoformat()}).json()
    assert rel["indicadores"]["facturacao_kz"] == "21000.00" and rel["indicadores"]["recebido_kz"] == "0"
    assert rel["por_receber"]["total_kz"] == "21000.00"
    # Pagamentos
    assert maira.post(f"{url}/pagamentos", {"valor_kz": "30000", "forma": "transferencia"}).json()["codigo"] == "pagamento_excessivo"
    assert maira.post(f"{url}/pagamentos", {"valor_kz": "10000", "forma": "multicaixa_express"}).json()["estado_pagamento"] == "parcial"
    assert maira.post(f"{url}/pagamentos", {"valor_kz": "11000", "forma": "numerario"}).json()["estado_pagamento"] == "pago"
    assert maira.post(f"{url}/pagamentos", {"valor_kz": "-1000", "forma": "numerario"}).json()["codigo"] == "motivo_obrigatorio"
    rel = luisa.get("/vendas/relatorios", params={"de": hoje().isoformat(), "ate": hoje().isoformat()}).json()
    assert rel["indicadores"]["recebido_kz"] == "21000.00" and rel["indicadores"]["ticket_medio_kz"] == "21000.00"
    assert [p["nome"] for p in rel["produtos_mais_vendidos"]] == ["Óleo de unhas", "Sabonete artesanal"]
    # Pagamentos imutáveis
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE pagamentos SET valor_kz = 1"))
    db.rollback()
    assert maira.post(f"{url}/estado", {"estado": "cancelada", "motivo": "x"}).json()["codigo"] == "estado_final"


def test_stock_reservado_e_insuficiente(equipa, loja):
    _, maira, diana = equipa
    a = _enc(maira, loja, [(loja["sabao"], 4)]).json()
    b = _enc(maira, loja, [(loja["sabao"], 3)]).json()
    assert diana.post(f"/vendas/encomendas/{a['id']}/estado", {"estado": "pronta"}).json()["estado"] == "pronta"
    r = diana.post(f"/vendas/encomendas/{b['id']}/estado", {"estado": "pronta"})
    assert r.json()["codigo"] == "stock_insuficiente"  # 5 em stock, 4 reservados
    maira.post(f"/vendas/encomendas/{a['id']}/estado", {"estado": "cancelada", "motivo": "Cliente desistiu"})
    assert diana.post(f"/vendas/encomendas/{b['id']}/estado", {"estado": "pronta"}).json()["estado"] == "pronta"
    assert diana.post(f"/vendas/encomendas/{b['id']}/estado", {"estado": "cancelada", "motivo": "x"}).status_code == 403


def test_desconto_acima_do_limite_precisa_ceo(equipa, loja, db):
    luisa, maira, diana = equipa
    e = _enc(maira, loja, [(loja["unhas"], 2)], desconto_kz="2000").json()  # 20% > 10%
    assert e["desconto_requer_aprovacao"] and e["total_kz"] == "8000.00"
    assert diana.post(f"/vendas/encomendas/{e['id']}/estado", {"estado": "em_preparacao"}).json()["codigo"] == "desconto_por_aprovar"
    assert any("desconto" in x for x in luisa.get("/dashboard/executivo").json()["resumo"]["intervencao_ceo"])
    assert [x["codigo"] for x in luisa.get("/excepcoes").json()["seccoes"]["encomendas_alerta"]] == [e["codigo"]]
    assert maira.post(f"/vendas/encomendas/{e['id']}/aprovar-desconto").status_code == 403
    luisa.post(f"/vendas/encomendas/{e['id']}/aprovar-desconto")
    assert diana.post(f"/vendas/encomendas/{e['id']}/estado", {"estado": "em_preparacao"}).json()["estado"] == "em_preparacao"
    # Dentro do limite não precisa
    assert not _enc(maira, loja, [(loja["unhas"], 2)], desconto_kz="1000").json()["desconto_requer_aprovacao"]
    # Alterar preço numa linha: só CEO
    r = maira.post("/vendas/encomendas", {"cliente_id": loja["cliente"]["id"], "canal": "loja",
                                          "linhas": [{"artigo_id": loja["unhas"]["id"], "quantidade": "1", "preco_unitario_kz": "100"}]})
    assert r.status_code == 403


def test_clientes_historico_whatsapp_e_inactivas(equipa, loja, db):
    luisa, maira, diana = equipa
    assert maira.post("/vendas/clientes", {"nome": "Duplicada", "telefone": "923000111"}).status_code == 409
    e = _enc(maira, loja, [(loja["unhas"], 1)]).json()
    for est in ("pronta", "entregue"):
        diana.post(f"/vendas/encomendas/{e['id']}/estado", {"estado": est})
    c = maira.get(f"/vendas/clientes/{loja['cliente']['id']}").json()
    assert c["compras"] == 1 and c["primeira_compra"] == hoje().isoformat() and c["produtos_preferidos"][0]["produto"] == "Óleo de unhas"
    w = maira.get(f"/vendas/encomendas/{e['id']}/whatsapp").json()
    assert w["numero"] == "244923000111" and w["url"].startswith("https://wa.me/244923000111?text=") and "E-0001" in w["texto"]
    assert diana.get("/vendas/clientes").status_code == 403
    db.execute(text("UPDATE encomendas SET data_encomenda = CURRENT_DATE - 120"))
    db.commit()
    ina = maira.get("/vendas/clientes-inactivas").json()
    assert [x["nome"] for x in ina["clientes"]] == ["Ana Teste"] and ina["clientes"][0]["pode_contactar_marketing"]


def test_cobranca_atrasada_alerta(equipa, loja, db):
    luisa, maira, diana = equipa
    e = _enc(maira, loja, [(loja["sabao"], 1)]).json()
    for est in ("pronta", "entregue"):
        diana.post(f"/vendas/encomendas/{e['id']}/estado", {"estado": est})
    db.execute(text("ALTER TABLE movimentos_stock DISABLE TRIGGER movimentos_stock_imutavel"))  # só para envelhecer o dado de teste
    db.execute(text("UPDATE encomendas SET entregue_em = now() - interval '10 days'"))
    db.execute(text("ALTER TABLE movimentos_stock ENABLE TRIGGER movimentos_stock_imutavel"))
    db.commit()
    from app.modules.automacao.alertas import verificar_encomendas
    verificar_encomendas(db)
    db.commit()
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "cobranca", Notificacao.utilizador_id == luisa.id)).first()
    assert any("Pagamento em falta" in x["motivo"] for x in luisa.get("/excepcoes").json()["seccoes"]["encomendas_alerta"])


def test_evento_venda_rapida_reconciliacao_e_rentabilidade(equipa, loja):
    luisa, maira, diana = equipa
    ev = maira.post("/eventos", {"nome": "Feira de Natal", "data_inicio": hoje().isoformat(), "data_fim": hoje().isoformat(),
                                 "local": "Luanda", "objectivo": "Vender e captar clientes", "meta_vendas_kz": "20000"}).json()
    assert len(ev["checklist"]) == 6 and ev["orcamento_kz"] is None
    assert maira.put(f"/eventos/{ev['id']}", {**{k: ev[k] for k in ("nome", "data_inicio", "data_fim", "local", "objectivo")},
                                              "orcamento_kz": "50000"}).status_code == 403
    url = f"/eventos/{ev['id']}"
    maira.put(f"{url}/produtos", [{"artigo_id": loja["unhas"]["id"], "quantidade_planeada": "10"}])
    v = maira.post("/vendas/venda-rapida", {"evento_id": ev["id"], "forma": "tpa",
                                            "linhas": [{"artigo_id": loja["unhas"]["id"], "quantidade": "4"}]}).json()
    assert v["estado"] == "entregue" and v["estado_pagamento"] == "pago" and v["cliente"]["nome"] == "Venda avulsa (sem registo)"
    assert _disp(diana, loja["unhas"]) == 16
    diana.put(f"{url}/produtos", [{"artigo_id": loja["unhas"]["id"], "quantidade_planeada": "10", "quantidade_levada": "10", "quantidade_devolvida": "5"}])
    det = maira.get(url).json()
    p = det["produtos"][0]
    assert p["quantidade_vendida"] == "4.000" and D(p["diferenca"]) == 1  # 10 - 4 - 5: uma unidade por explicar
    assert det["vendas"]["facturacao_kz"] == "20000.00" and det["vendas"]["meta_atingida_pct"] == "100.0"
    assert "rentabilidade" not in det
    assert maira.post(f"{url}/custos", {"descricao": "Inscrição", "valor_kz": "5000"}).status_code == 403
    luisa.post(f"{url}/custos", {"descricao": "Inscrição", "valor_kz": "5000"})
    rent = luisa.get(url).json()["rentabilidade"]
    assert rent["custo_produtos_vendidos_kz"] == "6000.00" and rent["resultado_kz"] == "9000.00"  # 20000 - 5000 - 4×1500
    t = det["checklist"][0]
    assert diana.post(f"{url}/checklist/{t['id']}/alternar").status_code == 403
    assert maira.post(f"{url}/checklist/{t['id']}/alternar").json()["checklist"][0]["feito"]
    assert len(diana.get("/eventos").json()) == 1


def test_dashboard_vendas(equipa, loja):
    luisa, maira, diana = equipa
    maira.post("/vendas/venda-rapida", {"cliente_id": loja["cliente"]["id"], "canal": "loja", "forma": "numerario",
                                        "linhas": [{"artigo_id": loja["sabao"]["id"], "quantidade": "2"}], "valor_pago_kz": "2000"})
    v = luisa.get("/dashboard/executivo").json()["vendas"]
    assert v["actual"]["facturacao_kz"] == "5000.00" and v["actual"]["recebido_kz"] == "2000.00"
    assert v["por_receber_kz"] == "3000.00" and v["top_produtos"][0]["nome"] == "Sabonete artesanal"
    assert diana.get("/dashboard/pessoal").json()["encomendas"] == []
    assert diana.get("/vendas/relatorios", params={"de": hoje().isoformat(), "ate": hoje().isoformat()}).status_code == 403
