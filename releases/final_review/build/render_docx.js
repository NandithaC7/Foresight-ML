// render_docx.js — render a JSON report spec (built by build_reports.py) into a .docx.
// Usage: node render_docx.js spec.json out.docx
// Block types: h1 h2 h3 p bullets numbered table figure note pagebreak kv
// Inline markup in text: **bold**, `code`
const fs = require("fs");
const path = require("path");
const d = require("docx");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, ImageRun, PageBreak, Header, Footer, PageNumber, LevelFormat,
  TableOfContents, BorderStyle, VerticalAlign, TabStopType, TableLayoutType,
} = d;

const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = process.argv[3];
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1134; // A4, 2 cm margins
const CONTENT_W = PAGE_W - 2 * MARGIN; // 9638 DXA
const FONT = "Calibri";
const STATUS_FILL = {
  "COMPLETE": "D7EDDD", "VERIFIED": "D7EDDD", "MEASURED": "D7EDDD", "PASS": "D7EDDD", "YES": "D7EDDD",
  "IN PROGRESS": "FCEFC7", "PARTIAL": "FCEFC7", "REQUIRES YOUR ACTION": "FCEFC7", "INCONCLUSIVE": "FCEFC7", "UNDER-TRAINED": "FCEFC7",
  "BLOCKED": "F6D5CC", "FAIL": "F6D5CC", "MISSING": "F6D5CC", "NO": "F6D5CC",
  "NOT IMPLEMENTED": "E4E4E4", "NOT RUN": "E4E4E4", "NOT AVAILABLE": "E4E4E4", "DISABLED": "E4E4E4", "N/A": "E4E4E4", "SIMULATED": "E4E4E4",
};

function runs(text, base = {}) {
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter((s) => s !== "");
  return parts.map((s) => {
    if (s.startsWith("**") && s.endsWith("**")) return new TextRun({ text: s.slice(2, -2), bold: true, font: FONT, ...base });
    if (s.startsWith("`") && s.endsWith("`")) return new TextRun({ text: s.slice(1, -1), font: "Consolas", size: (base.size || 21) - 2, ...base, bold: base.bold });
    return new TextRun({ text: s, font: FONT, ...base });
  });
}

let hCount = [0, 0, 0], tableN = 0, figN = 0;
const numberingRefs = [];
function heading(level, text) {
  if (level === 1) { hCount = [hCount[0] + 1, 0, 0]; }
  else if (level === 2) { hCount[1] += 1; hCount[2] = 0; }
  else { hCount[2] += 1; }
  const num = level === 1 ? `${hCount[0]}` : level === 2 ? `${hCount[0]}.${hCount[1]}` : `${hCount[0]}.${hCount[1]}.${hCount[2]}`;
  const lv = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][level - 1];
  return new Paragraph({ heading: lv, children: [new TextRun({ text: `${num}  ${text}` })] });
}

function cell(text, width, opts = {}) {
  const t = String(text ?? "");
  const fill = opts.header ? "2F4A3D" : STATUS_FILL[t.trim().toUpperCase()] || (opts.zebra ? "F5F7F5" : undefined);
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: fill ? { type: ShadingType.CLEAR, color: "auto", fill } : undefined,
    margins: { top: 50, bottom: 50, left: 80, right: 80 },
    verticalAlign: VerticalAlign.CENTER,
    children: t.split("\n").map((line) => new Paragraph({
      spacing: { before: 0, after: 0 },
      children: runs(line, { size: opts.size || 17, color: opts.header ? "FFFFFF" : "1E1E1E", bold: !!opts.header }),
    })),
  });
}

function table(b) {
  tableN += 1;
  const ncol = b.header.length;
  let widths = b.widths;
  if (!widths) {
    // proportional to max text length per column, clamped
    const lens = b.header.map((h, i) => Math.max(String(h).length, ...b.rows.map((r) => Math.min(60, String(r[i] ?? "").length))));
    const w = lens.map((l) => Math.max(4, Math.min(40, l)));
    const tot = w.reduce((a, c) => a + c, 0);
    widths = w.map((x) => Math.floor((x / tot) * CONTENT_W));
  } else {
    const tot = widths.reduce((a, c) => a + c, 0);
    widths = widths.map((x) => Math.floor((x / tot) * CONTENT_W));
  }
  widths[ncol - 1] += CONTENT_W - widths.reduce((a, c) => a + c, 0);
  const size = b.small ? 15 : 17;
  const rows = [new TableRow({ tableHeader: true, children: b.header.map((h, i) => cell(h, widths[i], { header: true, size })) })];
  b.rows.forEach((r, ri) => rows.push(new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i], { zebra: ri % 2 === 1, size })) })));
  const border = { style: BorderStyle.SINGLE, size: 4, color: "B8C2BB" };
  const out = [
    new Paragraph({ keepNext: true, spacing: { before: 160, after: 60 }, children: runs(`**Table ${tableN}.** ${b.caption}`, { size: 19 }) }),
    new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED, rows,
      borders: { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border } }),
  ];
  if (b.source) out.push(new Paragraph({ spacing: { before: 40, after: 160 }, children: runs(`Source: ${b.source}`, { size: 15, italics: true, color: "5A5A5A" }) }));
  else out.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
  return out;
}

