import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const skillDir = path.resolve(scriptDir, "..");
const defaultProductTemplate = path.join(skillDir, "assets", "Product-V392.xlsx");
const defaultPairingTemplate = path.join(skillDir, "assets", "导入配对商品模板 (按MSKU).xlsx");

const accountDefaults = new Map([
  ["久阅科技", { store: "jiuyuekeji-FR", country: "法国" }],
]);

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const key = token.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`Missing value for --${key}`);
    args[key] = value;
    index += 1;
  }
  return args;
}

function usage() {
  return [
    "Usage:",
    "  node generate_lingxing_imports.mjs --input <新品补录.xlsx>",
    "    --product-output <领星产品录用.xlsx>",
    "    --pairing-output <领星产品配对.xlsx>",
    "    [--product-template <Product-V392.xlsx>]",
    "    [--pairing-template <按MSKU模板.xlsx>]",
    "    [--preview-dir <qa-preview-dir>]",
  ].join("\n");
}

function canonical(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .replace(/\s+/g, "")
    .toLowerCase();
}

function cleanText(value) {
  if (value == null) return "";
  return String(value).replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim();
}

function cleanMsku(value) {
  return cleanText(value).replace(/[|｜]+$/g, "").trim();
}

function optionalNumber(value, label, rowNumber) {
  if (value == null || cleanText(value) === "") return null;
  const number = typeof value === "number" ? value : Number(cleanText(value).replaceAll(",", ""));
  if (!Number.isFinite(number) || number < 0) {
    throw new Error(`第 ${rowNumber} 行“${label}”不是有效的非负数字：${value}`);
  }
  return number;
}

function normalizedDate(value, rowNumber) {
  if (value == null || cleanText(value) === "") return null;
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    const date = new Date(Date.UTC(1899, 11, 30) + Math.round(value * 86400000));
    return date.toISOString().slice(0, 10);
  }
  const match = cleanText(value).match(/^(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})(?:日)?$/);
  if (!match) throw new Error(`第 ${rowNumber} 行“日期”格式无法识别：${value}`);
  const [, year, month, day] = match;
  const check = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  if (check.getUTCFullYear() !== Number(year) || check.getUTCMonth() + 1 !== Number(month) || check.getUTCDate() !== Number(day)) {
    throw new Error(`第 ${rowNumber} 行“日期”不是有效日期：${value}`);
  }
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function dimensions(value, rowNumber) {
  if (value == null || cleanText(value) === "") return null;
  const parts = cleanText(value).split(/\s*[*×xX]\s*/).map(Number);
  if (parts.length !== 3 || parts.some((number) => !Number.isFinite(number) || number <= 0)) {
    throw new Error(`第 ${rowNumber} 行“尺寸”必须是 长*宽*高：${value}`);
  }
  return parts;
}

function headerIndex(headers, aliases, required = true) {
  const index = headers.findIndex((header) => aliases.some((alias) => canonical(header) === canonical(alias)));
  if (required && index < 0) throw new Error(`缺少必需列：${aliases[0]}`);
  return index;
}

function getCell(row, indexes, key) {
  const index = indexes[key];
  return index >= 0 ? row[index] : null;
}

function mapStore(account, rowNumber) {
  const cleaned = cleanText(account);
  const mapped = accountDefaults.get(cleaned);
  if (mapped) return mapped;
  throw new Error(`第 ${rowNumber} 行账号“${cleaned}”没有店铺映射，请先在 Skill 规则中确认。`);
}

function setByHeader(row, outputIndexes, header, value, required = true) {
  const index = outputIndexes.get(canonical(header));
  if (index == null) {
    if (required) throw new Error(`领星产品模板缺少字段：${header}`);
    return;
  }
  row[index] = value;
}

