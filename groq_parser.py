# groq_parser.py
"""
Groq-API-powered payment field extractor.

Privacy note
────────────
The *text* argument received by groq_extract() is already privacy-masked:
  • Every digit sequence with 8+ digits has its last 3 digits replaced with ***
  • Space-separated digit groups are treated as one span
  • Letter-prefixed IDs with 8+ digits are also masked
  • Dates and amounts with commas/slashes are NOT masked (separators break spans)
  • tab_json._restore_dict() restores real values after this module returns
    using star-count-agnostic prefix matching (handles Groq returning 2 or 4
    stars instead of exactly 3).

Amount post-processing
──────────────────────
_apply_rules() calls _clean_amount() on every amount field before returning:
  • Strips any residual commas or spaces (e.g. Groq returns "50,000" → "50000")
  • Applies required decimal formatting per payment type
  • Tab_json._normalise_restored_amounts() then cross-validates against the
    original raw text to catch hallucinations (e.g. "500000" vs "50,000").

Phone normalisation — _extract_ug_phone_local()
────────────────────────────────────────────────
Strips ALL non-digit characters, then matches UG mobile prefix patterns:
  256XXXXXXXXX  →  local = last 9 digits
  0XXXXXXXXX    →  local = last 9 digits
  7XXXXXXXX     →  local = all 9 digits  (bare local, starting with 7)

Date parsing — _parse_date()
──────────────────────────────
• Unambiguous formats (ISO, month-name) tried first on original string.
• Slash/hyphen formats: DD/MM/YYYY tried before MM/DD/YYYY (Uganda convention).
• Internal whitespace stripped only for numeric formats ("27/12/ 2025" → "27/12/2025").
• Plausibility check: date must be within ±3 years of today to avoid
  month/day inversion (e.g. "05/04" correctly parsed as Apr 5, not May 4).
• Compact 8-digit: DDMMYYYY tried before YYYYMMDD.
• Prompt includes today's date so Groq can self-validate its output.
"""
import http.client
import json
import re
import ssl
from datetime import datetime, timedelta
from json_data import get_db_sample

GROQ_HOST     = "api.groq.com"
GROQ_PATH     = "/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.1-8b-instant"

# ─── Compiled patterns ────────────────────────────────────────────────────────
_BEYO_TXN_T_RE   = re.compile(r'\bT\d{6,}\b')
_BEYO_TXN_NUM_RE = re.compile(
    r'(?:txn\s*(?:id)?|transaction\s*(?:id)?|ref(?:erence)?|tid)\s*[:#\-]?\s*(\d{6,14})',
    re.IGNORECASE
)
_NET_TXN_RE = re.compile(
    r'(?:network\s*(?:txn|transaction|ref|id)?|tid|txnid|id|ref(?:erence)?)'
    r'\s*[:#\-]?\s*(\d{6,14})',
    re.IGNORECASE
)
_FLEX_TXN_RE   = re.compile(r'(?<!\d)(3000\d+)(?!\d)')
_GENERIC_ID_RE = re.compile(r'(?<!\d)(\d{8,14})(?!\d)')
_TIME_RE       = re.compile(r'\b([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b')

_AIRTEL_DATE_FIELDS = (
    "creationDate",
    "agentAssignmentDateTime",
    "paymentTransactionDateTime",
)
_MONTH_PAT = (
    r'jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?'
)
_MASKED_RE = re.compile(r'\*{1,}')   # any run of stars = masked


def _is_masked(v: str) -> bool:
    return bool(_MASKED_RE.search(str(v)))


