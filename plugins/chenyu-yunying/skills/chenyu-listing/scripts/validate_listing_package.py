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
NUMBERED_BULLET_SOURCE = re.compile(r'\b(B0[A-Z0-9]{8})\s*第\s*([1-5])\s*点', re.I)
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
TITLE_TARGET_MINIMUM = 70
TITLE_MEASUREMENT = re.compile(
    r'(?<!\w)\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?){0,2}'
    r'\s*(?:mm|cm|m|inches?|in|ft|pouces?|pollici|pulgadas?)\b', re.I
)
ITEM_HIGHLIGHTS_LIMIT = 125
ITEM_HIGHLIGHTS_TARGET_MINIMUM = 120
BULLET_BODY_MINIMUM = 201
SEARCH_TERMS_MAX_BYTES = 249
SEARCH_TERMS_TARGET_BYTES = 240
BUYER_FACT_FIELDS = (
    'title', 'item_highlights', 'bullet_1', 'bullet_2', 'bullet_3',
    'bullet_4', 'bullet_5', 'description',
)
FORBIDDEN_TITLE_CHARACTERS = set('!$?_{}^¬¦/')
ALLOWED_DESCRIPTION_TAGS = {'p', 'br', 'b'}
DESCRIPTION_TAG = re.compile(r'<\s*/?\s*([a-zA-Z0-9]+)(?:\s[^>]*)?>')
HTML_LAYOUT_TAG = re.compile(r'<\s*(/?)\s*(p|b|br)\s*/?\s*>', re.I)
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
INTERNAL_PROCESS_PATTERNS = {
    'DE': (
        re.compile(r'\b(?:bestätigt(?:e|er|es|en|em)?|nicht bestätigte?)\s+'
                   r'(?:Lieferumfang|Packungsinhalt|Material|Produktdaten|Angaben)\b', re.I),
        re.compile(r'\b(?:laut|gemäß)\s+(?:den\s+)?(?:Unterlagen|Produktdaten|'
                   r'Verpackungsangaben|Dokumentation)\b', re.I),
        re.compile(r'\b(?:Referenzprodukt|Referenzbild|Wettbewerberprodukt|'
                   r'Konkurrenzprodukt|interne Prüfung)\b', re.I),
        re.compile(r'\bgewählte Variante\b', re.I),
    ),
    'FR': (
        re.compile(r'\b(?:contenu|composition|matériau|données?|informations?)\s+'
                   r'(?:confirmé(?:e|s|es)?|non confirmé(?:e|s|es)?)\b', re.I),
        re.compile(r'\b(?:selon|d[’\']après)\s+(?:les\s+)?(?:documents?|données?|'
                   r'informations?|fiches?|indications? d[’\']emballage)\b', re.I),
        re.compile(r'\b(?:produit|image|photo|article) de référence\b', re.I),
        re.compile(r'\b(?:dimensions?|poids).{0,100}\bconcerne(?:nt)?\s+'
                   r'(?:uniquement\s+)?l[’\']emballage\b', re.I),
        re.compile(r'\b(?:et non de deux pancartes|non sur un éventuel emballage|'
                   r'à vérifier séparément)\b', re.I),
    ),
    'IT': (
        re.compile(r'\b(?:contenuto|composizione|materiale|dati|informazioni)\s+'
                   r'(?:confermat[oaie]|non confermat[oaie])\b', re.I),
        re.compile(r'\b(?:secondo|in base a)\s+(?:i\s+|le\s+)?(?:documenti|dati|'
                   r'informazioni|specifiche della confezione)\b', re.I),
        re.compile(r'\b(?:prodotto|immagine|foto|articolo) di riferimento\b', re.I),
    ),
    'ES': (
        re.compile(r'\b(?:contenido|composición|material|datos|información)\s+'
                   r'(?:confirmad[oa]s?|no confirmad[oa]s?)\b', re.I),
        re.compile(r'\b(?:según|de acuerdo con)\s+(?:los\s+|las\s+)?(?:documentos|'
                   r'datos|información|especificaciones del embalaje)\b', re.I),
        re.compile(r'\b(?:producto|imagen|foto|artículo) de referencia\b', re.I),
    ),
    'UK': (
        re.compile(r'\b(?:confirmed|unconfirmed)\s+(?:contents?|composition|material|'
                   r'product data|information)\b', re.I),
        re.compile(r'\b(?:according to|based on)\s+(?:the\s+)?(?:documents?|product data|'
                   r'packaging records?|packaging information)\b', re.I),
        re.compile(r'\b(?:reference product|reference image|competitor product|'
                   r'internal review)\b', re.I),
    ),
}
CHINESE_INTERNAL_PROCESS_PATTERNS = (
    re.compile(r'(?:已确认|待确认|未确认|未经确认)(?:的)?(?:套装|内容|组成|材质|数据|信息)?'),
    re.compile(r'(?:资料显示|根据.{0,12}资料|包装(?:资料|记录|数据)(?:记录|显示)?)'),
    re.compile(r'(?:开发文档|供应商(?:资料|报价)|内部(?:核对|审核|记录|流程))'),
    re.compile(r'(?:同款竞品|竞品(?:图|图片|链接|产品)|参考(?:产品|商品|图片|链接))'),
    re.compile(r'(?:自有产品|自有套装|与(?:标题|图片|文案)一致)'),
    re.compile(r'(?:不是两块独立的公告牌|而不是包装外尺寸|需要另行确认)'),
)


def words(text):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', str(text)).casefold(), re.UNICODE)


