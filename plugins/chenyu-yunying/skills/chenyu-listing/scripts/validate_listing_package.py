"""Validate that a listing task ends with complete own-product listings."""
import argparse
import json
import re
import unicodedata
from pathlib import Path

MARKETS = {
    'DE': ('de-DE', ('Eigenschaften', 'Produktdetails', 'Lieferumfang')),
    'FR': ('fr-FR', ('Caractéristiques', 'Informations sur le produit', "Contenu de l’emballage")),
    'IT': ('it-IT', ('Caratteristiche', 'Specifiche del prodotto', 'Contenuto della confezione')),
    'ES': ('es-ES', ('Características', 'Especificaciones del producto', 'Contenido del paquete')),
    'UK': ('en-GB', ('Features', 'Product specifications', 'Package contents')),
}
ASIN = re.compile(r'\bB0[A-Z0-9]{8}\b', re.I)
PLACEHOLDER = re.compile(r'\[(?:brand|marque|marca|marke|marchio|品牌|待确认|todo)\]', re.I)
BULLET_FORMAT = re.compile(
    r'^\s*[\U0001F300-\U0001FAFF\u2600-\u27BF]'
    r'[\uFE0F\u200D\U0001F300-\U0001FAFF\u2600-\u27BF]*\s*'
    r'【([^】\r\n]{1,40})】\s*(\S[\s\S]*)$'
)
SEARCH_TERMS_PUNCTUATION = re.compile(r'[,.;:!?|/\\，。；：！？]')
TITLE_TARGET = (150, 190)


def words(text):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', str(text)).casefold(), re.UNICODE)


