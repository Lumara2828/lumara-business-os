from datetime import timedelta

from sqlalchemy import select, text

from app.core.tempo import hoje
from app.modules.notificacoes.models import Notificacao


def _prazo(d=3):
    return (hoje() + timedelta(days=d)).isoformat()


def _notifs(db, uid, tipo=None):
    q = select(Notificacao).where(Notificacao.utilizador_id == uid)
    if tipo:
        q = q.where(Notificacao.tipo == tipo)
    return db.scalars(q).all()


def test_criar_com_validacoes(equipa, db):
    luisa, maira, _ = equipa
    r = luisa.post("/tarefas", {"titulo": "Publicar post", "responsavel_id": maira.id, "prazo": _prazo(),
                                "prioridade": "alta", "descricao": "Post educativo"})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["codigo"] == "T-0001" and t["estado"] == "nao_iniciada" and t["criado_por"]["id"] == luisa.id
    assert len(_notifs(db, maira.id, "tarefa_atribuida")) == 1
    assert luisa.post("/tarefas", {"titulo": "x", "prazo": _prazo()}).status_code == 400
    assert luisa.post("/tarefas", {"titulo": "Sem prazo"}).status_code == 400
    assert luisa.post("/tarefas", {"titulo": "Passado", "prazo": _prazo(-1)}).json()["codigo"] == "prazo_invalido"
    r = luisa.post("/tarefas", {"titulo": "Datas", "prazo": _prazo(1), "data_inicio": _prazo(5)})
    assert r.status_code == 400


def test_fluxo_aprovacao(equipa, db):
    luisa, maira, _ = equipa
    t = luisa.post("/tarefas", {"titulo": "Vídeo de produto", "responsavel_id": maira.id, "prazo": _prazo(),
                                "requer_aprovacao": True}).json()
    url = f"/tarefas/{t['id']}"
    assert maira.post(f"{url}/estado", {"estado": "em_andamento"}).json()["estado"] == "em_andamento"
    r = maira.post(f"{url}/estado", {"estado": "concluida"})
    assert r.status_code == 400 and r.json()["codigo"] == "requer_aprovacao"
    r = maira.post(f"{url}/estado", {"estado": "aguardar_aprovacao", "comentario": "Pronto para revisão"})
    assert r.json()["estado"] == "aguardar_aprovacao"
    assert len(_notifs(db, luisa.id, "aprovacao_pendente")) == 1
    assert maira.post(f"{url}/aprovar", {}).status_code == 403
    assert luisa.post(f"{url}/rejeitar", {}).status_code == 400
    r = luisa.post(f"{url}/rejeitar", {"comentario": "Melhorar a iluminação"})
    assert r.json()["estado"] == "em_andamento"
    assert len(_notifs(db, maira.id, "tarefa_rejeitada")) == 1
    tipos = [c["tipo"] for c in maira.get(f"{url}/comentarios").json()]
    assert tipos == ["submissao", "rejeicao"]
    maira.post(f"{url}/estado", {"estado": "aguardar_aprovacao"})
    r = luisa.post(f"{url}/aprovar", {"comentario": "Excelente"})
    assert r.json()["estado"] == "concluida" and r.json()["aprovada_em"]
    # Tarefa aprovada não pode ser reaberta pela colaboradora
    assert maira.post(f"{url}/estado", {"estado": "em_andamento"}).status_code == 403
    hist = [h["accao"] for h in luisa.get(f"{url}/historico").json()]
    assert hist == ["criar", "mudar_estado", "mudar_estado", "rejeitar", "mudar_estado", "aprovar"]


def test_conclusao_directa_sem_aprovacao(equipa):
    luisa, _, diana = equipa
    t = luisa.post("/tarefas", {"titulo": "Etiquetar lote", "responsavel_id": diana.id, "prazo": _prazo()}).json()
    r = diana.post(f"/tarefas/{t['id']}/estado", {"estado": "concluida"})
    assert r.json()["estado"] == "concluida" and r.json()["concluida_no_prazo"] is True


def test_bloqueio_exige_motivo_e_alerta_ceo(equipa, db):
    luisa, _, diana = equipa
    t = luisa.post("/tarefas", {"titulo": "Comprar óleo", "responsavel_id": diana.id, "prazo": _prazo()}).json()
    assert diana.post(f"/tarefas/{t['id']}/estado", {"estado": "bloqueada"}).status_code == 400
    r = diana.post(f"/tarefas/{t['id']}/estado", {"estado": "bloqueada", "comentario": "Fornecedor sem stock"})
    assert r.json()["motivo_bloqueio"] == "Fornecedor sem stock"
    assert len(_notifs(db, luisa.id, "tarefa_bloqueada")) == 1
    r = diana.post(f"/tarefas/{t['id']}/estado", {"estado": "em_andamento"})
    assert r.json()["motivo_bloqueio"] is None