def contains(text, phrase):
    haystack, needle = words(text), words(phrase)
    return bool(needle) and any(
        haystack[index:index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def repeats_pack_count_in_highlights(highlights, quantity, quantity_term, first_keyword_forms):
    """Catch a repeated pack count next to the same product name, not unrelated counts."""
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 1:
        return False
    product_heads = {words(form)[0] for form in first_keyword_forms if words(form)}
    quantity_forms = {str(quantity), str(quantity_term).strip()}
    return any(
        contains(highlights, f'{count_form} {product_head}')
        for count_form in quantity_forms if count_form
        for product_head in product_heads
    )


def contains_identifier(text, identifier):
    """Match model and part identifiers even when Chinese text has no surrounding spaces."""
    normalized_text = unicodedata.normalize('NFC', str(text)).casefold()
    normalized_identifier = unicodedata.normalize('NFC', str(identifier)).casefold().strip()
    return bool(normalized_identifier) and (
        contains(text, identifier) or normalized_identifier in normalized_text
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


def html_layout(text):
    return [f'{"/" if match.group(1) else ""}{match.group(2).lower()}'
            for match in HTML_LAYOUT_TAG.finditer(str(text))]


def description_numbers(text):
    return re.findall(r'(?m)^\s*(\d+)\.\s', visible_html(text))


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
        for pattern in INTERNAL_PROCESS_PATTERNS.get(market, ()):
            if pattern.search(text):
                errors.append(
                    f'{market}/{variant_id} {label} contains internal confirmation, '
                    'source-review, or reference-product language; keep that reasoning '
                    'in fact and reference records, not buyer-facing copy'
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


def validate_chinese_translations(errors, market, variant_id, translations, source_description):
    """Require complete Chinese translations and reject internal workflow narration."""
    if not isinstance(translations, dict):
        errors.append(f'{market}/{variant_id} translations must be an object')
        return
    required = ('title', 'item_highlights', 'description', 'search_terms')
    for field in required:
        if not str(translations.get(field, '')).strip():
            errors.append(f'{market}/{variant_id} Chinese translation for {field} is empty')
    translated_description = str(translations.get('description', ''))
    unsupported = sorted({tag.casefold() for tag in DESCRIPTION_TAG.findall(translated_description)}
                         - ALLOWED_DESCRIPTION_TAGS)
    if unsupported:
        errors.append(
            f'{market}/{variant_id} Chinese description uses unsupported HTML tags: '
            + ', '.join(unsupported)
        )
    if re.search(r'\\(?=<\s*/?\s*(?:p|b|br)\b)', translated_description, re.I):
        errors.append(f'{market}/{variant_id} Chinese description must not escape HTML tags')
    if source_description and html_layout(translated_description) != html_layout(source_description):
        errors.append(
            f'{market}/{variant_id} Chinese description HTML layout must match source description'
        )
    if source_description and description_numbers(translated_description) != description_numbers(source_description):
        errors.append(
            f'{market}/{variant_id} Chinese description feature numbers must match source description'
        )
    bullets = translations.get('bullets', [])
    if (not isinstance(bullets, list) or len(bullets) != 5
            or any(not str(item).strip() for item in bullets)):
        errors.append(
            f'{market}/{variant_id} Chinese translations must contain five non-empty bullets'
        )
        bullets = []
    labeled_texts = [
        ('title', translations.get('title', '')),
        ('item_highlights', translations.get('item_highlights', '')),
        *[(f'bullet {index}', value) for index, value in enumerate(bullets, 1)],
        ('description', visible_html(translations.get('description', ''))),
        ('search_terms', translations.get('search_terms', '')),
    ]
    for label, value in labeled_texts:
        text = str(value)
        for pattern in CHINESE_INTERNAL_PROCESS_PATTERNS:
            if pattern.search(text):
                errors.append(
                    f'{market}/{variant_id} Chinese translation {label} contains internal '
                    'confirmation, source-review, competitor-reference, or seller workflow '
                    'language; translate only the buyer-facing product claim'
                )
                break


def validate_compatibility_copy(errors, market, variant_id, listing, title,
                                item_highlights, bullets, description):
    """Ensure fitment-dependent products expose confirmed compatibility identifiers."""
    required = listing.get('compatibility_required', False)
    if not isinstance(required, bool):
        errors.append(f'{market}/{variant_id} compatibility_required must be boolean')
        return
    if not required:
        return
    terms = listing.get('compatibility_terms', [])
    if (not isinstance(terms, list) or not terms
            or any(not str(term).strip() for term in terms)):
        errors.append(
            f'{market}/{variant_id} compatibility_terms must contain confirmed model, '
            'series, or replacement-part identifiers when compatibility_required=true'
        )
        return
    normalized_terms = [str(term).strip() for term in terms]
    if len({unicodedata.normalize('NFC', term).casefold()
            for term in normalized_terms}) != len(normalized_terms):
        errors.append(f'{market}/{variant_id} compatibility_terms must be unique')
    primary = str(listing.get('primary_compatibility_term', '')).strip()
    if not primary:
        errors.append(f'{market}/{variant_id} primary_compatibility_term is required')
    elif not any(contains_identifier(term, primary)
                 or contains_identifier(primary, term)
                 for term in normalized_terms):
        errors.append(
            f'{market}/{variant_id} primary_compatibility_term must be represented in '
            'compatibility_terms'
        )
    elif not contains_identifier(title, primary):
        errors.append(
            f'{market}/{variant_id} title must contain primary compatibility term: {primary}'
        )
    target_copy = f'{title} {item_highlights}'
    missing_target = [
        term for term in normalized_terms if not contains_identifier(target_copy, term)
    ]
    if missing_target:
        errors.append(
            f'{market}/{variant_id} title and item_highlights omit confirmed compatibility '
            'terms: ' + ', '.join(missing_target)
        )
    if primary and (not isinstance(bullets, list) or not bullets
                    or not contains_identifier(bullets[0], primary)):
        errors.append(
            f'{market}/{variant_id} bullet 1 must lead with primary compatibility term: '
            f'{primary}'
        )
    missing_description = [
        term for term in normalized_terms if not contains_identifier(description, term)
    ]
    if missing_description:
        errors.append(
            f'{market}/{variant_id} description omits confirmed compatibility terms: '
            + ', '.join(missing_description)
        )
    translations = listing.get('translations')
    if isinstance(translations, dict):
        translated_copy = (
            f'{translations.get("title", "")} '
            f'{translations.get("item_highlights", "")}'
        )
        missing_translation = [
            term for term in normalized_terms
            if not contains_identifier(translated_copy, term)
        ]
        if missing_translation:
            errors.append(
                f'{market}/{variant_id} Chinese title and item_highlights omit confirmed '
                'compatibility terms: ' + ', '.join(missing_translation)
            )
        translated_bullets = translations.get('bullets', [])
        if primary and (not isinstance(translated_bullets, list)
                        or not translated_bullets
                        or not contains_identifier(translated_bullets[0], primary)):
            errors.append(
                f'{market}/{variant_id} Chinese bullet 1 must contain primary '
                f'compatibility term: {primary}'
            )
        translated_description = visible_html(translations.get('description', ''))
        missing_translated_description = [
            term for term in normalized_terms
            if not contains_identifier(translated_description, term)
        ]
        if missing_translated_description:
            errors.append(
                f'{market}/{variant_id} Chinese description omits confirmed '
                'compatibility terms: ' + ', '.join(missing_translated_description)
            )


def validate_field_fact_ids(errors, market, variant_id, listing, fact_by_id):
    """Require every substantive buyer field to declare its confirmed fact sources."""
    field_fact_ids = listing.get('field_fact_ids')
    if not isinstance(field_fact_ids, dict):
        errors.append(f'{market}/{variant_id} field_fact_ids must be an object')
        return
    claim_ids = listing.get('claim_fact_ids', [])
    claim_id_set = set(claim_ids) if isinstance(claim_ids, list) else set()
    used_ids = set()
    for field in BUYER_FACT_FIELDS:
        fact_ids = field_fact_ids.get(field)
        if (not isinstance(fact_ids, list) or not fact_ids
                or any(not str(fact_id).strip() for fact_id in fact_ids)):
            errors.append(
                f'{market}/{variant_id} field_fact_ids.{field} must contain at least '
                'one confirmed fact id'
            )
            continue
        if len(fact_ids) != len(set(fact_ids)):
            errors.append(
                f'{market}/{variant_id} field_fact_ids.{field} contains duplicate fact ids'
            )
        for fact_id in fact_ids:
            used_ids.add(fact_id)
            fact = fact_by_id.get(fact_id)
            if not fact:
                errors.append(
                    f'{market}/{variant_id} field_fact_ids.{field} references unknown '
                    f'fact {fact_id}'
                )
                continue
            if fact.get('status') != 'confirmed':
                errors.append(
                    f'{market}/{variant_id} field_fact_ids.{field} uses non-confirmed '
                    f'fact {fact_id}'
                )
            applies = fact.get('variant_ids', [])
            if applies and variant_id not in applies:
                errors.append(
                    f'{market}/{variant_id} field_fact_ids.{field} uses fact {fact_id} '
                    'from another variant'
                )
            if fact_id not in claim_id_set:
                errors.append(
                    f'{market}/{variant_id} field_fact_ids.{field} uses fact {fact_id} '
                    'absent from claim_fact_ids'
                )
    unused = sorted(claim_id_set - used_ids)
    if unused:
        errors.append(
            f'{market}/{variant_id} claim_fact_ids contains facts not assigned to a '
            'buyer field: ' + ', '.join(unused)
        )



def source_text(competitor, source_field):
    if source_field in ('title', 'description', 'aplus_text'):
        return str(competitor.get(source_field, ''))
    match = re.fullmatch(r'bullet_([1-5])', str(source_field))
    bullets = competitor.get('bullets', [])
    if match and isinstance(bullets, list) and len(bullets) >= int(match.group(1)):
        return str(bullets[int(match.group(1)) - 1])
    return ''


def validate_phrase_sources(errors, market, variant_id, listing, field, competitors, fact_by_id, strict=False):
    key = f'{field}_phrase_sources'
    sources = listing.get(key)
    if not isinstance(sources, list) or not sources:
        errors.append(f'{market}/{variant_id} {key} must map meaningful phrases to sources')
        return
    copy = str(listing.get(field, ''))
    reference = str(listing.get(f'{field}_reference', ''))
    competitor_keywords = set()
    has_competitor_source = False
    reference_segments = re.split(r'[；;\n]', reference)
    for source in sources:
        if not isinstance(source, dict):
            errors.append(f'{market}/{variant_id} {key} entries must be objects')
            continue
        phrase = str(source.get('phrase', '')).strip()
        if not phrase or phrase.casefold() not in copy.casefold():
            errors.append(f'{market}/{variant_id} {key} phrase must appear in {field}: {phrase}')
            continue
        if phrase.casefold() not in reference.casefold():
            errors.append(f'{market}/{variant_id} {key} phrase missing from visible reference: {phrase}')
        asin = str(source.get('asin', '')).strip().upper()
        if asin:
            source_field = str(source.get('source_field', '')).strip()
            source_phrase = str(source.get('source_phrase', '')).strip()
            if field == 'title' and source_field != 'title':
                errors.append(f'{market}/{variant_id} {key} must use competitor title sources only')
                continue
            matches = [item for item in competitors
                       if str(item.get('asin', '')).strip().upper() == asin]
            if not matches or source_field not in ('title', *(f'bullet_{i}' for i in range(1, 6))):
                errors.append(f'{market}/{variant_id} {key} invalid competitor source: {asin}/{source_field}')
                continue
            if not source_phrase or not any(source_phrase.casefold() in source_text(item, source_field).casefold()
                                            for item in matches):
                errors.append(f'{market}/{variant_id} {key} source_phrase not found in {asin}/{source_field}: {source_phrase}')
            label = '标题' if source_field == 'title' else f'第{source_field[-1]}点'
            citation = f'{asin} {label}'
            if not any(phrase.casefold() in segment.casefold()
                       and citation in segment.upper()
                       and (not strict or source_phrase.casefold() in segment.casefold())
                       for segment in reference_segments):
                errors.append(f'{market}/{variant_id} {key} visible reference must map {phrase} to {citation}')
            has_competitor_source = True
            if field == 'title':
                competitor_keywords.add(str(source.get('keyword', phrase)).strip().casefold())
        else:
            fact_id = str(source.get('fact_id', '')).strip()
            fact = fact_by_id.get(fact_id)
            if not fact or fact.get('status') != 'confirmed' or variant_id not in fact.get('variant_ids', []):
                errors.append(f'{market}/{variant_id} {key} requires a confirmed applicable fact: {fact_id}')
            if fact_id not in listing.get('field_fact_ids', {}).get(field, []):
                errors.append(f'{market}/{variant_id} {key} fact {fact_id} is absent from field_fact_ids.{field}')
            if not any(phrase.casefold() in segment.casefold()
                       and fact_id in segment for segment in reference_segments):
                errors.append(f'{market}/{variant_id} {key} visible reference must map {phrase} to fact {fact_id}')
    if competitors and not has_competitor_source:
        errors.append(f'{market}/{variant_id} {key} needs at least one competitor title/bullet source')
    if competitors and field == 'title':
        for keyword in listing.get('title_keywords', []):
            if str(keyword).strip().casefold() not in competitor_keywords:
                errors.append(f'{market}/{variant_id} title keyword needs a competitor title source: {keyword}')


def visible_source_text(value):
    """Normalize HTML boundaries without joining words from adjacent blocks."""
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value)))).strip()


