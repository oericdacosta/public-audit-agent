"""
Data Masking Utilities.

Provides functions to mask sensitive personal data (CPF) for LGPD compliance
while preserving data utility for analytics and auditing.
"""

import re


def mask_cpf(value: str | None) -> str | None:
    """
    Mask a CPF while keeping CNPJ visible.

    CPF (11 digits): Returns `***.XXX.XXX-**` (middle 6 visible)
    CNPJ (14 digits): Returns unchanged (public company data)
    Other: Returns unchanged

    Args:
        value: Document string (CPF or CNPJ)

    Returns:
        Masked CPF or original value
    """
    if not value:
        return value

    # Remove non-digits for analysis
    digits_only = re.sub(r"\D", "", str(value))

    # CPF has 11 digits
    if len(digits_only) == 11:
        # Format: ***.XXX.XXX-**
        return f"***.{digits_only[3:6]}.{digits_only[6:9]}-**"

    # CNPJ (14 digits) or other formats: return as-is
    return value


# Mapping of endpoints to their sensitive fields
SENSITIVE_FIELDS: dict[str, list[str]] = {
    "agentes_publicos": ["cpf_servidor"],
    "notas_pagamentos": ["cpf_pagador"],
    "contratados": ["documento_negociante"],
    "licitantes": ["numero_documento_negociante"],
    "notas_fiscais": ["nu_doc_emitente_nf"],
}


def sanitize_record(record: dict, table_name: str) -> dict:
    """
    Sanitize a record by masking sensitive fields based on target table.

    Args:
        record: Data record dictionary
        table_name: Target table name (used to lookup sensitive fields)

    Returns:
        Sanitized copy of the record
    """
    fields_to_mask = SENSITIVE_FIELDS.get(table_name, [])

    if not fields_to_mask:
        return record

    # Create a copy to avoid mutating original
    sanitized = record.copy()

    for field in fields_to_mask:
        if field in sanitized:
            sanitized[field] = mask_cpf(sanitized[field])

    return sanitized
