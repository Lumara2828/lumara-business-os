"""Melhorias pedidas durante a validação (lista «Melhorias» do manual)."""
from datetime import timedelta

from app.core.formato import fkz, fpct
from app.core.tempo import hoje
from tests.test_stock_producao import catalogo  # noqa: F401  (fixture)


def test_formato_numeros():
    # nº 5: Kz com ponto nos milhares e vírgula decimal; percentagens com vírgula.
    assert fkz("36000") == "36.000,00 Kz"
    assert fkz("9000.5") == "9.000,50 Kz"
    assert fkz(-1234567) == "-1.234.567,00 Kz"
    assert fpct(54.5) == "54,5%" and fpct("100.0") == "100%" and fpct(None) == "—"


def test_painel_lista_tarefas_a_aprovar(equipa):
    # nº 18: a CEO vê cada tarefa a aguardar aprovação, pelo nome, no painel executivo.
    luisa, maira, _ = equipa
    t = luisa.post("/tarefas", {"titulo": "Teste da tarefa", "responsavel_id": maira.id, "requer_aprovacao": True,
                                "prazo": (hoje() + timedelta(days=3)).isoformat()}).json()
    assert luisa.get("/dashboard/executivo").json()["a_aprovar"] == []
    r = maira.post(f"/tarefas/{t['id']}/estado", {"estado": "aguardar_aprovacao", "versao": t["versao"]})
    assert r.status_code == 200, r.text
    lista = luisa.get("/dashboard/executivo").json()["a_aprovar"]
    assert [x["codigo"] for x in lista] == [t["codigo"]] and lista[0]["responsavel"]["nome"] == "Maira"
    assert lista[0]["submetida_em"] and lista[0]["permissoes"]["aprovar"] is True


# --- nº 6: instruções passo a passo na tarefa --------------------------------------

def _pop(diana, luisa, **k):
    corpo = {"codigo": "POP-PRD-01", "titulo": "Produção de óleo corporal", "area": "producao", "objectivo": "Lote com qualidade constante",
             "funcao_responsavel": "producao", "etapas": ["Pesar os ingredientes", "Misturar", "Envasar"],
             "checklist": ["Bancada higienizada", "Pesagens conferidas"], "materiais": "Balança, funil",
             "seguranca_higiene": "Usar luvas e touca.", "checklist_obrigatoria": True, **k}
    p = diana.post("/procedimentos", corpo)
    assert p.status_code == 201, p.text
    p = p.json()
    diana.post(f"/procedimentos/{p['id']}/submeter")
    assert luisa.post(f"/procedimentos/{p['id']}/aprovar", {}).json()["estado"] == "aprovado"
    return p


