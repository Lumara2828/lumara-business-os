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
