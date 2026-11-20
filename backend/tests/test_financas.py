from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.tempo import hoje
from app.modules.notificacoes.models import Notificacao


def D(v):
    return Decimal(str(v))


def _cat(p, nome):
    return next(c for c in p.get("/financas/categorias").json() if c["nome"] == nome)


@pytest.fixture
def produto(equipa):
    """Produto com ficha técnica, custos e preço; uma venda entregue de 4 unidades (dados de teste)."""
    luisa, maira, diana = equipa
    mk = lambda **k: luisa.post("/stock/artigos", k).json()  # noqa: E731
    oleo = mk(codigo="MP", nome="Óleo", categoria="materia_prima", unidade="ml", stock_minimo="0", custo_unitario="2")
    frasco = mk(codigo="EMB", nome="Frasco", categoria="embalagem", unidade="un", stock_minimo="0", controla_lotes=False, custo_unitario="100")
    pa = mk(codigo="PA", nome="Óleo de unhas", categoria="produto_acabado", unidade="un", stock_minimo="0")
    f = luisa.post("/producao/fichas", {"codigo": "FT", "nome": "Óleo de unhas", "produto_id": pa["id"], "rendimento": "10", "tempo_producao_min": 60,
                                        "ingredientes": [{"artigo_id": oleo["id"], "quantidade": "300"}, {"artigo_id": frasco["id"], "quantidade": "10"}]}).json()
    luisa.post("/vendas/precos", {"artigo_id": pa["id"], "preco_kz": "2000"})
    luisa.post("/stock/movimentos/entrada", {"artigo_id": pa["id"], "quantidade": "10", "custo_unitario": "500", "lote_numero": "L1"})
    cli = maira.post("/vendas/clientes", {"nome": "Cliente F"}).json()
    e = maira.post("/vendas/encomendas", {"cliente_id": cli["id"], "canal": "loja", "linhas": [{"artigo_id": pa["id"], "quantidade": "4"}]}).json()
    for est in ("pronta", "entregue"):
        diana.post(f"/vendas/encomendas/{e['id']}/estado", {"estado": est})
    maira.post(f"/vendas/encomendas/{e['id']}/pagamentos", {"valor_kz": "8000", "forma": "tpa"})
    return {"pa": pa, "ficha": f, "encomenda": e}


def test_ficha_de_custos(equipa, produto):
    luisa, maira, _ = equipa
    p = luisa.get("/financas/custos-produtos").json()["produtos"][0]
    # por unidade: óleo 300×2/10 = 60; frasco 10×100/10 = 100; sem custo de mão-de-obra definido
    assert p["materias_primas_kz"] == "60.00" and p["embalagens_kz"] == "100.00" and p["mao_obra_kz"] is None and not p["completo"]
    luisa.put("/configuracao/custo_mao_obra_hora_kz", {"valor": 1000})
    luisa.put(f"/financas/custos-produtos/{produto['ficha']['id']}", {"outros_custos_unidade_kz": "40"})
    p = luisa.get("/financas/custos-produtos").json()["produtos"][0]
    # MO: 60 min × 1000 Kz/h ÷ 10 un. = 100; total 60+100+100+40 = 300; margem 2000−300 = 1700 (85%)
    assert p["mao_obra_kz"] == "100.00" and p["custo_total_kz"] == "300.00" and p["margem_bruta_kz"] == "1700.00" and p["margem_bruta_pct"] == "85.0"
    assert p["completo"] and p["alerta"] is None
    luisa.put("/configuracao/margem_minima_pct", {"valor": 90})
    assert "abaixo do mínimo" in luisa.get("/financas/custos-produtos").json()["produtos"][0]["alerta"]
    assert maira.get("/financas/custos-produtos").status_code == 403
    assert maira.put("/configuracao/custo_mao_obra_hora_kz", {"valor": 1}).status_code == 403
    assert all(c["chave"] != "custo_mao_obra_hora_kz" for c in maira.get("/configuracao").json())


