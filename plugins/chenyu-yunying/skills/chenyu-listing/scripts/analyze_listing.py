"""Deterministic evidence checks, not semantic review or publication approval."""
import argparse
import json
import re
import unicodedata
from pathlib import Path


def tokens(text):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', text).casefold(), re.UNICODE)


def contains(text, phrase):
    hay, needle = tokens(text), tokens(phrase)
    return bool(needle) and any(hay[i:i+len(needle)] == needle for i in range(len(hay)-len(needle)+1))


def fields(record):
    return {'title': record.get('title', ''),
            **{'bullet_' + str(i+1): v for i, v in enumerate(record.get('bullets', []))},
            'description': record.get('description', '')}


def analyze(data):
    competitors = data.get('competitors', [])
    keywords = data.get('keywords', [])
    listings = data.get('listings', [])
    frequency, reviews = [], []
    for kw in keywords:
        market = kw['marketplace']
        phrases = [kw['phrase']] + kw.get('aliases', [])
        candidates = [c for c in competitors if c['marketplace'] == market and c.get('status') in ('complete', 'partial')
                      and any(fields(c).values())]
        groups = {c['product_group'] for c in candidates}
        exact, semantic = set(), set()
        field_groups = {f: set() for f in ('title', 'bullets', 'description')}
        evidence = []
        for c in candidates:
            for f, v in fields(c).items():
                if v:
                    field_groups['bullets' if f.startswith('bullet_') else f].add(c['product_group'])
                if contains(v, kw['phrase']):
                    exact.add(c['product_group'])
                matches = [p for p in phrases if contains(v, p)]
                if matches:
                    semantic.add(c['product_group'])
                    evidence.append({'competitor': c['id'], 'field': f, 'phrases': matches})
        frequency.append({'marketplace': market, 'phrase': kw['phrase'], 'exact_groups': len(exact),
                          'semantic_groups': len(semantic), 'sample_groups': len(groups),
                          'field_sample_groups': {k: len(v) for k, v in field_groups.items()}, 'evidence': evidence})
    for listing in listings:
        fs = fields(listing)
        st = listing.get('search_terms', '')
        all_text = '\n'.join([*fs.values(), st])
        issues, overlaps = [], []
        for brand in data.get('brands', []):
            if contains(all_text, brand):
                issues.append('Known brand candidate: ' + brand)
        if re.search(r'\[(?:marque|brand|品牌)\]', all_text, re.I):
            issues.append('Brand placeholder')
        if re.search(r'\bB0[A-Z0-9]{8}\b', all_text, re.I):
            issues.append('ASIN-like token')
        if len(listing.get('bullets', [])) != 5:
            issues.append('Bullet count is not default five; verify category/user requirements')
        limits = data.get('limits', {}).get(listing['marketplace'], {})
        lengths = {'title_chars': len(fs['title']), 'search_terms_bytes': len(st.encode('utf-8'))}
        for name, count in lengths.items():
            if name in limits and count > limits[name]:
                issues.append(f'{name}: {count} exceeds {limits[name]}')
        for c in competitors:
            if c['marketplace'] != listing['marketplace'] or c.get('status') not in ('complete', 'partial'):
                continue
            source_grams = set()
            for v in fields(c).values():
                ts = tokens(v)
                source_grams.update(tuple(ts[i:i+8]) for i in range(len(ts)-7))
            for f, v in fs.items():
                ts = tokens(v)
                found = sorted({tuple(ts[i:i+8]) for i in range(len(ts)-7)} & source_grams)
                if found:
                    overlaps.append({'competitor': c['id'], 'field': f, 'phrases': [' '.join(x) for x in found]})
        coverage = [{'phrase': k['phrase'], 'exact_locations': [f for f, v in fs.items() if contains(v, k['phrase'])]}
                    for k in keywords if k['marketplace'] == listing['marketplace']]
        reviews.append({'marketplace': listing['marketplace'], 'variant_id': listing.get('variant_id'),
                        'lengths': lengths, 'unverified_limits': [k for k in lengths if k not in limits],
                        'issues': issues, 'overlap_review': overlaps, 'coverage': coverage,
                        'semantic_review_required': True})
    return {'keyword_frequency': frequency, 'listing_reviews': reviews}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = analyze(json.loads(a.input.read_text(encoding='utf-8-sig')))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(str(a.out.resolve()))


if __name__ == '__main__':
    main()