function columnName(columnCount) {
  let value = columnCount;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function populatedRowsAfterHeader(sheet, columnCount) {
  const used = sheet.getUsedRange();
  if (!used) return 0;
  const values = used.values ?? [];
  let count = 0;
  for (let index = 1; index < values.length; index += 1) {
    const row = values[index] ?? [];
    if (!row.slice(0, columnCount).some((value) => value != null && cleanText(value) !== "")) break;
    count += 1;
  }
  return count;
}

async function loadWorkbook(filePath) {
  return SpreadsheetFile.importXlsx(await FileBlob.load(filePath));
}

function locateSourceSheet(workbook) {
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange();
    if (!used) continue;
    const headers = used.values?.[0] ?? [];
    if (headers.some((header) => canonical(header) === canonical("Msku"))) return { sheet, values: used.values };
  }
  throw new Error("输入文件中找不到包含 Msku 列的新品补录工作表。");
}

function readSourceRecords(values) {
  const headers = values[0] ?? [];
  const indexes = {
    date: headerIndex(headers, ["日期"]),
    account: headerIndex(headers, ["账号"]),
    operator: headerIndex(headers, ["运营"]),
    developer: headerIndex(headers, ["开发"]),
    product: headerIndex(headers, ["产品"]),
    productName: headerIndex(headers, ["产品名称"]),
    msku: headerIndex(headers, ["Msku", "MSKU"]),
    purchaseCost: headerIndex(headers, ["进货成本"]),
    netWeight: headerIndex(headers, ["单个重量(净重）", "单个重量(净重)"]),
    size: headerIndex(headers, ["尺寸"]),
    grossWeight: headerIndex(headers, ["毛重（取最大者）", "毛重(取最大者)"]),
    purchasePrice: headerIndex(headers, ["采购价"], false),
  };

  const records = [];
  const seenMsku = new Set();
  for (let sourceIndex = 1; sourceIndex < values.length; sourceIndex += 1) {
    const row = values[sourceIndex] ?? [];
    const rowNumber = sourceIndex + 1;
    const msku = cleanMsku(getCell(row, indexes, "msku"));
    const anyValue = row.some((value) => value != null && cleanText(value) !== "");
    if (!anyValue) continue;
    if (!msku) throw new Error(`第 ${rowNumber} 行有数据但 Msku 为空。`);
    if (seenMsku.has(msku)) throw new Error(`Msku 重复：${msku}（第 ${rowNumber} 行）`);
    seenMsku.add(msku);

    const requiredText = {};
    for (const [key, label] of [
      ["account", "账号"],
      ["operator", "运营"],
      ["developer", "开发"],
      ["product", "产品"],
      ["productName", "产品名称"],
    ]) {
      requiredText[key] = cleanText(getCell(row, indexes, key));
      if (!requiredText[key]) throw new Error(`第 ${rowNumber} 行“${label}”为空。`);
    }

    records.push({
      rowNumber,
      date: normalizedDate(getCell(row, indexes, "date"), rowNumber),
      account: requiredText.account,
      operator: requiredText.operator,
      developer: requiredText.developer,
      product: requiredText.product,
      productName: requiredText.productName,
      msku,
      purchaseCost: optionalNumber(getCell(row, indexes, "purchaseCost"), "进货成本", rowNumber),
      purchasePrice: optionalNumber(getCell(row, indexes, "purchasePrice"), "采购价", rowNumber),
      netWeight: optionalNumber(getCell(row, indexes, "netWeight"), "单个重量(净重)", rowNumber),
      grossWeight: optionalNumber(getCell(row, indexes, "grossWeight"), "毛重(取最大者)", rowNumber),
      dimensions: dimensions(getCell(row, indexes, "size"), rowNumber),
      store: mapStore(requiredText.account, rowNumber),
    });
    if (!records.at(-1).date) throw new Error(`第 ${rowNumber} 行“日期”为空。`);
  }
  if (records.length === 0) throw new Error("输入文件没有可转换的产品记录。");
  return records;
}