def contains(text, phrase):
    haystack, needle = words(text), words(phrase)
    return bool(needle) and any(
        haystack[index:index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def validate(data):
    errors, warnings = [], []
    targets = data.get('targets', [])
    variants = data.get('variants', [])
    facts = data.get('facts', [])
    keywords = data.get('keywords', [])
    mappings = data.get('mappings', [])
    listings = data.get('listings', [])
    if not targets:
        errors.append('targets is empty')
    if len(targets) != len(set(targets)):
        errors.append('targets contains duplicates')
    for market in targets:
        if market not in MARKETS:
            errors.append('unsupported target marketplace: ' + str(market))

    variant_ids = [v.get('id') for v in variants]
    if not variants or any(not value for value in variant_ids):
        errors.append('variants must contain non-empty ids')
    if len(variant_ids) != len(set(variant_ids)):
        errors.append('variant ids must be unique')

    keyword_by_key = {}
    for keyword in keywords:
        market = keyword.get('marketplace')
        phrase = str(keyword.get('phrase', '')).strip()
        key = (market, unicodedata.normalize('NFC', phrase).casefold())
        if market not in MARKETS or not phrase:
            errors.append('keywords must contain a supported marketplace and non-empty phrase')
            continue
        if key in keyword_by_key:
            errors.append(f'duplicate keyword for {market}: {phrase}')
            continue
        keyword_by_key[key] = keyword

    fact_by_id = {}
    for fact in facts:
        fact_id = fact.get('id')
        if not fact_id or fact_id in fact_by_id:
            errors.append('fact ids must be non-empty and unique')
            continue
        fact_by_id[fact_id] = fact
        if fact.get('source_type') != 'own_product':
            errors.append(f'fact {fact_id} is not sourced from own_product')
        if fact.get('status') not in ('confirmed', 'unconfirmed', 'conflict'):
            errors.append(f'fact {fact_id} has invalid status')
        source = fact.get('source', {})
        if not isinstance(source, dict) or not any(source.get(k) for k in ('sheet', 'cell', 'file', 'user_message')):
            errors.append(f'fact {fact_id} has no traceable source')

    mapping_by_key = {}
    for mapping in mappings:
        key = (mapping.get('marketplace'), mapping.get('variant_id'))
        if key in mapping_by_key:
            errors.append(f'duplicate mapping for {key[0]}/{key[1]}')
        mapping_by_key[key] = mapping
        if key[0] not in targets or key[1] not in variant_ids:
            errors.append(f'unexpected mapping for {key[0]}/{key[1]}')
        for field in ('fact_ids', 'buying_reasons', 'keywords', 'listing_fields'):
            if not mapping.get(field):
                errors.append(f'mapping {key[0]}/{key[1]} has empty {field}')
        for fact_id in mapping.get('fact_ids', []):
            if fact_id not in fact_by_id:
                errors.append(f'mapping {key[0]}/{key[1]} references unknown fact {fact_id}')
            elif fact_by_id[fact_id].get('status') != 'confirmed':
                errors.append(f'mapping {key[0]}/{key[1]} uses non-confirmed fact {fact_id}')

    expected = set()
    for variant in variants:
        enabled = variant.get('marketplaces', targets)
        for market in enabled:
            if market not in targets:
                errors.append(f'variant {variant.get("id")} enables non-target marketplace {market}')
            else:
                expected.add((market, variant.get('id')))

    listing_by_key = {}
    for listing in listings:
        key = (listing.get('marketplace'), listing.get('variant_id'))
        if key in listing_by_key:
            errors.append(f'duplicate listing for {key[0]}/{key[1]}')
        listing_by_key[key] = listing
        market, variant_id = key
        if key not in expected:
            errors.append(f'unexpected listing for {market}/{variant_id}')
            continue
        language, headings = MARKETS[market]
        if listing.get('language') != language:
            errors.append(f'{market}/{variant_id} language must be {language}')
        title = str(listing.get('title', '')).strip()
        if not title:
            errors.append(f'{market}/{variant_id} title is empty')
        elif '\n' in title or '\r' in title:
            errors.append(f'{market}/{variant_id} title must be one line')
        elif not TITLE_TARGET[0] <= len(title) <= TITLE_TARGET[1]:
            warnings.append(
                f'{market}/{variant_id} title length {len(title)} is outside '
                f'the {TITLE_TARGET[0]}-{TITLE_TARGET[1]} editorial target; '
                'do not add unsupported facts or override verified category limits'
            )
        bullets = listing.get('bullets', [])
        if len(bullets) != 5 or any(not str(item).strip() for item in bullets):
            errors.append(f'{market}/{variant_id} must contain five non-empty bullets')
        else:
            for index, item in enumerate(bullets, 1):
                match = BULLET_FORMAT.fullmatch(str(item).strip())
                if not match:
                    errors.append(
                        f'{market}/{variant_id} bullet {index} must use '
                        'Emoji + 【localized heading】 + body'
                    )
                    continue
                sentence_count = len(re.findall(r'[.!?。！？]+', match.group(2)))
                if not 2 <= sentence_count <= 3:
                    errors.append(
                        f'{market}/{variant_id} bullet {index} body must contain 2-3 sentences'
                    )
        title_keywords = listing.get('title_keywords', [])
        normalized_title_keywords = [
            unicodedata.normalize('NFC', str(item).strip()).casefold()
            for item in title_keywords
        ]
        if (len(title_keywords) != 3 or any(not item for item in normalized_title_keywords)
                or len(set(normalized_title_keywords)) != 3):
            errors.append(f'{market}/{variant_id} title_keywords must contain three distinct phrases')
        else:
            bullet_text = '\n'.join(map(str, bullets))
            for phrase, normalized in zip(title_keywords, normalized_title_keywords):
                keyword = keyword_by_key.get((market, normalized))
                if not keyword:
                    errors.append(
                        f'{market}/{variant_id} title keyword is absent from marketplace keywords: {phrase}'
                    )
                    continue
                forms = [keyword.get('phrase', ''), *keyword.get('aliases', [])]
                forms = [str(form).strip() for form in forms if str(form).strip()]
                if not any(contains(title, form) for form in forms):
                    errors.append(
                        f'{market}/{variant_id} title does not cover keyword or alias: {phrase}'
                    )
                if not any(contains(bullet_text, form) for form in forms):
                    errors.append(
                        f'{market}/{variant_id} bullets do not cover title keyword or alias: {phrase}'
                    )
        title_scene = str(listing.get('title_scene', '')).strip()
        if not title_scene:
            errors.append(f'{market}/{variant_id} title_scene is empty')
        elif not contains(title, title_scene):
            errors.append(f'{market}/{variant_id} title does not contain title_scene: {title_scene}')
        description = str(listing.get('description', ''))
        positions = [description.find(heading) for heading in headings]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            errors.append(f'{market}/{variant_id} description headings are missing or out of order')
        else:
            overview = description[:positions[0]].strip()
            features = description[positions[0] + len(headings[0]):positions[1]]
            details = description[positions[1] + len(headings[1]):positions[2]].strip(' :\n\t')
            package = description[positions[2] + len(headings[2]):].strip(' :\n\t')
            feature_count = len(re.findall(
                r'(?m)^\s*[1-5][.)]\s*[^:\n：]{1,60}[:：]\s*\S', features
            ))
            if not overview:
                errors.append(f'{market}/{variant_id} description overview is empty')
            if not 3 <= feature_count <= 5:
                errors.append(f'{market}/{variant_id} description must contain 3-5 numbered features')
            if not details:
                errors.append(f'{market}/{variant_id} product details block is empty')
            if not package:
                errors.append(f'{market}/{variant_id} package contents block is empty')
        search_terms = str(listing.get('search_terms', '')).strip()
        if not search_terms:
            errors.append(f'{market}/{variant_id} search_terms is empty')
        else:
            if '\n' in search_terms or '\r' in search_terms:
                errors.append(f'{market}/{variant_id} search_terms must be one line')
            if SEARCH_TERMS_PUNCTUATION.search(search_terms):
                errors.append(f'{market}/{variant_id} search_terms must not contain punctuation')
            terms = words(search_terms)
            duplicates = sorted({term for term in terms if terms.count(term) > 1})
            if duplicates:
                errors.append(
                    f'{market}/{variant_id} search_terms repeats tokens: {", ".join(duplicates)}'
                )
        visible = '\n'.join([str(listing.get('title', '')), *map(str, bullets), description,
                             str(listing.get('search_terms', ''))])
        if ASIN.search(visible):
            errors.append(f'{market}/{variant_id} contains an ASIN')
        if PLACEHOLDER.search(visible):
            errors.append(f'{market}/{variant_id} contains a placeholder')
        claim_ids = listing.get('claim_fact_ids', [])
        if not claim_ids:
            errors.append(f'{market}/{variant_id} has no claim_fact_ids')
        for fact_id in claim_ids:
            fact = fact_by_id.get(fact_id)
            if not fact:
                errors.append(f'{market}/{variant_id} references unknown fact {fact_id}')
                continue
            if fact.get('status') != 'confirmed':
                errors.append(f'{market}/{variant_id} uses non-confirmed fact {fact_id}')
            applies = fact.get('variant_ids', [])
            if applies and variant_id not in applies:
                errors.append(f'{market}/{variant_id} uses fact {fact_id} from another variant')
        if key not in mapping_by_key:
            errors.append(f'{market}/{variant_id} has no fact-buying-reason-keyword mapping')
        else:
            mapped = set(mapping_by_key[key].get('fact_ids', []))
            for fact_id in claim_ids:
                if fact_id not in mapped:
                    errors.append(f'{market}/{variant_id} uses fact {fact_id} absent from its mapping')
            mapped_keywords = {
                unicodedata.normalize('NFC', str(value)).casefold()
                for value in mapping_by_key[key].get('keywords', [])
            }
            for phrase in normalized_title_keywords:
                if phrase and phrase not in mapped_keywords:
                    errors.append(
                        f'{market}/{variant_id} title keyword is absent from its mapping: {phrase}'
                    )

    missing = sorted(expected - set(listing_by_key))
    for market, variant_id in missing:
        errors.append(f'missing listing for {market}/{variant_id}')
    for fact in facts:
        if fact.get('status') in ('unconfirmed', 'conflict'):
            warnings.append(f'pending fact {fact.get("id")}: {fact.get("status")}')
    return {
        'ready_for_delivery': not errors,
        'errors': errors,
        'warnings': warnings,
        'coverage': {'expected_listings': len(expected), 'provided_listings': len(listing_by_key),
                     'targets': targets, 'variants': variant_ids},
        'semantic_review_required': True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = validate(json.loads(args.input.read_text(encoding='utf-8-sig')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(str(args.out.resolve()))
    return 0 if result['ready_for_delivery'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
