"""
Classificatore messaggi per il gruppo Offerte Lavoro Bar Torino.
Analizza il testo e determina: OFFERTA, RICHIESTA, SPAM, o ALTRO.
"""

import re

# ─── Keywords offerte di lavoro (datore cerca personale) ──────────────────────
OFFERTA_KEYWORDS = [
    "cerco personale", "cerchiamo", "selezioniamo", "ricerchiamo", "assumiamo",
    "si cerca", "cercasi", "offriamo lavoro", "offerta di lavoro", "offerta lavoro",
    "posizione aperta", "opportunità lavorativa", "siamo alla ricerca",
    "stiamo cercando", "inserimento immediato", "lavoro disponibile",
    "posto disponibile", "figura professionale", "candidarsi", "inviare cv",
    "mandare cv", "mandatemi cv", "contattate in privato", "contattami in privato",
    "zona torino", "bar torino", "caffetteria torino", "ristorante torino",
    "locale cerca", "assumo", "assume", "cerco barista", "cerco cameriere", "cerco cuoco",
    "cerco aiuto", "cerco lavapiatti", "cerco extra", "disponibilità immediata",
    "retribuzione", "stipendio da concordare", "pagamento", "compenso",
    "contratto offerto", "possibilità di crescita",
]

# ─── Keywords richiesta lavoro (candidato cerca impiego) ──────────────────────
RICHIESTA_KEYWORDS = [
    "cerco lavoro", "sono disponibile", "disponibile da subito", "disponibile immediatamente",
    "mi chiamo", "ho esperienza", "anni di esperienza", "anni nel settore",
    "cerco posizione", "sono alla ricerca di lavoro", "curriculum", " cv ",
    "patente", "sono un barista", "sono una barista", "sono cameriere",
    "sono cameriera", "faccio il barista", "faccio la barista",
    "esperienza come", "ho lavorato", "ho lavorato come", "ho lavorato in",
    "sono disponibile part", "sono disponibile full", "disponibile part-time",
    "disponibile full-time", "cerco un'opportunità", "cerco opportunità",
    "posso lavorare", "sono pronto", "sono pronta", "contattatemi",
    "disponibile per extra", "disponibile per turni", "zona preferita",
    "disponibile a torino", "abito a torino", "vivo a torino",
    "recapito", "numero di telefono", "whatsapp",
    "cerco impiego", "cerco occupazione", "cerco un lavoro", "cercando lavoro",
    "in cerca di lavoro", "valuto proposte", "valuto offerte", "posso iniziare",
    "libero per lavorare", "libera per lavorare", "qualcuno cerca un",
    "qualcuno cerca una", "qualche locale assume", "locali che cercano personale",
    "avete bisogno di personale", "dove posso mandare il curriculum",
    "looking for a job", "looking for work", "available for work", "i am available",
    "i'm available", "busco trabajo", "busco empleo", "estoy disponible",
    "disponible para trabajar",
]

# Forme brevi o con piccoli errori comuni. Richiedono un contesto personale o
# professionale per evitare di confondere le offerte dei datori con le ricerche.
RICHIESTA_PATTERNS = [
    r"\b(?:cerco|cercando|cerc[oa])\s+(?:un\s+)?lavor\w*\b",
    r"\b(?:sono|sn)\s+dispon\w*\b",
    r"\bdispon\w*\s+(?:da\s+subito|immediat\w*|(?:per|x)\s+(?:extra|turni|lavorare)|come\s+\w+)",
    r"\b(?:barista|camerier\w*|cuoc\w*|lavapiatt\w*|banconist\w*|pizzaiol\w*|chef)\s+(?:con\s+esperienza\s+)?(?:cerca\w*\s+lavor\w*|dispon+ibil\w*)",
    r"\b(?:qualcuno|qualche\s+locale)\s+(?:cerca|assume|ha\s+bisogno)\b",
    r"\b(?:i['’]?m|i\s+am)\s+(?:looking\s+for\s+(?:a\s+)?(?:job|work)|available)\b",
    r"\b(?:busco|estoy\s+buscando)\s+(?:trabajo|empleo)\b",
]

