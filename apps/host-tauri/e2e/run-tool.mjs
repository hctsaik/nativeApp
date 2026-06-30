// 單工具 E2E CLI:  node e2e/run-tool.mjs <toolId> <cdpPort> <workDir>
// 末行印 RESULT_JSON {...}(供 workflow agent / 人解析)。
import { testTool } from "./lib.mjs";

const [, , toolId = "sheet-edge-analysis", cdpPort = "9222", workDir] = process.argv;
const r = await testTool(toolId, cdpPort, workDir || `e2e/runs/${toolId}`);
console.log("RESULT_JSON " + JSON.stringify(r));
process.exit(0);
