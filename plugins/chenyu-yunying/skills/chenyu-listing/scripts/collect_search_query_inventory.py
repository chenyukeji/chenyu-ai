"""Collect every saved Amazon query, independently of the final candidate selection."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

DOMAINS = {'www.amazon.de': 'DE', 'www.amazon.fr': 'FR', 'www.amazon.it': 'IT',
           'www.amazon.es': 'ES', 'www.amazon.co.uk': 'UK'}


def collect(root):
    found = {}
    def walk(value, path, key=''):
        if isinstance(value, list):
            for item in value:
                walk(item, path, key)
        elif isinstance(value, dict):
            query = value.get('query')
            market = DOMAINS.get(urlparse(str(value.get('url', ''))).hostname)
            market = market or (key if key in DOMAINS.values() else None)
            if market and isinstance(query, str) and query.strip() and isinstance(value.get('results'), list):
                identity = (market, query.strip().casefold())
                entry = found.setdefault(identity, {'marketplace': market, 'query': query.strip(), 'evidence': []})
                entry['evidence'].append(str(path.relative_to(root)))
            for child_key, item in value.items():
                if isinstance(item, (dict, list)):
                    walk(item, path, child_key)
    for path in sorted(root.rglob('search-*.json')):
        walk(json.loads(path.read_text(encoding='utf-8-sig')), path)
    return list(found.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.directory)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(f'{len(result)} distinct queries: {args.out}')


if __name__ == '__main__':
    main()