# ═══════════════════════════════════════════════════════════════════════════
# AMOUNT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _clean_amount(raw: str, decimal_places: int = 0) -> str:
    """
    Strip commas, spaces, currency symbols from *raw* and apply decimal format.

    Examples (decimal_places=0):
      "50,000"   → "50000"
      "50 000"   → "50000"
      "UGX 50,000" → "50000"
      "50000.00" → "50000"

    Examples (decimal_places=2):
      "651000"   → "651000.00"
      "651,000"  → "651000.00"
    """
    if not raw:
        return raw
    # Strip everything except digits and decimal point
    cleaned = re.sub(r'[^\d.]', '', str(raw))
    if not cleaned:
        return raw
    try:
        value = float(cleaned)
        if decimal_places > 0:
            return f"{value:.{decimal_places}f}"
        else:
            return str(int(value))
    except ValueError:
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# PHONE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_ug_phone_local(raw: str) -> str:
    """
    Extract the 9-digit local Ugandan number (7XXXXXXXX) from any input format.

    Algorithm:
      1. Strip every non-digit character (spaces, hyphens, +, parentheses…)
      2. Match the pure digit string against known UG prefix patterns:
           256XXXXXXXXX  (12 digits)  →  local = digits[3:]
           0XXXXXXXXX    (10 digits)  →  local = digits[1:]
           7XXXXXXXX     ( 9 digits)  →  local = digits       ← bare local
    """
    if not raw:
        return ""
    digits = re.sub(r'\D', '', raw)
    for pat in [
        r'^256(7\d{8})$',
        r'^0(7\d{8})$',
        r'^(7\d{8})$',
    ]:
        m = re.fullmatch(pat, digits)
        if m:
            return m.group(1)
    return ""


def _to_256(local9: str) -> str:      return "256"  + local9
def _to_plus256(local9: str) -> str:  return "+256" + local9


def _normalise_256(raw: str) -> str:
    local = _extract_ug_phone_local(raw)
    return _to_256(local) if local else ""


def _normalise_plus256(raw: str) -> str:
    local = _extract_ug_phone_local(raw)
    return _to_plus256(local) if local else ""


def _is_valid_ug_local(d: str) -> bool:
    return bool(re.fullmatch(r'7\d{8}', d))


# ═══════════════════════════════════════════════════════════════════════════
# TRANSACTION ID HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_beyonic_txn_id(raw_val: str, raw_text: str) -> str:
    v = (raw_val or "").strip()
    if re.fullmatch(r'[Tt]\d+', v):
        return "T" + v.lstrip("Tt")
    if v and not _is_valid_ug_local(v) and re.fullmatch(r'[A-Za-z0-9]{6,14}', v):
        return v
    m = _BEYO_TXN_T_RE.search(raw_text)
    if m:
        return m.group()
    m = _BEYO_TXN_NUM_RE.search(raw_text)
    if m:
        cand = m.group(1)
        if not _is_valid_ug_local(cand):
            return cand
    if re.fullmatch(r'\d{6,14}', v) and not _is_valid_ug_local(v):
        labelled = re.search(
            r'(?:txn(?:id)?|transaction\s*(?:id)?|ref(?:erence)?|tid)'
            r'\s*[:#\-]?\s*' + re.escape(v),
            raw_text, re.IGNORECASE
        )
        if labelled or len(v) >= 8:
            return v
    return ""


def _extract_network_txn_id(raw_val: str, raw_text: str) -> str:
    v = (raw_val or "").strip()
    if re.fullmatch(r'\d{6,14}', v) and not _is_valid_ug_local(v):
        return v
    m = _NET_TXN_RE.search(raw_text)
    if m:
        cand = m.group(1)
        if not _is_valid_ug_local(cand):
            return cand
    for m2 in _GENERIC_ID_RE.finditer(raw_text):
        cand = m2.group(1)
        if _is_valid_ug_local(cand) or cand.startswith("3000"):
            continue
        return cand
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# DATE + TIME PARSING
# ═══════════════════════════════════════════════════════════════════════════

_UNAMBIGUOUS_DATE_FMTS = [
    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",  "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",     "%Y-%m-%d",
    "%d %b %Y %H:%M",     "%d %B %Y %H:%M",
    "%d %b %Y",           "%d %B %Y",
    "%b %d, %Y %H:%M",    "%B %d, %Y %H:%M",
    "%b %d, %Y",          "%B %d, %Y",
    "%b %d %Y",           "%B %d %Y",
    "%d-%b-%Y",           "%d-%B-%Y",
]

