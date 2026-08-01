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
    "locale cerca", "assumo", "cerco barista", "cerco cameriere", "cerco cuoco",
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

    # 4. Classifica in base ai conteggi
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