def test_despesas_propostas_aprovacao_e_pagamento(equipa, db):
    luisa, maira, diana = equipa
    cat = _cat(diana, "Matérias-primas")
    r = diana.post("/financas/lancamentos", {"categoria_id": cat["id"], "descricao": "Manteiga de karité 5 kg", "valor_kz": "25000",
                                             "justificacao": "Stock abaixo do mínimo"})
    assert r.status_code == 201 and r.json()["estado"] == "proposta"
    lid = r.json()["id"]
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "despesa", Notificacao.utilizador_id == luisa.id)).first()
    assert diana.post("/financas/lancamentos", {"categoria_id": cat["id"], "descricao": "Já paga", "valor_kz": "1", "paga": True}).status_code == 403
    assert diana.post(f"/financas/lancamentos/{lid}/aprovar", {}).status_code == 403
    assert maira.get("/financas/lancamentos").json() == []  # só vê as suas
    assert len(diana.get("/financas/lancamentos").json()) == 1
    assert diana.get("/financas/resultados").status_code == 403
    assert luisa.post(f"/financas/lancamentos/{lid}/pagar", {"forma_pagamento": "transferencia"}).json()["codigo"] == "estado_invalido"
    assert luisa.post(f"/financas/lancamentos/{lid}/aprovar", {}).json()["estado"] == "aprovada"
    assert diana.put(f"/financas/lancamentos/{lid}", {"categoria_id": cat["id"], "descricao": "x y z", "valor_kz": "1"}).json()["codigo"] == "lancamento_fechado"
    cp = luisa.get("/financas/contas-a-pagar").json()
    assert cp["total_kz"] == "25000.00"
    assert luisa.post(f"/financas/lancamentos/{lid}/pagar", {"forma_pagamento": "transferencia"}).json()["estado"] == "paga"
    assert luisa.get("/financas/contas-a-pagar").json()["itens"] == []
    assert luisa.post(f"/financas/lancamentos/{lid}/anular", {}).json()["codigo"] == "motivo_obrigatorio"


def test_orcamento_excedido_vai_para_excepcoes(equipa, db):
    luisa, _, _ = equipa
    mk = _cat(luisa, "Marketing e publicidade")
    d = hoje()
    luisa.put("/financas/orcamento", {"ano": d.year, "mes": d.month, "valores": [{"categoria_id": mk["id"], "valor_kz": "10000"}]})
    r = luisa.post("/financas/lancamentos", {"categoria_id": mk["id"], "descricao": "Anúncios Instagram", "valor_kz": "12000"}).json()
    assert r["estado"] == "aprovada" and r["excede_orcamento"]["excesso_kz"] == "2000.00"
    orc = {o["categoria"]["nome"]: o for o in luisa.get("/financas/orcamento", params={"ano": d.year, "mes": d.month}).json()}
    assert orc["Marketing e publicidade"]["excedido"] and orc["Marketing e publicidade"]["utilizacao_pct"] == "120.0"
    exc = luisa.get("/excepcoes").json()["seccoes"]["financas"]
    assert exc["orcamento_excedido"][0]["categoria"] == "Marketing e publicidade"
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "orcamento")).first()


def test_despesas_fixas_idempotentes_e_vencidas(equipa, db):
    luisa, _, _ = equipa
    renda = _cat(luisa, "Renda")
    luisa.post("/financas/despesas-fixas", {"descricao": "Renda do atelier", "categoria_id": renda["id"], "valor_kz": "50000", "dia_vencimento": 5})
    d = hoje()
    assert luisa.post("/financas/despesas-fixas/gerar", params={"ano": d.year, "mes": d.month}).json()["criadas"] == 1
    assert luisa.post("/financas/despesas-fixas/gerar", params={"ano": d.year, "mes": d.month}).json()["criadas"] == 0
    db.execute(text("UPDATE lancamentos SET data_vencimento = CURRENT_DATE - 3"))
    db.commit()
    from app.modules.automacao.alertas import verificar_financas
    verificar_financas(db)
    db.commit()
    assert db.scalars(select(Notificacao).where(Notificacao.tipo == "conta_vencida")).first()
    assert len(luisa.get("/excepcoes").json()["seccoes"]["financas"]["contas_vencidas"]) == 1


def test_demonstracao_de_resultados(equipa, produto):
    luisa, maira, _ = equipa
    luisa.post("/financas/lancamentos", {"categoria_id": _cat(luisa, "Renda")["id"], "descricao": "Renda", "valor_kz": "3000"})
    luisa.post("/financas/lancamentos", {"categoria_id": _cat(luisa, "Matérias-primas")["id"], "descricao": "Compra de óleo", "valor_kz": "9999", "paga": True,
                                         "data_pagamento": hoje().isoformat(), "forma_pagamento": "transferencia"})
    luisa.post("/financas/lancamentos", {"categoria_id": _cat(luisa, "Equipamentos")["id"], "descricao": "Balança", "valor_kz": "15000"})
    luisa.post("/financas/lancamentos", {"categoria_id": _cat(luisa, "Outras receitas")["id"], "tipo": "receita", "descricao": "Workshop", "valor_kz": "1000"})
    # Proposta não aprovada não conta
    maira.post("/financas/lancamentos", {"categoria_id": _cat(maira, "Marketing e publicidade")["id"], "descricao": "Proposta", "valor_kz": "500"})
    r = luisa.get("/financas/resultados").json()["actual"]
    assert r["facturacao_liquida_kz"] == "8000.00"            # 4 × 2000
    assert r["custo_mercadorias_vendidas_kz"] == "2000.00"     # 4 × 500 (custo registado na saída)
    assert r["margem_bruta_kz"] == "6000.00" and r["margem_bruta_pct"] == "75.0"
    assert r["despesas_total_kz"] == "3000.00"                 # renda; compras de stock e investimentos ficam fora
    assert r["fora_do_resultado"] == {"compras_stock_kz": "9999.00", "investimentos_kz": "15000.00"}
    assert r["outras_receitas_kz"] == "1000.00" and r["resultado_kz"] == "4000.00" and r["margem_lucro_pct"] == "50.0"
    assert r["caixa"]["entradas_kz"] == "8000.00" and r["caixa"]["saidas_kz"] == "9999.00"
    dash = luisa.get("/dashboard/executivo").json()["financas"]
    assert dash["actual"]["resultado_kz"] == "4000.00" and dash["despesas_propostas"] == 1