function productRows(records, headers) {
  const outputIndexes = new Map();
  headers.forEach((header, index) => {
    if (header != null && cleanText(header)) outputIndexes.set(canonical(header), index);
  });

  return records.map((record) => {
    const row = Array(headers.length).fill(null);
    setByHeader(row, outputIndexes, "*SKU", record.msku);
    setByHeader(row, outputIndexes, "品名", record.productName);
    setByHeader(row, outputIndexes, "产品类型", "普通产品");
    setByHeader(row, outputIndexes, "状态", "待售");
    setByHeader(row, outputIndexes, "单位", "件");
    setByHeader(row, outputIndexes, "开发人", record.developer);
    setByHeader(row, outputIndexes, "开发日期", record.date, false);
    setByHeader(row, outputIndexes, "产品负责人", record.operator);
    setByHeader(row, outputIndexes, "SPU", record.product);
    setByHeader(row, outputIndexes, "采购成本(CNY)", record.purchaseCost);
    setByHeader(
      row,
      outputIndexes,
      "采购备注",
      record.purchasePrice == null ? null : `原始采购价：${record.purchasePrice.toFixed(2)} CNY`,
    );
    setByHeader(row, outputIndexes, "单品净重", record.netWeight);
    setByHeader(row, outputIndexes, "单品净重单位", record.netWeight == null ? null : "g");
    setByHeader(row, outputIndexes, "单品毛重", record.grossWeight);
    setByHeader(row, outputIndexes, "单品毛重单位", record.grossWeight == null ? null : "g");
    const [length, width, height] = record.dimensions ?? [null, null, null];
    setByHeader(row, outputIndexes, "包装规格长", length);
    setByHeader(row, outputIndexes, "包装规格宽", width);
    setByHeader(row, outputIndexes, "包装规格高", height);
    setByHeader(row, outputIndexes, "包装规格单位", record.dimensions ? "cm" : null);
    const headFreight = record.dimensions
      ? Math.round(Math.max(2, length * width * height * 0.006) * 100) / 100
      : null;
    setByHeader(row, outputIndexes, "全部国家头程费用(含税)", headFreight);
    setByHeader(row, outputIndexes, "全部国家头程费用币种", headFreight == null ? null : "CNY");
    return row;
  });
}

function pairingRows(records) {
  return records.map((record) => [
    record.msku,
    record.msku,
    record.store.store,
    record.store.country,
    "是",
  ]);
}

function assertNoFormulaErrors(result, label) {
  const matches = result.records.filter((record) => record.kind === "match");
  if (matches.length > 0) throw new Error(`${label} 存在公式错误：${JSON.stringify(matches.slice(0, 10))}`);
}

