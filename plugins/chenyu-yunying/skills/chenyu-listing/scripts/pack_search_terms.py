"""Pack reviewed, priority-ordered product phrases into the UTF-8 byte budget.

This utility does not judge relevance or translate phrases. Supply only candidates
already reviewed against the product and their sources, best candidates first.
Optional broad_candidates are relevant fallback terms, used only below 240 bytes
after all precise candidates have been considered; they never replace them.
"""
import argparse
import json
from pathlib import Path
from validate_listing_package import SEARCH_TERMS_STOP_WORDS, words, visible_source_text


def pack(marketplace, front_end, candidates, limit=249, broad_candidates=None):
    if marketplace not in SEARCH_TERMS_STOP_WORDS:
        raise ValueError('Unsupported marketplace')
    if type(limit) is not int or not 1 <= limit <= 249:
        raise ValueError('Byte limit must be between 1 and 249')
    front_tokens = set(words(visible_source_text(front_end)))
    covered = front_tokens | SEARCH_TERMS_STOP_WORDS[marketplace]
    tokens, decisions = [], []
    precise_bytes = 0
    for specificity, pool in (('product_specific', candidates), ('related_broad', broad_candidates or [])):
        for phrase in pool:
            if not isinstance(phrase, str) or not words(phrase):
                raise ValueError('Candidates must be non-empty phrases')
            incremental = list(dict.fromkeys(t for t in words(phrase) if t not in covered))
            new = [t for t in incremental if t not in tokens]
            combined = ' '.join(tokens + new)
            if specificity == 'related_broad' and len(' '.join(tokens).encode('utf-8')) >= min(240, limit):
                decision, reason = 'exclude', 'fallback_not_needed'
            elif not incremental:
                decision, reason = 'exclude', 'front_end_covered'
            elif len(combined.encode('utf-8')) > limit:
                decision, reason = 'exclude', 'byte_limit'
            else:
                tokens.extend(new)
                decision, reason = 'adopt', None
            decisions.append({'phrase': phrase, 'specificity': specificity, 'decision': decision, 'exclusion_reason': reason,
                              'front_end_tokens': list(dict.fromkeys(t for t in words(phrase) if t in front_tokens)),
                              'incremental_tokens': incremental,
                              'added_tokens': new if decision == 'adopt' else []})
        if specificity == 'product_specific':
            precise_bytes = len(' '.join(tokens).encode('utf-8'))
    result = ' '.join(tokens)
    return {'search_terms': result, 'characters': len(result), 'utf8_bytes': len(result.encode('utf-8')),
            'remaining_bytes': limit - len(result.encode('utf-8')),
            'precise_utf8_bytes': precise_bytes,
            'broad_added_tokens': [t for d in decisions if d['specificity'] == 'related_broad' for t in d['added_tokens']],
            'decisions': decisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON: marketplace, front_end, candidates (priority ordered)')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8-sig'))
    result = pack(data['marketplace'], data['front_end'], data['candidates'],
                  broad_candidates=data.get('broad_candidates'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(f"{result['utf8_bytes']}/249 UTF-8 bytes: {args.out}")


if __name__ == '__main__':
    main()
