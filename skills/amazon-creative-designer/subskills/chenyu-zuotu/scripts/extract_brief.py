#!/usr/bin/env python3
"""Extract XLSX text and original drawing media without assigning semantic roles."""
import argparse
import hashlib
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
}
RID = '{' + NS['r'] + '}'


def recover_archive_images(container, out):
    """Read ZIP-compatible attachments, including some OLE-packaged ZIPs.

    ZipFile validates member headers and CRC. Non-contiguous OLE streams may
    require a separate OLE reader; failures are surfaced, never called complete.
    """
    result = {'images': [], 'warnings': []}
    if not zipfile.is_zipfile(container):
        result['warnings'].append('not a directly readable ZIP; inspect with a read-only OLE/archive tool')
        return result
    try:
        with zipfile.ZipFile(container) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(i.file_size for i in entries) > 200 * 1024 * 1024:
                result['warnings'].append('archive exceeds extraction limits; review separately')
                return result
            for entry in entries:
                suffix = Path(entry.filename).suffix.lower()
                if entry.is_dir():
                    continue
                if suffix not in {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp', '.gif', '.emf', '.wmf'}:
                    result['warnings'].append('unextracted non-image member: ' + entry.filename)
                    continue
                if entry.file_size > 50 * 1024 * 1024 or entry.flag_bits & 1:
                    result['warnings'].append('oversized or encrypted member: ' + entry.filename)
                    continue
                data = archive.read(entry)
                # Never use untrusted member paths as filesystem destinations.
                dest = out / ('asset-%03d' % (len(result['images']) + 1) + suffix)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                info = {'source_member': entry.filename, 'path': str(dest.resolve()), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'role': 'unknown'}
                try:
                    from PIL import Image
                    with Image.open(dest) as img:
                        info.update(width=img.width, height=img.height, format=img.format)
                except (ImportError, OSError, ValueError):
                    info['inspection'] = 'image inspection unavailable; verify manually'
                result['images'].append(info)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        result['warnings'].append('archive not fully recovered: ' + str(exc))
    return result


def relationships(z, part):
    name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if name not in z.namelist():
        return {}
    result = {}
    for r in ET.fromstring(z.read(name)):
        target = r.get('Target', '')
        external = r.get('TargetMode') == 'External'
        if not external:
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
        result[r.get('Id')] = {'target': target, 'external': external, 'type': r.get('Type')}
    return result


def marker(anchor, tag):
    node = anchor.find('xdr:' + tag, NS)
    if node is None:
        return None
    return {c.tag.split('}')[-1]: int(c.text) for c in node}


def extract(source, out):
    if source.suffix.lower() != '.xlsx':
        raise ValueError('Only .xlsx is supported. Convert legacy .xls on a copy and verify images separately.')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty; use a new run directory.')
    out.mkdir(parents=True, exist_ok=True)
    media_dir = out / 'media'
    media_dir.mkdir(exist_ok=True)
    result = {'source': str(source.resolve()), 'sheets': [], 'media': [], 'images': [], 'embedded_objects': [], 'warnings': [], 'anchor_units': 'row/col are zero-based; offsets and extents are EMU'}
    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        if 'xl/workbook.xml' not in names:
            raise ValueError('Unsupported workbook layout: missing xl/workbook.xml')
        suspicious = [n for n in names if any(k in n.lower() for k in ('cellimage', 'richdata/', 'vml'))]
        if suspicious:
            result['warnings'].append({'kind': 'unparsed_image_or_object_parts', 'parts': suspicious})
        for n in sorted(names):
            if n.startswith('xl/embeddings/') and not n.endswith('/'):
                destination = out / 'embedded' / ('object-%03d' % (len(result['embedded_objects']) + 1) + (Path(n).suffix or '.bin'))
                destination.parent.mkdir(exist_ok=True)
                data = z.read(n)
                destination.write_bytes(data)
                recovered = recover_archive_images(destination, destination.parent / destination.stem)
                result['embedded_objects'].append({'source_part': n, 'path': str(destination.resolve()), 'bytes': len(data), 'recovered_images': recovered['images'], 'warnings': recovered['warnings'], 'status': 'images recovered; semantic roles require visual review' if recovered['images'] and not recovered['warnings'] else 'requires further read-only attachment review'})
                if recovered['warnings']:
                    result['warnings'].append({'kind': 'embedded_archive_review', 'part': n, 'details': recovered['warnings']})
        shared = []
        if 'xl/sharedStrings.xml' in names:
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS):
                shared.append(''.join(t.text or '' for t in si.findall('.//s:t', NS)))
        media_map = {}
        for n in sorted(names):
            if not n.startswith('xl/media/') or n.endswith('/'):
                continue
            data = z.read(n)
            mid = 'media-%03d' % (len(media_map) + 1)
            suffix = Path(n).suffix.lower() or '.bin'
            destination = media_dir / (mid + suffix)
            destination.write_bytes(data)
            info = {'id': mid, 'source_part': n, 'path': str(destination.resolve()), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            try:
                from PIL import Image
                with Image.open(destination) as img:
                    info.update(width=img.width, height=img.height, format=img.format)
            except (ImportError, OSError, ValueError):
                info['inspection'] = 'image dimensions unavailable; inspect with a suitable viewer'
            media_map[n] = info
            result['media'].append(info)
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        wb_rels = relationships(z, 'xl/workbook.xml')
        used = set()
        for sh in wb.findall('s:sheets/s:sheet', NS):
            rel = wb_rels.get(sh.get(RID + 'id'))
            if not rel or rel['external'] or rel['target'] not in names:
                result['warnings'].append({'kind': 'unreadable_sheet', 'sheet': sh.get('name')})
                continue
            part = rel['target']
            root = ET.fromstring(z.read(part))
            if root.find('s:oleObjects', NS) is not None:
                result['warnings'].append({'kind': 'embedded_ole_objects_require_review', 'sheet': sh.get('name')})
            cells = []
            for c in root.findall('s:sheetData/s:row/s:c', NS):
                typ = c.get('t')
                value = c.findtext('s:v', default='', namespaces=NS)
                if typ == 's':
                    value = shared[int(value)] if value else ''
                elif typ == 'inlineStr':
                    value = ''.join(t.text or '' for t in c.findall('.//s:t', NS))
                formula = c.findtext('s:f', namespaces=NS)
                if value or formula:
                    cells.append({'cell': c.get('r'), 'value': value, 'type': typ, 'formula': formula})
                if formula and ('DISPIMG' in formula.upper() or 'IMAGE(' in formula.upper()):
                    result['warnings'].append({'kind': 'image_formula_requires_review', 'sheet': sh.get('name'), 'cell': c.get('r')})
            info = {
                'name': sh.get('name'), 'part': part, 'cells': cells,
                'merged_ranges': [m.get('ref') for m in root.findall('s:mergeCells/s:mergeCell', NS)],
                'columns': [dict(c.attrib) for c in root.findall('s:cols/s:col', NS)],
                'rows': [dict(r.attrib) for r in root.findall('s:sheetData/s:row', NS)],
                'task_marker_candidates': [c for c in cells if re.fullmatch(r'(?:第\s*[零一二三四五六七八九十百\d]+\s*张|图\s*\d+)', c['value'].strip())],
            }
            result['sheets'].append(info)
            sr = relationships(z, part)
            for extrel in sr.values():
                if extrel['external'] and extrel['type'] and extrel['type'].endswith('/image'):
                    result['warnings'].append({'kind': 'external_sheet_image', 'sheet': sh.get('name')})
            for drawing in root.findall('s:drawing', NS):
                dr = sr.get(drawing.get(RID + 'id'))
                if not dr or dr['external'] or dr['target'] not in names:
                    result['warnings'].append({'kind': 'unreadable_drawing', 'sheet': sh.get('name')})
                    continue
                dp = dr['target']
                drawing_rels = relationships(z, dp)
                for anchor in ET.fromstring(z.read(dp)):
                    for blip in anchor.findall('.//a:blip', NS):
                        r = drawing_rels.get(blip.get(RID + 'embed') or blip.get(RID + 'link'))
                        image = {'id': 'image-%03d' % (len(result['images']) + 1), 'sheet': sh.get('name'), 'drawing': dp, 'anchor_type': anchor.tag.split('}')[-1], 'from': marker(anchor, 'from'), 'to': marker(anchor, 'to'), 'role': 'unknown'}
                        for tag in ('ext', 'pos'):
                            node = anchor.find('xdr:' + tag, NS)
                            if node is not None:
                                image[tag] = dict(node.attrib)
                        props = anchor.find('.//xdr:cNvPr', NS)
                        if props is not None:
                            image['description'] = props.get('descr')
                            image['name'] = props.get('name')
                        if r and not r['external'] and r['target'] in media_map:
                            image['media_id'] = media_map[r['target']]['id']
                            image['path'] = media_map[r['target']]['path']
                            used.add(r['target'])
                        else:
                            image['unresolved'] = True
                            result['warnings'].append({'kind': 'unresolved_image', 'image_id': image['id']})
                        result['images'].append(image)
        result['unplaced_media'] = [m['id'] for p, m in media_map.items() if p not in used]
        if result['unplaced_media']:
            result['warnings'].append({'kind': 'media_without_drawing_anchor', 'media_ids': result['unplaced_media']})
    (out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    try:
        r = extract(args.input, args.out)
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        p.exit(2, str(exc) + '\n')
    print(json.dumps({'sheets': len(r['sheets']), 'images': len(r['images']), 'media': len(r['media']), 'warnings': r['warnings'], 'manifest': str((args.out / 'manifest.json').resolve())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
