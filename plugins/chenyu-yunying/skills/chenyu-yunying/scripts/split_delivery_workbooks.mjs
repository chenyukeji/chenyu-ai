import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [sourcePath, listingOutput, imageBriefOutput, previewDir] = process.argv.slice(2);
if (!sourcePath || !listingOutput || !imageBriefOutput) {
  throw new Error(
    "Usage: split_delivery_workbooks.mjs <source.xlsx> <listing.xlsx> <image-brief.xlsx> [preview-dir]",
  );
}

const listingSheets = ["产品内容", "DE Listing", "FR Listing", "IT Listing", "ES Listing"];
const imageBriefSheets = ["产品内容", "作图要求"];

async function loadWorkbook() {
  return SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
}

function keepOnly(workbook, keepNames) {
  const keep = new Set(keepNames);
  for (const sheet of [...workbook.worksheets.items]) {
    if (!keep.has(sheet.name)) sheet.delete();
  }
}

async function verifyAndExport(workbook, outputPath, expectedSheets, previewPrefix) {
  const actualSheets = workbook.worksheets.items.map((sheet) => sheet.name);
  if (JSON.stringify(actualSheets) !== JSON.stringify(expectedSheets)) {
    throw new Error(
      `Unexpected worksheets for ${outputPath}: ${JSON.stringify(actualSheets)}`,
    );
  }

  workbook.recalculate();
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
    maxChars: 3000,
  });
  const errorResult = JSON.parse(errors.ndjson);
  if (errorResult.kind !== "notice" || !String(errorResult.message).includes("0 entries")) {
    throw new Error(`Formula error scan failed for ${outputPath}: ${errors.ndjson}`);
  }

  const productCheck = await workbook.inspect({
    kind: "table",
    range: "产品内容!A1:F2",
    include: "values,formulas",
    tableMaxRows: 2,
    tableMaxCols: 6,
  });
  const productValues = JSON.parse(productCheck.ndjson).values;

  if (previewDir) {
    await fs.mkdir(previewDir, { recursive: true });
    const ranges = {
      "产品内容": "A1:F2",
      "作图要求": "A1:G8",
      "DE Listing": "A1:D10",
      "FR Listing": "A1:D10",
      "IT Listing": "A1:D10",
      "ES Listing": "A1:D10",
    };
    for (const sheetName of expectedSheets) {
      const preview = await workbook.render({
        sheetName,
        range: ranges[sheetName],
        scale: 1,
        format: "png",
      });
      const safeName = sheetName.replaceAll(" ", "_");
      await fs.writeFile(
        path.join(previewDir, `${previewPrefix}_${safeName}.png`),
        new Uint8Array(await preview.arrayBuffer()),
      );
    }
  }

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  return { actualSheets, productValues };
}

const listingWorkbook = await loadWorkbook();
keepOnly(listingWorkbook, listingSheets);
const listingResult = await verifyAndExport(
  listingWorkbook,
  listingOutput,
  listingSheets,
  "listing",
);

const imageBriefWorkbook = await loadWorkbook();
keepOnly(imageBriefWorkbook, imageBriefSheets);
const imageBriefResult = await verifyAndExport(
  imageBriefWorkbook,
  imageBriefOutput,
  imageBriefSheets,
  "image-brief",
);

if (JSON.stringify(listingResult.productValues) !== JSON.stringify(imageBriefResult.productValues)) {
  throw new Error("The 产品内容 values differ between the two output workbooks.");
}

console.log(JSON.stringify({
  listingOutput,
  listingSheets: listingResult.actualSheets,
  imageBriefOutput,
  imageBriefSheets: imageBriefResult.actualSheets,
  sharedProductContentMatches: true,
}, null, 2));