def test_edicao_e_concorrencia(equipa, db):
    luisa, maira, diana = equipa
    t = luisa.post("/tarefas", {"titulo": "Plano mensal", "responsavel_id": maira.id, "prazo": _prazo()}).json()
    assert maira.patch(f"/tarefas/{t['id']}", {"prazo": _prazo(10)}).status_code == 403
    r = luisa.patch(f"/tarefas/{t['id']}", {"prazo": _prazo(5), "versao": t["versao"]})
    assert r.status_code == 200 and r.json()["versao"] == t["versao"] + 1
    assert luisa.patch(f"/tarefas/{t['id']}", {"prazo": _prazo(6), "versao": t["versao"]}).status_code == 409
    assert luisa.patch(f"/tarefas/{t['id']}", {"titulo": None}).status_code == 400
    r = luisa.patch(f"/tarefas/{t['id']}", {"responsavel_id": diana.id})
    assert r.json()["responsavel"]["id"] == diana.id
    assert len(_notifs(db, diana.id, "tarefa_atribuida")) == 1
    assert maira.get(f"/tarefas/{t['id']}").status_code == 404


def test_filtros_e_atraso(equipa, db):
    luisa, maira, _ = equipa
    t = luisa.post("/tarefas", {"titulo": "Atrasada", "responsavel_id": maira.id, "prazo": _prazo(1)}).json()
    db.execute(text("UPDATE tarefas SET prazo = prazo - 4 WHERE id = :i"), {"i": t["id"]})
    db.commit()
    luisa.post("/tarefas", {"titulo": "Normal", "responsavel_id": maira.id, "prazo": _prazo(1), "prioridade": "critica"})
    r = luisa.get("/tarefas", params={"atrasadas": True}).json()
    assert [x["titulo"] for x in r] == ["Atrasada"] and r[0]["dias_atraso"] == 3
    assert len(luisa.get("/tarefas", params={"prioridade": "critica"}).json()) == 1
    assert len(luisa.get("/tarefas", params={"pesquisa": "norm"}).json()) == 1
    assert len(luisa.get("/tarefas", params={"estado": ["nao_iniciada", "em_andamento"]}).json()) == 2


def test_anexos(equipa):
    luisa, maira, diana = equipa
    t = luisa.post("/tarefas", {"titulo": "Fotos", "responsavel_id": maira.id, "prazo": _prazo()}).json()
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = maira.post(f"/tarefas/{t['id']}/anexos", files={"ficheiro": ("foto.png", png, "image/png")}, data={"descricao": "Capa"})
    assert r.status_code == 201, r.text
    a = r.json()
    d = luisa.get(f"/tarefas/{t['id']}/anexos/{a['id']}")
    assert d.content == png
    r = maira.post(f"/tarefas/{t['id']}/anexos", files={"ficheiro": ("x.exe", b"MZ", "application/x-msdownload")})
    assert r.status_code == 400
    assert diana.get(f"/tarefas/{t['id']}/anexos").status_code == 404
    assert maira.get(f"/tarefas/{t['id']}").json()["n_anexos"] == 1
    assert maira.delete(f"/tarefas/{t['id']}/anexos/{a['id']}").status_code == 204


def test_eliminar_so_ceo_e_fica_registado(equipa, db):
    luisa, maira, _ = equipa
    t = maira.post("/tarefas", {"titulo": "Minha", "prazo": _prazo()}).json()
    assert maira.delete(f"/tarefas/{t['id']}").status_code == 403
    assert luisa.delete(f"/tarefas/{t['id']}").status_code == 204
    accoes = [r["accao"] for r in luisa.get("/auditoria", params={"entidade": "tarefa"}).json()["itens"]]
    assert "eliminar" in accoes


def test_registo_de_actividade_e_imutavel(equipa, db):
    import pytest
    from sqlalchemy.exc import DBAPIError
    luisa, _, _ = equipa
    luisa.post("/tarefas", {"titulo": "Qualquer", "prazo": _prazo()})
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE registos_actividade SET resumo = 'adulterado'"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM registos_actividade"))
    db.rollback()