def test_instrucoes_na_tarefa_de_producao(equipa, catalogo):
    from tests.test_stock_producao import _entrada
    luisa, maira, diana = equipa
    regra = _pop(diana, luisa, codigo="POP-HIG-01", titulo="Higiene da produção", area="qualidade", regra_geral=True,
                 checklist_obrigatoria=False, seguranca_higiene="Lavar as mãos. Cabelo apanhado.")
    pop = _pop(diana, luisa)
    _entrada(luisa, catalogo["oleo"], 400, lote_numero="B-curto", validade=(hoje() + timedelta(days=20)).isoformat())
    _entrada(luisa, catalogo["oleo"], 1000, lote_numero="A-longo", validade=(hoje() + timedelta(days=300)).isoformat())
    _entrada(luisa, catalogo["frasco"], 100)
    o = diana.post("/producao/ordens", {"ficha_id": catalogo["ficha"]["id"], "quantidade_planeada": "20", "data_inicio": hoje().isoformat(),
                                        "data_prevista": (hoje() + timedelta(days=2)).isoformat()}).json()
    tid = o["tarefa_id"]
    assert diana.patch(f"/tarefas/{tid}", {"procedimento_codigo": "pop-prd-01"}).status_code in (200, 403)
    luisa.patch(f"/tarefas/{tid}", {"procedimento_codigo": "pop-prd-01"})
    assert luisa.patch(f"/tarefas/{tid}", {"procedimento_codigo": "POP-NAO-EXISTE"}).json()["codigo"] == "procedimento_invalido"

    i = diana.get(f"/tarefas/{tid}/instrucoes").json()
    assert i["procedimento"]["codigo"] == "POP-PRD-01" and i["procedimento"]["etapas"][0] == "Pesar os ingredientes"
    assert [s["texto"] for s in i["seguranca"]] == ["Usar luvas e touca.", "Lavar as mãos. Cabelo apanhado."]
    assert i["exige_leitura"] and i["leitura"] is None and i["exige_checklist"]
    prod = i["producao"]
    assert prod["quantidade"] == "20.000" and not prod["faltam_materiais"]
    oleo = next(x for x in prod["ingredientes"] if x["artigo"] == "Óleo de coco")
    # 20 un. = 2 receitas de 10 → 600 ml, primeiro o lote que expira primeiro.
    assert oleo["quantidade"] == "600.000" and [(l["lote"], l["usar"]) for l in oleo["lotes"]] == [("B-curto", "400.000"), ("A-longo", "200.000")]
    assert "custo" not in str(prod).lower()

    # Sem confirmar a leitura das regras não se começa (nem pela tarefa nem pela ordem).
    assert diana.post(f"/tarefas/{tid}/estado", {"estado": "em_andamento"}).json()["codigo"] == "seguranca_por_confirmar"
    assert diana.post(f"/producao/ordens/{o['id']}/iniciar").json()["codigo"] == "seguranca_por_confirmar"
    assert maira.post(f"/tarefas/{tid}/confirmar-seguranca").status_code in (403, 404)
    assert diana.post(f"/tarefas/{tid}/confirmar-seguranca").json()["seguranca_confirmada_em"]
    assert diana.post(f"/producao/ordens/{o['id']}/iniciar").json()["estado"] == "em_curso"

    # Checklist obrigatória: concluir a ordem não fecha a tarefa enquanto a checklist não estiver completa.
    assert diana.post(f"/producao/ordens/{o['id']}/concluir", {"quantidade_produzida": "20"}).status_code == 200
    t = diana.get(f"/tarefas/{tid}").json()
    assert t["estado"] == "em_andamento"
    assert diana.post(f"/tarefas/{tid}/estado", {"estado": "concluida"}).json()["codigo"] == "checklist_obrigatoria"
    diana.post(f"/procedimentos/{pop['id']}/execucoes", {"feitos": [True, False], "observacoes": "Faltou papel", "tarefa_id": tid})
    assert diana.post(f"/tarefas/{tid}/estado", {"estado": "concluida"}).json()["codigo"] == "checklist_obrigatoria"
    diana.post(f"/procedimentos/{pop['id']}/execucoes", {"feitos": [True, True], "tarefa_id": tid})
    assert diana.get(f"/tarefas/{tid}/instrucoes").json()["execucao"]["completa"]
    assert diana.post(f"/tarefas/{tid}/estado", {"estado": "concluida"}).json()["estado"] == "concluida"


def test_tarefa_sem_procedimento_nao_exige_nada(equipa):
    luisa, maira, _ = equipa
    t = luisa.post("/tarefas", {"titulo": "Publicar post", "responsavel_id": maira.id, "prazo": (hoje() + timedelta(days=2)).isoformat()}).json()
    i = maira.get(f"/tarefas/{t['id']}/instrucoes").json()
    assert i["procedimento"] is None and i["seguranca"] == [] and not i["exige_leitura"] and i["producao"] is None
    assert maira.post(f"/tarefas/{t['id']}/estado", {"estado": "concluida"}).json()["estado"] == "concluida"


# --- nº 1: ausências e substituições --------------------------------------------