def validate_source_coverage(errors, context, copy, fragments):
    text = visible_source_text(copy).casefold()
    covered = [False] * len(text)
    for fragment in fragments:
        phrase = visible_source_text(fragment).casefold()
        if not phrase:
            continue
        for match in re.finditer(re.escape(phrase), text):
            covered[match.start():match.end()] = [True] * len(match.group())
    missing = [match.group() for match in re.finditer(r'\w+', text)
               if not all(covered[match.start():match.end()])]
    if missing:
        errors.append(f'{context} has text without source coverage: ' + ', '.join(missing[:12]))


def validate_clause_sources(errors, market, variant_id, listing, competitors, fact_by_id):
    mappings = listing.get('clause_sources')
    if not isinstance(mappings, dict):
        errors.append(f'{market}/{variant_id} clause_sources must map bullets and description')
        return
    for field in (*(f'bullet_{i}' for i in range(1, 6)), 'description'):
        context = f'{market}/{variant_id} clause_sources.{field}'
        entries = mappings.get(field)
        if not isinstance(entries, list) or not entries:
            errors.append(f'{context} must contain sourced short clauses')
            continue
        if field == 'description':
            copy = listing.get(field, '')
            reference = str(listing.get('description_reference', ''))
        else:
            index = int(field[-1]) - 1
            bullets, references = listing.get('bullets', []), listing.get('bullet_references', [])
            copy = bullets[index] if isinstance(bullets, list) and len(bullets) > index else ''
            reference = str(references[index]) if isinstance(references, list) and len(references) > index else ''
        fragments = []
        bullet_source_found = False
        description_source_found = False
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append(f'{context} entries must be objects')
                continue
            text = visible_source_text(entry.get('text', ''))
            if not text or text.casefold() not in visible_source_text(copy).casefold():
                errors.append(f'{context} text must appear in target copy: {text}')
                continue
            fragments.append(text)
            if entry.get('kind') == 'editorial':
                if not str(entry.get('reason', '')).strip() or entry.get('sources'):
                    errors.append(f'{context} editorial text needs a reason and no claimed sources')
                continue  # Semantic review must reject factual claims disguised as headings/connectives.
            sources = entry.get('sources')
            if not isinstance(sources, list) or not sources:
                errors.append(f'{context} text requires actual sources: {text}')
                continue
            for source in sources:
                if not isinstance(source, dict):
                    errors.append(f'{context} source must be an object')
                    continue
                asin = str(source.get('asin', '')).strip().upper()
                if asin:
                    source_field = str(source.get('source_field', ''))
                    original = visible_source_text(source.get('source_phrase', ''))
                    if field.startswith('bullet_') and source_field not in tuple(f'bullet_{i}' for i in range(1, 6)):
                        errors.append(f'{context} must use competitor bullet sources only')
                        continue
                    allowed = ('title', 'description', 'aplus_text', *(f'bullet_{i}' for i in range(1, 6)))
                    matches = [item for item in competitors
                               if str(item.get('asin', '')).upper() == asin]
                    if source_field not in allowed or not original or not any(
                        original.casefold() in visible_source_text(source_text(item, source_field)).casefold()
                        for item in matches
                    ):
                        errors.append(f'{context} source_phrase not found in {asin}/{source_field}')
                    else:
                        if source_field.startswith('bullet_'):
                            bullet_source_found = True
                        if source_field != 'title':
                            description_source_found = True
                    label = {'title': '标题', 'description': '详情', 'aplus_text': 'A+'}.get(source_field)
                    if label is None:
                        label = f'第{source_field[-1:]}点'
                    required = [text, f'{asin} {label}', original]
                else:
                    fact_id = str(source.get('fact_id', ''))
                    fact = fact_by_id.get(fact_id, {})
                    if (fact.get('status') != 'confirmed'
                            or variant_id not in fact.get('variant_ids', [])
                            or fact_id not in listing.get('field_fact_ids', {}).get(field, [])):
                        errors.append(f'{context} requires a confirmed applicable field fact: {fact_id}')
                    required = [text, fact_id]
                # A clause and its source must occur together, not somewhere in a global citation list.
                segments = re.split(r'[；;\n]', reference)
                if not any(all(value.casefold() in visible_source_text(segment).casefold()
                               for value in required) for segment in segments):
                    errors.append(f'{context} visible reference must map clause and original source: {text}')
        validate_source_coverage(errors, context, copy, fragments)
        if competitors and field.startswith('bullet_') and not bullet_source_found:
            errors.append(f'{context} needs an actual competitor bullet source for a clause')
        if competitors and field == 'description' and not description_source_found:
            errors.append(f'{context} needs actual competitor bullet/description/A+ content, not only own facts')


