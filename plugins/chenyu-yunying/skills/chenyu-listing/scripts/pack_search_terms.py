"""Pack reviewed, priority-ordered product phrases into the UTF-8 byte budget.

This utility does not judge relevance or translate phrases. Supply only candidates
already reviewed against the product and their sources, best candidates first.
"""
import argparse
import json
from pathlib import Path
from validate_listing_package import SEARCH_TERMS_STOP_WORDS, words, visible_source_text


def pack(marketplace, front_end, candidates, limit=249):
    if marketplace not in SEARCH_TERMS_STOP_WORDS:
        raise ValueError('Unsupported marketplace')
    if type(limit) is not int or not 1 <= limit <= 249:
        raise ValueError('Byte limit must be between 1 and 249')
    covered = set(words(visible_source_text(front_end))) | SEARCH_TERMS_STOP_WORDS[marketplace]
    tokens, decisions = [], []
    for phrase in candidates:
        if not isinstance(phrase, str) or not words(phrase):
            raise ValueError('Candidates must be non-empty phrases')
        incremental = list(dict.fromkeys(t for t in words(phrase) if t not in covered))
        new = [t for t in incremental if t not in tokens]
        combined = ' '.join(tokens + new)
        if not incremental:
            decision, reason = 'exclude', 'front_end_covered'
        elif len(combined.encode('utf-8')) > limit:
            decision, reason = 'exclude', 'byte_limit'
        else:
            tokens.extend(new)
            decision, reason = 'adopt', None
        decisions.append({'phrase': phrase, 'decision': decision, 'exclusion_reason': reason})
    result = ' '.join(tokens)
    return {'search_terms': result, 'utf8_bytes': len(result.encode('utf-8')),
            'remaining_bytes': limit - len(result.encode('utf-8')), 'decisions': decisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON: marketplace, front_end, candidates (priority ordered)')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8-sig'))
    result = pack(data['marketplace'], data['front_end'], data['candidates'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(f"{result['utf8_bytes']}/249 UTF-8 bytes: {args.out}")


if __name__ == '__main__':
    main()