def test_ausencia_pedida_aprovada_transfere_e_devolve(equipa, db, monkeypatch):
    from app.modules.ausencias import service as aus
    luisa, maira, diana = equipa
    d = hoje()
    em = lambda n: (d + timedelta(days=n)).isoformat()  # noqa: E731
    t1 = luisa.post("/tarefas", {"titulo": "Contar frascos", "responsavel_id": diana.id, "prazo": em(1)}).json()
    t2 = luisa.post("/tarefas", {"titulo": "Encomendar rótulos", "responsavel_id": diana.id, "prazo": em(20)}).json()

    # A Diana pede; nada muda até a CEO aprovar.
    a = diana.post("/ausencias", {"inicio": em(0), "fim": em(3), "motivo": "doenca", "substituta_id": maira.id,
                                  "herdar_permissoes": True}).json()
    assert a["estado"] == "pedida" and a["herdar_permissoes"] is False  # só a CEO decide isso
    assert diana.get(f"/tarefas/{t1['id']}").json()["responsavel"]["id"] == diana.id
    assert diana.post(f"/ausencias/{a['id']}/aprovar", {}).status_code == 403
    assert maira.post("/stock/movimentos/entrada", {"artigo_id": "00000000-0000-0000-0000-000000000000", "quantidade": "1"}).status_code == 403

    r = luisa.post(f"/ausencias/{a['id']}/aprovar", {"herdar_permissoes": True}).json()
    assert r["estado"] == "aprovada" and r["em_curso"]
    # Tarefa com prazo dentro da ausência passa para a Maira; a de prazo depois do regresso fica.
    assert maira.get(f"/tarefas/{t1['id']}").json()["responsavel"]["id"] == maira.id
    assert luisa.get(f"/tarefas/{t2['id']}").json()["responsavel"]["id"] == diana.id
    # Permissões temporárias da Produção, sem as financeiras.
    perfil = maira.get("/auth/me").json()["permissoes"]
    assert "stock.movimentar" in perfil and "producao.ordens" in perfil and "financas.ver" not in perfil
    # Tarefas novas para a ausente vão para a substituta; notificações são copiadas.
    t3 = luisa.post("/tarefas", {"titulo": "Limpar bancada", "responsavel_id": diana.id, "prazo": em(2)}).json()
    assert t3["responsavel"]["id"] == maira.id
    from app.modules.notificacoes.service import notificar
    notificar(db, diana.id, "teste", "Aviso para a Diana")
    db.commit()
    assert any(n["titulo"] == "[Diana] Aviso para a Diana" for n in maira.get("/notificacoes").json()["itens"])

    # Regresso: a Maira concluiu uma; a outra volta à Diana. As permissões extra acabam.
    maira.post(f"/tarefas/{t3['id']}/estado", {"estado": "concluida"})
    monkeypatch.setattr(aus, "hoje", lambda: d + timedelta(days=4))
    assert aus.processar(db)["tarefas_devolvidas"] == 1
    assert luisa.get(f"/tarefas/{t1['id']}").json()["responsavel"]["id"] == diana.id
    assert luisa.get(f"/tarefas/{t3['id']}").json()["responsavel"]["id"] == maira.id
    assert aus.processar(db)["tarefas_devolvidas"] == 0  # idempotente


def test_ausencia_regras(equipa):
    luisa, maira, diana = equipa
    d = hoje()
    em = lambda n: (d + timedelta(days=n)).isoformat()  # noqa: E731
    assert maira.post("/ausencias", {"utilizador_id": diana.id, "inicio": em(1), "fim": em(2), "motivo": "ferias"}).status_code == 403
    assert maira.post("/ausencias", {"inicio": em(-3), "fim": em(2), "motivo": "ferias"}).json()["codigo"] == "data_invalida"
    assert maira.post("/ausencias", {"inicio": em(3), "fim": em(1), "motivo": "ferias"}).status_code == 400
    a = maira.post("/ausencias", {"inicio": em(5), "fim": em(9), "motivo": "ferias"}).json()
    assert maira.post("/ausencias", {"inicio": em(8), "fim": em(12), "motivo": "ferias"}).json()["codigo"] == "sobreposicao"
    assert luisa.post(f"/ausencias/{a['id']}/rejeitar", {}).json()["codigo"] == "motivo_obrigatorio"
    assert luisa.post(f"/ausencias/{a['id']}/rejeitar", {"comentario": "Semana de feira"}).json()["estado"] == "rejeitada"
    # CEO regista directamente (já aprovada); a CEO ausente não transfere permissões.
    c = luisa.post("/ausencias", {"inicio": em(0), "fim": em(1), "motivo": "formacao", "substituta_id": maira.id,
                                  "herdar_permissoes": True}).json()
    assert c["estado"] == "aprovada"
    assert "financas.ver" not in maira.get("/auth/me").json()["permissoes"]
    assert "tarefas.aprovar" not in maira.get("/auth/me").json()["permissoes"]
    # Regresso antecipado
    assert luisa.post(f"/ausencias/{c['id']}/cancelar").json()["estado"] == "cancelada"
    lst = diana.get("/ausencias").json()
    assert lst["itens"] == [] and lst["ausentes_hoje"] == []


# --- nº 20: a minha função --------------------------------------------------------