def validate_numbered_bullet_references(errors, market, variant_id, listing, competitors):
    references = listing.get('bullet_references', [])
    if not isinstance(references, list) or len(references) != 5 or any(not str(item).strip() for item in references):
        errors.append(f'{market}/{variant_id} bullet_references must contain five non-empty sources')
        return
    for index, reference in enumerate(references, 1):
        pairs = NUMBERED_BULLET_SOURCE.findall(str(reference))
        if not pairs:
            errors.append(f'{market}/{variant_id} bullet {index} reference must cite ASIN 第N点 from an actual competitor bullet')
            continue
        for asin, number in pairs:
            if not any(source_text(item, f'bullet_{number}').strip()
                       for item in competitors
                       if str(item.get('asin', '')).strip().upper() == asin.upper()):
                errors.append(f'{market}/{variant_id} bullet {index} cites missing competitor point: {asin.upper()} 第{number}点')


def validate_search_localization(errors, audit, *, source_supported=False):
    """Check the source-to-local-query record, not the translation's semantics."""
    label = f"search term audit {audit.get('marketplace')}/{audit.get('variant_id')}"
    target = MARKETS.get(audit.get('marketplace'), ('', ()))[0].split('-')[0]
    source_phrase = audit.get('source_phrase')
    source_language = audit.get('source_language')
    if not isinstance(audit.get('phrase'), str) or not audit['phrase'].strip():
        errors.append(f'{label} requires a non-empty localized phrase')
    if not isinstance(source_phrase, str) or not source_phrase.strip():
        errors.append(f'{label} requires the original source_phrase')
    if not isinstance(source_language, str) or not re.fullmatch(r'[a-z]{2}', source_language):
        errors.append(f'{label} requires source_language as a two-letter language code')
    if audit.get('target_language') != target:
        errors.append(f'{label} target_language must be {target}')
    if source_language != target:
        if audit.get('localization_method') != 'ai':
            errors.append(f'{label} must AI-localize foreign source terms before review')
        if (isinstance(source_phrase, str)
                and words(source_phrase) == words(audit.get('phrase', ''))
                and not str(audit.get('localization_note') or '').strip()):
            errors.append(f'{label} unchanged foreign phrase requires a local-usage explanation')
    if not source_supported and (audit.get('search_marketplace') != audit.get('marketplace')
            or not words(audit.get('phrase', ''))
            or words(audit.get('search_query', '')) != words(audit.get('phrase', ''))):
        errors.append(f'{label} must search the localized phrase in the target marketplace')
    if not source_supported and (not isinstance(audit.get('search_evidence'), str) or not audit['search_evidence'].strip()):
        errors.append(f'{label} requires search_evidence for the actual local query')
    if audit.get('decision') not in ('adopt', 'exclude'):
        errors.append(f'{label} decision must be adopt or exclude')
    if audit.get('decision') == 'exclude':
        if audit.get('exclusion_reason') not in (
                'front_end_covered', 'product_mismatch', 'low_relevance', 'byte_limit'):
            errors.append(f'{label} exclusion must be based on localized coverage, product match, relevance or bytes; source language and absent local volume are not exclusion reasons')
        detail = audit.get('exclusion_detail')
        if not isinstance(detail, str) or not detail.strip():
            errors.append(f'{label} requires candidate-specific exclusion_detail')
        if (audit.get('exclusion_reason') == 'low_relevance'
                and audit.get('relevance_band') == 'high'):
            errors.append(f'{label} cannot exclude a high-relevance phrase as low_relevance')


