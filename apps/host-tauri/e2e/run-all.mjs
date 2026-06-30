// 全套 E2E:依序測每個 menu 工具(隔離實例、逐一拆除,資源可控、CI 友善)。
//   node e2e/run-all.mjs            → 測全部 MENU_TOOLS
//   node e2e/run-all.mjs app-lv …   → 只測指定工具
// 產 e2e/reports/latest.{md,json};exit 0=全 PASS,否則 1。
import { testTool, MENU_TOOLS } from "./lib.mjs";
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const tools = process.argv.slice(2).length ? process.argv.slice(2) : MENU_TOOLS;
const results = [];
let port = 9340;

for (const t of tools) {
  process.stdout.write(`\n▶ ${t} ... `);
  const r = await testTool(t, port++, `e2e/runs/${t}`);
  results.push(r);
  process.stdout.write(`${r.verdict} / ${r.attribution} (${Math.round((r.durationMs || 0) / 1000)}s)`);
}

const pass = results.filter((r) => r.attribution === "PASS");
const envBlocked = results.filter((r) => r.attribution === "ENV_BLOCKED");
const other = results.filter((r) => !["PASS", "ENV_BLOCKED"].includes(r.attribution));
const rows = results
  .map((r) => `| ${r.toolId} | ${r.verdict} | ${r.attribution} | ${r.health ?? "-"}/${r.rootStatus ?? "-"} | ${r.consoleErrorCount} | ${(r.evidence || r.rootCause || r.error || "").slice(0, 70).replace(/\|/g, "/")} |`)
  .join("\n");

const md = `# Tauri E2E 報告

共 ${results.length} 個功能 — **PASS ${pass.length} / ${results.length}**${envBlocked.length ? `,ENV_BLOCKED ${envBlocked.length}` : ""}${other.length ? `,其他 ${other.length}` : ""}。

| 功能 | verdict | 判定 | health/root | console err | 證據 / 根因 |
|---|---|---|---|---|---|
${rows}

**判定意義**
- **PASS** — 在 Tauri WebView2 真實算繪 Streamlit 業務畫面(\`[data-testid="stApp"]\` 存在且非「Not Found」)。
- **ENV_BLOCKED** — Streamlit 核心起得來(\`/_stcore/health\`=200)但工具頁缺失 → engine/外掛打包或依賴問題,**與 Tauri 殼無關**(換不換框架都一樣)。
- **INCONCLUSIVE / INFRA** — 需人工查 \`e2e/runs/<tool>/logs/\`(engine.log、streamlit-*.log)。

> 前提:app 由 \`engine.py\`(原始碼版,含 Streamlit static)驅動;frozen \`engine.exe\` 因未包全 static 會讓所有工具 \`/\` 回 404。
`;

mkdirSync(resolve("e2e", "reports"), { recursive: true });
writeFileSync(resolve("e2e", "reports", "latest.md"), md, "utf8");
writeFileSync(resolve("e2e", "reports", "latest.json"), JSON.stringify(results, null, 2), "utf8");
console.log("\n\n" + md);
console.log("報告寫入: e2e/reports/latest.md  (+ latest.json)");
process.exit(pass.length === results.length ? 0 : 1);