_DMY_FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]
_MDY_FMTS = ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"]


def _parse_date(raw: str) -> datetime | None:
    """
    Parse a date string using Uganda date conventions (DD/MM/YYYY preferred).

    Handles "13/05/ 2026" (space before year) by collapsing internal whitespace
    in numeric-only formats before attempting to parse.
    """
    if not raw:
        return None

    s = raw.strip()
    sl = s.lower()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if sl in ("today", "now"):   return today
    if sl == "yesterday":        return today - timedelta(days=1)
    if sl == "tomorrow":         return today + timedelta(days=1)

    # Step 1: unambiguous formats on original string
    for fmt in _UNAMBIGUOUS_DATE_FMTS:
        try:
            dt = datetime.strptime(s, fmt)
            if 2000 <= dt.year <= 2099:
                return dt
        except ValueError:
            pass

    # Step 2: collapse ALL internal whitespace for numeric formats
    # "13/05/ 2026" → "13/05/2026", "27/12/ 2025 10:03" → "27/12/202510:03" handled below
    s_num = re.sub(r'\s+', '', s)

    def _try(raw_s: str, fmt: str) -> datetime | None:
        try:
            dt = datetime.strptime(raw_s, fmt)
            return dt if 2000 <= dt.year <= 2099 else None
        except ValueError:
            return None

    def _plausible(dt: datetime) -> bool:
        return abs((dt - today).days) < 365 * 3

    # Step 3: DD/MM first (Uganda convention), then MM/DD
    candidates = []
    for fmt in _DMY_FMTS:
        dt = _try(s_num, fmt)
        if dt and _plausible(dt):
            candidates.append(("dmy", dt))
            break
    if not candidates:
        for fmt in _MDY_FMTS:
            dt = _try(s_num, fmt)
            if dt and _plausible(dt):
                candidates.append(("mdy", dt))
                break

    if candidates:
        return candidates[0][1]

    # Step 4: compact 8-digit
    digits = re.sub(r'\D', '', s)
    if len(digits) == 8:
        for fmt in ["%d%m%Y", "%Y%m%d"]:
            try:
                dt = datetime.strptime(digits, fmt)
                if 2000 <= dt.year <= 2099 and _plausible(dt):
                    return dt
            except ValueError:
                pass
    if len(digits) == 6:
        try:
            dt = datetime.strptime(digits, "%d%m%y")
            if 2000 <= dt.year <= 2099:
                return dt
        except ValueError:
            pass

    return None


