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

await browser.close();
assert.deepEqual(erros, [], `Erros na consola: ${erros.join("\n")}`);
console.log("E2E OK");
