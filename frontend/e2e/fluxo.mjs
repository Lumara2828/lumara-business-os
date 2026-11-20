// Teste ponta-a-ponta (requer API em :8000 com dados DEMO e o Vite em :5173).
// Uso: node e2e/fluxo.mjs [pasta-capturas]
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
import assert from "node:assert/strict";

const BASE = process.env.E2E_URL ?? "http://localhost:5173";
const PASTA = process.argv[2] ?? "e2e/capturas";
const PW = "Lumara-Demo-2026";
const browser = await chromium.launch();
const erros = [];

async function sessao(email, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport, locale: "pt-PT" });
  const p = await ctx.newPage();
  p.on("pageerror", (e) => erros.push(`${email}: ${e.message}`));
  p.on("console", (m) => m.type() === "error" && !m.text().includes("401") && erros.push(`${email}: ${m.text()}`));
  await p.goto(BASE);
  await p.fill("#email", email);
  await p.fill("#password", PW);
  await p.click("button:has-text('Entrar')");
  await p.waitForSelector("main");
  return p;
}
const foto = (p, n) => p.screenshot({ path: `${PASTA}/${n}.png`, fullPage: true });

// --- CEO ---
const luisa = await sessao("luisa@demo.lumara.ao");
await luisa.waitForSelector("text=Como está a Lumara?");
await foto(luisa, "01-painel-ceo");
await luisa.click("nav >> text=Tarefas");
await luisa.waitForSelector("section[aria-label='Bloqueada']");
await foto(luisa, "02-kanban");
await luisa.click("role=tab[name='Lista']");
await luisa.waitForSelector("table");
await foto(luisa, "03-lista");
await luisa.click("role=tab[name='Calendário']");
await luisa.waitForSelector("text=Segunda");
await foto(luisa, "04-calendario");
await luisa.click("role=tab[name='Kanban']");

// Criar e delegar uma tarefa à Maira, com aprovação
await luisa.click("text=+ Nova tarefa");
await luisa.fill("#t-titulo", "E2E: legenda para publicação de óleo corporal");
const amanha = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
await luisa.fill("#t-prazo", amanha);
const opcaoMaira = await luisa.locator("#t-resp option", { hasText: "Maira" }).getAttribute("value");
await luisa.selectOption("#t-resp", opcaoMaira);
await luisa.check("text=Requer aprovação da CEO");
await luisa.click("button:has-text('Criar tarefa')");
await luisa.waitForSelector("role=dialog >> text=E2E: legenda");
await foto(luisa, "05-detalhe-tarefa");
await luisa.keyboard.press("Escape");

await luisa.click("nav >> text=Central de Excepções");
await luisa.waitForSelector("text=Tarefas bloqueadas");
await foto(luisa, "06-excepcoes");
await luisa.click("nav >> text=Rotina semanal");
await luisa.click("role=tab[name='Sexta · Revisão']");
await luisa.waitForSelector("text=Relatório semanal de execução");
await foto(luisa, "07-relatorio-semanal");
await luisa.click("nav >> text=Responsabilidades");
await luisa.waitForSelector("text=Matriz de decisões");
await foto(luisa, "08-responsabilidades");

// --- Marketing ---
const maira = await sessao("maira@demo.lumara.ao", { width: 390, height: 844 });
await maira.waitForSelector("text=Olá, Maira");
await foto(maira, "09-painel-maira-telemovel");
assert.equal(await maira.locator("text=Central de Excepções").count(), 0, "Maira não deve ver a Central de Excepções");
await maira.goto(`${BASE}/excepcoes`);
await maira.waitForSelector("text=Olá, Maira"); // redireccionada
await maira.goto(`${BASE}/tarefas`);
await maira.waitForSelector("text=As suas tarefas");
await maira.waitForSelector("section button p.font-medium");
const titulos = await maira.locator("section button p.font-medium").allTextContents();
assert.ok(titulos.length > 0 && !titulos.some((t) => t.includes("sabonetes")), "Maira só vê as suas tarefas");
await maira.click("text=E2E: legenda para publicação");
await maira.waitForSelector("role=dialog");
await maira.selectOption("role=dialog >> select", "aguardar_aprovacao");
await maira.fill("role=dialog >> textarea[placeholder='Comentário (opcional)']", "Legenda pronta para revisão.");
await maira.click("role=dialog >> button:has-text('Confirmar')");
await maira.waitForSelector("role=dialog >> text=A aguardar aprovação");
await foto(maira, "10-maira-submete");

