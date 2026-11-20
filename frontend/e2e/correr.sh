#!/usr/bin/env bash
# Corre o teste ponta-a-ponta numa base de dados DEMO acabada de recriar.
# Requer: API em :8000 (backend/.env a apontar para a BD local) e Vite em :5173.
set -euo pipefail
cd "$(dirname "$0")/../../backend"
.venv/bin/python -m scripts.seed_demo --limpar >/dev/null
.venv/bin/python -m scripts.seed_demo >/dev/null
cd ../frontend
XLSX="$(mktemp -d)/calendario-teste.xlsx"
../backend/.venv/bin/python - "$XLSX" <<'PY'
import sys
from datetime import date, timedelta
from openpyxl import Workbook
wb = Workbook(); ws = wb.active; ws.title = "Dezembro"
ws.append(["Calendário Lumara — exemplo de teste"]); ws.append([])
ws.append(["Data", "Rede", "Pilar", "Formato", "Tema", "Legenda", "Responsável", "Status"])
d = date.today()
ws.append([d + timedelta(days=4), "Insta", "Educação", "Carrossel", "E2E: ingredientes naturais explicados", "", "Maira", "Por fazer"])
ws.append([(d + timedelta(days=5)).strftime("%d/%m/%Y"), "FB", "Bastidores", "Reel", "E2E: embalar encomendas", "", "", "em produção"])
ws.append(["sem data", "Snapchat", "x", "Post", "linha inválida", "", "", ""])
wb.save(sys.argv[1])
PY
E2E_XLSX="$XLSX" NODE_PATH="$(npm root -g)" node e2e/fluxo.mjs "${1:-e2e/capturas}"