def test_devolucao_repoe_stock_e_reduz_facturacao(equipa, produto):
    luisa, maira, diana = equipa
    e = produto["encomenda"]
    url = f"/vendas/encomendas/{e['id']}/devolucoes"
    assert diana.post(url, {"itens": [{"artigo_id": produto["pa"]["id"], "quantidade": "1"}], "motivo": "x y z"}).status_code == 403
    r = maira.post(url, {"itens": [{"artigo_id": produto["pa"]["id"], "quantidade": "1", "repor_stock": True}], "motivo": "Frasco com fuga",
                         "reembolso_kz": "2000", "forma_reembolso": "tpa"})
    assert r.status_code == 201, r.text
    det = r.json()
    assert det["devolucoes"][0]["valor_kz"] == "2000.00" and det["pago_kz"] == "6000.00"
    assert D(diana.get(f"/stock/artigos/{produto['pa']['id']}").json()["disponivel"]) == 7  # 10 − 4 + 1, de volta ao lote L1
    lotes = {l["numero"]: D(l["saldo"]) for l in diana.get("/stock/lotes", params={"artigo_id": produto["pa"]["id"]}).json()}
    assert lotes == {"L1": 7}
    assert maira.post(url, {"itens": [{"artigo_id": produto["pa"]["id"], "quantidade": "4"}], "motivo": "Demasiado"}).json()["codigo"] == "quantidade_excessiva"
    r = luisa.get("/financas/resultados").json()["actual"]
    assert r["devolucoes_kz"] == "2000.00" and r["facturacao_liquida_kz"] == "6000.00" and r["custo_mercadorias_vendidas_kz"] == "1500.00"


def test_procedimentos_ciclo_e_execucao(equipa):
    luisa, maira, diana = equipa
    corpo = {"codigo": "pop-stk-01", "titulo": "Contagem semanal de stock", "area": "stock", "objectivo": "Garantir stock fiável",
             "funcao_responsavel": "producao", "etapas": ["Imprimir a lista", "Contar", "Registar no sistema"], "checklist": ["Lista impressa", "Contagem registada"]}
    p = diana.post("/procedimentos", corpo).json()
    assert p["codigo"] == "POP-STK-01" and p["estado"] == "rascunho"
    assert diana.post(f"/procedimentos/{p['id']}/execucoes", {"feitos": [True, True]}).json()["codigo"] == "nao_aprovado"
    diana.post(f"/procedimentos/{p['id']}/submeter")
    assert diana.post(f"/procedimentos/{p['id']}/aprovar", {}).status_code == 403
    assert luisa.get("/excepcoes").json()["seccoes"]["procedimentos_aprovacao"][0]["codigo"] == "POP-STK-01"
    assert luisa.post(f"/procedimentos/{p['id']}/aprovar", {}).json()["estado"] == "aprovado"
    assert diana.put(f"/procedimentos/{p['id']}", corpo).json()["codigo"] == "procedimento_fechado"
    assert diana.post(f"/procedimentos/{p['id']}/execucoes", {"feitos": [True, False]}).json()["codigo"] == "observacao_obrigatoria"
    assert diana.post(f"/procedimentos/{p['id']}/execucoes", {"feitos": [True, True]}).json()["completa"]
    v2 = maira.post(f"/procedimentos/{p['id']}/nova-versao").json()
    assert v2["versao"] == 2 and v2["estado"] == "rascunho"
    luisa.post(f"/procedimentos/{v2['id']}/aprovar", {})
    assert luisa.get(f"/procedimentos/{p['id']}").json()["estado"] == "obsoleto"
    assert maira.get("/procedimentos/codigo/pop-stk-01").json()["versao"] == 2
    # Matriz de responsabilidades reconhece o POP aprovado
    a = luisa.post("/responsabilidades/actividades", {"nome": "Contagem", "area": "stock", "responsavel_id": diana.id, "frequencia": "semanal",
                                                      "dia_prazo": 0, "procedimento_ref": "POP-STK-01", "indicador": "Contagem registada"}).json()
    assert a["lacunas"] == []
    b = luisa.post("/responsabilidades/actividades", {"nome": "Outra", "area": "stock", "responsavel_id": diana.id, "frequencia": "semanal",
                                                      "dia_prazo": 0, "procedimento_ref": "POP-XXX", "indicador": "x"}).json()
    assert b["lacunas"] == ["Procedimento POP-XXX não existe ou não está aprovado"]
