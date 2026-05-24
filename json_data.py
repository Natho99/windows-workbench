# json_data.py
"""
JSON field definitions for each payment type and the payload builder.
"""
from settings_store import load_settings


def get_db_sample(key: str, fallback: str) -> str:
    try:
        cfg = load_settings()
        return cfg.get(key, fallback)
    except Exception:
        return fallback


def get_json_fields() -> dict[str, list[tuple]]:
    return {
        "Beyonic": [
            ("BeyonicWallet", "BeyonicWallet",  "KUZA",         False),
            ("BeyonicTxnId",  "BeyonicTxnId",   "",             False),
            ("Name",          "Name",            "",             False),
            ("PhoneNumber",   "PhoneNumber",     "+256",         False),
            ("Amount",        "Amount",          "",             True),
            ("Network",       "Network",         "MTN Uganda",   False),
            ("NetworkTxnId",  "NetworkTxnId",    "",             False),
            ("PaymentDate",   "PaymentDate",     "",             False),
        ],
        "Airtel": [
            ("creationDate",               "creationDate",               "",             False),
            ("agentAssignmentDateTime",    "agentAssignmentDateTime",    "",             False),
            ("customerReferenceNumber",    "customerReferenceNumber",    "256",          False),
            ("transactionId",              "transactionId",              "",             False),
            ("customerReferenceType",      "customerReferenceType",      "PHONE_NUMBER", False),
            ("paymentAmount",              "paymentAmount",              "",             True),
            ("paymentTransactionDateTime", "paymentTransactionDateTime", "",             False),
            ("senderPhoneNumber",          "senderPhoneNumber",          "256",          False),
        ],
        "Bank": [
            ("name",          "name",          "FOURTH", False),
            ("amount",        "amount",        "",       False),
            ("transactionId", "transactionId", "",       False),
            ("billRefNumber", "billRefNumber", "256",    False),
            ("countryCode",   "countryCode",   "UG",     False),
            ("completionDate","completionDate","",        False),
            ("mobile",        "mobile",        "256",    False),
            ("loanAccountId", "loanAccountId", "",       False),
        ],
        "Flexipay": [
            ("name",          "name",          "FOURTH", False),
            ("amount",        "amount",        "",       False),
            ("transactionId", "transactionId", "",       False),
            ("billRefNumber", "billRefNumber", "256",    False),
            ("countryCode",   "countryCode",   "UG",     False),
            ("completionDate","completionDate","",        False),
            ("mobile",        "mobile",        "256",    False),
            ("loanAccountId", "loanAccountId", "",       False),
        ],
    }


def get_json_hints() -> dict[str, dict[str, str]]:
    return {
        "Beyonic": {
            "BeyonicTxnId": f"e.g. {get_db_sample('BeyonicTxnId', 'T91592568')}",
            "PhoneNumber":  "e.g. +256753890912",
            "Amount":       "numeric  e.g. 126500",
            "PaymentDate":  "e.g. Feb 27, 2026 10:03",
            "NetworkTxnId": f"e.g. {get_db_sample('NetworkTxnId', '141693582907')}",
        },
        "Airtel": {
            "creationDate":               "e.g. 2026-03-21T11:39:23Z",
            "agentAssignmentDateTime":    "e.g. 2026-03-21T11:39:23Z",
            "customerReferenceNumber":    "e.g. 256702987351",
            "transactionId":              f"e.g. {get_db_sample('AirtelTxnId', '143363767927')}",
            "paymentAmount":              "numeric  e.g. 32000",
            "paymentTransactionDateTime": "e.g. 2026-03-21T11:39:23Z",
            "senderPhoneNumber":          "e.g. 256702987351",
        },
        "Bank": {
            "amount":        "e.g. 651000.00",
            "transactionId": f"e.g. {get_db_sample('BankTxnId', 'S34111201')}",
            "billRefNumber": "e.g. 256774718807",
            "completionDate":"e.g. 2026-03-20",
            "mobile":        "e.g. 256774718807",
            "loanAccountId": "e.g. 401d0a03-419f-47b6-b3d1-2884b8128fdc",
        },
        "Flexipay": {
            "amount":        "e.g. 1140000",
            "transactionId": f"e.g. {get_db_sample('FlexipayTxnId', '772774570001')}",
            "billRefNumber": "e.g. 256759762086",
            "completionDate":"e.g. 2026-03-30",
            "mobile":        "e.g. 256759762086",
            "loanAccountId": "e.g. 233ea078-1250-4a8d-985a-d3faa2407580",
        },
    }


class _DynamicData:
    @property
    def JSON_FIELDS(self): return get_json_fields()
    @property
    def JSON_HINTS(self):  return get_json_hints()


_data_proxy = _DynamicData()
JSON_FIELDS = _data_proxy.JSON_FIELDS
JSON_HINTS  = _data_proxy.JSON_HINTS


def build_json_payload(json_type: str, values_dict: dict) -> dict:
    result = {}
    fields = get_json_fields().get(json_type, [])
    for key, _label, _default, is_numeric in fields:
        val = values_dict.get(key, "").strip()
        if key == "name" and json_type in ("Bank", "Flexipay"):
            val = "FOURTH"
        if is_numeric:
            try:
                num = float(val)
                result[key] = int(num) if num == int(num) else num
            except (ValueError, TypeError):
                result[key] = val
        else:
            result[key] = val
    return result