"""Melhorias pedidas durante a validação (lista «Melhorias» do manual)."""
from datetime import timedelta

from app.core.formato import fkz, fpct
from app.core.tempo import hoje


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
