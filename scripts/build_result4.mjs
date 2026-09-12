// 用官方附件5模板生成 result4-2.xlsx / result4-3.xlsx（波动电价模型）。
// 数据来自 scripts/export_q4.py 落盘的 payload。
// 表2 采用"模板行框"：六个段为 t=0..23,24..47,...,120..143，
// 分别覆盖 0:10-4:10 / 4:10-8:10 / 8:10-12:10 / 12:10-16:10 / 16:10-20:10 / 20:10-0:10+1。
//
// 用法： node scripts/build_result4.mjs <2|3> [K]
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const repoRoot = path.resolve(import.meta.dirname, "..");
const variant = process.argv[2] ?? "3";
const K = process.argv[3] ?? "30";
if (!["2", "3"].includes(variant)) throw new Error(`variant must be 2 or 3, got ${variant}`);

const templatePath = path.join(repoRoot, "problem", "data", "附件5", `result4-${variant}.xlsx`);
const payloadPath = path.join(repoRoot, "outputs", "q4", `payload_q4-${variant}_K${K}.json`);
const outputDir = path.join(repoRoot, "outputs", "q4");
const outputPath = path.join(outputDir, `result4-${variant}.xlsx`);
const previewDir = path.join(outputDir, "previews");

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
if (!Array.isArray(payload.days) || payload.days.length !== 334) {
  throw new Error(`Expected 334 output days, received ${payload.days?.length ?? "none"}`);
}
console.log(`meta: ${JSON.stringify(payload.meta)}`);

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const planSheet = workbook.worksheets.getItem("计划购电量");
const storageSheet = workbook.worksheets.getItem("充放电量");
const emergencySheet = workbook.worksheets.getItem("紧急购电量");
const adjustSheet = variant === "3" ? workbook.worksheets.getItem("调整购电量") : null;

const toDate = (iso) => new Date(`${iso}T00:00:00+08:00`);

// 计划购电量 / 调整购电量：官方模板已给出完整 334 行结构，末两列为全天购电量与全天购电费。
const writePriceSheet = (sheet, kwhKey, totalKey, costKey) => {
  sheet.getRange("A2:A335").values = payload.days.map((day) => [toDate(day.date)]);
  sheet.getRange("B2:EQ335").values = payload.days.map((day) => [
    ...day[kwhKey],
    day[totalKey],
    day[costKey],
  ]);
  sheet.getRange("A2:A335").format.numberFormat = "yyyy-mm-dd";
  sheet.getRange("B2:EQ335").format.numberFormat = "0.0000";
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
  for (const table of [...sheet.tables.items]) table.delete();
};
writePriceSheet(planSheet, "plan_kwh", "plan_total_kwh", "plan_cost_yuan");
if (adjustSheet) writePriceSheet(adjustSheet, "adjusted_kwh", "adjusted_total_kwh", "adjusted_cost_yuan");

// 充放电量：官方模板仅给出示例日，扩展为 334 天 × 6 段 = 2005 行。
// 时刻列只在每段的前两行填，分别给出该段起点与终点的储电量。
const storageRows = [["日期", "时间段", "充电量", "放电量", "时刻", "储电量"]];
for (const day of payload.days) {
  day.storage_blocks.forEach((block, index) => {
    storageRows.push([
      index === 0 ? toDate(day.date) : null,
      block.time_range,
      block.charge_kwh,
      block.discharge_kwh,
      index === 0 ? "0:10" : index === 1 ? "0:10+1" : null,
      index === 0 ? day.soc_start_kwh : index === 1 ? day.soc_end_kwh : null,
    ]);
  });
}
for (const table of [...storageSheet.tables.items]) table.delete();
storageSheet.getRange("A1:F2005").clear({ applyTo: "contents" });
storageSheet.getRange("A1").write(storageRows);
const storageTable = storageSheet.tables.add("A1:F2005", true, `Q4-${variant}StorageTable`);
storageTable.style = "TableStyleMedium2";
storageSheet.getRange("A2:A2005").format.numberFormat = "yyyy-mm-dd";
storageSheet.getRange("C2:F2005").format.numberFormat = "0.0000";
storageSheet.freezePanes.freezeRows(1);

// 紧急购电量：连续的非零 10 分钟时段合并为一段；无紧急购电的日期保留一行零。
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
emergencySheet.getRange(`A1:C${Math.max(11, emergencyRows.length)}`).clear({ applyTo: "contents" });
emergencySheet.getRange("A1").write(emergencyRows);
const emergencyEndRow = emergencyRows.length;
const emergencyTable = emergencySheet.tables.add(`A1:C${emergencyEndRow}`, true, `Q4-${variant}EmergencyTable`);
emergencyTable.style = "TableStyleMedium2";
emergencySheet.getRange(`A2:A${emergencyEndRow}`).format.numberFormat = "yyyy-mm-dd";
emergencySheet.getRange(`C2:C${emergencyEndRow}`).format.numberFormat = "0.0000";
emergencySheet.freezePanes.freezeRows(1);

workbook.recalculate();

for (const [sheetName, maxCols] of [["计划购电量", 147], ["调整购电量", 147], ["充放电量", 6], ["紧急购电量", 3]]) {
  if (!workbook.worksheets.items.some((ws) => ws.name === sheetName)) continue;
  const check = await workbook.inspect({
    kind: "table", range: `${sheetName}!A1`,
    include: "values", tableMaxRows: 2, tableMaxCols: maxCols, maxChars: 1500,
  });
  console.log(`--- ${sheetName} ---\n${check.ndjson}`);
}

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range, filename] of [
  ["计划购电量", "A1:H6", `plan_q4-${variant}.png`],
  ["充放电量", "A1:F8", `storage_q4-${variant}.png`],
  ["紧急购电量", `A1:C${Math.min(emergencyEndRow, 20)}`, `emergency_q4-${variant}.png`],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.5, format: "png" });
  await fs.writeFile(path.join(previewDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`Saved ${outputPath}`);