function pngSize(buf) { return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }; }
function jpgSize(buf) {
  let i = 2;
  while (i < buf.length) {
    if (buf[i] !== 0xff) { i++; continue; }
    const m = buf[i + 1], len = buf.readUInt16BE(i + 2);
    if (m >= 0xc0 && m <= 0xc3) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
    i += 2 + len;
  }
  throw new Error("jpg size");
}

function figure(b) {
  figN += 1;
  const buf = fs.readFileSync(b.path);
  const isPng = b.path.toLowerCase().endsWith(".png");
  const { w, h } = isPng ? pngSize(buf) : jpgSize(buf);
  const maxW = Math.round((b.width_frac || 1.0) * 6.6 * 96); // px at 96 dpi; content width ~6.7in
  const maxH = 8.2 * 96;
  let W = maxW, H = Math.round((h / w) * W);
  if (H > maxH) { H = maxH; W = Math.round((w / h) * H); }
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 60 },
      children: [new ImageRun({ type: isPng ? "png" : "jpg", data: buf, transformation: { width: W, height: H },
        altText: { title: `Figure ${figN}`, description: b.caption, name: path.basename(b.path) } })] }),
    new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 200 },
      children: runs(`**Figure ${figN}.** ${b.caption}${b.source ? `  [${b.source}]` : ""}`, { size: 18 }) }),
  ];
}

const children = [];
// title page
children.push(new Paragraph({ spacing: { before: 2400, after: 120 }, children: [new TextRun({ text: "FORESIGHT", font: FONT, size: 26, bold: true, color: "2F4A3D", characterSpacing: 60 })] }));
children.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: spec.title, font: FONT, size: 44, bold: true, color: "1E1E1E" })] }));
if (spec.subtitle) children.push(new Paragraph({ spacing: { after: 400 }, children: runs(spec.subtitle, { size: 24, color: "4B584C" }) }));
children.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "CBBE95", space: 4 } }, children: [] }));
(spec.meta || []).forEach(([k, v]) => children.push(new Paragraph({ spacing: { before: 60, after: 0 }, children: [...runs(`**${k}:** `, { size: 20 }), ...runs(v, { size: 20 })] })));
if (spec.status_legend !== false) {
  children.push(new Paragraph({ spacing: { before: 300 }, children: runs("Every number in this document is generated by `releases/final_review/build/build_reports.py` from saved run logs and result files; nothing is hand-entered. Labels such as **NOT RUN**, **NOT AVAILABLE**, **BLOCKED** or **SIMULATED** mark results that do not exist.", { size: 18, italics: true, color: "4B584C" }) }));
}
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Contents", font: FONT, size: 30, bold: true, color: "2F4A3D" })] }));
children.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));
children.push(new Paragraph({ children: runs("(Right-click → Update Field in Word if the contents list appears empty.)", { size: 16, italics: true, color: "7A7A7A" }) }));
children.push(new Paragraph({ children: [new PageBreak()] }));

for (const b of spec.blocks) {
  switch (b.type) {
    case "h1": children.push(heading(1, b.text)); break;
    case "h2": children.push(heading(2, b.text)); break;
    case "h3": children.push(heading(3, b.text)); break;
    case "p": children.push(new Paragraph({ spacing: { after: 120 }, alignment: AlignmentType.JUSTIFIED, children: runs(b.text) })); break;
    case "note": children.push(new Paragraph({ spacing: { before: 80, after: 140 }, shading: { type: ShadingType.CLEAR, color: "auto", fill: b.tone === "warn" ? "FCEFC7" : "EAF1EC" },
      border: { left: { style: BorderStyle.SINGLE, size: 18, color: b.tone === "warn" ? "B5852A" : "2F4A3D", space: 6 } }, indent: { left: 120, right: 120 },
      children: runs(b.text, { size: 19 }) })); break;
    case "bullets": b.items.forEach((it) => children.push(new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 }, children: runs(it) }))); break;
    case "numbered": { const ref = `num${children.length}`; numberingRefs.push(ref); b.items.forEach((it) => children.push(new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60 }, children: runs(it) }))); break; }
    case "kv": b.items.forEach(([k, v]) => children.push(new Paragraph({ spacing: { after: 40 }, children: [...runs(`**${k}:** `), ...runs(v)] }))); break;
    case "table": children.push(...table(b)); break;
    case "figure": children.push(...figure(b)); break;
    case "pagebreak": children.push(new Paragraph({ children: [new PageBreak()] })); break;
    default: throw new Error("unknown block " + b.type);
  }
}

const doc = new Document({
  creator: "Foresight project", title: spec.title, description: spec.subtitle || "",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: "2F4A3D" }, paragraph: { spacing: { before: 360, after: 140 }, outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, font: FONT, color: "2F4A3D" }, paragraph: { spacing: { before: 260, after: 100 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: FONT, color: "4B584C" }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    ...numberingRefs.map((r) => ({ reference: r, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] })),
  ] },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: `Foresight — ${spec.short || spec.title}`, font: FONT, size: 16, color: "7A7A7A" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ font: FONT, size: 16, color: "7A7A7A", children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES] })] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log(`wrote ${out} (${tableN} tables, ${figN} figures)`); });
