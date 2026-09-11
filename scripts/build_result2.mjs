import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const repoRoot = path.resolve(import.meta.dirname, "..");
const templatePath = path.join(repoRoot, "problem", "data", "附件5", "result2.xlsx");
const payloadPath = path.join(repoRoot, "outputs", "q2", "solver_payload.json");
const outputDir = path.join(repoRoot, "outputs", "q2");
const outputPath = path.join(outputDir, "result2.xlsx");
const previewDir = path.join(outputDir, "previews");

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
if (!Array.isArray(payload.days) || payload.days.length !== 334) {
  throw new Error(`Expected 334 output days, received ${payload.days?.length ?? "none"}`);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const planSheet = workbook.worksheets.getItem("计划购电量");
const storageSheet = workbook.worksheets.getItem("充放电量");
const emergencySheet = workbook.worksheets.getItem("紧急购电量");

const toDate = (iso) => new Date(`${iso}T00:00:00+08:00`);

// 计划购电量：保留官方模板已有的完整334行结构。
planSheet.getRange("A2:A335").values = payload.days.map((day) => [toDate(day.date)]);
planSheet.getRange("B2:EQ335").values = payload.days.map((day) => [
  ...day.template_grid_kwh,
  day.template_grid_total_kwh,
  day.template_grid_cost_yuan,
]);
planSheet.getRange("A2:A335").format.numberFormat = "yyyy-mm-dd";
planSheet.getRange("B2:EQ335").format.numberFormat = "0.0000";
planSheet.freezePanes.freezeRows(1);
planSheet.freezePanes.freezeColumns(1);

// 充放电量：官方模板仅给出示例行，扩展为334天×6时段。
const storageRows = [["日期", "时间段", "充电量", "放电量", "时刻", "储电量"]];
for (const day of payload.days) {
  day.storage_blocks.forEach((block, index) => {
    storageRows.push([
      index === 0 ? toDate(day.date) : null,
      block.time_range,
      block.charge_kwh,
      block.discharge_kwh,
      index === 0 ? "0:00" : index === 1 ? "24:00" : null,
      index === 0 ? day.soc_start_kwh : index === 1 ? day.soc_end_kwh : null,
    ]);
  });
}
for (const table of [...storageSheet.tables.items]) table.delete();
storageSheet.getRange("A1:F2005").clear({ applyTo: "contents" });
storageSheet.getRange("A1").write(storageRows);
const storageTable = storageSheet.tables.add("A1:F2005", true, "Q2StorageTable");
storageTable.style = "TableStyleMedium2";
storageSheet.getRange("A2:A2005").format.numberFormat = "yyyy-mm-dd";
storageSheet.getRange("C2:F2005").format.numberFormat = "0.0000";
storageSheet.freezePanes.freezeRows(1);

// 紧急购电量：连续的非零10分钟时段合并为一个区间；无紧急购电的日期保留一行。
const emergencyRows = [["日期", "购电时间段", "购电量"]];
for (const day of payload.days) {
  if (day.emergency_segments.length === 0) {
    emergencyRows.push([toDate(day.date), null, 0]);
    continue;
  }
  day.emergency_segments.forEach((segment, index) => {
    emergencyRows.push([
      index === 0 ? toDate(day.date) : null,
      segment.time_range,
      segment.energy_kwh,
    ]);
  });
}
for (const table of [...emergencySheet.tables.items]) table.delete();
const emergencyEndRow = emergencyRows.length;
emergencySheet.getRange(`A1:C${Math.max(9, emergencyEndRow)}`).clear({ applyTo: "contents" });
emergencySheet.getRange("A1").write(emergencyRows);
const emergencyTable = emergencySheet.tables.add(
  `A1:C${emergencyEndRow}`,
  true,
  "Q2EmergencyTable",
);
emergencyTable.style = "TableStyleMedium2";
emergencySheet.getRange(`A2:A${emergencyEndRow}`).format.numberFormat = "yyyy-mm-dd";
emergencySheet.getRange(`C2:C${emergencyEndRow}`).format.numberFormat = "0.0000";
emergencySheet.freezePanes.freezeRows(1);

workbook.recalculate();

const planCheck = await workbook.inspect({
  kind: "table",
  range: "计划购电量!A1:EQ6",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 147,
  maxChars: 12000,
});
console.log(planCheck.ndjson);

const storageCheck = await workbook.inspect({
  kind: "table",
  range: "充放电量!A1:F15",
  include: "values,formulas",
  tableMaxRows: 15,
  tableMaxCols: 6,
  maxChars: 6000,
});
console.log(storageCheck.ndjson);

const emergencyCheck = await workbook.inspect({
  kind: "table",
  range: `紧急购电量!A1:C${Math.min(emergencyEndRow, 20)}`,
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 3,
  maxChars: 6000,
});
console.log(emergencyCheck.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
const previews = [
  ["计划购电量", "A1:H12", "plan_start.png"],
  ["计划购电量", "EN1:EQ12", "plan_totals.png"],
  ["充放电量", "A1:F20", "storage_start.png"],
  ["紧急购电量", `A1:C${Math.min(emergencyEndRow, 30)}`, "emergency_start.png"],
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
  maxChars: 6000,
  tableMaxRows: 3,
  tableMaxCols: 8,
});
console.log(savedCheck.ndjson);
console.log(`Saved ${outputPath}`);