async function renderPreviews(productWorkbook, pairingWorkbook, previewDir, productLastRow, pairingLastRow) {
  await fs.mkdir(previewDir, { recursive: true });
  const jobs = [
    [productWorkbook, "产品", `A1:AE${productLastRow}`, "产品录用_左侧.png"],
    [productWorkbook, "产品", `AF1:BK${productLastRow}`, "产品录用_中部.png"],
    [productWorkbook, "产品", `BL1:CO${productLastRow}`, "产品录用_右侧.png"],
    [pairingWorkbook, "Sheet1", `A1:E${pairingLastRow}`, "产品配对.png"],
  ];
  const outputs = [];
  for (const [workbook, sheetName, range, fileName] of jobs) {
    const image = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    const output = path.join(previewDir, fileName);
    await fs.writeFile(output, new Uint8Array(await image.arrayBuffer()));
    outputs.push(output);
  }
  return outputs;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.input || !args["product-output"] || !args["pairing-output"]) {
    throw new Error(usage());
  }

  const inputPath = path.resolve(args.input);
  const productTemplate = path.resolve(args["product-template"] ?? defaultProductTemplate);
  const pairingTemplate = path.resolve(args["pairing-template"] ?? defaultPairingTemplate);
  const productOutput = path.resolve(args["product-output"]);
  const pairingOutput = path.resolve(args["pairing-output"]);
  if (productOutput === pairingOutput) throw new Error("两份输出文件必须使用不同路径。");
  for (const outputPath of [productOutput, pairingOutput]) {
    try {
      await fs.access(outputPath);
      throw new Error(`输出文件已存在，不能覆盖：${outputPath}`);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }

  const sourceWorkbook = await loadWorkbook(inputPath);
  const source = locateSourceSheet(sourceWorkbook);
  const records = readSourceRecords(source.values);

  const productWorkbook = await loadWorkbook(productTemplate);
  const productSheet = productWorkbook.worksheets.getItem("产品");
  const productHeaders = productSheet.getRange("A1:CO1").values[0].filter((value) => value != null);
  if (productHeaders.length < 90) throw new Error("领星产品模板的“产品”表头不完整。");
  const existingProductRows = populatedRowsAfterHeader(productSheet, productHeaders.length);
  const productStartRow = existingProductRows + 2;
  const productEndRow = productStartRow + records.length - 1;
  productSheet
    .getRange(`A${productStartRow}:${columnName(productHeaders.length)}${productEndRow}`)
    .values = productRows(records, productHeaders);

  const pairingWorkbook = await loadWorkbook(pairingTemplate);
  const pairingSheet = pairingWorkbook.worksheets.getItem("Sheet1");
  const pairingHeaders = pairingSheet.getRange("A1:E1").values[0].map(cleanText);
  const expectedPairingHeaders = ["*SKU", "*MSKU", "店铺名称", "国家", "是否同步listing图"];
  if (JSON.stringify(pairingHeaders) !== JSON.stringify(expectedPairingHeaders)) {
    throw new Error(`配对模板表头不匹配：${JSON.stringify(pairingHeaders)}`);
  }
  const existingPairingRows = populatedRowsAfterHeader(pairingSheet, pairingHeaders.length);
  const pairingStartRow = existingPairingRows + 2;
  const pairingEndRow = pairingStartRow + records.length - 1;
  pairingSheet.getRange(`A${pairingStartRow}:E${pairingEndRow}`).values = pairingRows(records);

  productWorkbook.recalculate();
  pairingWorkbook.recalculate();

  const productErrors = await productWorkbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
  });
  const pairingErrors = await pairingWorkbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
  });
  assertNoFormulaErrors(productErrors, "领星产品录用表");
  assertNoFormulaErrors(pairingErrors, "领星产品配对表");

  const actualProductRows = populatedRowsAfterHeader(productSheet, productHeaders.length);
  const actualPairingRows = populatedRowsAfterHeader(pairingSheet, pairingHeaders.length);
  if (actualProductRows !== existingProductRows + records.length) {
    throw new Error(`产品录用表行数错误：期望新增 ${records.length} 行，实际数据行 ${actualProductRows}。`);
  }
  if (actualPairingRows !== existingPairingRows + records.length) {
    throw new Error(`产品配对表行数错误：期望新增 ${records.length} 行，实际数据行 ${actualPairingRows}。`);
  }

  let previews = [];
  if (args["preview-dir"]) {
    previews = await renderPreviews(
      productWorkbook,
      pairingWorkbook,
      path.resolve(args["preview-dir"]),
      existingProductRows + records.length + 1,
      existingPairingRows + records.length + 1,
    );
  }

  await fs.mkdir(path.dirname(productOutput), { recursive: true });
  await fs.mkdir(path.dirname(pairingOutput), { recursive: true });
  await (await SpreadsheetFile.exportXlsx(productWorkbook)).save(productOutput);
  await (await SpreadsheetFile.exportXlsx(pairingWorkbook)).save(pairingOutput);
  await Promise.all([
    fs.rm(`${productOutput}.inspect.ndjson`, { force: true }),
    fs.rm(`${pairingOutput}.inspect.ndjson`, { force: true }),
  ]);

  console.log(JSON.stringify({
    input: inputPath,
    records: records.length,
    productOutput,
    pairingOutput,
    templates: { productTemplate, pairingTemplate },
    previews,
  }, null, 2));
  process.exitCode = 0;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