def test_a_minha_funcao(equipa):
    luisa, maira, diana = equipa
    p = diana.get("/funcoes/minha").json()
    assert p["pessoa"]["funcao_rotulo"] == "Produção" and p["descricao"] is None
    assert "Registar entradas, saídas, perdas e inventários" in p["sistema"]["pode"]
    assert "Ver finanças, custos e margens" in p["sistema"]["nao_pode"]
    corpo = {"titulo": "Produção e stock", "missao": "Produzir as bases com qualidade.", "responsabilidades": ["Produzir", " "],
             "decide_sozinha": ["Ordem do dia"], "decide_e_informa": [], "precisa_aprovacao": ["Compras"], "indicadores": []}
    assert diana.put(f"/funcoes/{diana.id}", corpo).status_code == 403
    assert maira.get(f"/funcoes/{diana.id}").status_code == 403
    r = luisa.put(f"/funcoes/{diana.id}", corpo).json()
    assert r["descricao"]["estado"] == "rascunho" and r["descricao"]["responsabilidades"] == ["Produzir"]
    assert diana.get("/funcoes/minha").json()["descricao_em_preparacao"] is True  # rascunho não aparece à pessoa
    luisa.post(f"/funcoes/{diana.id}/aprovar")
    assert diana.get("/funcoes/minha").json()["descricao"]["missao"] == "Produzir as bases com qualidade."
    assert {x["nome"]: x["estado"] for x in luisa.get("/funcoes").json()}["Diana"] == "aprovada"


# --- nº 19: agenda de reuniões -----------------------------------------------------

def test_agenda_de_reunioes(equipa, db, monkeypatch):
    luisa, maira, diana = equipa
    d = hoje()
    em = lambda n: (d + timedelta(days=n)).isoformat()  # noqa: E731
    base = {"titulo": "Planeamento semanal", "tipo": "equipa", "data": em(0), "hora": "09:00", "participantes": [maira.id, diana.id]}
    assert maira.post("/reunioes", base).status_code == 403  # só a CEO marca reuniões de equipa
    r = luisa.post("/reunioes", {**base, "semanal_ate": em(21), "local": "Atelier"}).json()
    assert r["criadas"] == 4 and r["semanal"] and {p["nome"] for p in r["participantes"]} == {"Luísa", "Maira", "Diana"}
    assert len(diana.get("/reunioes").json()) == 4 and diana.get("/reunioes/proximas").json()[0]["titulo"] == "Planeamento semanal"
    # A Maira marca uma reunião com um fornecedor só para si; a Diana não a vê.
    f = maira.post("/reunioes", {"titulo": "Fornecedor de frascos", "tipo": "fornecedor", "data": em(2), "hora": "15:30",
                                 "externos": "Vidros Luanda"}).json()
    assert all(x["id"] != f["id"] for x in diana.get("/reunioes").json())
    assert diana.get(f"/reunioes/{f['id']}").status_code == 404
    assert diana.put(f"/reunioes/{r['id']}", {**base, "hora": "10:00"}).status_code == 403
    # Lembretes no dia (uma vez por pessoa)
    from app.modules.agenda.router import lembretes
    assert lembretes(db)["lembretes"] == 3
    lembretes(db)
    assert sum(1 for n in diana.get("/notificacoes").json()["itens"] if n["titulo"].startswith("Hoje às 09:00")) == 1
    # Acta: decisões com responsável e prazo viram tarefas; sem responsável ficam só registadas.
    assert diana.post(f"/reunioes/{r['id']}/acta", {"acta": "Revimos a semana.", "decisoes": [
        {"texto": "Comprar frascos", "responsavel_id": maira.id, "prazo": em(3)}]}).status_code == 403
    a = luisa.post(f"/reunioes/{r['id']}/acta", {"acta": "Revimos a semana.", "decisoes": [
        {"texto": "Encomendar frascos âmbar", "responsavel_id": diana.id, "prazo": em(3)},
        {"texto": "Pensar numa campanha de Natal"}]}).json()
    assert a["estado"] == "realizada" and a["decisoes"][0]["tarefa"]["responsavel"] == "Diana" and a["decisoes"][1]["tarefa"] is None
    assert any(t["titulo"] == "Encomendar frascos âmbar" for t in diana.get("/tarefas").json())
    # Cancelar o resto da série
    seguinte = sorted(diana.get("/reunioes").json(), key=lambda x: x["data"])[1]
    c = luisa.post(f"/reunioes/{seguinte['id']}/cancelar", {"motivo": "Feira", "toda_a_serie": True}).json()
    assert c["estado"] == "cancelada"
    assert sum(1 for x in diana.get("/reunioes").json() if x["estado"] == "cancelada") == 3
