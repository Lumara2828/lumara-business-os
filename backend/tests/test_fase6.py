"""Fase 6: assistente de gestão, relatório mensal e automações internas."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.core.errors import ErroNegocio
from app.core.tempo import FUSO, hoje
from app.main import app
from app.modules.automacao import agendador
from app.modules.ia.fornecedores import RespostaConversa, get_fornecedor
from app.modules.marketing.models import InteracaoIA
from app.modules.notificacoes.models import Notificacao


def _ids(p) -> set[str]:
    r = p.get("/assistente/consultas")
    assert r.status_code == 200, r.text
    return {c["id"] for c in r.json()["consultas"]}


def test_consultas_respeitam_a_funcao(equipa):
    luisa, maira, diana = equipa
    todas, mk, prod = _ids(luisa), _ids(maira), _ids(diana)
    assert {"resultado_mes", "despesas_por_aprovar", "desempenho_equipa", "o_que_produzir", "clientes_inactivos"} <= todas
    # Marketing: vendas e conteúdos, nunca finanças nem desempenho da equipa.
    assert {"conteudos_semana", "clientes_inactivos", "por_receber"} <= mk
    assert not mk & {"resultado_mes", "despesas_por_aprovar", "desempenho_equipa"}
    # Produção: produção, stock e encomendas a preparar; sem clientes, cobranças, marketing ou finanças.
    assert {"o_que_produzir", "stock_baixo", "encomendas_pendentes"} <= prod
    assert not prod & {"clientes_inactivos", "por_receber", "conteudos_semana", "resultado_mes", "vendas_mes"}
    # O acesso directo também é bloqueado.
    assert diana.get("/assistente/consultas/resultado_mes").status_code == 403
    assert maira.get("/assistente/consultas/despesas_por_aprovar").status_code == 403
    assert luisa.get("/assistente/consultas/nao_existe").status_code == 404


def test_tarefas_atrasadas_so_mostra_o_que_a_pessoa_ve(equipa, db):
    luisa, maira, diana = equipa
    t = luisa.post("/tarefas", {"titulo": "Contar frascos", "responsavel_id": diana.id,
                                "prazo": (hoje() + timedelta(days=2)).isoformat()}).json()
    db.execute(text("UPDATE tarefas SET prazo = :p WHERE id = :i"), {"p": hoje() - timedelta(days=3), "i": t["id"]})
    db.commit()
    r = diana.get("/assistente/consultas/tarefas_atrasadas").json()["resultado"]
    assert r["total_linhas"] == 1 and r["linhas"][0][0] == "T-0001" and r["linhas"][0][4] == 3
    assert luisa.get("/assistente/consultas/tarefas_atrasadas").json()["resultado"]["total_linhas"] == 1
    assert maira.get("/assistente/consultas/tarefas_atrasadas").json()["resultado"]["total_linhas"] == 0


def test_o_que_produzir(equipa):
    _, _, diana = equipa
    mk = lambda **k: diana.post("/stock/artigos", k).json()  # noqa: E731
    mk(codigo="PA-SAB", nome="Sabonete de karité", categoria="produto_acabado", unidade="un", stock_minimo="12")
    mk(codigo="PA-OK", nome="Produto sem mínimo", categoria="produto_acabado", unidade="un", stock_minimo="0")
    r = diana.get("/assistente/consultas/o_que_produzir").json()["resultado"]
    assert r["total_linhas"] == 1
    linha = r["linhas"][0]
    assert linha[0] == "Sabonete de karité" and linha[5] == "12 un" and linha[6] == "sem ficha técnica activa"


def test_perguntar_sem_ia_usa_as_consultas(equipa):
    luisa, _, diana = equipa
    r = diana.post("/assistente/perguntar", {"pergunta": "Que tarefas estão atrasadas?"}).json()
    assert r["modo"] == "consultas" and r["consultas"][0]["id"] == "tarefas_atrasadas"
    # Palavras de finanças não abrem consultas que a função não tem.
    r = diana.post("/assistente/perguntar", {"pergunta": "Qual foi o lucro e a margem?"}).json()
    assert all(c["id"] != "resultado_mes" for c in r["consultas"])
    r = luisa.post("/assistente/perguntar", {"pergunta": "Qual foi o lucro e a margem?"}).json()
    assert r["consultas"][0]["id"] == "resultado_mes"


class ConversaFalsa:
    """Só para testes: pede as ferramentas indicadas e devolve um texto fixo."""
    nome, modelo = "teste", "modelo-teste"

    def __init__(self, pedir: list[str]):
        self.pedir, self.oferecidas, self.erros = pedir, [], []

    def configurado(self):
        return True

    def conversar(self, sistema, pergunta, ferramentas, executar, max_voltas=6):
        self.oferecidas = [f["name"] for f in ferramentas]
        for nome in self.pedir:
            try:
                executar(nome, {})
            except ErroNegocio as e:
                self.erros.append(e.detail["codigo"])
        return RespostaConversa("Há 0 tarefas em atraso.", self.modelo, list(self.pedir), 900, 120)


@pytest.fixture
def conversa():
    holder = {}

    def usar(pedir):
        holder["f"] = ConversaFalsa(pedir)
        app.dependency_overrides[get_fornecedor] = lambda: holder["f"]
        return holder["f"]
    yield usar
    app.dependency_overrides.pop(get_fornecedor, None)


def test_ia_so_recebe_ferramentas_autorizadas(equipa, db, conversa):
    _, _, diana = equipa
    f = conversa(["tarefas_atrasadas", "resultado_mes"])
    r = diana.post("/assistente/perguntar", {"pergunta": "Como estamos de tarefas e de lucro?"})
    assert r.status_code == 200, r.text
    assert "resultado_mes" not in f.oferecidas and "o_que_produzir" in f.oferecidas
    # Mesmo que o modelo peça uma consulta fora da função, o servidor recusa-a.
    assert f.erros == ["sem_permissao"]
    corpo = r.json()
    assert corpo["modo"] == "ia" and [c["id"] for c in corpo["consultas"]] == ["tarefas_atrasadas"]
    i = db.scalar(select(InteracaoIA).where(InteracaoIA.tipo == "gestao"))
    assert i.pedido["pergunta"] == "Como estamos de tarefas e de lucro?" and i.tokens_entrada == 900


def test_relatorio_mensal(equipa):
    luisa, maira, diana = equipa
    d = hoje()
    r = luisa.get("/relatorios/mensal", params={"ano": d.year, "mes": d.month})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["periodo"]["em_curso"] is True and j["destaques"]
    assert {"tarefas", "vendas", "financas", "producao", "stock", "marketing", "ocorrencias"} <= set(j)
    assert maira.get("/relatorios/mensal", params={"ano": d.year, "mes": d.month}).status_code == 403
    assert diana.get("/relatorios/mensal", params={"ano": d.year, "mes": d.month}).status_code == 403
    futuro = d.replace(day=1) + timedelta(days=40)
    assert luisa.get("/relatorios/mensal", params={"ano": futuro.year, "mes": futuro.month}).status_code == 400


def _relogio(monkeypatch, momento: datetime):
    monkeypatch.setattr(agendador, "hoje", lambda: momento.date())
    monkeypatch.setattr(agendador, "agora", lambda: momento)


def test_resumo_semanal(equipa, db, monkeypatch):
    luisa, maira, diana = equipa
    seg = hoje() - timedelta(days=hoje().weekday())
    _relogio(monkeypatch, datetime(seg.year, seg.month, seg.day, 6, 30, tzinfo=FUSO))
    assert agendador.resumo_semanal(db)["enviados"] == 0  # antes das 07:00
    _relogio(monkeypatch, datetime(seg.year, seg.month, seg.day, 8, 0, tzinfo=FUSO))
    assert agendador.resumo_semanal(db)["enviados"] == 3
    agendador.resumo_semanal(db)  # repetir não duplica
    notas = db.scalars(select(Notificacao).where(Notificacao.tipo == "resumo_semanal")).all()
    assert len(notas) == 4  # 3 pessoais + 1 da equipa para a CEO
    assert sum(1 for n in notas if str(n.utilizador_id) == luisa.id) == 2
    quarta = seg + timedelta(days=2)
    _relogio(monkeypatch, datetime(quarta.year, quarta.month, quarta.day, 9, 0, tzinfo=FUSO))
    assert agendador.resumo_semanal(db)["enviados"] == 0


def test_aviso_relatorio_mensal(equipa, db, monkeypatch):
    luisa, _, _ = equipa
    _relogio(monkeypatch, datetime(2026, 12, 2, 9, 0, tzinfo=FUSO))
    assert agendador.relatorio_mensal(db)["enviados"] == 1
    agendador.relatorio_mensal(db)
    notas = db.scalars(select(Notificacao).where(Notificacao.tipo == "relatorio_mensal")).all()
    assert len(notas) == 1 and notas[0].ligacao == "/relatorio?ano=2026&mes=11" and "Novembro de 2026" in notas[0].titulo
    _relogio(monkeypatch, datetime(2026, 12, 15, 9, 0, tzinfo=FUSO))
    assert agendador.relatorio_mensal(db)["enviados"] == 0


def test_automacoes_pagina_e_configuracao(equipa):
    luisa, maira, _ = equipa
    lista = luisa.get("/automacoes").json()
    assert [a["id"] for a in lista] == ["alertas", "ausencias", "lembretes_reunioes", "resumo_semanal", "relatorio_mensal"] and all(a["activa"] for a in lista)
    assert maira.get("/automacoes").status_code == 403
    assert maira.post("/automacoes/executar").status_code == 403
    r = luisa.post("/automacoes/executar").json()
    assert "alertas" in r["resultado"]
    assert next(a for a in r["automacoes"] if a["id"] == "alertas")["ultima_execucao"]
    assert luisa.put("/configuracao/automacao_resumo_semanal", {"valor": 0}).status_code == 200
    assert next(a for a in luisa.get("/automacoes").json() if a["id"] == "resumo_semanal")["activa"] is False
    assert luisa.put("/configuracao/automacao_resumo_semanal", {"valor": 2}).status_code == 400


class _B:
    def __init__(self, **k):
        self.__dict__.update(k)


class _ClienteFalso:
    """Imita a forma das respostas da API: primeiro pede uma ferramenta, depois responde."""

    def __init__(self):
        self.pedidos = []
        self.beta = _B(messages=_B(create=self._create))

    def _create(self, **params):
        self.pedidos.append(params)
        uso = _B(input_tokens=100, output_tokens=20)
        if len(self.pedidos) == 1:
            return _B(model="m", stop_reason="tool_use", usage=uso,
                      content=[_B(type="tool_use", id="tu_1", name="stock_baixo", input={})])
        return _B(model="m", stop_reason="end_turn", usage=uso, content=[_B(type="text", text="Nada abaixo do mínimo.")])


def test_ciclo_de_ferramentas_anthropic():
    from app.modules.ia.fornecedores import AnthropicFornecedor
    f = AnthropicFornecedor("chave-falsa", "claude-opus-5-5", "medium")
    cli = _ClienteFalso()
    f._cliente = cli
    r = f.conversar("sistema", "Há stock baixo?", [{"name": "stock_baixo", "description": "d", "input_schema": {"type": "object"}}],
                    lambda nome, args: '{"resumo": "ok"}')
    assert r.texto == "Nada abaixo do mínimo." and r.ferramentas_usadas == ["stock_baixo"] and r.tokens_entrada == 200
    segundo = cli.pedidos[1]
    assert segundo["fallbacks"] == "default" and segundo["output_config"] == {"effort": "medium"}
    assert segundo["messages"][1]["role"] == "assistant"
    assert segundo["messages"][2]["content"][0] == {"type": "tool_result", "tool_use_id": "tu_1", "content": '{"resumo": "ok"}'}