def validate_search_coverage(data, errors):
    """Reconcile raw research, semantic concepts and prior output with decisions."""
    concepts = data.get('search_term_concepts')
    inventory = data.get('search_query_inventory')
    if not isinstance(concepts, list) or not concepts:
        errors.append('search_term_concepts must list the source concepts before localization')
        concepts = []
    concept_ids = set()
    for concept in concepts:
        if (not isinstance(concept, dict) or not isinstance(concept.get('id'), str)
                or not concept['id'].strip() or not str(concept.get('source_phrase') or '').strip()
                or not str(concept.get('meaning') or '').strip()):
            errors.append('search_term_concepts requires id, source_phrase and meaning')
            continue
        if concept['id'] in concept_ids:
            errors.append('search_term_concepts has duplicate id: ' + concept['id'])
        concept_ids.add(concept['id'])
    if not isinstance(inventory, list):
        errors.append('search_query_inventory must be collected from all saved query files')
        inventory = []
    for listing in data.get('listings', []):
        market, variant = listing.get('marketplace'), listing.get('variant_id')
        label = f'{market}/{variant}'
        audits = [a for a in data.get('search_term_audits', [])
                  if a.get('marketplace') == market and a.get('variant_id') == variant]
        audited_ids = {a.get('concept_id') for a in audits}
        if concept_ids - audited_ids:
            errors.append(f'{label} omits source concepts: {", ".join(sorted(concept_ids - audited_ids))}')
        if any(a.get('concept_id') not in concept_ids for a in audits):
            errors.append(f'{label} audit must reference a known concept_id')
        queried = {tuple(words(a.get('search_query', ''))) for a in audits if a.get('search_query')}
        exclusions = listing.get('search_query_exclusions', [])
        for entry in exclusions if isinstance(exclusions, list) else []:
            if (isinstance(entry, dict) and entry.get('reason') in
                    ('front_end_covered', 'product_mismatch', 'low_relevance', 'byte_limit', 'invalid_capture')
                    and str(entry.get('detail') or '').strip()):
                queried.add(tuple(words(entry.get('query', ''))))
        for query in inventory:
            if (isinstance(query, dict) and query.get('marketplace') == market
                    and tuple(words(query.get('query', ''))) not in queried):
                errors.append(f'{label} saved search query has no decision: {query.get("query", "")}')
        previous = set(words(listing.get('previous_search_terms', '')))
        front = ' '.join([str(listing.get('title', '')), str(listing.get('item_highlights', '')),
                          *map(str, listing.get('bullets', [])),
                          re.sub(r'<[^>]+>', ' ', str(listing.get('description', ''))),
                          *map(str, listing.get('front_end_attributes', []))])
        removed = previous - set(words(listing.get('search_terms', ''))) - set(words(front))
        previous_exclusions = listing.get('previous_term_exclusions', [])
        for entry in previous_exclusions if isinstance(previous_exclusions, list) else []:
            if (isinstance(entry, dict) and entry.get('reason') in
                    ('product_mismatch', 'low_relevance', 'byte_limit')
                    and str(entry.get('detail') or '').strip()):
                removed -= set(words(entry.get('term', '')))
        if removed:
            errors.append(f'{label} prior search terms removed without review: {", ".join(sorted(removed))}')


