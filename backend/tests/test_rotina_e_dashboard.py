from datetime import timedelta

from sqlalchemy import select, text

from app.core.tempo import hoje, inicio_semana
from app.modules.automacao.alertas import verificar
from app.modules.notificacoes.models import Notificacao


def _prazo(d):
    return (hoje() + timedelta(days=d)).isoformat()


def _atrasar(db, tid, dias):
    db.execute(text("UPDATE tarefas SET prazo = CURRENT_DATE - :d WHERE id = :i"), {"d": dias, "i": tid})
    db.commit()


def test_alertas_escalonam_para_ceo_so_apos_limite(equipa, db):
    luisa, maira, _ = equipa
    a = luisa.post("/tarefas", {"titulo": "Um dia", "responsavel_id": maira.id, "prazo": _prazo(1)}).json()
    b = luisa.post("/tarefas", {"titulo": "Cinco dias", "responsavel_id": maira.id, "prazo": _prazo(1)}).json()
    _atrasar(db, a["id"], 1)
    _atrasar(db, b["id"], 5)
    verificar(db)
    verificar(db)  # idempotente
    para_maira = db.scalars(select(Notificacao).where(Notificacao.utilizador_id == maira.id,
                                                      Notificacao.tipo == "tarefa_atrasada")).all()
    para_ceo = db.scalars(select(Notificacao).where(Notificacao.utilizador_id == luisa.id,
                                                    Notificacao.tipo == "tarefa_atrasada")).all()
    assert len(para_maira) == 2
    assert len(para_ceo) == 1 and "Cinco dias" in para_ceo[0].titulo


def test_notificacoes_marcar_lidas(equipa):
    luisa, maira, _ = equipa
    luisa.post("/tarefas", {"titulo": "Nova", "responsavel_id": maira.id, "prazo": _prazo(2)})
    r = maira.get("/notificacoes").json()
    assert r["nao_lidas"] == 1
    assert maira.post(f"/notificacoes/{r['itens'][0]['id']}/lida").status_code == 204
    assert maira.get("/notificacoes").json()["nao_lidas"] == 0
    assert luisa.post(f"/notificacoes/{r['itens'][0]['id']}/lida").status_code == 404


def test_gerar_tarefas_recorrentes_idempotente(equipa):
    luisa, maira, diana = equipa
    r = luisa.post("/responsabilidades/actividades", {
        "nome": "Publicar conteúdos", "area": "marketing", "responsavel_id": maira.id, "frequencia": "semanal",
        "dia_prazo": 4, "indicador": "Publicações feitas/planeadas"})
    assert r.status_code == 201 and r.json()["lacunas"] == ["Sem procedimento documentado"]
    luisa.post("/responsabilidades/actividades", {
        "nome": "Atender mensagens", "area": "marketing", "responsavel_id": maira.id, "frequencia": "diaria", "dia_prazo": 0})
    assert luisa.post("/responsabilidades/actividades", {
        "nome": "Errada", "area": "geral", "responsavel_id": diana.id, "frequencia": "semanal", "dia_prazo": 9}).status_code == 400
    proxima = (inicio_semana(hoje()) + timedelta(days=7)).isoformat()
    r = luisa.post("/responsabilidades/gerar-tarefas-semana", {"semana_inicio": proxima}).json()
    assert r["criadas"] == 6
    r = luisa.post("/responsabilidades/gerar-tarefas-semana", {"semana_inicio": proxima}).json()
    assert r["criadas"] == 0 and r["ja_existentes"] == 6
    assert len(maira.get("/tarefas").json()) == 6
    assert maira.post("/responsabilidades/gerar-tarefas-semana", {"semana_inicio": proxima}).status_code == 403