# ─── Pattern spam ──────────────────────────────────────────────────────────────
SPAM_PATTERNS = [
    r'https?://\S+',                    # URL generici
    r'www\.\S+\.\S+',                   # siti web
    r't\.me/(?!joinchat)',              # link telegram (non inviti al gruppo)
    r'@\w+bot\b',                       # bot telegram
    r'guadagna \d+',                    # schemi guadagno facile
    r'guadagni facili',
    r'lavora da casa',
    r'marketing multilivello',
    r'mlm',
    r'criptovalut',
    r'bitcoin',
    r'investimento sicuro',
    r'clicca qui',
    r'click here',
    r'iscriviti al canale',
    r'unisciti al canale',
    r'promo\s+esclusiv',
]

# ─── Soglie ────────────────────────────────────────────────────────────────────
MIN_TEXT_LENGTH = 5    # caratteri minimi per non essere considerato "troppo corto"
OFFERTA_THRESHOLD = 1  # keyword minime per classificare come OFFERTA
RICHIESTA_THRESHOLD = 1


def classify(text: str) -> str:
    """
    Classifica il messaggio.
    Ritorna: 'OFFERTA', 'RICHIESTA', 'SPAM', 'CORTO', 'ALTRO'
    """
    if not text or not text.strip():
        return "ALTRO"

    text_lower = text.lower()

    # Le formule esplicite del datore hanno priorità: una vera offerta può
    # contenere "disponibile da subito" riferito alla persona ricercata.
    candidate_question = any(kw in text_lower for kw in (
        "qualcuno cerca", "sapete se", "qualche locale assume",
        "conoscete locali", "ci sono offerte", "avete bisogno di personale",
        "dove posso mandare",
    ))
    employer_intent = not candidate_question and any(kw in text_lower for kw in (
        "cerchiamo", "ricerchiamo", "selezioniamo", "assumiamo", "assume",
        "cercasi", "si cerca", "stiamo cercando", "siamo alla ricerca",
        "offerta di lavoro", "offerta lavoro", "posizione aperta",
    ))

    # 1. Controlla spam
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text_lower):
            return "SPAM"

    # Troppo corto
    if len(text.strip()) < MIN_TEXT_LENGTH:
        return "CORTO"

    # 2. Conta keyword offerta
    offerta_count = sum(1 for kw in OFFERTA_KEYWORDS if kw in text_lower)

    # 3. Conta keyword richiesta
    richiesta_count = sum(1 for kw in RICHIESTA_KEYWORDS if kw in text_lower)
    richiesta_count += sum(1 for pattern in RICHIESTA_PATTERNS if re.search(pattern, text_lower))

    # 4. Classifica in base ai conteggi
    if employer_intent and offerta_count >= OFFERTA_THRESHOLD:
        return "OFFERTA"
    if offerta_count >= OFFERTA_THRESHOLD and offerta_count > richiesta_count:
        return "OFFERTA"
    elif richiesta_count >= RICHIESTA_THRESHOLD:
        return "RICHIESTA"
    elif offerta_count >= OFFERTA_THRESHOLD:
        return "OFFERTA"

    return "ALTRO"


def has_external_link(text: str) -> bool:
    """Controlla se il testo contiene link esterni."""
    text_lower = text.lower()
    for pattern in [r'https?://\S+', r'www\.\S+\.\S+']:
        if re.search(pattern, text_lower):
            return True
    return False


def get_category_emoji(category: str) -> str:
    return {
        "OFFERTA": "📋",
        "RICHIESTA": "🙋",
        "SPAM": "🚫",
        "CORTO": "⚠️",
        "ALTRO": "💬",
    }.get(category, "💬")


def format_category_label(category: str) -> str:
    return {
        "OFFERTA": "📋 Offerta di lavoro",
        "RICHIESTA": "🙋 Ricerca lavoro",
        "SPAM": "🚫 Spam",
        "CORTO": "⚠️ Annuncio incompleto",
        "ALTRO": "💬 Messaggio generico",
    }.get(category, category)
