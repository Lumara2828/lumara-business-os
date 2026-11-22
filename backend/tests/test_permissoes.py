from datetime import timedelta

import pytest

from app.core.permissions import MATRIZ, Funcao, P
from app.core.tempo import hoje

FINANCEIRAS = {P.FINANCAS_VER, P.FINANCAS_APROVAR_DESPESAS, P.PRECOS_ALTERAR, P.STOCK_VER_VALOR}


def test_matriz_confidencialidade():
    assert MATRIZ[Funcao.CEO] == frozenset(P)
    for f in (Funcao.MARKETING, Funcao.PRODUCAO):
        assert not FINANCEIRAS & MATRIZ[f]
    assert P.ESTRATEGIA_METAS not in MATRIZ[Funcao.PRODUCAO]
    assert P.DASHBOARD_EXECUTIVO not in MATRIZ[Funcao.PRODUCAO]


@pytest.mark.parametrize("url", ["/dashboard/executivo", "/excepcoes", "/auditoria", "/equipa/utilizadores",
                                 "/rotina/relatorio-semanal"])
def test_colaboradoras_sem_acesso_a_areas_de_gestao(equipa, url):
    luisa, maira, diana = equipa
    assert luisa.get(url).status_code == 200
    assert maira.get(url).status_code == 403
    assert diana.get(url).status_code == 403


def test_colaboradora_so_ve_as_suas_tarefas(equipa):
    luisa, maira, diana = equipa
    prazo = (hoje() + timedelta(days=3)).isoformat()
    t = luisa.post("/tarefas", {"titulo": "Tarefa da Diana", "responsavel_id": diana.id, "prazo": prazo}).json()
    assert maira.get(f"/tarefas/{t['id']}").status_code == 404
    assert maira.get("/tarefas").json() == []
    assert [x["id"] for x in diana.get("/tarefas").json()] == [t["id"]]
    assert len(luisa.get("/tarefas").json()) == 1


def test_colaboradora_nao_delega(equipa):
    _, maira, diana = equipa
    prazo = (hoje() + timedelta(days=3)).isoformat()
    # Melhoria nº 2: pedir a uma colega é permitido, mas fica pendente até ela aceitar (não é uma ordem).
    r = maira.post("/tarefas", {"titulo": "Para a Diana", "responsavel_id": diana.id, "prazo": prazo})
    assert r.status_code == 201 and r.json()["pedido_estado"] == "pendente"
    assert maira.patch(f"/tarefas/{r.json()['id']}", {"responsavel_id": maira.id}).status_code == 403
    r = maira.post("/tarefas", {"titulo": "Para mim", "prazo": prazo})
    assert r.status_code == 201 and r.json()["responsavel"]["id"] == maira.id


def test_colaboradora_nao_aprova_nem_gere_regras(equipa):
    _, maira, _ = equipa
    assert maira.get("/responsabilidades/decisoes").status_code == 200  # consulta permitida
    r = maira.post("/responsabilidades/decisoes", {"decisao": "x y z", "area": "geral", "nivel": "autonoma"})
    assert r.status_code == 403
    assert maira.put("/configuracao/meta_cumprimento_prazos", {"valor": 10}).status_code == 403
