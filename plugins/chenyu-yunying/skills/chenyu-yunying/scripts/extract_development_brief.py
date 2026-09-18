"""Read shared XLSX evidence without evaluating formulas or fetching URLs (stdlib)."""
import argparse
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'd': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'}
RID = '{' + NS['r'] + '}id'
URL = re.compile(r'https?://[^\s<>"\u3000]+', re.I)


def rels(z, part):
    name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if name not in z.namelist():
        return {}
    result = {}
    for n in ET.fromstring(z.read(name)):
        target = n.get('Target', '')
        external = n.get('TargetMode') == 'External'
        if not external:
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
        result[n.get('Id')] = {'target': target, 'external': external}
    return result


def extract(source, out):
    source, out = Path(source), Path(out)
    if source.suffix.lower() != '.xlsx':
        raise ValueError('Only .xlsx supported; convert other formats on a copy.')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty.')
    result = {'source': str(source.resolve()), 'sheets': [], 'links': [], 'images': [],
              'media': [], 'attachments': [], 'warnings': []}
    seen = set()

    def link(sheet, cell, url, kind):
        url = url.strip().rstrip('，。；')
        if not re.match(r'^https?://', url, re.I):
            result['warnings'].append(f'Non-HTTP link not followed: {sheet}!{cell}')
            return
        key = (sheet, cell, url, kind)
        if key not in seen:
            result['links'].append(dict(sheet=sheet, cell=cell, url=url, kind=kind))
            seen.add(key)

    with zipfile.ZipFile(source) as z:
        members = z.infolist()
        if len(members) > 20000 or sum(m.file_size for m in members) > 300 * 1024 * 1024:
            raise ValueError('Workbook exceeds extraction size limits.')
        out.mkdir(parents=True, exist_ok=True)
        names = set(z.namelist())
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = [''.join(t.text or '' for t in n.findall('.//s:t', NS))
                      for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        media = {}
        for name in sorted(names):
            if name.startswith('xl/media/') and not name.endswith('/'):
                dest = out / ('media-%03d' % (len(media) + 1) + Path(name).suffix)
                dest.write_bytes(z.read(name))
                media[name] = str(dest.resolve())
                result['media'].append({'part': name, 'path': media[name]})
            if name.startswith('xl/embeddings/') and not name.endswith('/'):
                result['attachments'].append({'part': name, 'status': 'not parsed; read-only review required'})
            if any(k in name.lower() for k in ('cellimage', 'richdata/', 'vml')):
                result['warnings'].append('Unparsed image/object part: ' + name)
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        wr = rels(z, 'xl/workbook.xml')
        for sh in wb.findall('s:sheets/s:sheet', NS):
            sn = sh.get('name')
            part = wr[sh.get(RID)]['target']
            root = ET.fromstring(z.read(part))
            sr = rels(z, part)
            cells = []
            for c in root.findall('s:sheetData/s:row/s:c', NS):
                value = c.findtext('s:v', '', NS)
                if c.get('t') == 's':
                    value = shared[int(value)] if value else ''
                elif c.get('t') == 'inlineStr':
                    value = ''.join(n.text or '' for n in c.findall('.//s:t', NS))
                formula = c.findtext('s:f', None, NS)
                coord = c.get('r')
                if value or formula:
                    cells.append({'cell': coord, 'value': value, 'formula': formula, 'type': c.get('t')})
                for url in URL.findall(value):
                    link(sn, coord, url, 'text')
                if formula and 'HYPERLINK' in formula.upper():
                    literal = re.match(r'\s*(?:_xlfn\.)?HYPERLINK\(\s*"((?:[^"]|"")*)"\s*[,;]', formula, re.I)
                    if literal:
                        link(sn, coord, literal.group(1).replace('""', '"'), 'formula')
                    else:
                        result['warnings'].append(f'Dynamic HYPERLINK not evaluated: {sn}!{coord}')
                if formula and re.search(r'DISPIMG|IMAGE\(', formula, re.I):
                    result['warnings'].append(f'Image formula requires review: {sn}!{coord}')
            for h in root.findall('s:hyperlinks/s:hyperlink', NS):
                r = sr.get(h.get(RID))
                if r and r['external']:
                    link(sn, h.get('ref'), r['target'], 'hyperlink')
            result['sheets'].append({'name': sn, 'state': sh.get('state', 'visible'), 'cells': cells,
                                     'merged_ranges': [m.get('ref') for m in root.findall('s:mergeCells/s:mergeCell', NS)]})
            for drawing in root.findall('s:drawing', NS):
                dr = sr.get(drawing.get(RID))
                if not dr or dr['external'] or dr['target'] not in names:
                    result['warnings'].append('Unresolved drawing: ' + sn)
                    continue
                dp = dr['target']
                drel = rels(z, dp)
                for anchor in ET.fromstring(z.read(dp)):
                    start = anchor.find('d:from', NS)
                    position = None if start is None else {
                        'row': int(start.findtext('d:row', '0', NS)) + 1,
                        'column': int(start.findtext('d:col', '0', NS)) + 1}
                    for blip in anchor.findall('.//a:blip', NS):
                        rid = blip.get('{' + NS['r'] + '}embed')
                        ir = drel.get(rid, {})
                        if ir.get('target') not in media:
                            result['warnings'].append('Unresolved or external drawing image: ' + sn)
                        result['images'].append({'sheet': sn, 'anchor_one_based': position,
                                                 'path': media.get(ir.get('target')), 'role': 'unconfirmed'})
        if result['attachments']:
            result['warnings'].append('Embedded attachments inventoried only; not opened or executed.')
    (out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    try:
        r = extract(a.input, a.out)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        p.exit(2, str(e) + '\n')
    print(json.dumps({k: len(r[k]) for k in ('sheets', 'links', 'images', 'attachments', 'warnings')}))


if __name__ == '__main__':
    main()