// --- CEO aprova ---
await luisa.goto(`${BASE}/excepcoes`);
await luisa.click("text=E2E: legenda para publicação");
await luisa.waitForSelector("role=dialog >> button:has-text('Aprovar')");
await luisa.click("role=dialog >> button:has-text('Aprovar')");
await luisa.click("role=dialog >> button:has-text('Confirmar')");
await luisa.waitForSelector("role=dialog >> text=Concluída");
await luisa.click("role=dialog >> role=tab[name='Histórico']");
await luisa.waitForSelector("text=Aprovou");
await foto(luisa, "11-aprovada-historico");

// --- Produção: comunicar ocorrência ---
const diana = await sessao("diana@demo.lumara.ao", { width: 820, height: 1180 });
await diana.click("nav >> text=Ocorrências").catch(async () => { await diana.click("button[aria-label='Abrir menu']"); await diana.click("nav >> text=Ocorrências"); });
await diana.click("text=+ Comunicar");
await diana.fill("#o-tit", "E2E: óleo de rícino abaixo do mínimo");
await diana.fill("#o-desc", "Restam 2 litros.");
await diana.click("role=dialog >> button:has-text('Comunicar')");
await diana.waitForSelector("text=E2E: óleo de rícino");
await foto(diana, "12-ocorrencias-tablet");

await luisa.goto(`${BASE}/`);
await luisa.click("button[aria-label^='Notificações']");
await luisa.waitForSelector("text=E2E: óleo de rícino");
await foto(luisa, "13-notificacoes");

// --- Fase 2: produção e stock ---
await diana.goto(`${BASE}/producao`);
await diana.waitForSelector("text=Ordens de produção");
await foto(diana, "14-producao");
await diana.click("text=Óleo fortalecedor de unhas 30 ml >> nth=0");
await diana.waitForSelector("role=dialog >> text=Materiais necessários");
await diana.click("role=dialog >> button:has-text('Iniciar')");
await diana.waitForSelector("role=dialog >> text=Em curso");
await diana.click("role=dialog >> button:has-text('Concluir e registar lote')");
await diana.fill("#op-prod", "19");
await diana.click("role=dialog >> button:has-text('Confirmar conclusão')");
await diana.waitForSelector("role=dialog >> text=Rastreabilidade do lote");
await diana.click("role=dialog >> button:has-text('Rastreabilidade do lote')");
await diana.waitForSelector("text=Origem: OP-");
await foto(diana, "15-rastreabilidade");
await diana.keyboard.press("Escape");
await diana.keyboard.press("Escape");
await diana.goto(`${BASE}/stock`);
await diana.waitForSelector("text=Stock e inventário");
assert.equal(await diana.locator("th:has-text('Valor')").count(), 0, "Diana não vê valores do stock");
await diana.click("role=tab[name='Relatórios']");
await diana.waitForSelector("text=a comprar");
assert.equal(await diana.locator("text=Valor do inventário").count(), 0);
await foto(diana, "16-stock-relatorios");
await diana.click("text=+ Entrada");
await diana.selectOption("#mv-artigo", { label: await diana.locator("#mv-artigo option", { hasText: "Frasco âmbar" }).textContent() });
await diana.fill("#mv-qtd", "100");
await diana.click("role=dialog >> button:has-text('Registar')");
await diana.waitForSelector("text=Entrada registada");

await luisa.goto(`${BASE}/stock`);
await luisa.click("role=tab[name='Relatórios']");
await luisa.waitForSelector("text=Valor do inventário");
await luisa.goto(`${BASE}/`);
await luisa.waitForSelector("text=Estado da produção");
await foto(luisa, "17-painel-ceo-fase2");

await maira.goto(`${BASE}/stock`);
await maira.waitForSelector("text=Stock e inventário");
assert.equal(await maira.locator("button:has-text('+ Entrada')").count(), 0, "Maira só consulta o stock");

