"""Check that an image brief does not reuse Listing copy or SEO structure."""
import argparse
import json
import re
import unicodedata
from pathlib import Path


LISTING_FIELDS = {'title', 'item_name', 'item_highlights', 'bullets', 'description', 'search_terms'}
IMAGE_TEXT_KEYS = {'on_image_text', 'image_text', 'overlay_text', '上图文字', '图片文案'}
LISTING_STRUCTURE_LEAK = re.compile(
    r'(?i)\b(?:search terms|seo keywords?|keyword coverage|bullet point [1-5]|bullet [1-5])\b'
    r'|(?:搜索词|关键词覆盖|五点[一二三四五1-5]|卖点[一二三四五1-5])'
)


def words(value):
    return re.findall(
        r'[^\W_]+', unicodedata.normalize('NFC', str(value)).casefold(), re.UNICODE
    )


def walk_strings(value, path='$'):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_strings(item, f'{path}[{index}]')
    elif isinstance(value, str) and value.strip():
        yield path, value.strip()


def listing_strings(value, path='$'):
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f'{path}.{key}'
            if key in LISTING_FIELDS:
                yield from walk_strings(item, next_path)
            else:
                yield from listing_strings(item, next_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from listing_strings(item, f'{path}[{index}]')


def ngrams(value, size=8):
    tokens = words(value)
    return {
        tuple(tokens[index:index + size])
        for index in range(max(0, len(tokens) - size + 1))
    }


def validate(image_brief, listing_package=None):
    errors, warnings = [], []
    image_strings = list(walk_strings(image_brief))

    for path, value in image_strings:
        if LISTING_STRUCTURE_LEAK.search(value):
            errors.append(
                f'{path} uses Listing/SEO field structure to drive an image task'
            )
        key = path.rsplit('.', 1)[-1]
        if key in IMAGE_TEXT_KEYS and len(words(value)) > 6:
            warnings.append(
                f'{path} has more than 6 words; default image text should be 1-3 words '
                'or necessary numeric labels'
            )

    if listing_package is not None:
        listing_ngrams = {}
        for path, value in listing_strings(listing_package):
            for gram in ngrams(value):
                listing_ngrams.setdefault(gram, path)
        for image_path, value in image_strings:
            for gram in ngrams(value):
                if gram in listing_ngrams:
                    phrase = ' '.join(gram)
                    errors.append(
                        f'{image_path} copies Listing wording from '
                        f'{listing_ngrams[gram]}: {phrase}'
                    )
                    break

    return {
        'ready_for_delivery': not errors,
        'errors': errors,
        'warnings': warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image_brief_package', type=Path)
    parser.add_argument('--listing-package', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    image_brief = json.loads(args.image_brief_package.read_text(encoding='utf-8'))
    listing_package = None
    if args.listing_package:
        listing_package = json.loads(args.listing_package.read_text(encoding='utf-8'))
    result = validate(image_brief, listing_package)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    raise SystemExit(0 if result['ready_for_delivery'] else 1)


if __name__ == '__main__':
    main()
