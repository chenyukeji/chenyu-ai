import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "../../..");
const envNodeModules = path.join(projectRoot, "env", "node_modules");
const require = createRequire(import.meta.url);
const artifactEntry = require.resolve("@oai/artifact-tool", { paths: [envNodeModules] });
const { SpreadsheetFile, Workbook } = await import(pathToFileURL(artifactEntry).href);

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: node build_amazon_upload.mjs <rows.json> <output.xlsx>");
}

const rows = JSON.parse(await fs.readFile(inputPath, "utf8"));
if (!Array.isArray(rows) || rows.length === 0) {
  throw new Error("At least one upload row is required");
}

const headers = [];
for (const row of rows) {
  for (const key of Object.keys(row)) {
    if (!headers.includes(key)) headers.push(key);
  }
}

const workbook = Workbook.create();
const upload = workbook.worksheets.add("Amazon Upload");
const summary = workbook.worksheets.add("Pre-launch Summary");
upload.showGridLines = false;
summary.showGridLines = false;

const matrix = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))];
const lastColumn = columnName(headers.length);
for (const identifierHeader of ["sku", "ean"]) {
  const index = headers.indexOf(identifierHeader);
  if (index >= 0 && matrix.length > 1) {
    upload.getRange(`${columnName(index + 1)}2:${columnName(index + 1)}${matrix.length}`).setNumberFormat("@");
  }
}
upload.getRange(`A1:${lastColumn}${matrix.length}`).values = matrix;
upload.getRange(`A1:${lastColumn}1`).format = {
  fill: "#172554",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  verticalAlignment: "center",
};
upload.getRange(`A1:${lastColumn}${matrix.length}`).format.borders = {
  preset: "inside",
  style: "thin",
  color: "#D9E2F3",
};
upload.getRange(`A1:${lastColumn}${matrix.length}`).format.autofitColumns();
upload.getRange(`A1:${lastColumn}${matrix.length}`).format.autofitRows();
upload.getRange(`A1:${lastColumn}${matrix.length}`).format.columnWidth = 18;
upload.getRange(`A1:${lastColumn}1`).format.rowHeight = 30;
if (matrix.length > 1) {
  upload.getRange(`A2:${lastColumn}${matrix.length}`).format.rowHeight = 120;
  upload.getRange(`A2:${lastColumn}${matrix.length}`).format.verticalAlignment = "top";
}
for (const textHeader of ["title", "description", "bullet_1", "bullet_2", "bullet_3", "bullet_4", "bullet_5"]) {
  const index = headers.indexOf(textHeader);
  if (index >= 0) {
    const textRange = upload.getRange(`${columnName(index + 1)}1:${columnName(index + 1)}${matrix.length}`);
    textRange.format.columnWidth = 36;
    textRange.format.wrapText = true;
  }
}
upload.freezePanes.freezeRows(1);
upload.tables.add(`A1:${lastColumn}${matrix.length}`, true, "AmazonUploadTable").style = "TableStyleMedium2";

summary.getRange("A1:D1").merge();
summary.getRange("A1").values = [["Amazon Upload Package"]];
summary.getRange("A1:D1").format = {
  fill: "#172554",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
};
summary.getRange("A3:B6").values = [
  ["Metric", "Value"],
  ["Marketplace rows", null],
  ["Rows with SKU", null],
  ["Workbook status", "READY FOR OPERATOR REVIEW"],
];
summary.getRange("B4").formulas = [[`=COUNTA('Amazon Upload'!A2:A${matrix.length})`]];
const skuColumn = columnName(headers.indexOf("sku") + 1);
summary.getRange("B5").formulas = [[`=COUNTA('Amazon Upload'!${skuColumn}2:${skuColumn}${matrix.length})`]];
summary.getRange("A3:B3").format = { fill: "#DBEAFE", font: { bold: true, color: "#172554" } };
summary.getRange("A3:B6").format.borders = { preset: "outside", style: "thin", color: "#93C5FD" };
summary.getRange("A1:A6").format.columnWidth = 24;
summary.getRange("B1:B6").format.columnWidth = 32;

if (process.env.AMAZON_OS_VERIFY) {
  const summaryCheck = await workbook.inspect({
    kind: "table",
    range: "Pre-launch Summary!A1:B6",
    include: "values,formulas",
    tableMaxRows: 10,
    tableMaxCols: 4,
  });
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: "final formula error scan",
  });
  console.log(summaryCheck.ndjson);
  console.log(formulaErrors.ndjson);
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

if (process.env.AMAZON_OS_PREVIEW) {
  const preview = await workbook.render({ sheetName: "Pre-launch Summary", autoCrop: "all", scale: 2, format: "png" });
  await fs.writeFile(process.env.AMAZON_OS_PREVIEW, new Uint8Array(await preview.arrayBuffer()));
  const previewPath = path.parse(process.env.AMAZON_OS_PREVIEW);
  const uploadPreviewPath = path.join(previewPath.dir, `${previewPath.name}_upload${previewPath.ext || ".png"}`);
  const uploadPreview = await workbook.render({ sheetName: "Amazon Upload", range: `A1:${lastColumn}${matrix.length}`, scale: 1, format: "png" });
  await fs.writeFile(uploadPreviewPath, new Uint8Array(await uploadPreview.arrayBuffer()));
}

// The bundled renderer may keep native worker handles alive on Windows. All
// awaited files are durable at this point, so exit cleanly instead of letting
// native teardown turn a successful export into a false failure.
process.exit(0);

function columnName(number) {
  let result = "";
  let value = number;
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}