// --- Fase 3: marketing ---
const XLSX = process.env.E2E_XLSX;
await maira.goto(`${BASE}/marketing`);
await maira.waitForSelector("text=Marketing e conteúdos");
await maira.click("role=tab[name='Importar Excel']");
await maira.setInputFiles("input[type=file][accept='.xlsx,.xlsm']", XLSX);
await maira.waitForSelector("text=Pré-visualização");
await foto(maira, "18-importar-excel");
await maira.click("button:has-text('Importar linhas válidas')");
await maira.waitForSelector("text=Importação concluída");
assert.ok(await maira.locator("text=2 conteúdo(s) criado(s)").count() === 1, "Importa as 2 linhas válidas");
await maira.click("button:has-text('Ver no calendário')");
await maira.click("role=tab[name='Fluxo de trabalho']");
await maira.click("text=E2E: ingredientes naturais explicados");
await maira.waitForSelector("role=dialog");
await maira.fill("#ct-texto", "Conhece os ingredientes que usamos e porquê. Guarda este post. 🌿");
await maira.click("role=dialog >> button:has-text('Guardar')");
await maira.waitForSelector("text=Guardado.");
await maira.click("role=dialog >> role=tab[name='Assistente IA']");
await maira.waitForSelector("text=Assistente de IA não configurado");
await maira.click("role=dialog >> role=tab[name='Conteúdo']");
await maira.click("role=dialog >> button:has-text('Submeter para aprovação')");
await maira.waitForSelector("role=dialog >> text=Revisão");
await maira.keyboard.press("Escape");

await luisa.goto(`${BASE}/marketing`);
await luisa.waitForSelector("text=a aguardar a sua aprovação");
await luisa.click("role=tab[name='Fluxo de trabalho']");
await foto(luisa, "19-marketing-fluxo");
await luisa.click("text=E2E: ingredientes naturais explicados");
luisa.once("dialog", (d) => d.accept("Muito bom"));
await luisa.click("role=dialog >> button:has-text('Aprovar publicação')");
await luisa.waitForSelector("role=dialog >> text=Aprovado");
await luisa.keyboard.press("Escape");
await luisa.click("role=tab[name='Calendário']");
await foto(luisa, "20-marketing-calendario");
await luisa.click("role=tab[name='Integrações']");
await luisa.waitForSelector("text=Nenhuma integração é simulada");
assert.equal(await diana.locator("nav >> text=Marketing").count(), 0, "Diana não vê o marketing");

// --- Fase 4: vendas e eventos ---
await maira.goto(`${BASE}/vendas`);
await maira.waitForSelector("text=Vendas e clientes");
await maira.click("button:has-text('+ Encomenda')");
await maira.selectOption("#enc-cli", { label: await maira.locator("#enc-cli option", { hasText: "Cliente B (DEMO)" }).textContent() });
const optUnhas = await maira.locator("select[aria-label='Produto 1'] option", { hasText: "fortalecedor" }).textContent();
await maira.selectOption("select[aria-label='Produto 1']", { label: optUnhas });
await maira.fill("input[aria-label='Quantidade']", "2");
await maira.click("role=dialog >> button:has-text('Criar encomenda')");
await maira.waitForSelector("role=dialog >> text=Recebida");
const codigoEnc = (await maira.locator("role=dialog >> h2").first().textContent()).split(" · ")[0];
await foto(maira, "21-encomenda-telemovel");
await maira.keyboard.press("Escape");

await diana.goto(`${BASE}/vendas`);
await diana.waitForSelector(`text=${codigoEnc}`);
assert.equal(await diana.locator("text=Kz").count(), 0, "Diana não vê valores das encomendas");
await diana.click(`text=${codigoEnc}`);
await diana.click("role=dialog >> button:has-text('Marcar como pronta')");
await diana.waitForSelector("role=dialog >> text=Pronta");
diana.once("dialog", (d) => d.accept());
await diana.click("role=dialog >> button:has-text('Marcar como entregue')");
await diana.waitForSelector("role=dialog >> text=Lotes entregues");
await diana.keyboard.press("Escape");

await maira.reload();
await maira.selectOption("select[aria-label='Filtro']", "por_pagar");
await maira.click(`text=${codigoEnc}`);
await maira.click("role=dialog >> button:has-text('Registar pagamento')");
await maira.click("role=dialog >> button:has-text('Registar') >> nth=-1");
await maira.waitForSelector("role=dialog >> text=Pagamentos");
await maira.keyboard.press("Escape");

