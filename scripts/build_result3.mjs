import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "..");
const templatePath = path.join(root, "problem", "data", "附件5", "result3.xlsx");
const payloadPath = path.join(root, "outputs", "q3", "solver_payload.json");
const outputDir = path.join(root, "outputs", "q3");
const outputPath = path.join(outputDir, "result3.xlsx");
const previewDir = path.join(outputDir, "previews");
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
if (!Array.isArray(payload.days) || payload.days.length !== 334) throw new Error("Expected 334 Q3 days");

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const planSheet = workbook.worksheets.getItem("计划购电量");
const adjustSheet = workbook.worksheets.getItem("调整购电量");
const storageSheet = workbook.worksheets.getItem("充放电量");
const emergencySheet = workbook.worksheets.getItem("紧急购电量");
const toDate = (iso) => new Date(`${iso}T00:00:00+08:00`);

for (const [sheet, vectorKey, totalKey, costKey] of [
  [planSheet, "plan_kwh", "plan_total_kwh", "plan_cost_yuan"],
  [adjustSheet, "adjusted_kwh", "adjusted_total_kwh", "adjusted_settlement_yuan"],
]) {
  sheet.getRange("A2:A335").values = payload.days.map((day) => [toDate(day.date)]);
  sheet.getRange("B2:EQ335").values = payload.days.map((day) => [...day[vectorKey], day[totalKey], day[costKey]]);
  sheet.getRange("A2:A335").format.numberFormat = "yyyy-mm-dd";
  sheet.getRange("B2:EQ335").format.numberFormat = "0.0000";
  sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(1);
}

const storageRows = [["日期", "时间段", "充电量", "放电量", "时刻", "储电量"]];
for (const day of payload.days) {
  day.storage_blocks.forEach((block, index) => storageRows.push([
    index === 0 ? toDate(day.date) : null, block.time_range, block.charge_kwh, block.discharge_kwh,
    index === 0 ? "0:00" : index === 1 ? "24:00" : null,
    index === 0 ? day.soc_start_kwh : index === 1 ? day.soc_end_kwh : null,
  ]));
}
for (const table of [...storageSheet.tables.items]) table.delete();
storageSheet.getRange("A1:F2005").clear({ applyTo: "contents" });
storageSheet.getRange("A1").write(storageRows);
const storageTable = storageSheet.tables.add("A1:F2005", true, "Q3StorageTable"); storageTable.style = "TableStyleMedium2";
storageSheet.getRange("A2:A2005").format.numberFormat = "yyyy-mm-dd";
storageSheet.getRange("C2:F2005").format.numberFormat = "0.0000"; storageSheet.freezePanes.freezeRows(1);

const emergencyRows = [["日期", "购电时间段", "购电量"]];
for (const day of payload.days) {
  if (day.emergency_segments.length === 0) emergencyRows.push([toDate(day.date), null, 0]);
  else day.emergency_segments.forEach((segment, index) => emergencyRows.push([index === 0 ? toDate(day.date) : null, segment.time_range, segment.energy_kwh]));
}
for (const table of [...emergencySheet.tables.items]) table.delete();
const emergencyEnd = emergencyRows.length;
emergencySheet.getRange(`A1:C${Math.max(11, emergencyEnd)}`).clear({ applyTo: "contents" });
emergencySheet.getRange("A1").write(emergencyRows);
const emergencyTable = emergencySheet.tables.add(`A1:C${emergencyEnd}`, true, "Q3EmergencyTable"); emergencyTable.style = "TableStyleMedium2";
emergencySheet.getRange(`A2:A${emergencyEnd}`).format.numberFormat = "yyyy-mm-dd";
emergencySheet.getRange(`C2:C${emergencyEnd}`).format.numberFormat = "0.0000"; emergencySheet.freezePanes.freezeRows(1);

workbook.recalculate();
for (const [sheetName, range] of [["计划购电量", "A1:H8"], ["调整购电量", "A1:H8"], ["充放电量", "A1:F15"], ["紧急购电量", `A1:C${Math.min(25, emergencyEnd)}`]]) {
  console.log((await workbook.inspect({ kind: "table", range: `${sheetName}!${range}`, include: "values,formulas", tableMaxRows: 25, tableMaxCols: 8, maxChars: 7000 })).ndjson);
}
console.log((await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "Q3 formula error scan" })).ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range, name] of [["计划购电量", "EN1:EQ10", "plan_totals.png"], ["调整购电量", "EN1:EQ10", "adjust_totals.png"], ["充放电量", "A1:F20", "storage.png"], ["紧急购电量", `A1:C${Math.min(30, emergencyEnd)}`, "emergency.png"]]) {
  const blob = await workbook.render({ sheetName, range, scale: 1.5, format: "png" });
  await fs.writeFile(path.join(previewDir, name), new Uint8Array(await blob.arrayBuffer()));
}
await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook); await output.save(outputPath);
const saved = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
console.log((await saved.inspect({ kind: "sheet,table", maxChars: 7000, tableMaxRows: 3, tableMaxCols: 8 })).ndjson);
console.log(`Saved ${outputPath}`);
