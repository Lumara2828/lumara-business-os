from sqlalchemy import select

from app.modules.equipa.models import Sessao


def test_login_e_perfil(equipa):
    luisa, maira, _ = equipa
    r = maira.get("/auth/me")
    assert r.status_code == 200
    perfil = r.json()
    assert perfil["funcao"] == "marketing"
    assert "financas.ver" not in perfil["permissoes"]
    assert "tarefas.ver_todas" in luisa.get("/auth/me").json()["permissoes"]


def test_password_errada_e_email_inexistente_dao_o_mesmo_erro(api, equipa):
    a = api.post("/auth/login", json={"email": "luisa@teste.ao", "password": "errada-Errada1"})
    b = api.post("/auth/login", json={"email": "ninguem@teste.ao", "password": "errada-Errada1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_bloqueio_apos_tentativas_falhadas(api, equipa):
    for _ in range(5):
        api.post("/auth/login", json={"email": "diana@teste.ao", "password": "errada-Errada1"})
    r = api.post("/auth/login", json={"email": "diana@teste.ao", "password": "Teste-Segura-123"})
    assert r.status_code == 429
    assert r.json()["codigo"] == "conta_bloqueada"


def test_sem_token_e_token_invalido(api):
    assert api.get("/auth/me").status_code == 401
    assert api.get("/auth/me", headers={"Authorization": "Bearer xpto"}).status_code == 401


def test_logout_revoga_sessao(equipa):
    _, maira, _ = equipa
    assert maira.post("/auth/logout").status_code == 204
    assert maira.get("/auth/me").status_code == 401


def test_token_guardado_apenas_como_hash(equipa, db):
    _, maira, _ = equipa
    hashes = list(db.scalars(select(Sessao.token_hash)))
    assert maira.token not in hashes and len(hashes[0]) == 64


def test_mudar_password(api, equipa):
    _, maira, _ = equipa
    r = maira.post("/auth/mudar-password", json={"password_actual": "Teste-Segura-123", "password_nova": "fraca"})
    assert r.status_code == 400
    r = maira.post("/auth/mudar-password", json={"password_actual": "Teste-Segura-123", "password_nova": "NovaPalavra-2026"})
    assert r.status_code == 204
    assert api.post("/auth/login", json={"email": "maira@teste.ao", "password": "NovaPalavra-2026"}).status_code == 200


def test_ceo_gere_equipa_e_desactivar_termina_sessoes(equipa):
    luisa, maira, _ = equipa
    r = luisa.post("/equipa/utilizadores", json={"nome": "Nova", "email": "nova@teste.ao", "funcao": "producao",
                                                  "password_inicial": "Inicial-Forte-1"})
    assert r.status_code == 201
    assert luisa.post("/equipa/utilizadores", json={"nome": "Nova", "email": "NOVA@teste.ao", "funcao": "producao",
                                                     "password_inicial": "Inicial-Forte-1"}).status_code == 409
    assert luisa.patch(f"/equipa/utilizadores/{maira.id}", {"activo": False}).status_code == 200
    assert maira.get("/auth/me").status_code == 401
    assert luisa.patch(f"/equipa/utilizadores/{luisa.id}", {"activo": False}).status_code == 400