await maira.goto(`${BASE}/eventos`);
await maira.click("text=Feira de artesanato");
await maira.click("role=dialog >> button:has-text('Registar venda no evento')");
const opt2 = await maira.locator("select[aria-label='Produto 1'] >> nth=-1 >> option", { hasText: "fortalecedor" }).textContent();
await maira.locator("select[aria-label='Produto 1']").last().selectOption({ label: opt2 });
await maira.click("button:has-text('Registar venda') >> nth=-1");
await maira.waitForSelector("text=Vendas registadas");

await luisa.goto(`${BASE}/vendas`);
await luisa.click("role=tab[name='Relatórios']");
await luisa.waitForSelector("text=Contas a receber");
await foto(luisa, "22-vendas-relatorios");
await luisa.goto(`${BASE}/eventos`);
await luisa.click("text=Feira de artesanato");
await luisa.waitForSelector("text=Resultado do evento");
await foto(luisa, "23-evento");
await luisa.keyboard.press("Escape");
await luisa.goto(`${BASE}/`);
await luisa.waitForSelector("text=Facturação (entregues)");
await foto(luisa, "24-painel-ceo-fase4");

// --- Fase 5: finanças e procedimentos ---
await diana.goto(`${BASE}/financas`);
await diana.waitForSelector("text=Propostas de despesa");
await diana.click("button:has-text('+ Propor despesa')");
await diana.selectOption("#l-cat", { label: "Matérias-primas" });
await diana.fill("#l-desc", "E2E: óleo de rícino 2 L");
await diana.fill("#l-valor", "8000");
await diana.click("role=dialog >> button:has-text('Propor')");
await diana.waitForSelector("text=E2E: óleo de rícino 2 L");
await diana.goto(`${BASE}/procedimentos`);
await diana.click("text=Contagem semanal");
await diana.click("role=dialog >> button:has-text('Executar checklist')");
for (const cb of await diana.locator("role=dialog >> .bg-folha-50 input[type=checkbox]").all()) await cb.check();
await diana.click("role=dialog >> button:has-text('Registar') >> nth=-1");
await diana.waitForSelector("role=dialog >> text=Execuções registadas");
await foto(diana, "25-procedimento-tablet");
await diana.keyboard.press("Escape");

await luisa.goto(`${BASE}/excepcoes`);
await luisa.waitForSelector("text=Proposta");
await luisa.goto(`${BASE}/financas`);
await luisa.click("role=tab[name='Despesas e receitas']");
await luisa.click("text=E2E: óleo de rícino 2 L");
await luisa.click("role=dialog >> button:has-text('Aprovar')");
await luisa.waitForSelector("role=dialog >> text=Aprovada");
await luisa.keyboard.press("Escape");
await luisa.click("role=tab[name='Resultados']");
await luisa.waitForSelector("text=Demonstração de resultados");
await foto(luisa, "26-financas-resultados");
await luisa.click("role=tab[name='Custos por produto']");
await luisa.waitForSelector("text=Custo de mão-de-obra directa");
await foto(luisa, "27-custos-produto");
assert.equal(await maira.goto(`${BASE}/financas`).then(() => maira.locator("text=Finanças e rentabilidade").count()), 0, "Maira não vê as finanças");

// --- Fase 6: assistente, relatório mensal, automações ---
await diana.goto(`${BASE}/assistente`);
await diana.click("text=O que devo produzir esta semana?");
await diana.waitForSelector("section >> text=O que produzir");
await foto(diana, "28-assistente-producao");
assert.equal(await diana.locator("text=Resultado do mês").count(), 0, "Diana não tem consultas financeiras");
await luisa.goto(`${BASE}/assistente`);
await luisa.click("button:has-text('Clientes inactivas')");
await luisa.waitForSelector("text=sem compras há mais de");
await foto(luisa, "29-assistente-clientes");
await luisa.click("nav >> text=Relatório mensal");
await luisa.waitForSelector("text=Destaques");
await foto(luisa, "30-relatorio-mensal");
await luisa.click("nav >> text=Automações");
await luisa.click("button:has-text('Executar agora')");
await luisa.waitForSelector("text=Automações executadas.");
await foto(luisa, "31-automacoes");
assert.equal(await maira.goto(`${BASE}/relatorio`).then(() => maira.locator("text=Destaques").count()), 0, "Maira não vê o relatório mensal");

await browser.close();
assert.deepEqual(erros, [], `Erros na consola: ${erros.join("\n")}`);
console.log("E2E OK");