def validate(data, *, require_current_search_policy=True):
    errors, warnings = [], []
    search_policy = data.get('search_term_policy_version', 1)
    if type(search_policy) is not int or search_policy not in (1, 2, 3, 4):
        errors.append('search_term_policy_version must be 1, 2, 3 or 4')
    if require_current_search_policy and search_policy != 4:
        errors.append('Delivery requires search_term_policy_version=4 with AI localization and candidate-level expansion review')
    if search_policy in (1, 2, 3):
        warnings.append('Legacy search-term policy: upgrade to search_term_policy_version=4 before delivery')
    mapping_version = data.get('source_mapping_version', 1)
    if mapping_version not in (1, 2):
        errors.append('source_mapping_version must be 1 or 2')
    if mapping_version == 1:
        warnings.append('Legacy source mapping: upgrade to source_mapping_version=2 for clause-level traceability')
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
        if source_type not in (
            'own_product', 'same_product_evidence', 'material_match_evidence'
        ):
            errors.append(
                f'fact {fact_id} source_type must be own_product, '
                'same_product_evidence, or material_match_evidence'
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
        source_supported = search_policy == 4 and audit.get('relevance_basis') == 'source_product_match'
        if search_policy in (3, 4):
            validate_search_localization(errors, audit, source_supported=source_supported)
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
        if (search_policy == 4 and audit.get('decision') == 'adopt'
                and audit.get('search_intent') == 'different_product'):
            errors.append(f'search term audit {key[0]}/{key[1]} cannot adopt a different-product search intent')
        if source_supported:
            ids = audit.get('relevance_fact_ids')
            valid_facts = {f.get('id') for f in facts if f.get('status') == 'confirmed'
                           and f.get('source_type') in ('own_product', 'same_product_evidence', 'material_match_evidence')
                           and (not f.get('variant_ids') or audit.get('variant_id') in f['variant_ids'])}
            if (audit.get('decision') == 'adopt' and (not isinstance(ids, list) or not ids
                    or any(not isinstance(i, str) or i not in valid_facts for i in ids))):
                errors.append(f'search term audit {key[0]}/{key[1]} source_product_match requires applicable confirmed relevance_fact_ids')
            if (not str(audit.get('source_evidence') or '').strip()
                    or (audit.get('decision') == 'adopt' and (audit.get('specificity') != 'product_specific'
                    or not str(audit.get('product_match_reason') or '').strip()))):
                errors.append(f'search term audit {key[0]}/{key[1]} source_product_match requires specific source evidence and product match explanation')
            if audit.get('decision') == 'adopt' and audit.get('search_intent') not in ('same_product', 'not_measured'):
                errors.append(f'search term audit {key[0]}/{key[1]} source evidence cannot override a different-product search intent')
            if audit.get('local_volume_claimed') is not False:
                errors.append(f'search term audit {key[0]}/{key[1]} source evidence does not establish local search volume')
            if audit.get('relevance_band') == 'not_measured':
                if audit.get('organic_results_checked') is not None or audit.get('relevant_results') is not None:
                    errors.append(f'search term audit {key[0]}/{key[1]} unmeasured search must not contain invented counts')
                continue
        checked = audit.get('organic_results_checked')
        relevant = audit.get('relevant_results')
        minimum_checked = 1 if search_policy == 4 else 20
        if (isinstance(checked, bool) or not isinstance(checked, int) or checked < minimum_checked):
            errors.append(
                f'search term audit {key[0]}/{key[1]} must check at least {minimum_checked} organic results'
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
        if search_policy != 4 and audit.get('decision') == 'adopt' and expected_band == 'low':
            errors.append(
                f'search term audit {key[0]}/{key[1]} must not adopt a low-relevance phrase'
            )
        if search_policy in (2, 3, 4) and audit.get('decision') == 'adopt':
            if search_policy != 4 and expected_band != 'high':
                errors.append(f'search term audit {key[0]}/{key[1]} must adopt only high-relevance phrases')
            if audit.get('specificity') != 'product_specific':
                errors.append(f'search term audit {key[0]}/{key[1]} must be product_specific, not generic')
            reason = audit.get('product_match_reason')
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f'search term audit {key[0]}/{key[1]} requires product_match_reason')
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
        elif title and len(title) < TITLE_TARGET_MINIMUM:
            warnings.append(
                f'{market}/{variant_id} title length {len(title)} is below '
                f'the {TITLE_TARGET_MINIMUM}-{TITLE_LIMIT} editorial target; '
                'only add source-backed, relevant words to approach the limit'
            )
        title_measurements = list(TITLE_MEASUREMENT.finditer(title))
        title_size_term = str(listing.get('title_size_term', '')).strip()
        title_size_reason = str(listing.get('title_size_reason', '')).strip()
        if len(title_measurements) > 1:
            errors.append(f'{market}/{variant_id} title may contain at most one size group')
        if title_measurements:
            measurement = title_measurements[0]
            if measurement.end() != len(title):
                errors.append(f'{market}/{variant_id} title size must appear at the end')
            if not title_size_term or measurement.group().casefold() != title_size_term.casefold():
                errors.append(f'{market}/{variant_id} title_size_term must match the title size')
            if not title_size_reason:
                errors.append(
                    f'{market}/{variant_id} title_size_reason must record the competitor '
                    'title source and any product-specific correction'
                )
        elif title_size_term or title_size_reason:
            errors.append(
                f'{market}/{variant_id} title_size_term and title_size_reason '
                'must be empty without a title size'
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
        validate_buyer_copy(
            errors, market, variant_id,
            [('title', title), ('item_highlights', item_highlights)],
        )
        if competitors:
            title_reference = str(listing.get('title_reference', '')).strip()
            if not title_reference:
                errors.append(f'{market}/{variant_id} title_reference is required when competitor evidence exists')
            elif mapping_version == 1:
                # Legacy references included the candidate audit. V2 visible references
                # cite only adopted phrases, checked by validate_phrase_sources below.
                usable_title_asins = sorted({
                    str(competitor.get('asin', '')).strip().upper()
                    for competitor in competitors
                    if ASIN.fullmatch(str(competitor.get('asin', '')).strip())
                    and str(competitor.get('title', '')).strip()
                })
                missing_title_sources = [
                    asin for asin in usable_title_asins
                    if asin not in title_reference.upper()
                ]
                if missing_title_sources:
                    errors.append(
                        f'{market}/{variant_id} title_reference must cite every usable '
                        'competitor title: ' + ', '.join(missing_title_sources)
                    )
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
            for field in ('title', 'item_highlights'):
                validate_phrase_sources(
                    errors, market, variant_id, listing, field, competitors, fact_by_id, strict=mapping_version == 2
                )
        if mapping_version == 2:
            validate_clause_sources(errors, market, variant_id, listing, competitors, fact_by_id)
            for field in ('title', 'item_highlights'):
                if not competitors:
                    validate_phrase_sources(errors, market, variant_id, listing, field, competitors, fact_by_id, strict=True)
                entries = listing.get(f'{field}_phrase_sources', [])
                fragments = [entry.get('phrase', '') for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
                editorial_mapping = listing.get('editorial_phrases', {})
                if not isinstance(editorial_mapping, dict):
                    errors.append(f'{market}/{variant_id} editorial_phrases must be an object')
                    editorial_mapping = {}
                editorial = editorial_mapping.get(field, [])
                if not isinstance(editorial, list):
                    errors.append(f'{market}/{variant_id} editorial_phrases.{field} must be a list')
                    editorial = []
                for entry in editorial:
                    if not isinstance(entry, dict) or not entry.get('text') or not entry.get('reason'):
                        errors.append(f'{market}/{variant_id} editorial_phrases.{field} needs text and reason')
                    elif visible_source_text(entry['text']).casefold() not in visible_source_text(listing.get(field, '')).casefold():
                        errors.append(f'{market}/{variant_id} editorial phrase must appear in {field}')
                    else:
                        fragments.append(entry['text'])
                validate_source_coverage(errors, f'{market}/{variant_id} {field}', listing.get(field, ''), fragments)
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
                validate_numbered_bullet_references(
                    errors, market, variant_id, listing, competitors
                )
            validate_buyer_copy(errors, market, variant_id, buyer_bullet_texts)
        title_keywords = listing.get('title_keywords', [])
        if not isinstance(title_keywords, list):
            title_keywords = []
        normalized_title_keywords = [
            unicodedata.normalize('NFC', str(item).strip()).casefold()
            for item in title_keywords
        ]
        if (len(title_keywords) != 3
                or any(not item for item in normalized_title_keywords)
                or len(set(normalized_title_keywords)) != len(title_keywords)):
            errors.append(
                f'{market}/{variant_id} title_keywords must contain exactly 3 distinct phrases'
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
            if item_highlights and not any(
                contains(item_highlights, form)
                for phrase, normalized in zip(title_keywords, normalized_title_keywords)
                for form in [phrase, *keyword_by_key.get((market, normalized), {}).get('aliases', [])]
                if str(form).strip()
            ):
                errors.append(
                    f'{market}/{variant_id} item_highlights must include at least one '
                    'title core keyword or a verified alias'
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
        if repeats_pack_count_in_highlights(
                item_highlights, title_quantity, title_quantity_term, first_keyword_forms):
            errors.append(
                f'{market}/{variant_id} item_highlights repeats the title pack quantity '
                'with the same product name'
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
        validate_chinese_translations(
            errors, market, variant_id, listing.get('translations'), description
        )
        validate_compatibility_copy(
            errors, market, variant_id, listing, title, item_highlights,
            bullets, description_text
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
            if byte_count < SEARCH_TERMS_TARGET_BYTES:
                warnings.append(
                    f'{market}/{variant_id} search_terms uses only {byte_count} UTF-8 bytes; '
                    'target 240–249 when supported: expand omitted reference-title terms and '
                    'high-relevance reverse-ASIN keywords, never generic filler'
                )
                if search_policy in (2, 3, 4):
                    expansion = listing.get('search_term_expansion')
                    expansion = expansion if isinstance(expansion, dict) else {}
                    queries = expansion.get('queries')
                    reason = expansion.get('shortfall_reason')
                    if (not isinstance(queries, list) or not queries
                            or any(not isinstance(query, str) or not query.strip()
                                   for query in queries)
                            or not isinstance(reason, str) or not reason.strip()):
                        errors.append(
                            f'{market}/{variant_id} search_terms below 240 bytes requires '
                            'search_term_expansion with actual queries and shortfall_reason'
                        )
            if byte_count > SEARCH_TERMS_MAX_BYTES:
                errors.append(
                    f'{market}/{variant_id} search_terms uses {byte_count} UTF-8 bytes; '
                    f'maximum is {SEARCH_TERMS_MAX_BYTES}'
                )
            terms = words(search_terms)
            if len(set(terms)) <= 2:
                warnings.append(
                    f'{market}/{variant_id} search_terms has only {len(set(terms))} distinct '
                    'tokens; review additional target-market titles and relevant ASIN reverse '
                    'keywords before accepting a short field'
                )
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
                    reverse_asins = {
                        str(audit.get('source_asin', '')).strip().upper()
                        for audit in audits
                        if audit.get('source_tool') == 'sellersprite_reverse_asin'
                    }
                    if primary_asin and primary_asin.upper() not in reverse_asins:
                        errors.append(
                            f'{market}/{variant_id} SellerSprite audit must include '
                            'primary_reference_asin'
                        )
                    for audit in audits:
                        audit_asin = str(audit.get('source_asin', '')).strip().upper()
                        if audit.get('source_tool') == 'sellersprite_reverse_asin':
                            if audit_asin not in competitor_asins:
                                errors.append(
                                    f'{market}/{variant_id} SellerSprite audit source_asin '
                                    'must match a competitor record'
                                )
                        elif (audit.get('source_tool') in (
                                'reference_title_terms', 'same_category_title_terms')
                                and audit_asin not in competitor_asins):
                            errors.append(
                                f'{market}/{variant_id} title-term audit source_asin must '
                                'match a competitor record'
                            )
                    if search_policy in (3, 4):
                        for audit in audits:
                            phrase_tokens = set(words(audit.get('phrase', '')))
                            incremental = (phrase_tokens - front_end_words
                                           - SEARCH_TERMS_STOP_WORDS.get(market, set()))
                            if (audit.get('decision') == 'exclude'
                                    and audit.get('exclusion_reason') == 'front_end_covered'
                                    and incremental):
                                errors.append(
                                    f'{market}/{variant_id} front_end_covered exclusion has '
                                    f'uncovered localized tokens: {", ".join(sorted(incremental))}'
                                )
                            if audit.get('source_tool') in ('reference_title_terms', 'same_category_title_terms'):
                                source_phrase = audit.get('source_phrase', '')
                                source_asin = str(audit.get('source_asin', '')).upper()
                                if not any(str(c.get('asin', '')).upper() == source_asin
                                           and source_phrase and contains(str(c.get('title', '')), source_phrase)
                                           for c in competitors):
                                    errors.append(f'{market}/{variant_id} original search-term source_phrase must exist in its reference title')
                        if byte_count < SEARCH_TERMS_TARGET_BYTES:
                            expansion = listing.get('search_term_expansion')
                            expansion = expansion if isinstance(expansion, dict) else {}
                            reviewed = expansion.get('reviewed_phrases')
                            phrases = {str(a.get('phrase', '')).strip() for a in audits}
                            if (not isinstance(reviewed, list) or not reviewed
                                    or any(not isinstance(p, str) or not p.strip() for p in reviewed)
                                    or {p.strip() for p in reviewed} != phrases):
                                errors.append(f'{market}/{variant_id} shortfall requires reviewed_phrases matching all localized candidate audits')
                            reference_audit = data.get('title_candidate_audit')
                            references = reference_audit.get('all_user_references') if isinstance(reference_audit, dict) else None
                            if (not isinstance(references, list) or not references
                                    or any(not isinstance(ref, dict) or not ASIN.fullmatch(str(ref.get('asin', ''))) for ref in references)):
                                errors.append(f'{market}/{variant_id} shortfall requires all_user_references to verify title-source coverage')
                            else:
                                title_asins = {str(a.get('source_asin', '')).upper() for a in audits
                                               if a.get('source_tool') == 'reference_title_terms'}
                                missing_titles = {str(ref['asin']).upper() for ref in references} - title_asins
                                if missing_titles:
                                    errors.append(f'{market}/{variant_id} shortfall omits reference-title localization: {", ".join(sorted(missing_titles))}')
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
                    if search_policy in (2, 3, 4):
                        for audit in audits:
                            if (audit.get('decision') != 'exclude'
                                    or audit.get('exclusion_reason') != 'byte_limit'):
                                continue
                            extra = sorted(
                                set(words(audit.get('phrase', '')))
                                - front_end_words - set(terms)
                                - SEARCH_TERMS_STOP_WORDS.get(market, set())
                            )
                            if extra and len((search_terms + ' ' + ' '.join(extra)).encode('utf-8')) <= SEARCH_TERMS_MAX_BYTES:
                                errors.append(
                                    f'{market}/{variant_id} byte_limit exclusion still fits '
                                    f'within 249 bytes: {audit.get("phrase", "")}'
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
        validate_field_fact_ids(
            errors, market, variant_id, listing, fact_by_id
        )

    if search_policy == 4:
        validate_search_coverage(data, errors)

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
    result = validate(json.loads(args.input.read_text(encoding='utf-8-sig')),
                      require_current_search_policy=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(str(args.out.resolve()))
    return 0 if result['ready_for_delivery'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
