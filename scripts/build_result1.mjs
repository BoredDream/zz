import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const repoRoot = path.resolve(import.meta.dirname, "..");
const templatePath = path.join(repoRoot, "problem", "data", "附件5", "result1.xlsx");
const payloadPath = path.join(repoRoot, "outputs", "q1", "solver_payload.json");
const outputDir = path.join(repoRoot, "outputs", "q1");
const outputPath = path.join(outputDir, "result1.xlsx");
const previewDir = path.join(outputDir, "previews");

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
if (!Array.isArray(payload.template_grid_kwh) || payload.template_grid_kwh.length !== 144) {
  throw new Error(`Expected 144 template intervals, received ${payload.template_grid_kwh?.length ?? "none"}`);
}
if (!Array.isArray(payload.storage_blocks) || payload.storage_blocks.length !== 6) {
  throw new Error(`Expected 6 storage blocks, received ${payload.storage_blocks?.length ?? "none"}`);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const planSheet = workbook.worksheets.getItem("计划购电量");
const storageSheet = workbook.worksheets.getItem("充放电量");

// 计划购电量：官方模板已有144行区间标签，只写购电量列。
planSheet.getRange("B2:B145").values = payload.template_grid_kwh.map((value) => [value]);
planSheet.getRange("B2:B145").format.numberFormat = "0.0000";

// 充放电量：官方模板为 A 时间段 / B 充电量 / C 放电量 / D 时刻 / E 储电量。
// 只写 B、C、E 三列，保留模板已有的 D2='0:00'、D3='24:00' 标签。
storageSheet.getRange("B2:C7").values = payload.storage_blocks.map((block) => [
  block.charge_kwh,
  block.discharge_kwh,
]);
storageSheet.getRange("B2:C7").format.numberFormat = "0.0000";
storageSheet.getRange("E2").values = [[payload.soc_start_kwh]];
storageSheet.getRange("E3").values = [[payload.soc_end_kwh]];
storageSheet.getRange("E2:E3").format.numberFormat = "0.0000";

workbook.recalculate();

const planCheck = await workbook.inspect({
  kind: "table",
  range: "计划购电量!A1:B12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 2,
  maxChars: 4000,
});
console.log(planCheck.ndjson);

const planTail = await workbook.inspect({
  kind: "table",
  range: "计划购电量!A140:B145",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 2,
  maxChars: 4000,
});
console.log(planTail.ndjson);

const storageCheck = await workbook.inspect({
  kind: "table",
  range: "充放电量!A1:E7",
  include: "values,formulas",
  tableMaxRows: 7,
  tableMaxCols: 5,
  maxChars: 4000,
});
console.log(storageCheck.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
const previews = [
  ["计划购电量", "A1:B12", "plan_start.png"],
  ["计划购电量", "A134:B145", "plan_end.png"],
  ["充放电量", "A1:F7", "storage.png"],
];
for (const [sheetName, range, filename] of previews) {
  const preview = await workbook.render({ sheetName, range, scale: 1.5, format: "png" });
  await fs.writeFile(path.join(previewDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const savedCheck = await saved.inspect({
  kind: "sheet,table",
  maxChars: 4000,
  tableMaxRows: 3,
  tableMaxCols: 6,
});
console.log(savedCheck.ndjson);
console.log(`Saved ${outputPath}`);
