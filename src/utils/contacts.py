"""Contact information extraction utilities.

Provides functions for extracting emails, phone numbers, and other
contact information from text.
"""

import re


def extract_email(text: str | None) -> str | None:
    """Extract email address from text.

    Args:
        text: Text that may contain an email

    Returns:
        Email address or None
    """
    if not text:
        return None

    # Standard email pattern
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(pattern, text)

    return match.group(0).lower() if match else None


def extract_all_emails(text: str | None) -> list[str]:
    """Extract all email addresses from text.

    Args:
        text: Text that may contain emails

    Returns:
        List of email addresses
    """
    if not text:
        return []

    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    matches = re.findall(pattern, text)

    return [email.lower() for email in matches]


def extract_phone(text: str | None) -> str | None:
    """Extract phone number from text.

    Handles Spanish phone formats:
    - +34 XXX XXX XXX
    - 34 XXX XXX XXX
    - XXX XXX XXX
    - XXX-XXX-XXX
    - XXX.XXX.XXX

    Args:
        text: Text that may contain a phone number

    Returns:
        Normalized phone number or None
    """
    if not text:
        return None

    # Patterns for Spanish phone numbers
    patterns = [
        # +34 or 34 prefix
        r'(?:\+34|34)?[\s.-]?([6789]\d{2})[\s.-]?(\d{3})[\s.-]?(\d{3})',
        # 9 digits without prefix
        r'\b([6789]\d{2})[\s.-]?(\d{3})[\s.-]?(\d{3})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # Normalize to XXX XXX XXX format
            groups = match.groups()
            if len(groups) == 3:
                return f"{groups[0]} {groups[1]} {groups[2]}"

    return None


def extract_all_phones(text: str | None) -> list[str]:
    """Extract all phone numbers from text.

    Args:
        text: Text that may contain phone numbers

    Returns:
        List of normalized phone numbers
    """
    if not text:
        return []

    phones = []
    pattern = r'(?:\+34|34)?[\s.-]?([6789]\d{2})[\s.-]?(\d{3})[\s.-]?(\d{3})'

    for match in re.finditer(pattern, text):
        groups = match.groups()
        phone = f"{groups[0]} {groups[1]} {groups[2]}"
        if phone not in phones:
            phones.append(phone)

    return phones


def normalize_phone(phone: str | None) -> str | None:
    """Normalize a phone number to standard format.

    Args:
        phone: Raw phone number

    Returns:
        Normalized phone number (XXX XXX XXX) or None
    """
    if not phone:
        return None

    # Remove all non-digits
    digits = re.sub(r'\D', '', phone)

    # Remove country code if present
    if digits.startswith('34') and len(digits) == 11:
        digits = digits[2:]

    # Must be 9 digits and start with 6, 7, 8, or 9
    if len(digits) == 9 and digits[0] in '6789':
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"

    return None


def is_valid_email(email: str | None) -> bool:
    """Check if email address is valid.

    Args:
        email: Email to validate

    Returns:
        True if valid email format
    """
    if not email:
        return False

    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_phone(phone: str | None) -> bool:
    """Check if phone number is valid Spanish format.

    Args:
        phone: Phone to validate

    Returns:
        True if valid Spanish phone
    """
    if not phone:
        return False

    # Remove spaces and check
    digits = re.sub(r'\D', '', phone)

    # 9 digits starting with 6, 7, 8, or 9
    return len(digits) == 9 and digits[0] in '6789'


def extract_contact_info(text: str | None) -> dict[str, str | None]:
    """Extract all contact information from text.

    Args:
        text: Text that may contain contact info

    Returns:
        Dict with email, phone, website keys
    """
    if not text:
        return {"email": None, "phone": None, "website": None}

    email = extract_email(text)
    phone = extract_phone(text)

    # Simple URL extraction for website
    website = None
    url_match = re.search(r'https?://[^\s<>"\']+', text)
    if url_match:
        website = url_match.group(0).rstrip('.,;:')

    return {
        "email": email,
        "phone": phone,
        "website": website,
    }


# Known ticket/registration platforms
TICKET_PLATFORMS = [
    "eventbrite.es", "eventbrite.com",
    "ticketmaster.es", "ticketmaster.com",
    "secutix.com",
    "entradas.com",
    "ticketea.com",
    "wegow.com",
    "fever.co", "ffrr.co",
    "dice.fm",
    "gigantic.com",
    "bandsintown.com",
    "songkick.com",
    "notikumi.com",
    "compralasentrada.com",
    "atrápalo.com", "atrapalo.com",
    "taquilla.com",
    "ticketstarter.es",
    "stubhub.es",
    "kutxabank.com/entradas",
    "kursaal.eus",
    "auditoriodetenerife.com",
    "auditoriomigueldelibes.com",
    "teatroscanal.com",
    "teatroreal.es",
    "liceubarcelona.cat",
]

# Keywords that indicate registration URLs
REGISTRATION_KEYWORDS = [
    "entradas", "tickets", "entrada", "ticket",
    "reservar", "reserva", "booking", "book",
    "inscripcion", "inscribirse", "registro",
    "comprar", "compra", "buy",
    "venta", "taquilla",
]


def extract_registration_url(text: str | None, urls: list[str] | None = None) -> str | None:
    """Extract registration/ticket URL from text or URL list.

    Looks for URLs from known ticket platforms or URLs containing
    registration keywords.

    Args:
        text: Text that may contain registration URLs
        urls: Optional list of URLs to check

    Returns:
        Registration URL or None
    """
    if not text and not urls:
        return None

    # Collect URLs from text
    all_urls = list(urls) if urls else []
    if text:
        # Pattern 1: URLs with protocol (https?://)
        url_pattern = r'https?://[^\s<>"\']+[^\s<>"\'.,;:!?)]'
        for match in re.finditer(url_pattern, text):
            url = match.group(0)
            if url not in all_urls:
                all_urls.append(url)

        # Pattern 2: URLs starting with www. (no protocol)
        www_pattern = r'\bwww\.[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z]{2,})+(?:/[^\s<>"\']*)?'
        for match in re.finditer(www_pattern, text):
            url = "https://" + match.group(0).rstrip('.,;:!?)')
            if url not in all_urls:
                all_urls.append(url)

    if not all_urls:
        return None

    # Priority 1: Known ticket platforms
    for url in all_urls:
        url_lower = url.lower()
        for platform in TICKET_PLATFORMS:
            if platform in url_lower:
                return url

    # Priority 2: URLs with registration keywords
    for url in all_urls:
        url_lower = url.lower()
        for keyword in REGISTRATION_KEYWORDS:
            if keyword in url_lower:
                return url

    return None


def extract_registration_info(text: str | None) -> dict[str, any]:
    """Extract registration information from text.

    Args:
        text: Text that may contain registration info

    Returns:
        Dict with:
        - requires_registration: bool | None
        - registration_url: str | None
        - registration_info: str | None (how to register if no URL)
    """
    if not text:
        return {
            "requires_registration": None,
            "registration_url": None,
            "registration_info": None,
        }

    text_lower = text.lower()

    # Check for registration requirement indicators
    requires_registration = None

    # Strong indicators of required registration
    registration_required_patterns = [
        r"inscripci[óo]n\s+(?:previa\s+)?(?:obligatoria|necesaria|requerida)",
        r"reserva\s+(?:previa\s+)?(?:obligatoria|necesaria|requerida)",
        r"aforo\s+limitado.*?(?:inscri|reserv)",
        r"plazas\s+limitadas",
        r"(?:es\s+)?necesario\s+(?:inscribirse|reservar)",
        r"imprescindible\s+(?:inscripci[óo]n|reserva)",
    ]

    for pattern in registration_required_patterns:
        if re.search(pattern, text_lower):
            requires_registration = True
            break

    # No registration needed indicators
    no_registration_patterns = [
        r"entrada\s+libre",
        r"sin\s+(?:inscripci[óo]n|reserva)",
        r"no\s+(?:es\s+)?necesari[oa]\s+(?:inscripci[óo]n|reserva)",
        r"acceso\s+libre",
        r"hasta\s+completar\s+aforo",
    ]

    if requires_registration is None:
        for pattern in no_registration_patterns:
            if re.search(pattern, text_lower):
                requires_registration = False
                break

    # Extract registration URL
    registration_url = extract_registration_url(text)

    # If we found a URL, registration is likely required
    if registration_url and requires_registration is None:
        requires_registration = True

    # Extract registration info (non-URL instructions)
    registration_info = None
    info_patterns = [
        r"(?:inscripci[óo]n|reserva)[:\s]+([^.]+(?:@[^.]+\.[^\s]+|[\d\s]{9,}))",
        r"(?:para\s+)?(?:inscribirse|reservar)[:\s]+([^.]+)",
        r"(?:inscripciones|reservas)\s+(?:en|a\s+trav[ée]s\s+de)[:\s]+([^.]+)",
    ]

    for pattern in info_patterns:
        match = re.search(pattern, text_lower)
        if match:
            info = match.group(1).strip()
            # Only use if it contains useful info (email, phone, or meaningful text)
            if "@" in info or re.search(r"\d{9}", info) or len(info) > 20:
                registration_info = info[:200]  # Limit length
                break

    return {
        "requires_registration": requires_registration,
        "registration_url": registration_url,
        "registration_info": registration_info,
    }


def extract_organizer(text: str | None) -> dict[str, str | None]:
    """Extract organizer information from text.

    Looks for patterns like:
    - "Organiza: Ayuntamiento de Madrid"
    - "Organizado por: Fundación X"
    - "Organización: Asociación Y"

    Args:
        text: Text that may contain organizer info

    Returns:
        Dict with organizer_name and organizer_type
    """
    if not text:
        return {"organizer_name": None, "organizer_type": None}

    # Patterns to extract organizer name (more strict - require colon or "por")
    organizer_patterns = [
        # "Organiza: Name" (with colon)
        r"(?:organiza|organizaci[óo]n)\s*:\s*([^.\n,]{3,60})(?:\.|,|$|\n)",
        # "Organizado por Name"
        r"organizado\s+por\s+(?:el\s+|la\s+|los\s+|las\s+)?([^.\n,]{3,60})(?:\.|,|$|\n)",
        # "Colabora: Name" (with colon)
        r"(?:colabora|patrocina)\s*:\s*([^.\n,]{3,60})(?:\.|,|$|\n)",
        # "A cargo de: Name" or "Producido por Name"
        r"(?:a\s+cargo\s+de|producido\s+por)\s*:?\s*([^.\n,]{3,60})(?:\.|,|$|\n)",
    ]

    organizer_name = None
    for pattern in organizer_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up common artifacts
            name = re.sub(r'\s+', ' ', name)
            # Remove trailing punctuation
            name = name.rstrip(',:;')
            # Skip if too short, too long, or looks like a URL/generic text
            if (len(name) >= 5 and len(name) <= 60
                and not name.startswith(('http', 'www.', 'en ', 'el ', 'la '))
                and not any(w in name.lower() for w in ['show', 'concierto', 'evento', 'espectáculo'])):
                organizer_name = name
                break

    # Try to detect organizer type
    organizer_type = None
    if organizer_name:
        name_lower = organizer_name.lower()
        if any(w in name_lower for w in ['ayuntamiento', 'diputación', 'gobierno', 'ministerio', 'consejería']):
            organizer_type = 'government'
        elif any(w in name_lower for w in ['fundación', 'fundacion']):
            organizer_type = 'foundation'
        elif any(w in name_lower for w in ['asociación', 'asociacion', 'ong', 'colectivo']):
            organizer_type = 'ngo'
        elif any(w in name_lower for w in ['universidad', 'colegio', 'escuela', 'instituto']):
            organizer_type = 'education'
        elif any(w in name_lower for w in ['museo', 'teatro', 'auditorio', 'biblioteca', 'centro cultural']):
            organizer_type = 'venue'
        elif any(w in name_lower for w in ['s.l.', 's.a.', 'sl', 'sa', 'producciones', 'eventos']):
            organizer_type = 'company'

    return {
        "organizer_name": organizer_name,
        "organizer_type": organizer_type,
    }


def extract_price_info(text: str | None) -> dict[str, any]:
    """Extract price information from text.

    Args:
        text: Text that may contain price info

    Returns:
        Dict with:
        - is_free: bool | None
        - price: float | None (numeric price)
        - price_info: str | None (descriptive text)
    """
    if not text:
        return {"is_free": None, "price": None, "price_info": None}

    text_lower = text.lower()

    # Check for free indicators
    free_patterns = [
        r"\bgratis\b",
        r"\bgratuito\b",
        r"\bgratuita\b",
        r"\bentrada\s+libre\b",
        r"\bacceso\s+libre\b",
        r"\bacceso\s+gratuito\b",
        r"\bsin\s+coste\b",
        r"\b0\s*[€$]\b",
        r"\b0,00\s*[€$]\b",
    ]

    for pattern in free_patterns:
        if re.search(pattern, text_lower):
            return {"is_free": True, "price": 0.0, "price_info": "Gratuito"}

    # Extract numeric price
    price_patterns = [
        # "15€" or "15 €" or "15 euros"
        r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?)",
        # "€15" or "€ 15"
        r"[€]\s*(\d+(?:[.,]\d{1,2})?)",
        # "Precio: 15" or "Entrada: 15"
        r"(?:precio|entrada|entradas)[:\s]+(\d+(?:[.,]\d{1,2})?)",
        # "desde 15€" or "desde 15 euros"
        r"desde\s+(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?)?",
    ]

    price = None
    for pattern in price_patterns:
        match = re.search(pattern, text_lower)
        if match:
            price_str = match.group(1).replace(",", ".")
            try:
                price = float(price_str)
                break
            except ValueError:
                pass

    # Extract price info text
    price_info = None
    info_patterns = [
        r"((?:precio|entrada|entradas)[:\s]+[^.]+)",
        r"(desde\s+\d+[^.]+)",
        r"(\d+\s*(?:€|euros?)[^.]*(?:reducida|general|anticipada)[^.]*)",
    ]

    for pattern in info_patterns:
        match = re.search(pattern, text_lower)
        if match:
            price_info = match.group(1).strip()[:200]
            break

    # Determine is_free based on price
    is_free = None
    if price is not None:
        is_free = price == 0.0

    return {
        "is_free": is_free,
        "price": price,
        "price_info": price_info,
    }
