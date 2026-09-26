"""Validate that a listing task ends with complete own-product listings."""
import argparse
import html
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
INTERNAL_VARIANT_CODE = re.compile(
    r'\b(?:design|diseño|disegno|modèle|modell|modello|variante|variant|style|stil|motif|muster)'
    r'\b\s*[-_:]?\s*[a-z]\b|(?:款式|变体|设计)\s*[-_:：]?\s*[a-z]\b',
    re.I,
)
BULLET_FORMAT = re.compile(
    r'^\s*(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]'
    r'[\uFE0F\u200D\U0001F300-\U0001FAFF\u2600-\u27BF]*\s*)'
    r'【([^】\r\n]{1,40})】\s*(\S[\s\S]*)$'
)
SEARCH_TERMS_PUNCTUATION = re.compile(r'[^\w\s]', re.UNICODE)
BAD_PUNCTUATION_SPACING = re.compile(r'[,;](?=\S)|:(?=[A-Za-zÀ-ÖØ-öø-ÿ])')
TITLE_LIMIT = 75
TITLE_MINIMUM = 68
TITLE_TARGET = (70, 75)
ITEM_HIGHLIGHTS_LIMIT = 125
ITEM_HIGHLIGHTS_TARGET_MINIMUM = 115
BULLET_BODY_MINIMUM = 201
SEARCH_TERMS_MAX_BYTES = 249
FORBIDDEN_TITLE_CHARACTERS = set('!$?_{}^¬¦/')
ALLOWED_DESCRIPTION_TAGS = {'p', 'br', 'b'}
DESCRIPTION_TAG = re.compile(r'<\s*/?\s*([a-zA-Z0-9]+)(?:\s[^>]*)?>')
NOTICE_HEADINGS = {
    'DE': 'Hinweise', 'FR': 'Remarques', 'IT': 'Avvertenze',
    'ES': 'Avisos', 'UK': 'Notes',
}
USE_CARE_HEADINGS = {
    'DE': ('Verwendung', 'Pflege'),
    'FR': ('Utilisation', 'Entretien'),
    'IT': ('Uso', 'Cura'),
    'ES': ('Uso', 'Cuidado'),
    'UK': ('Use', 'Care'),
}
SEARCH_TERMS_STOP_WORDS = {
    'DE': {'ein', 'eine', 'einer', 'eines', 'einem', 'einen', 'und', 'oder', 'bei',
           'für', 'fuer', 'von', 'das', 'die', 'der', 'den', 'dem', 'des', 'mit',
           'zu', 'im', 'in', 'am', 'an'},
    'FR': {'un', 'une', 'des', 'le', 'la', 'les', 'et', 'ou', 'de', 'du', 'en',
           'pour', 'avec', 'sur'},
    'IT': {'un', 'uno', 'una', 'il', 'lo', 'la', 'i', 'gli', 'le', 'e', 'o',
           'di', 'da', 'per', 'con', 'su', 'in'},
    'ES': {'un', 'una', 'unos', 'unas', 'el', 'la', 'los', 'las', 'y', 'o',
           'de', 'del', 'para', 'con', 'en', 'por'},
    'UK': {'a', 'an', 'the', 'and', 'or', 'of', 'for', 'with', 'in', 'on', 'to'},
}
DESCRIPTION_SENTENCE = re.compile(r'[.!?。！？]+')
BUYER_META_PATTERNS = {
    'DE': (
        re.compile(r'\b(?:Käufer|Kunden|Verbraucher)\b', re.I),
        re.compile(
            r'\b(?:Lieferumfang|Packungsinhalt)\b.{0,80}'
            r'\b(?:erkennbar|unterscheidbar|verwechseln|klar)\b', re.I
        ),
        re.compile(
            r'\b(?:erkennbar|unterscheidbar|verwechseln|klar)\b.{0,80}'
            r'\b(?:Lieferumfang|Packungsinhalt)\b', re.I
        ),
    ),
    'FR': (
        re.compile(r'\b(?:acheteur|acheteuse|client|cliente|consommateur|consommatrice)s?\b', re.I),
        re.compile(
            r'\bcontenu (?:du lot|de l[’\']emballage)\b.{0,80}'
            r'\b(?:identifier|distinguer|clair|confondre)\b', re.I
        ),
    ),
    'IT': (
        re.compile(r'\b(?:acquirente|cliente|consumatore|consumatrice)i?\b', re.I),
        re.compile(
            r'\bcontenuto (?:del set|della confezione)\b.{0,80}'
            r'\b(?:identificare|distinguere|chiaro|confondere)\b', re.I
        ),
    ),
    'ES': (
        re.compile(
            r'\b(?:comprador(?:es)?|compradora(?:s)?|cliente(?:s)?|'
            r'consumidor(?:es)?|consumidora(?:s)?)\b', re.I
        ),
        re.compile(
            r'\bcontenido (?:del pack|del paquete)\b.{0,80}'
            r'\b(?:identificar|distinguir|claro|confundir)\b', re.I
        ),
    ),
    'UK': (
        re.compile(r'\b(?:buyer|customer|consumer)s?\b', re.I),
        re.compile(
            r'\b(?:package contents|what is included)\b.{0,80}'
            r'\b(?:identify|distinguish|clear|confuse)\b', re.I
        ),
    ),
}
GENERIC_COHERENCE_PATTERNS = {
    'DE': (re.compile(r'\bzusammengehörige (?:Gruppe|Serie)\b', re.I),
           re.compile(r'\boptisch (?:zusammen|einheitlich)\b', re.I)),
    'FR': (re.compile(r'\bvisuellement cohérent', re.I),
           re.compile(r'\bapparence coordonnée\b', re.I)),
    'IT': (re.compile(r'\baspetto (?:coordinato|uniforme)\b', re.I),
           re.compile(r'\briconoscibile come (?:set|gruppo)\b', re.I)),
    'ES': (re.compile(r'\b(?:aspecto|imagen) (?:coordinado|coordinada|uniforme)\b', re.I),),
    'UK': (re.compile(r'\b(?:coordinated look|cohesive set)\b', re.I),),
}
IMAGE_BRIEF_LEAK_PATTERNS = {
    'DE': (
        re.compile(
            r'\b(?:Bildwirkung|Bildaufbau|Komposition|Kamerawinkel|Nahaufnahme|'
            r'Vordergrund|Hintergrund|visuelle Ebenen)\b', re.I
        ),
        re.compile(r'\bmehr Dynamik in (?:die|der) Szene\b', re.I),
        re.compile(r'\bversetzt.{0,80}\b(?:Ebenen|Gruppe)\b', re.I),
    ),
    'FR': (
        re.compile(
            r'\b(?:composition colorée|composition visuelle|cadrage|gros plan|'
            r'premier plan|arrière-plan|niveaux visuels)\b', re.I
        ),
        re.compile(r'\bplus de mouvement à la scène\b', re.I),
        re.compile(r'\ben décalé.{0,80}\b(?:plusieurs niveaux|petit groupe)\b', re.I),
    ),
    'IT': (
        re.compile(
            r'\b(?:composizione colorata|composizione visiva|inquadratura|primo piano|'
            r'sfondo|livelli visivi)\b', re.I
        ),
        re.compile(r'\bscena più dinamica\b', re.I),
        re.compile(r'\bsfalsat[ei].{0,80}\blivelli differenti\b', re.I),
    ),
    'ES': (
        re.compile(
            r'\b(?:composición colorida|composición visual|encuadre|primer plano|'
            r'fondo|niveles visuales)\b', re.I
        ),
        re.compile(r'\bmás dinamismo\b', re.I),
        re.compile(r'\bescalonad[ao]s?.{0,80}\balturas distintas\b', re.I),
    ),
    'UK': (
        re.compile(
            r'\b(?:visual composition|camera angle|close-up|foreground|background|'
            r'visual layers|framing)\b', re.I
        ),
        re.compile(r'\b(?:add movement to the scene|make the scene more dynamic)\b', re.I),
        re.compile(r'\bstaggered.{0,80}\b(?:different heights|visual layers)\b', re.I),
    ),
}
BLANKET_PROP_DISCLAIMER_PATTERNS = {
    'DE': (re.compile(
        r'\b(?:weitere|andere).{0,40}(?:Dekorationen|Requisiten|Zubehör).{0,60}'
        r'(?:nicht enthalten|nicht im Lieferumfang)\b', re.I
    ),),
    'FR': (re.compile(
        r'\b(?:autres|éléments).{0,40}(?:décoratifs|accessoires).{0,60}'
        r'(?:ne sont pas inclus|non inclus)\b', re.I
    ),),
    'IT': (re.compile(
        r'\b(?:altri|elementi).{0,40}(?:decorativi|accessori).{0,60}'
        r'(?:non sono inclusi|non inclusi)\b', re.I
    ),),
    'ES': (re.compile(
        r'\b(?:otros|demás).{0,40}(?:elementos|decoraciones|accesorios).{0,60}'
        r'(?:no están incluidos|no incluidos)\b', re.I
    ),),
    'UK': (re.compile(
        r'\b(?:other|additional).{0,40}(?:props|decorations|accessories).{0,60}'
        r'(?:not included|not supplied)\b', re.I
    ),),
}


