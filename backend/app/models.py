"""Importa todos os modelos para registar as tabelas em Base.metadata
(usado pelo Alembic e pelos testes)."""
from app.modules.auditoria.models import RegistoActividade  # noqa: F401
from app.modules.configuracao.models import Configuracao  # noqa: F401
from app.modules.equipa.models import Sessao, Utilizador  # noqa: F401
from app.modules.notificacoes.models import Notificacao  # noqa: F401
from app.modules.ocorrencias.models import Ocorrencia  # noqa: F401
from app.modules.responsabilidades.models import ActividadeRecorrente, RegraDecisao  # noqa: F401
from app.modules.rotina.models import RelatorioSemanal  # noqa: F401
from app.modules.tarefas.models import AnexoTarefa, CategoriaTarefa, ComentarioTarefa, Tarefa  # noqa: F401
from app.modules.producao.models import FichaIngrediente, FichaTecnica, NaoConformidade, OrdemProducao  # noqa: F401,E402
from app.modules.stock.models import Artigo, ComponenteKit, Fornecedor, Lote, Movimento  # noqa: F401,E402
from app.modules.marketing.models import Campanha, ComentarioConteudo, Conteudo, InteracaoIA, MediaConteudo  # noqa: F401,E402
from app.modules.eventos.models import Evento, EventoCusto, EventoProduto, EventoTarefa  # noqa: F401,E402
from app.modules.vendas.models import Cliente, Encomenda, LinhaEncomenda, Pagamento, Preco  # noqa: F401,E402
from app.modules.financas.models import CategoriaFinanceira, DespesaFixa, Lancamento, Orcamento  # noqa: F401,E402
from app.modules.procedimentos.models import ExecucaoProcedimento, Procedimento  # noqa: F401,E402
from app.modules.vendas.models import Devolucao  # noqa: F401,E402
from app.modules.ausencias.models import Ausencia, TransferenciaTarefa  # noqa: F401,E402
from app.modules.funcoes.models import DescricaoFuncao  # noqa: F401,E402
from app.modules.agenda.models import DecisaoReuniao, ParticipanteReuniao, Reuniao  # noqa: F401,E402