def _extract_time(text: str) -> tuple[int, int, int] | None:
    iso_m = re.search(r'T([01]\d|2[0-3]):([0-5]\d):([0-5]\d)Z?', text)
    if iso_m:
        return (int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
    for m in _TIME_RE.finditer(text):
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    return None


def _scan_date_in_text(text: str) -> datetime | None:
    """
    Scan free text for any recognisable date+time.
    Month-name patterns tried first (unambiguous), then ISO, then DD/MM.
    """
    def _nearby_time(pos: int, window: int = 120):
        return _extract_time(text[max(0, pos - window): pos + window])

    def _with_time(dt: datetime, pos: int) -> datetime:
        t = _nearby_time(pos)
        return dt.replace(hour=t[0], minute=t[1], second=t[2]) if t else dt

    # Month-name patterns
    for pat in [
        rf'\d{{1,2}}\s+(?:{_MONTH_PAT})\s+\d{{4}}(?:\s+\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?',
        rf'(?:{_MONTH_PAT})\s+\d{{1,2}},?\s+\d{{4}}(?:\s+\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?',
    ]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            dt = _parse_date(m.group())
            if dt:
                return _with_time(dt, m.start())

    # ISO YYYY-MM-DD
    for m in re.finditer(
        r'\d{4}[-/]\d{2}[-/]\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?', text
    ):
        dt = _parse_date(m.group())
        if dt:
            return _with_time(dt, m.start())

    # DD/MM/YYYY (Uganda convention — with optional space before year)
    for m in re.finditer(
        r'\d{1,2}[-/]\d{1,2}[-/]\s*\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?', text
    ):
        raw = re.sub(r'\s+', '', m.group())
        dt = _parse_date(raw)
        if dt:
            return _with_time(dt, m.start())

    # Compact 8-digit
    for m in re.finditer(r'(?<!\d)(\d{8})(?!\d)', text):
        cand = m.group(1)
        day, tail, yr4 = int(cand[:2]), int(cand[4:]), int(cand[:4])
        is_dmy = 1 <= day <= 31 and 2000 <= tail <= 2099
        is_ymd = 2000 <= yr4 <= 2099 and 1 <= int(cand[4:6]) <= 12
        if not (is_dmy or is_ymd):
            continue
        dt = _parse_date(cand)
        if dt:
            return _with_time(dt, m.start())

    # Natural language
    for m in re.finditer(r'\b(today|yesterday|tomorrow|now)\b', text, re.IGNORECASE):
        dt = _parse_date(m.group())
        if dt:
            return _with_time(dt, m.start())

    return None


# ═══════════════════════════════════════════════════════════════════════════
# PER-TYPE FIELD SPECS
# ═══════════════════════════════════════════════════════════════════════════

def _build_type_specs() -> dict:
    beyo_txn_sample   = get_db_sample("BeyonicTxnId",  "T91592568")
    beyo_net_sample   = get_db_sample("NetworkTxnId",   "141693582907")
    airtel_txn_sample = get_db_sample("AirtelTxnId",    "143363767927")
    bank_txn_sample   = get_db_sample("BankTxnId",      "S34111201")
    flex_txn_sample   = get_db_sample("FlexipayTxnId",  "300068579130")

    return {
        "Beyonic": [
            ("BeyonicWallet", "string",
             'Wallet / recipient name, e.g. "KUZA". Labels: wallet, account, recipient.'),
            ("BeyonicTxnId",  "string",
             f'Transaction ID — T-prefixed code like "{beyo_txn_sample}" or a label '
             f'"Txn id / TxnId / ref" followed by a number. '
             f'Output exactly as found (including *** if masked). '
             f'Do NOT output if only an amount or phone number exists.'),
            ("Name",          "string", 'Full name of the sender / payer.'),
            ("PhoneNumber",   "string",
             'PHONE: Ugandan mobile. Starts with 7/07/0/+256/256 then 8 more digits. '
             'May be spaced or hyphenated — output as-found, *** included if masked. '
             'NOT an ID, amount, or date.'),
            ("Amount",        "NUMBER",
             'Payment amount — DIGITS ONLY, strip ALL commas and spaces. '
             'Example: "50,000" → 50000  |  "1,521,250" → 1521250. No symbols.'),
            ("Network",       "string", '"MTN Uganda" or "Airtel Uganda".'),
            ("NetworkTxnId",  "string",
             f'Numeric reference near labels Tid/TxnId/Id/Ref. '
             f'Example: "{beyo_net_sample}" (may have *** at end). NOT a phone.'),
            ("PaymentDate",   "string",
             'DATE + TIME: Uganda uses DD/MM/YYYY — interpret slash dates accordingly. '
             'Output: "Mon DD, YYYY HH:MM" e.g. "May 13, 2026 10:03". '
             'Use 00:00 only if no time found.'),
        ],
        "Airtel": [
            ("creationDate",            "string",
             'DATE + TIME. Uganda uses DD/MM/YYYY — interpret slash dates accordingly. '
             'Format output as: "YYYY-MM-DDTHH:MM:SSZ" e.g. "2026-05-13T10:03:00Z". '
             'Use T00:00:00Z if no time found.'),
            ("agentAssignmentDateTime", "string",
             'Same date/time as creationDate. Format: "YYYY-MM-DDTHH:MM:SSZ".'),
            ("customerReferenceNumber", "string",
             'PHONE: Ugandan mobile starting with 7/07/0/+256/256. '
             'Output as-found, *** included if masked. NOT an ID.'),
            ("transactionId",           "string",
             f'Plain numeric ID (may have *** at end). Example: "{airtel_txn_sample}". '
             f'Do NOT add any prefix.'),
            ("customerReferenceType",   "string", 'Always "PHONE_NUMBER".'),
            ("paymentAmount",           "NUMBER",
             'Payment amount — DIGITS ONLY, strip ALL commas and spaces. '
             'Example: "50,000" → 50000  |  "4,012,500" → 4012500. No quotes or symbols.'),
            ("paymentTransactionDateTime", "string",
             'Same date/time as creationDate. Format: "YYYY-MM-DDTHH:MM:SSZ".'),
            ("senderPhoneNumber",       "string",
             'Same as customerReferenceNumber. Output as-found.'),
        ],
        "Bank": [
            ("name",          "string", 'CONSTANT: always "FOURTH".'),
            ("amount",        "string",
             'Payment amount with 2 decimal places. Strip ALL commas and spaces first. '
             'Example: "651,000" → "651000.00"  |  "50,000" → "50000.00".'),
            ("transactionId", "string",
             f'Transaction ID (may have *** at end). Example: "{bank_txn_sample}". '
             f'Output exactly as found.'),
            ("billRefNumber", "string",
             'PHONE: Ugandan mobile starting with 7/07/0/+256/256. '
             'Output as-found, *** included if masked. NOT an ID.'),
            ("countryCode",   "string", '"UG".'),
            ("completionDate","string",
             'DATE: Uganda uses DD/MM/YYYY — interpret slash dates accordingly. '
             'Output as: "YYYY-MM-DD" e.g. "2026-05-13".'),
            ("mobile",        "string", 'Same as billRefNumber. Output as-found.'),
            ("loanAccountId", "string", 'UUID format.'),
        ],
        "Flexipay": [
            ("name",          "string", 'CONSTANT: always "FOURTH".'),
            ("amount",        "string",
             'Payment amount — whole number, NO decimals, strip ALL commas and spaces. '
             'Example: "50,000" → "50000"  |  "1,521,250" → "1521250". '
             'CRITICAL: "50,000" is fifty thousand = 50000, NOT 500000.'),
            ("transactionId", "string",
             f'Transaction ID (may have *** at end). Example: "{flex_txn_sample}". '
             f'Output "" if none found.'),
            ("billRefNumber", "string",
             'PHONE: Ugandan mobile starting with 7/07/0/+256/256. '
             'Output as-found, *** included if masked. NOT an ID.'),
            ("countryCode",   "string", '"UG".'),
            ("completionDate","string",
             'DATE: Uganda uses DD/MM/YYYY — interpret slash dates accordingly. '
             'Output as: "YYYY-MM-DD" e.g. "2026-05-13".'),
            ("mobile",        "string", 'Same as billRefNumber. Output as-found.'),
            ("loanAccountId", "string", 'UUID format.'),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════

_PROMPT_TEMPLATE = """\
You are a payment data extraction assistant.
Today's date: {today}
Payment type: {json_type}
Extract field values from the source text. Return ONLY a flat JSON object:
{field_lines}

═══ CRITICAL EXTRACTION RULES ═══

PRIVACY MASKING
- The last 3 digits of phone numbers and IDs have been replaced with ***
- Identify each value from its PREFIX and CONTEXT:
    782669***      → Ugandan phone (7 prefix, 9 chars)     → phone field
    0782669***     → Ugandan phone (0 prefix, 10 chars)    → phone field
    256774054***   → Ugandan phone (256 prefix, 12 chars)  → phone field
    0751 046 ***   → Ugandan phone (07, spaced)            → phone field
    S45377***      → Bank txn ID  (S prefix)               → transactionId
    T91592***      → Beyonic txn (T prefix)                → BeyonicTxnId
    40676469***    → Numeric ID near TRANSACTION ID label  → transactionId
    14136376***    → Numeric ID near a label               → NetworkTxnId
- Output the value EXACTLY as it appears in the text, including *** and spaces.
  The application restores original digits from a lookup table after response.

PHONE NUMBERS  (PhoneNumber, customerReferenceNumber, senderPhoneNumber,
                billRefNumber, mobile)
- Valid Ugandan mobile: starts with 7 / 07 / 0 / +256 / 256
  followed by exactly 8 more digits  (local format: 7XXXXXXXX = 9 digits)
- May be entered with spaces or start bare — output as-found including ***
- NEVER use amounts, IDs, or dates as phone numbers

AMOUNTS — READ THIS CAREFULLY
- Strip ALL commas and ALL spaces from amounts before outputting
- "50,000"     → 50000      (fifty thousand)
- "1,521,250"  → 1521250    (one point five million)
- "4,012,500"  → 4012500
- CRITICAL: DO NOT add or remove digits. "50,000" has 5 digits → 50000 (5 digits)
- Flexipay/Airtel: whole number only (no decimal point)
- Bank: 2 decimal places  e.g. "651000.00"
- Numeric only, no currency symbols, no commas, no spaces

DATE AND TIME
- Uganda uses DD/MM/YYYY format — interpret slash dates as Day/Month/Year
- Today is {today} — use this to validate your date output is sensible
- "13/05/ 2026" means May 13 2026 (ignore the extra space)
- "05/04/2026" means April 5 2026 (NOT May 4)
- Search the ENTIRE text for any date AND any time token (HH:MM or HH:MM:SS)
- Beyonic PaymentDate    : "Mon DD, YYYY HH:MM"   e.g. "May 13, 2026 10:03"
- Airtel date fields     : "YYYY-MM-DDTHH:MM:SSZ"  e.g. "2026-05-13T10:03:00Z"
- Bank/Flexipay dates    : "YYYY-MM-DD"            e.g. "2026-05-13"
- Use 00:00 / T00:00:00Z ONLY when absolutely no time token exists

TRANSACTION IDs — output exactly as found in the text (including ***)
- BeyonicTxnId          : T-prefixed or labelled numeric
- Airtel transactionId  : numeric only, no prefix added
- Bank/Flexipay transactionId: exactly as found

OTHER
- Bank/Flexipay name: always "FOURTH"
- Missing value: output ""
"""

_HEADERS = {
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
}


def _build_prompt(json_type: str) -> str:
    """Build the system prompt, injecting today's date for date validation."""
    type_specs = _build_type_specs()
    if json_type not in type_specs:
        raise ValueError(f"Unknown payment type: {json_type!r}")
    lines = [
        f'  "{key}": {kind}  // {hint}'
        for key, kind, hint in type_specs[json_type]
    ]
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")
    return _PROMPT_TEMPLATE.format(
        today=today_str,
        json_type=json_type,
        field_lines="{\n" + "\n".join(lines) + "\n}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# POST-PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

def _apply_rules(json_type: str, processed: dict, raw_text: str = "") -> dict:
    """
    Normalise and validate extracted fields.

    Amount fields: commas/spaces stripped immediately here via _clean_amount().
    tab_json._normalise_restored_amounts() then cross-validates the cleaned
    amount against the original raw text (before masking) as a second safety net.

    Phone values containing *** are left as-is — tab_json._restore_dict()
    restores them, then tab_json._normalise_restored_phones() applies prefix rules.
    """
    def _v256(raw_val: str) -> str:
        if _is_masked(raw_val):   return raw_val
        result = _normalise_256(raw_val)
        if result:
            return result
        collapsed = re.sub(r'\s', '', raw_text)
        for pat in [r'256(7\d{8})', r'0(7\d{8})', r'(?<!\d)(7\d{8})(?!\d)']:
            m = re.search(pat, collapsed)
            if m:
                return _to_256(m.group(1))
        return ""

    def _v_plus256(raw_val: str) -> str:
        if _is_masked(raw_val):   return raw_val
        result = _normalise_plus256(raw_val)
        if result:
            return result
        collapsed = re.sub(r'\s', '', raw_text)
        for pat in [r'256(7\d{8})', r'0(7\d{8})', r'(?<!\d)(7\d{8})(?!\d)']:
            m = re.search(pat, collapsed)
            if m:
                return _to_plus256(m.group(1))
        return ""

    # ── Beyonic ──────────────────────────────────────────────────────────
    if json_type == "Beyonic":
        phone = processed.get("PhoneNumber", "").strip()
        vp = _v_plus256(phone)
        if vp:   processed["PhoneNumber"] = vp
        else:    processed.pop("PhoneNumber", None)

        txn_raw = processed.get("BeyonicTxnId", "").strip()
        if not _is_masked(txn_raw):
            txn = _extract_beyonic_txn_id(txn_raw, raw_text)
            if txn:  processed["BeyonicTxnId"] = txn
            else:    processed.pop("BeyonicTxnId", None)

        net_raw = processed.get("NetworkTxnId", "").strip()
        if not _is_masked(net_raw):
            net = _extract_network_txn_id(net_raw, raw_text)
            if net:  processed["NetworkTxnId"] = net
            else:    processed.pop("NetworkTxnId", None)

        # Clean amount
        amt = processed.get("Amount", "").strip()
        if amt and not _is_masked(amt):
            processed["Amount"] = _clean_amount(amt, decimal_places=0)

        pd_raw = processed.get("PaymentDate", "").strip()
        if not _is_masked(pd_raw):
            dt = _parse_date(pd_raw) if pd_raw else None
            if dt is not None:
                t = _extract_time(raw_text)
                if t and dt.hour == 0 and dt.minute == 0:
                    dt = dt.replace(hour=t[0], minute=t[1], second=t[2])
            else:
                dt = _scan_date_in_text(raw_text)
            if dt:   processed["PaymentDate"] = dt.strftime("%b %d, %Y %H:%M")
            else:    processed.pop("PaymentDate", None)

    # ── Airtel ───────────────────────────────────────────────────────────
    elif json_type == "Airtel":
        crn = processed.get("customerReferenceNumber", "").strip()
        spn = processed.get("senderPhoneNumber", "").strip()
        if _is_masked(crn) or _is_masked(spn):
            master = crn if crn else spn
            processed["customerReferenceNumber"] = master
            processed["senderPhoneNumber"]        = master
        else:
            mp = _v256(crn or spn)
            if mp:
                processed["customerReferenceNumber"] = mp
                processed["senderPhoneNumber"]        = mp
            else:
                processed.pop("customerReferenceNumber", None)
                processed.pop("senderPhoneNumber", None)

        tid = processed.get("transactionId", "").strip()
        if tid and not _is_masked(tid) and not re.fullmatch(r'\d+', tid):
            tid = re.sub(r'^\D+', '', tid)
        if tid:
            processed["transactionId"] = tid

        # Clean amount — strip commas immediately
        amt = processed.get("paymentAmount", "").strip()
        if amt and not _is_masked(amt):
            processed["paymentAmount"] = _clean_amount(amt, decimal_places=0)

        dt = None
        for df in _AIRTEL_DATE_FIELDS:
            val = processed.get(df, "").strip()
            if _is_masked(val):
                break
            dt = _parse_date(val) if val else None
            if dt:
                break
        if dt is not None:
            t = _extract_time(raw_text)
            if t and dt.hour == 0 and dt.minute == 0:
                dt = dt.replace(hour=t[0], minute=t[1], second=t[2])
        else:
            dt = _scan_date_in_text(raw_text)
        if dt:
            fmt = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            for df in _AIRTEL_DATE_FIELDS:
                if not _is_masked(processed.get(df, "")):
                    processed[df] = fmt

    # ── Bank ─────────────────────────────────────────────────────────────
    elif json_type == "Bank":
        processed["name"] = "FOURTH"
        brn    = processed.get("billRefNumber", "").strip()
        mobile = processed.get("mobile", "").strip()
        if _is_masked(brn) or _is_masked(mobile):
            master = brn if brn else mobile
            processed["billRefNumber"] = master
            processed["mobile"]        = master
        else:
            mp = _v256(brn or mobile)
            if mp:
                processed["billRefNumber"] = mp
                processed["mobile"]        = mp
            else:
                processed.pop("billRefNumber", None)
                processed.pop("mobile", None)

        # Clean amount — strip commas, apply 2 decimal places
        amt = processed.get("amount", "").strip()
        if amt and not _is_masked(amt):
            processed["amount"] = _clean_amount(amt, decimal_places=2)

        cd_raw = processed.get("completionDate", "").strip()
        if not _is_masked(cd_raw):
            dt = _parse_date(cd_raw) if cd_raw else None
            if dt is None:
                dt = _scan_date_in_text(raw_text)
            if dt:   processed["completionDate"] = dt.strftime("%Y-%m-%d")
            else:    processed.pop("completionDate", None)

    # ── Flexipay ─────────────────────────────────────────────────────────
    elif json_type == "Flexipay":
        processed["name"] = "FOURTH"
        tid = processed.get("transactionId", "").strip()
        if not tid and not _is_masked(tid):
            m = _FLEX_TXN_RE.search(raw_text)
            tid = m.group(1) if m else ""
        processed["transactionId"] = tid

        brn    = processed.get("billRefNumber", "").strip()
        mobile = processed.get("mobile", "").strip()
        if _is_masked(brn) or _is_masked(mobile):
            master = brn if brn else mobile
            processed["billRefNumber"] = master
            processed["mobile"]        = master
        else:
            mp = _v256(brn or mobile)
            if mp:
                processed["billRefNumber"] = mp
                processed["mobile"]        = mp
            else:
                processed.pop("billRefNumber", None)
                processed.pop("mobile", None)

        # Clean amount — whole number, no decimals, strip commas immediately
        amt = processed.get("amount", "").strip()
        if amt and not _is_masked(amt):
            processed["amount"] = _clean_amount(amt, decimal_places=0)

        cd_raw = processed.get("completionDate", "").strip()
        if not _is_masked(cd_raw):
            dt = _parse_date(cd_raw) if cd_raw else None
            if dt is None:
                dt = _scan_date_in_text(raw_text)
            if dt:   processed["completionDate"] = dt.strftime("%Y-%m-%d")
            else:    processed.pop("completionDate", None)

    return processed


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def groq_extract(
    text: str,
    json_type: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    return_raw: bool = False,
) -> dict | tuple[dict, dict]:
    """
    Call the Groq API and apply post-processing rules.

    *text* is already privacy-masked (8+-digit numbers have last 3 digits → ***).
    tab_json._restore_dict() restores originals after this returns.
    """
    if not api_key or not api_key.strip():
        raise ValueError("No API key provided. Enter your Groq API key in Settings.")

    type_specs = _build_type_specs()
    if json_type not in type_specs:
        raise ValueError(f"Unknown payment type: {json_type!r}")

    prompt = _build_prompt(json_type)
    body_bytes = json.dumps({
        "model":    model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user",   "content": text},
        ],
        "temperature":     0,
        "max_tokens":      700,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    headers = dict(_HEADERS)
    headers["Authorization"]  = f"Bearer {api_key.strip()}"
    headers["Content-Length"] = str(len(body_bytes))

    ctx = ssl.create_default_context()
    try:
        conn = http.client.HTTPSConnection(GROQ_HOST, timeout=20, context=ctx)
        conn.request("POST", GROQ_PATH, body=body_bytes, headers=headers)
        resp     = conn.getresponse()
        raw_resp = resp.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise ConnectionError(f"Network error: {exc}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if resp.status not in (200, 201):
        raise ConnectionError(f"Groq API error {resp.status}: {raw_resp[:200]}")

    try:
        envelope    = json.loads(raw_resp)
        raw_content = envelope["choices"][0]["message"]["content"].strip()
        raw_ai_dict = json.loads(raw_content)
    except Exception as exc:
        raise ValueError(f"Failed to parse AI response: {exc}")

    processed = {
        k: str(v).strip()
        for k, v in raw_ai_dict.items()
        if str(v).strip()
    }
    processed = _apply_rules(json_type, processed, raw_text=text)

    if return_raw:
        return processed, raw_ai_dict
    return processed