def words(text):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', str(text)).casefold(), re.UNICODE)


def contains(text, phrase):
    haystack, needle = words(text), words(phrase)
    return bool(needle) and any(
        haystack[index:index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def phrase_preceded_by_token(text, phrase, token, lookback=2):
    haystack, needle = words(text), words(phrase)
    if not needle:
        return False
    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index:index + len(needle)] == needle:
            if token in haystack[max(0, index - lookback):index]:
                return True
    return False


def visible_html(text):
    value = str(text)
    value = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', value)
    value = re.sub(r'(?i)</\s*p\s*>', '\n', value)
    value = re.sub(r'<[^>]*>', '', value)
    return html.unescape(value)


def normalized_sentences(text):
    """Return long normalized sentences for exact repetition checks."""
    value = re.sub(r'\s+', ' ', str(text)).strip()
    sentences = []
    for part in DESCRIPTION_SENTENCE.split(value):
        normalized = ' '.join(words(part))
        if len(normalized) >= 24:
            sentences.append(normalized)
    return sentences


def validate_buyer_copy(errors, market, variant_id, labeled_texts):
    """Reject seller-facing narration, generic filler, disclaimers, and repeated sentences."""
    seen_sentences = {}
    for label, value in labeled_texts:
        text = str(value)
        for pattern in BUYER_META_PATTERNS.get(market, ()):
            if pattern.search(text):
                errors.append(
                    f'{market}/{variant_id} {label} contains seller-facing explanation '
                    'instead of buyer-useful product copy'
                )
                break
        for pattern in GENERIC_COHERENCE_PATTERNS.get(market, ()):
            if pattern.search(text):
                errors.append(
                    f'{market}/{variant_id} {label} contains generic coordination filler; '
                    'replace it with a concrete product fact, action, placement, or result'
                )
                break
        for pattern in IMAGE_BRIEF_LEAK_PATTERNS.get(market, ()):
            if pattern.search(text):
                errors.append(
                    f'{market}/{variant_id} {label} contains image-brief or composition '
                    'language; replace it with product facts, real use, fit, or buyer benefit'
                )
                break
        for pattern in BLANKET_PROP_DISCLAIMER_PATTERNS.get(market, ()):
            if pattern.search(text):
                errors.append(
                    f'{market}/{variant_id} {label} contains a blanket prop disclaimer; '
                    'package contents should list included items only unless a specific '
                    'evidence-backed notice is required'
                )
                break
        for sentence in normalized_sentences(text):
            if sentence in seen_sentences:
                errors.append(
                    f'{market}/{variant_id} repeats the same sentence in '
                    f'{seen_sentences[sentence]} and {label}'
                )
            else:
                seen_sentences[sentence] = label


def validate(data):
    errors, warnings = [], []
    targets = data.get('targets', [])
    variants = data.get('variants', [])
    facts = data.get('facts', [])
    competitors = data.get('competitors', [])
    keywords = data.get('keywords', [])
    mappings = data.get('mappings', [])
    listings = data.get('listings', [])
    search_term_audits = data.get('search_term_audits', [])
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
        source_type = fact.get('source_type')
        if source_type not in ('own_product', 'same_product_evidence'):
            errors.append(
                f'fact {fact_id} source_type must be own_product or same_product_evidence'
            )
        if fact.get('status') not in ('confirmed', 'unconfirmed', 'conflict'):
            errors.append(f'fact {fact_id} has invalid status')
        source = fact.get('source', {})
        if not isinstance(source, dict) or not any(
                source.get(k) for k in ('sheet', 'cell', 'file', 'user_message', 'asin')):
            errors.append(f'fact {fact_id} has no traceable source')
        if source_type == 'same_product_evidence':
            if fact.get('same_product_confirmed') is not True:
                errors.append(f'fact {fact_id} lacks explicit same-product confirmation')
            if not isinstance(source, dict) or not ASIN.fullmatch(str(source.get('asin', ''))):
                errors.append(f'fact {fact_id} same-product evidence requires a valid source ASIN')
            if fact.get('status') != 'confirmed':
                errors.append(f'fact {fact_id} same-product evidence must be confirmed')

    audits_by_key = {}
    for audit in search_term_audits:
        key = (audit.get('marketplace'), audit.get('variant_id'))
        audits_by_key.setdefault(key, []).append(audit)
        source_asin = str(audit.get('source_asin', '')).strip()
        if not ASIN.fullmatch(source_asin):
            errors.append(f'search term audit {key[0]}/{key[1]} requires a valid source_asin')
        source_tool = audit.get('source_tool')
        if source_tool not in ('sellersprite_reverse_asin', 'reference_title_terms',
                               'same_category_title_terms'):
            errors.append(
                f'search term audit {key[0]}/{key[1]} source_tool must be '
                'sellersprite_reverse_asin, reference_title_terms, or '
                'same_category_title_terms'
            )
        if (source_tool in ('reference_title_terms', 'same_category_title_terms')
                and audit.get('source_field') != 'title'):
            errors.append(
                f'search term audit {key[0]}/{key[1]} from {source_tool} '
                'must use source_field=title'
            )
        checked = audit.get('organic_results_checked')
        relevant = audit.get('relevant_results')
        if (isinstance(checked, bool) or not isinstance(checked, int) or checked < 20):
            errors.append(
                f'search term audit {key[0]}/{key[1]} must check at least 20 organic results'
            )
            continue
        if (isinstance(relevant, bool) or not isinstance(relevant, int)
                or relevant < 0 or relevant > checked):
            errors.append(
                f'search term audit {key[0]}/{key[1]} has invalid relevant_results'
            )
            continue
        ratio = relevant / checked
        expected_band = 'high' if ratio >= 0.70 else 'medium' if ratio >= 0.40 else 'low'
        if audit.get('relevance_band') != expected_band:
            errors.append(
                f'search term audit {key[0]}/{key[1]} relevance_band must be {expected_band}'
            )
        if audit.get('decision') == 'adopt' and expected_band == 'low':
            errors.append(
                f'search term audit {key[0]}/{key[1]} must not adopt a low-relevance phrase'
            )
        if (audit.get('source_marketplace') != audit.get('marketplace')
                and audit.get('local_volume_claimed') is not False):
            errors.append(
                f'search term audit {key[0]}/{key[1]} must not claim local volume from '
                'another marketplace'
            )

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
        elif BAD_PUNCTUATION_SPACING.search(title) or '  ' in title:
            errors.append(f'{market}/{variant_id} title uses non-standard punctuation spacing')
        if len(title) > TITLE_LIMIT:
            errors.append(
                f'{market}/{variant_id} title uses {len(title)} characters; maximum is {TITLE_LIMIT}'
            )
        elif title and len(title) < TITLE_MINIMUM:
            errors.append(
                f'{market}/{variant_id} title uses {len(title)} characters; minimum internal '
                f'requirement is {TITLE_MINIMUM}'
            )
        elif title and len(title) < TITLE_TARGET[0]:
            warnings.append(
                f'{market}/{variant_id} title length {len(title)} is outside '
                f'the {TITLE_TARGET[0]}-{TITLE_TARGET[1]} editorial target'
            )
        forbidden = sorted(set(title) & FORBIDDEN_TITLE_CHARACTERS)
        if forbidden:
            errors.append(
                f'{market}/{variant_id} title contains forbidden separators or characters: '
                + ' '.join(forbidden)
            )
        title_tokens = words(title)
        repeated_title_tokens = sorted({
            token for token in title_tokens
            if title_tokens.count(token) > 2
            and token not in SEARCH_TERMS_STOP_WORDS.get(market, set())
        })
        if repeated_title_tokens:
            errors.append(
                f'{market}/{variant_id} title repeats content words more than twice: '
                + ', '.join(repeated_title_tokens)
            )
        item_highlights = str(listing.get('item_highlights', '')).strip()
        if not item_highlights:
            errors.append(f'{market}/{variant_id} item_highlights is empty')
        else:
            if '\n' in item_highlights or '\r' in item_highlights:
                errors.append(f'{market}/{variant_id} item_highlights must be one line')
            if BAD_PUNCTUATION_SPACING.search(item_highlights) or '  ' in item_highlights:
                errors.append(
                    f'{market}/{variant_id} item_highlights uses non-standard punctuation spacing'
                )
            if len(item_highlights) > ITEM_HIGHLIGHTS_LIMIT:
                errors.append(
                    f'{market}/{variant_id} item_highlights uses {len(item_highlights)} '
                    f'characters; maximum is {ITEM_HIGHLIGHTS_LIMIT}'
                )
            elif len(item_highlights) < ITEM_HIGHLIGHTS_TARGET_MINIMUM:
                warnings.append(
                    f'{market}/{variant_id} item_highlights length {len(item_highlights)} is below '
                    f'the {ITEM_HIGHLIGHTS_TARGET_MINIMUM}-{ITEM_HIGHLIGHTS_LIMIT} editorial target'
                )
        if competitors:
            title_reference = str(listing.get('title_reference', '')).strip()
            if not title_reference:
                errors.append(f'{market}/{variant_id} title_reference is required when competitor evidence exists')
            description_reference = str(listing.get('description_reference', '')).strip()
            if not description_reference:
                errors.append(f'{market}/{variant_id} description_reference is required when competitor evidence exists')
            search_terms_reference = str(listing.get('search_terms_reference', '')).strip()
            if not search_terms_reference:
                errors.append(f'{market}/{variant_id} search_terms_reference is required when competitor evidence exists')
            item_highlights_reference = str(
                listing.get('item_highlights_reference', '')
            ).strip()
            if not item_highlights_reference:
                errors.append(
                    f'{market}/{variant_id} item_highlights_reference is required when '
                    'competitor evidence exists'
                )
        bullets = listing.get('bullets', [])
        buyer_bullet_texts = []
        if len(bullets) != 5 or any(not str(item).strip() for item in bullets):
            errors.append(f'{market}/{variant_id} must contain five non-empty bullets')
        else:
            for index, item in enumerate(bullets, 1):
                match = BULLET_FORMAT.fullmatch(str(item).strip())
                if not match:
                    errors.append(
                        f'{market}/{variant_id} bullet {index} must use '
                        'a related Emoji + 【localized benefit heading】 + body'
                    )
                    continue
                body = re.sub(r'\s+', ' ', match.group(2)).strip()
                buyer_bullet_texts.append((f'bullet {index}', body))
                sentence_count = len(DESCRIPTION_SENTENCE.findall(body))
                if not 2 <= sentence_count <= 4:
                    errors.append(
                        f'{market}/{variant_id} bullet {index} body must contain 2-4 sentences'
                    )
                if len(body) < BULLET_BODY_MINIMUM:
                    errors.append(
                        f'{market}/{variant_id} bullet {index} body must contain more than '
                        '200 visible characters of substantive copy'
                    )
            if competitors:
                bullet_references = listing.get('bullet_references', [])
                if (len(bullet_references) != 5
                        or any(not str(item).strip() for item in bullet_references)):
                    errors.append(
                        f'{market}/{variant_id} bullet_references must contain five non-empty sources'
                    )
            validate_buyer_copy(errors, market, variant_id, buyer_bullet_texts)
        title_keywords = listing.get('title_keywords', [])
        normalized_title_keywords = [
            unicodedata.normalize('NFC', str(item).strip()).casefold()
            for item in title_keywords
        ]
        if (not 2 <= len(title_keywords) <= 4
                or any(not item for item in normalized_title_keywords)
                or len(set(normalized_title_keywords)) != len(title_keywords)):
            errors.append(
                f'{market}/{variant_id} title_keywords must contain 2-4 distinct phrases'
            )
            first_keyword_forms = []
        else:
            bullet_text = '\n'.join(map(str, bullets))
            first_keyword_forms = []
            for keyword_index, (phrase, normalized) in enumerate(
                    zip(title_keywords, normalized_title_keywords)):
                keyword = keyword_by_key.get((market, normalized))
                if not keyword:
                    errors.append(
                        f'{market}/{variant_id} title keyword is absent from marketplace keywords: {phrase}'
                    )
                    continue
                forms = [keyword.get('phrase', ''), *keyword.get('aliases', [])]
                forms = [str(form).strip() for form in forms if str(form).strip()]
                if keyword_index == 0:
                    first_keyword_forms = forms
                if not any(contains(title, form) for form in forms):
                    errors.append(
                        f'{market}/{variant_id} title does not cover keyword or alias: {phrase}'
                    )
                if keyword.get('is_core') is not True:
                    errors.append(
                        f'{market}/{variant_id} title keyword is not marked as core: {phrase}'
                    )
        title_quantity = listing.get('title_quantity')
        title_quantity_term = str(listing.get('title_quantity_term', '')).strip()
        if (isinstance(title_quantity, bool) or not isinstance(title_quantity, int)
                or title_quantity < 1):
            errors.append(f'{market}/{variant_id} title_quantity must be a positive integer')
        elif title_quantity == 1:
            if title_quantity_term:
                errors.append(
                    f'{market}/{variant_id} title_quantity_term must be empty when title_quantity is 1'
                )
            if first_keyword_forms and any(
                    phrase_preceded_by_token(title, form, '1')
                    for form in first_keyword_forms):
                errors.append(
                    f'{market}/{variant_id} title must omit quantity 1 before the first core keyword'
                )
        else:
            if not title_quantity_term:
                errors.append(
                    f'{market}/{variant_id} title_quantity_term is required when title_quantity exceeds 1'
                )
            elif str(title_quantity) not in title_quantity_term:
                errors.append(
                    f'{market}/{variant_id} title_quantity_term must contain title_quantity '
                    f'{title_quantity}'
                )
            elif first_keyword_forms and not any(
                    contains(title, f'{title_quantity_term} {form}')
                    for form in first_keyword_forms):
                errors.append(
                    f'{market}/{variant_id} title quantity must immediately precede '
                    'the first core keyword or alias'
                )
        color_mode = listing.get('color_mode')
        if color_mode not in ('single', 'multi', 'not_applicable'):
            errors.append(
                f'{market}/{variant_id} color_mode must be single, multi, or not_applicable'
            )
        title_color_terms = listing.get('title_color_terms', [])
        if not isinstance(title_color_terms, list):
            errors.append(f'{market}/{variant_id} title_color_terms must be a list')
            title_color_terms = []
        if color_mode in ('multi', 'not_applicable') and title_color_terms:
            errors.append(
                f'{market}/{variant_id} must not use title_color_terms when color_mode is {color_mode}'
            )
        if color_mode == 'single' and len(title_color_terms) > 1:
            errors.append(f'{market}/{variant_id} single-color title may use at most one color term')
        for color_term in title_color_terms:
            if not contains(title, color_term):
                errors.append(
                    f'{market}/{variant_id} title does not contain declared color term: {color_term}'
                )
            if any(contains(color_term, keyword) or contains(keyword, color_term)
                   for keyword in title_keywords):
                errors.append(
                    f'{market}/{variant_id} color term must not replace a title keyword: {color_term}'
                )
        critical_differentiators = listing.get('critical_differentiators', [])
        if not isinstance(critical_differentiators, list):
            errors.append(f'{market}/{variant_id} critical_differentiators must be a list')
            critical_differentiators = []
        for differentiator in critical_differentiators:
            differentiator = str(differentiator).strip()
            if not differentiator or not contains(title, differentiator):
                errors.append(
                    f'{market}/{variant_id} title does not contain declared critical '
                    f'differentiator: {differentiator}'
                )
                continue
            first_token = words(differentiator)[0]
            token_positions = words(title)
            if first_token in token_positions and token_positions.index(first_token) > 6:
                errors.append(
                    f'{market}/{variant_id} critical differentiator must appear near the front '
                    f'of the title: {differentiator}'
                )
        title_scene = str(listing.get('title_scene', '')).strip()
        if title_scene and not contains(title, title_scene):
            errors.append(f'{market}/{variant_id} title does not contain title_scene: {title_scene}')
        description = str(listing.get('description', ''))
        tags = [tag.casefold() for tag in DESCRIPTION_TAG.findall(description)]
        if not tags:
            errors.append(f'{market}/{variant_id} description must use basic HTML')
        unsupported = sorted(set(tags) - ALLOWED_DESCRIPTION_TAGS)
        if unsupported:
            errors.append(
                f'{market}/{variant_id} description uses unsupported HTML tags: '
                + ', '.join(unsupported)
            )
        description_text = visible_html(description)
        validate_buyer_copy(
            errors, market, variant_id, [('description', description_text)]
        )
        heading_matches = [re.search(r'(?mi)^\s*' + re.escape(heading) + r'\s*:',
                                     description_text)
                           for heading in headings]
        positions = [match.start() if match else -1 for match in heading_matches]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            errors.append(f'{market}/{variant_id} description headings are missing or out of order')
        else:
            overview = description_text[:positions[0]].strip()
            features = description_text[positions[0] + len(headings[0]):positions[1]]
            details = description_text[positions[1] + len(headings[1]):positions[2]].strip(' :\n\t')
            package = description_text[positions[2] + len(headings[2]):].strip(' :\n\t')
            if not overview:
                errors.append(f'{market}/{variant_id} description overview is empty')
            else:
                overview_sentences = len(DESCRIPTION_SENTENCE.findall(overview))
                if not 2 <= overview_sentences <= 3:
                    errors.append(
                        f'{market}/{variant_id} description overview must contain 2-3 sentences'
                    )
            feature_matches = list(re.finditer(
                r'(?m)^\s*[1-5][.)]\s*[^:\n：]{1,60}[:：]\s*\S', features
            ))
            if not 3 <= len(feature_matches) <= 5:
                errors.append(f'{market}/{variant_id} description must contain 3-5 numbered features')
            for index, match in enumerate(feature_matches, 1):
                end = (feature_matches[index].start()
                       if index < len(feature_matches) else len(features))
                feature_text = features[match.start():end].strip()
                feature_body = re.split(r'[:：]', feature_text, maxsplit=1)[-1].strip()
                sentence_count = len(DESCRIPTION_SENTENCE.findall(feature_body))
                if not 2 <= sentence_count <= 4:
                    errors.append(
                        f'{market}/{variant_id} description feature {index} must contain '
                        '2-4 detailed sentences'
                    )
            if not details:
                errors.append(f'{market}/{variant_id} product details block is empty')
            if not package:
                errors.append(f'{market}/{variant_id} package contents block is empty')
            use_care_positions = []
            for heading in USE_CARE_HEADINGS[market]:
                match = re.search(
                    r'(?mi)^\s*' + re.escape(heading) + r'\s*:', description_text
                )
                if match:
                    use_care_positions.append(match.start())
            if use_care_positions and not all(
                    positions[1] < position < positions[2]
                    for position in use_care_positions):
                errors.append(
                    f'{market}/{variant_id} description use/care block must follow product '
                    'details and precede package contents'
                )
            notice_match = re.search(
                r'(?mi)^\s*' + re.escape(NOTICE_HEADINGS[market]) + r'\s*:',
                description_text,
            )
            if notice_match and notice_match.start() <= positions[2]:
                errors.append(f'{market}/{variant_id} description notices must follow package contents')
            if listing.get('notice_fact_ids') and not notice_match:
                errors.append(
                    f'{market}/{variant_id} description must include localized notices '
                    'when notice_fact_ids are provided'
                )

        adopted_secondary = []
        for keyword in keywords:
            if keyword.get('marketplace') != market:
                continue
            phrase = str(keyword.get('phrase', '')).strip()
            normalized = unicodedata.normalize('NFC', phrase).casefold()
            if (not phrase or normalized in normalized_title_keywords
                    or keyword.get('decision') == 'exclude'):
                continue
            forms = [phrase, *keyword.get('aliases', [])]
            adopted_secondary.append([str(form).strip() for form in forms if str(form).strip()])
        front_end_copy = '\n'.join([
            title, item_highlights, *map(str, bullets), description_text,
            *map(str, listing.get('front_end_attributes', [])),
        ])
        for forms in adopted_secondary:
            if not any(contains(front_end_copy, form) for form in forms):
                warnings.append(
                    f'{market}/{variant_id} does not naturally cover available non-title '
                    f'keyword: {forms[0]}'
                )
        search_terms = str(listing.get('search_terms', '')).strip()
        if not search_terms:
            errors.append(f'{market}/{variant_id} search_terms is empty')
        else:
            if '\n' in search_terms or '\r' in search_terms:
                errors.append(f'{market}/{variant_id} search_terms must be one line')
            if search_terms != search_terms.lower():
                errors.append(f'{market}/{variant_id} search_terms must be lowercase')
            if SEARCH_TERMS_PUNCTUATION.search(search_terms):
                errors.append(f'{market}/{variant_id} search_terms must not contain punctuation')
            if re.search(r'[^\S ]', search_terms) or '  ' in search_terms:
                errors.append(
                    f'{market}/{variant_id} search_terms must use single spaces as separators'
                )
            byte_count = len(search_terms.encode('utf-8'))
            if byte_count > SEARCH_TERMS_MAX_BYTES:
                errors.append(
                    f'{market}/{variant_id} search_terms uses {byte_count} UTF-8 bytes; '
                    f'maximum is {SEARCH_TERMS_MAX_BYTES}'
                )
            terms = words(search_terms)
            duplicates = sorted({term for term in terms if terms.count(term) > 1})
            if duplicates:
                errors.append(
                    f'{market}/{variant_id} search_terms repeats tokens: {", ".join(duplicates)}'
                )
            stop_words = sorted(set(terms) & SEARCH_TERMS_STOP_WORDS.get(market, set()))
            if stop_words:
                errors.append(
                    f'{market}/{variant_id} search_terms contains stop words: '
                    + ', '.join(stop_words)
                )
            front_end_words = set(words(front_end_copy))
            overlap = sorted(set(terms) & front_end_words)
            if overlap:
                errors.append(
                    f'{market}/{variant_id} search_terms repeats front-end tokens: '
                    + ', '.join(overlap)
                )
            if competitors:
                primary_asin = str(listing.get('primary_reference_asin', '')).strip()
                if not ASIN.fullmatch(primary_asin):
                    errors.append(
                        f'{market}/{variant_id} primary_reference_asin is required when '
                        'competitor evidence exists'
                    )
                audits = audits_by_key.get(key, [])
                if not audits:
                    errors.append(
                        f'{market}/{variant_id} requires SellerSprite and Amazon search-term audits'
                    )
                else:
                    source_tools = {audit.get('source_tool') for audit in audits}
                    if 'sellersprite_reverse_asin' not in source_tools:
                        errors.append(
                            f'{market}/{variant_id} requires SellerSprite reverse-ASIN '
                            'search-term candidates'
                        )
                    if 'reference_title_terms' not in source_tools:
                        errors.append(
                            f'{market}/{variant_id} requires synonym candidates from reference '
                            'listing titles'
                        )
                    adopted_audits = [
                        audit for audit in audits if audit.get('decision') == 'adopt'
                    ]
                    competitor_asins = {
                        str(competitor.get('asin', '')).strip().upper()
                        for competitor in competitors
                        if ASIN.fullmatch(str(competitor.get('asin', '')).strip())
                    }
                    for audit in audits:
                        audit_asin = str(audit.get('source_asin', '')).strip().upper()
                        if (audit.get('source_tool') == 'sellersprite_reverse_asin'
                                and primary_asin and audit_asin != primary_asin.upper()):
                            errors.append(
                                f'{market}/{variant_id} SellerSprite audit source_asin must '
                                'match primary_reference_asin'
                            )
                        if (audit.get('source_tool') in (
                                'reference_title_terms', 'same_category_title_terms')
                                and audit_asin not in competitor_asins):
                            errors.append(
                                f'{market}/{variant_id} title-term audit source_asin must '
                                'match a competitor record'
                            )
                    adopted_tokens = {
                        token
                        for audit in adopted_audits
                        for token in words(audit.get('phrase', ''))
                    }
                    unaudited = sorted(set(terms) - adopted_tokens)
                    if unaudited:
                        errors.append(
                            f'{market}/{variant_id} search_terms contains tokens without an '
                            f'adopted relevance audit: {", ".join(unaudited)}'
                        )
                    unused_adopted = sorted(
                        adopted_tokens
                        - front_end_words
                        - set(terms)
                        - SEARCH_TERMS_STOP_WORDS.get(market, set())
                    )
                    if unused_adopted:
                        errors.append(
                            f'{market}/{variant_id} search_terms omits audited incremental '
                            f'tokens: {", ".join(unused_adopted)}'
                        )
        visible = '\n'.join([str(listing.get('title', '')), item_highlights,
                             *map(str, bullets), description_text,
                             str(listing.get('search_terms', ''))])
        if ASIN.search(visible):
            errors.append(f'{market}/{variant_id} contains an ASIN')
        if PLACEHOLDER.search(visible):
            errors.append(f'{market}/{variant_id} contains a placeholder')
        allowed_variant_terms = {
            unicodedata.normalize('NFC', str(term)).casefold().strip()
            for term in listing.get('buyer_visible_variant_terms', [])
            if str(term).strip()
        }
        leaked_variant_codes = sorted({
            unicodedata.normalize('NFC', match.group(0)).casefold().strip()
            for match in INTERNAL_VARIANT_CODE.finditer(visible)
            if unicodedata.normalize('NFC', match.group(0)).casefold().strip()
            not in allowed_variant_terms
        })
        if leaked_variant_codes:
            errors.append(
                f'{market}/{variant_id} contains internal variant codes in buyer-visible copy: '
                + ', '.join(leaked_variant_codes)
            )
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
        for fact_id in listing.get('notice_fact_ids', []):
            fact = fact_by_id.get(fact_id)
            if not fact:
                errors.append(f'{market}/{variant_id} notice references unknown fact {fact_id}')
                continue
            if fact.get('status') != 'confirmed':
                errors.append(f'{market}/{variant_id} notice uses non-confirmed fact {fact_id}')
            if fact_id not in claim_ids:
                errors.append(f'{market}/{variant_id} notice fact {fact_id} is absent from claim_fact_ids')
            applies = fact.get('variant_ids', [])
            if applies and variant_id not in applies:
                errors.append(f'{market}/{variant_id} notice uses fact {fact_id} from another variant')
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
