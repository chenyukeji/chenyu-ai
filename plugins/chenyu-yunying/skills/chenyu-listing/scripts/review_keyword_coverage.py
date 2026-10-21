"""Export per-market candidate placement for semantic review; never invent terms.

Run again after any front-end or keyword change. This diagnostic does not replace
validate_listing_package.py or evidence/language review.
"""
import argparse
import copy
import csv
import json
from pathlib import Path

from validate_listing_package import keyword_coverage


def review(data, previous=None):
    current = copy.deepcopy(data)
    unmatched = []
    if previous is not None:
        prior = {(row.get('marketplace'), row.get('variant_id')): row
                 for row in previous.get('listings', [])}
        for row in current.get('listings', []):
            key = row.get('marketplace'), row.get('variant_id')
            if key in prior:
                row['previous_search_terms'] = prior[key].get('search_terms', '')
            else:
                unmatched.append({'marketplace': key[0], 'variant_id': key[1]})
    return {'market_variants': keyword_coverage(current),
            'unmatched_previous_listings': unmatched,
            'semantic_review_required': True,
            'note': 'Token locations do not prove natural phrasing, source truth, search volume or Amazon indexing. '
                    'A byte target is not a relevance score; review shortfalls per market.'}


def write_csv(report, path):
    fields = ['marketplace', 'variant_id', 'characters', 'utf8_bytes', 'phrase', 'concept_id',
              'source_phrase', 'source_asin', 'source_marketplace', 'source_tool', 'source_evidence',
              'product_match_reason', 'relevance_fact_ids', 'exact_front_end_fields',
              'front_end_tokens_by_field', 'backend_tokens', 'uncovered_tokens', 'placement',
              'decision', 'exclusion_reason', 'exclusion_detail', 'next_actions']
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for listing in report['market_variants']:
            for candidate in listing['candidates'] or [{}]:
                row = {**listing, **candidate}
                values = {key: (json.dumps(row.get(key), ensure_ascii=False)
                                if isinstance(row.get(key), (list, dict)) else row.get(key, '')) for key in fields}
                # Source titles are untrusted spreadsheet cells, not formulas.
                values = {key: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@'))
                          else value for key, value in values.items()}
                writer.writerow(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Current listing-package.json, including draft candidate audits')
    parser.add_argument('--previous', type=Path, help='Selected baseline package; exact market/variant IDs only')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--csv', type=Path, help='Optional internal candidate coverage table')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8-sig'))
    previous = json.loads(args.previous.read_text(encoding='utf-8-sig')) if args.previous else None
    report = review(data, previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    if args.csv:
        write_csv(report, args.csv)
    for row in report['market_variants']:
        print(f"{row['marketplace']}/{row['variant_id']}: {row.get('characters', 0)} chars, "
              f"{row.get('utf8_bytes', 0)} bytes; {', '.join(row['next_actions']) or 'semantic review'}")


if __name__ == '__main__':
    main()