def test_relatorio_semanal_e_fecho(equipa, db):
    luisa, maira, diana = equipa
    t1 = luisa.post("/tarefas", {"titulo": "Feita", "responsavel_id": maira.id, "prazo": _prazo(0)}).json()
    t2 = luisa.post("/tarefas", {"titulo": "Atrasada", "responsavel_id": diana.id, "prazo": _prazo(0)}).json()
    maira.post(f"/tarefas/{t1['id']}/estado", {"estado": "concluida"})
    _atrasar(db, t2["id"], 1)
    r = luisa.get("/rotina/relatorio-semanal").json()
    calc = r["calculado"]
    assert r["guardado"] is None
    assert any(x["titulo"] == "Feita" for x in calc["concluidas"])
    assert any(x["titulo"] == "Atrasada" for x in calc["em_atraso"])
    pessoas = {p["nome"]: p for p in calc["por_pessoa"]}
    assert pessoas["Maira"]["concluidas_semana"] == 1 and pessoas["Diana"]["em_atraso_total"] == 1
    semana = calc["semana_inicio"]
    assert luisa.post("/rotina/relatorio-semanal/fechar", {"semana_inicio": semana, "notas_ceo": "Ok"}).status_code == 201
    assert luisa.post("/rotina/relatorio-semanal/fechar", {"semana_inicio": semana}).status_code == 409
    assert len(luisa.get("/rotina/relatorios").json()) == 1
    assert luisa.get("/rotina/relatorio-semanal").json()["guardado"]["notas_ceo"] == "Ok"


def test_excepcoes_e_dashboard(equipa, db):
    luisa, maira, diana = equipa
    t = luisa.post("/tarefas", {"titulo": "Aprovar", "responsavel_id": maira.id, "prazo": _prazo(2), "requer_aprovacao": True}).json()
    maira.post(f"/tarefas/{t['id']}/estado", {"estado": "aguardar_aprovacao"})
    b = luisa.post("/tarefas", {"titulo": "Bloq", "responsavel_id": diana.id, "prazo": _prazo(2)}).json()
    diana.post(f"/tarefas/{b['id']}/estado", {"estado": "bloqueada", "comentario": "Falta material"})
    r = diana.post("/ocorrencias", {"tipo": "necessidade_material", "gravidade": "alta", "titulo": "Manteiga de karité",
                                    "descricao": "Stock para 2 dias"})
    assert r.status_code == 201
    exc = luisa.get("/excepcoes").json()["seccoes"]
    assert [x["titulo"] for x in exc["aprovacoes"]] == ["Aprovar"]
    assert [x["titulo"] for x in exc["bloqueadas"]] == ["Bloq"]
    assert [x["titulo"] for x in exc["rupturas_stock"]] == ["Manteiga de karité"]
    dash = luisa.get("/dashboard/executivo", params={"tipo_periodo": "trimestre"}).json()
    assert dash["estado_actual"]["aguardar_aprovacao"] == 1 and dash["estado_actual"]["bloqueadas"] == 1
    assert len(dash["serie_semanal"]) == 8
    resumo = dash["resumo"]
    assert any("aprovação" in x for x in resumo["intervencao_ceo"])
    assert any("Bloq" in x for x in resumo["intervencao_ceo"])
    assert resumo["prioridades"][0].startswith("T-0002")  # bloqueada primeiro
    pessoal = maira.get("/dashboard/pessoal").json()
    assert len(pessoal["aguardar_aprovacao"]) == 1
    # Ocorrência resolvida pela CEO exige descrição
    oid = r.json()["id"]
    assert luisa.post(f"/ocorrencias/{oid}/tratamento", {"estado": "resolvida"}).status_code == 400
    assert luisa.post(f"/ocorrencias/{oid}/tratamento", {"estado": "resolvida", "resolucao": "Comprado"}).status_code == 200
    assert maira.get("/ocorrencias").json() == []


def test_configuracao_com_limites(equipa):
    luisa, _, _ = equipa
    assert luisa.put("/configuracao/meta_cumprimento_prazos", {"valor": 150}).status_code == 400
    assert luisa.put("/configuracao/meta_cumprimento_prazos", {"valor": 90}).status_code == 200
    vals = {c["chave"]: c["valor"] for c in luisa.get("/configuracao").json()}
    assert vals["meta_cumprimento_prazos"] == 90
