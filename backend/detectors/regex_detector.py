"""Regex-based detector for structured PII patterns.

Covers: IP addresses, emails, credit cards, SSNs, phone numbers,
URLs, hostnames, MAC addresses, and high-entropy secrets.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from backend.detectors.base import BaseDetector, DetectedEntity

# --------------------------------------------------------------------------
# Pattern definitions
# --------------------------------------------------------------------------


@dataclass
class PatternDef:
    entity_type: str
    pattern: re.Pattern
    confidence: float = 0.95
    entity_subtype: str | None = None
    validator: Callable[[str], bool] | None = None


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10 == 0


def _is_valid_ip(match_str: str) -> bool:
    """Validate that each octet is 0-255."""
    parts = match_str.split(".")
    if len(parts) != 4:
        return False
    return all(0 <= int(p) <= 255 for p in parts if p.isdigit())


def _is_likely_phone(match_str: str) -> bool:
    """Filter out false positive phone matches (hex strings, SID fragments, IDs, etc.)."""
    digits_only = re.sub(r"[^\d]", "", match_str)
    # All same digit = likely not a phone (0000000000, 1111111111)
    if len(set(digits_only)) <= 2:
        return False
    # Sequential digits = likely not a phone (1234567890)
    if digits_only in "01234567890123456789":
        return False
    # Require formatting (parens, dashes, dots, spaces, or +) for phone numbers.
    # Bare 10-digit blobs are almost always session IDs, counters, or serial
    # numbers in log/CSV data — not phone numbers.
    stripped = match_str.strip()
    has_formatting = any(c in stripped for c in "()-+. ")
    if not has_formatting:
        return False
    return True


# Core patterns
PATTERNS: list[PatternDef] = [
    # --- IP Addresses ---
    PatternDef(
        entity_type="IP_ADDRESS",
        pattern=re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        confidence=0.98,
        validator=_is_valid_ip,
    ),
    # IPv6 (simplified — matches common formats)
    PatternDef(
        entity_type="IP_ADDRESS",
        pattern=re.compile(
            r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
            r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b"
            r"|\b::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}\b"
        ),
        confidence=0.95,
        entity_subtype="IPv6",
    ),

    # --- Email Addresses ---
    PatternDef(
        entity_type="EMAIL",
        pattern=re.compile(
            r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
        ),
        confidence=0.99,
    ),

    # --- Credit Card Numbers ---
    # Visa
    PatternDef(
        entity_type="CREDIT_CARD",
        pattern=re.compile(r"\b4\d{3}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
        confidence=0.95,
        entity_subtype="VISA",
        validator=lambda s: _luhn_check(re.sub(r"[\s\-]", "", s)),
    ),
    # Mastercard
    PatternDef(
        entity_type="CREDIT_CARD",
        pattern=re.compile(r"\b5[1-5]\d{2}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
        confidence=0.95,
        entity_subtype="MASTERCARD",
        validator=lambda s: _luhn_check(re.sub(r"[\s\-]", "", s)),
    ),
    # Amex
    PatternDef(
        entity_type="CREDIT_CARD",
        pattern=re.compile(r"\b3[47]\d{2}[\s\-]?\d{6}[\s\-]?\d{5}\b"),
        confidence=0.95,
        entity_subtype="AMEX",
        validator=lambda s: _luhn_check(re.sub(r"[\s\-]", "", s)),
    ),
    # Generic (13-19 digits, Luhn validated)
    PatternDef(
        entity_type="CREDIT_CARD",
        pattern=re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}\b"),
        confidence=0.7,
        validator=lambda s: _luhn_check(re.sub(r"[\s\-]", "", s)),
    ),

    # --- SSN (US) — requires at least one separator to avoid matching bare digit sequences ---
    # With dashes or spaces (the standard SSN format people actually write)
    PatternDef(
        entity_type="SSN",
        pattern=re.compile(
            r"\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b"
        ),
        confidence=0.95,
    ),
    # Bare 9-digit SSN — only when preceded by a context keyword
    PatternDef(
        entity_type="SSN",
        pattern=re.compile(
            r"(?:SSN|Social\s*Security(?:\s*(?:Number|No\.?|#))?)"
            r"\s*[:=]?\s+"
            r"(?!000|666|9\d{2})\d{3}(?!00)\d{2}(?!0000)\d{4}\b",
            re.IGNORECASE,
        ),
        confidence=0.90,
        entity_subtype="CONTEXT",
    ),

    # --- Phone Numbers ---
    # US format — requires leading word boundary or start-of-string,
    # and must not be preceded/followed by hex prefix or longer digits
    PatternDef(
        entity_type="PHONE",
        pattern=re.compile(
            r"(?<![0-9a-fA-FxX\-])"  # not preceded by hex chars, digits, or dash
            r"(?:\+?1[\s\-.]?)?"
            r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
            r"(?!\d)"  # not followed by more digits
        ),
        confidence=0.85,
        validator=_is_likely_phone,
    ),
    # International with country code (+ required — avoids false positives)
    PatternDef(
        entity_type="PHONE",
        pattern=re.compile(
            r"\+\d{1,3}[\s\-.]?\(?\d{1,4}\)?[\s\-.]?\d{2,4}[\s\-.]?\d{2,4}[\s\-.]?\d{0,4}\b"
        ),
        confidence=0.80,
    ),

    # --- URLs ---
    PatternDef(
        entity_type="URL",
        pattern=re.compile(
            r"https?://[^\s<>\"')\]]+",
            re.IGNORECASE,
        ),
        confidence=0.99,
    ),

    # --- Hostnames / Internal domains ---
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)"
            r"{1,3}(?:internal|local|corp|intranet|private|lan|company|"
            r"example|test|staging|dev|prod)\b",
            re.IGNORECASE,
        ),
        confidence=0.80,
    ),

    # --- MAC Addresses ---
    PatternDef(
        entity_type="MAC_ADDRESS",
        pattern=re.compile(
            r"\b(?:[0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}\b"
        ),
        confidence=0.95,
    ),

    # --- API Keys / Secrets (high-entropy strings) ---
    # AWS access key
    PatternDef(
        entity_type="API_KEY",
        pattern=re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        confidence=0.98,
        entity_subtype="AWS",
    ),
    # Stripe API keys (sk_live_, pk_live_, sk_test_, pk_test_, rk_live_, rk_test_)
    PatternDef(
        entity_type="API_KEY",
        pattern=re.compile(r"\b[spr]k_(?:live|test)_[a-zA-Z0-9]{20,}\b"),
        confidence=0.98,
        entity_subtype="STRIPE",
    ),
    # GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_)
    PatternDef(
        entity_type="API_KEY",
        pattern=re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b"),
        confidence=0.98,
        entity_subtype="GITHUB",
    ),
    # OpenAI API keys (sk-...)
    PatternDef(
        entity_type="API_KEY",
        pattern=re.compile(r"\bsk-[a-zA-Z0-9\-]{20,}\b"),
        confidence=0.95,
        entity_subtype="OPENAI",
    ),
    # Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-, xoxs-)
    PatternDef(
        entity_type="API_KEY",
        pattern=re.compile(r"\bxox[bpars]-[a-zA-Z0-9\-]{20,}\b"),
        confidence=0.98,
        entity_subtype="SLACK",
    ),
    # Generic secret patterns (key= or token= or password= followed by value)
    PatternDef(
        entity_type="SECRET",
        pattern=re.compile(
            r"""(?:api[_\-]?key|api[_\-]?secret|access[_\-]?token|"""
            r"""auth[_\-]?token|secret[_\-]?key|password|passwd|pwd)"""
            r"""[\s]*[=:]\s*['"]?([a-zA-Z0-9\-_.]{16,})['"]?""",
            re.IGNORECASE,
        ),
        confidence=0.90,
    ),

    # --- Connection Strings ---
    PatternDef(
        entity_type="CONNECTION_STRING",
        pattern=re.compile(
            r"(?:mongodb|postgresql|postgres|mysql|redis|amqp|mssql)"
            r"(?:\+\w+)?://[^\s<>\"']+",
            re.IGNORECASE,
        ),
        confidence=0.98,
    ),

    # --- IBAN (International Bank Account Number) ---
    # 2 letter country code + 2 check digits + up to 30 alphanumeric chars
    PatternDef(
        entity_type="IBAN",
        pattern=re.compile(
            r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?(?:[\dA-Z]{4}[\s]?){1,7}[\dA-Z]{1,4}\b"
        ),
        confidence=0.90,
    ),

    # --- SWIFT/BIC Code ---
    # 8 or 11 alphanumeric chars (bank code + country + location + optional branch)
    PatternDef(
        entity_type="SWIFT_BIC",
        pattern=re.compile(
            r"(?:SWIFT|BIC|SWIFT/BIC)[\s:]*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b",
            re.IGNORECASE,
        ),
        confidence=0.92,
    ),

    # --- US Bank Routing Number (ABA) ---
    # 9 digits, requires context keyword to avoid SSN false positives
    PatternDef(
        entity_type="ROUTING_NUMBER",
        pattern=re.compile(
            r"(?:routing|ABA|routing\s*(?:number|no|#))[\s:#]*(\d{9})\b",
            re.IGNORECASE,
        ),
        confidence=0.90,
    ),

    # --- Bank Account Number ---
    # 8-17 digits, requires context keyword
    PatternDef(
        entity_type="BANK_ACCOUNT",
        pattern=re.compile(
            r"(?:account|acct)[\s]*(?:number|no|num|#)?[\s:#]*(\d{8,17})\b",
            re.IGNORECASE,
        ),
        confidence=0.85,
    ),

    # --- US Driver's License ---
    # State-specific formats with context keyword
    PatternDef(
        entity_type="DRIVERS_LICENSE",
        pattern=re.compile(
            r"(?:driver'?s?\s*licen[sc]e|DL|license\s*(?:number|no|#))[\s:#]*"
            r"([A-Z]{1,2}\s*[A-Z]?\d{4,10})\b",
            re.IGNORECASE,
        ),
        confidence=0.88,
    ),

    # --- NPI (National Provider Identifier) ---
    # 10-digit number used in US healthcare, requires context
    PatternDef(
        entity_type="NPI",
        pattern=re.compile(
            r"(?:NPI|National\s*Provider)[\s:#]*(\d{10})\b",
            re.IGNORECASE,
        ),
        confidence=0.90,
    ),

    # --- AWS Account ID ---
    # 12 digits, requires context keyword
    PatternDef(
        entity_type="AWS_ACCOUNT_ID",
        pattern=re.compile(
            r"(?:AWS\s*Account\s*(?:ID|#)?|account[\s_-]*id)[\s:#]*(\d{12})\b",
            re.IGNORECASE,
        ),
        confidence=0.88,
    ),

    # --- Base64 Encoded Payloads ---
    # Long base64 strings (50+ chars) preceded by common indicators
    PatternDef(
        entity_type="ENCODED_PAYLOAD",
        pattern=re.compile(
            r"(?:-enc(?:oded)?|base64|--data|payload)\s+([A-Za-z0-9+/]{50,}={0,2})",
            re.IGNORECASE,
        ),
        confidence=0.85,
    ),

    # --- EIN (US Employer Identification Number) ---
    # XX-XXXXXXX format, first two digits 10-99, often preceded by "EIN" context
    PatternDef(
        entity_type="EIN",
        pattern=re.compile(
            r"(?:EIN|Tax\s*ID|Employer\s*(?:Identification|ID))"
            r"[\s:#()\w]*?(\d{2}-\d{7})",
            re.IGNORECASE,
        ),
        confidence=0.92,
    ),

    # --- Bearer / Authorization Tokens ---
    PatternDef(
        entity_type="AUTH_TOKEN",
        pattern=re.compile(
            r"(?:Authorization|Bearer|Token)[\s:]+([A-Za-z0-9\-_\.]{20,})",
            re.IGNORECASE,
        ),
        confidence=0.95,
        entity_subtype="BEARER",
    ),

    # --- JWT Tokens (standalone eyJ...) ---
    PatternDef(
        entity_type="AUTH_TOKEN",
        pattern=re.compile(
            r"\beyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"
        ),
        confidence=0.98,
        entity_subtype="JWT",
    ),

    # --- Private Key Blocks ---
    PatternDef(
        entity_type="PRIVATE_KEY",
        pattern=re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        ),
        confidence=0.99,
    ),

    # --- File Paths with Usernames ---
    # Unix: /home/username/ or /Users/username/
    PatternDef(
        entity_type="FILE_PATH",
        pattern=re.compile(
            r"(?:/home/|/Users/)([a-zA-Z0-9._\-]+)(?:/[^\s:\"']*)?",
        ),
        confidence=0.85,
        entity_subtype="UNIX",
    ),
    # Windows: C:\Users\username\
    PatternDef(
        entity_type="FILE_PATH",
        pattern=re.compile(
            r"[A-Za-z]:\\Users\\([a-zA-Z0-9._\-]+)(?:\\[^\s:\"']*)?",
        ),
        confidence=0.85,
        entity_subtype="WINDOWS",
    ),

    # --- HTTP Cookies ---
    PatternDef(
        entity_type="AUTH_TOKEN",
        pattern=re.compile(
            r"(?:Cookie|Set-Cookie)[\s:]+([^\r\n;]{20,})",
            re.IGNORECASE,
        ),
        confidence=0.90,
        entity_subtype="COOKIE",
    ),

    # --- Basic Auth in URLs ---
    PatternDef(
        entity_type="CREDENTIAL",
        pattern=re.compile(
            r"https?://([^:@\s]+):([^@\s]+)@[^\s<>\"']+",
            re.IGNORECASE,
        ),
        confidence=0.98,
    ),

    # --- Server/Host Naming Patterns ---
    # Catches PROD-DB-01, web-server-03, app-worker-2, etc.
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"\b(?:prod|production|staging|stage|stg|dev|development|test|qa|uat|demo)"
            r"[\-_]"
            r"(?:[a-zA-Z0-9]+[\-_]?){1,4}"
            r"[\-_]?\d{1,3}\b",
            re.IGNORECASE,
        ),
        confidence=0.80,
        entity_subtype="SERVER_NAME",
    ),

    # =====================================================================
    # Security / SIEM Log Patterns
    # =====================================================================

    # --- Usernames in Key-Value Pairs ---
    # Covers: user=jsmith, username=admin, srcuser=DOMAIN\jsmith,
    # dstuser=admin, UserName=jsmith, AccountName=jsmith, loginID=jsmith,
    # user_id=jsmith, src_user=jsmith, dest_user=admin, usrName=admin,
    # Domain=ACME (AD domain names are sensitive org identifiers)
    PatternDef(
        entity_type="USERNAME",
        pattern=re.compile(
            r"(?:(?:src_?|dst_?|dest_?|source_?|target_?)?(?:user(?:_?name)?|usr(?:_?name)?|login_?(?:id|name)?|account_?name|logon_?name|actor|domain)"
            r")\s*[=:]\s*"
            r"(?:\"([^\"]{1,80})\"|'([^']{1,80})'|([^\s,;|\"'}{)\]]{1,80}))",
            re.IGNORECASE,
        ),
        confidence=0.90,
    ),

    # --- Domain\Username (Windows/AD format) ---
    # Covers: ACME\jsmith, acme\admin, NT AUTHORITY\SYSTEM
    PatternDef(
        entity_type="USERNAME",
        pattern=re.compile(
            r"\b([A-Za-z][A-Za-z0-9\-]{1,15})\\([a-zA-Z0-9._\-]{1,64})\b"
        ),
        confidence=0.92,
        entity_subtype="DOMAIN_USER",
    ),

    # --- Hostnames in Key-Value Pairs ---
    # Covers: host=WEB-01, hostname=DC-SERVER, ComputerName=DESKTOP-ABC,
    # src_host=fw-01, dst_host=db-02, dvchost=FIREWALL-01,
    # Workstation Name: WS-01, deviceHostName=PROD-FW
    # Excludes IP addresses (let the IP pattern handle those)
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"(?:(?:src_?|dst_?|dest_?|source_?|target_?|dvc)?(?:host(?:_?name)?|computer_?name|workstation(?:\s+name)?|device_?(?:host_?name|name)?|machine_?name)"
            r")\s*[=:]\s*"
            r"(?!(?:\d{1,3}\.){3}\d{1,3}\b)"  # negative lookahead: skip IP addresses
            r"(?:\"([^\"]{1,80})\"|'([^']{1,80})'|([^\s,;|\"'}{)\]]{1,80}))",
            re.IGNORECASE,
        ),
        confidence=0.88,
        entity_subtype="LOG_HOST",
    ),

    # --- Windows SIDs ---
    # S-1-5-21-3623811015-3361044348-30300820-1013
    PatternDef(
        entity_type="WINDOWS_SID",
        pattern=re.compile(
            r"\bS-1-\d{1,2}(?:-\d+){1,15}\b"
        ),
        confidence=0.95,
    ),

    # --- LDAP Distinguished Names ---
    # CN=John Smith,OU=Users,DC=acme,DC=com
    PatternDef(
        entity_type="LDAP_DN",
        pattern=re.compile(
            r"\bCN=[^,]+(?:,\s*(?:OU|DC|CN|O|L|ST|C)=[^,]+){2,}",
            re.IGNORECASE,
        ),
        confidence=0.92,
    ),

    # --- CEF/LEEF Source and Destination Fields ---
    # CEF format: suser=jsmith duser=admin shost=web01 dhost=db01
    # sntdom=ACME
    PatternDef(
        entity_type="USERNAME",
        pattern=re.compile(
            r"\b(?:suser|duser|cs\dLabel)\s*=\s*([^\s|]{1,80})",
            re.IGNORECASE,
        ),
        confidence=0.88,
        entity_subtype="CEF_USER",
    ),
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"\b(?:shost|dhost|deviceHostName|deviceDnsDomain)\s*=\s*([^\s|]{1,80})",
            re.IGNORECASE,
        ),
        confidence=0.88,
        entity_subtype="CEF_HOST",
    ),

    # --- Palo Alto Specific ---
    # Palo Alto CSV fields: srcuser, dstuser in traffic/threat logs
    # Serial numbers: serial=012345678901
    PatternDef(
        entity_type="DEVICE_ID",
        pattern=re.compile(
            r"(?:serial|device_?(?:serial|id)|agent_?id|aid|sensor_?id)"
            r"\s*[=:]\s*"
            r"([A-Za-z0-9\-]{8,64})",
            re.IGNORECASE,
        ),
        confidence=0.85,
    ),

    # --- CrowdStrike / EDR Specific ---
    # SHA256 hashes (file indicators)
    PatternDef(
        entity_type="HASH",
        pattern=re.compile(
            r"\b(?:sha256|SHA256|hash|filehash)\s*[=:]\s*([a-fA-F0-9]{64})\b"
        ),
        confidence=0.95,
        entity_subtype="SHA256",
    ),
    # MD5 hashes
    PatternDef(
        entity_type="HASH",
        pattern=re.compile(
            r"\b(?:md5|MD5)\s*[=:]\s*([a-fA-F0-9]{32})\b"
        ),
        confidence=0.90,
        entity_subtype="MD5",
    ),
    # Command line paths (often contain usernames/sensitive info)
    PatternDef(
        entity_type="COMMAND_LINE",
        pattern=re.compile(
            r"(?:CommandLine|command_line|cmd_line|process_command_line)"
            r"\s*[=:]\s*"
            r"(?:\"([^\"]{10,500})\"|([^\r\n]{10,500}))",
            re.IGNORECASE,
        ),
        confidence=0.88,
    ),

    # --- Windows Event Log Patterns ---
    # Account Name:\t\tjsmith
    # Workstation Name:\tWS-01
    PatternDef(
        entity_type="USERNAME",
        pattern=re.compile(
            r"Account\s+Name\s*:\s*([A-Za-z0-9._\-\\]{1,80})",
            re.IGNORECASE,
        ),
        confidence=0.90,
        entity_subtype="WINDOWS_EVENT",
    ),
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"Workstation\s+Name\s*:\s*([A-Za-z0-9._\-]{1,80})",
            re.IGNORECASE,
        ),
        confidence=0.88,
        entity_subtype="WINDOWS_EVENT",
    ),

    # --- Generic Computer/Desktop/Server Names ---
    # DESKTOP-ABC1234, LAPTOP-XYZ5678, SERVER-01, DC-01, FW-01, WS-01
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"\b(?:DESKTOP|LAPTOP|SERVER|WORKSTATION|WS|DC|FW|SW|AP|NAS)"
            r"[\-_][A-Z0-9]{2,15}\b"
        ),
        confidence=0.82,
        entity_subtype="DEVICE_NAME",
    ),

    # --- Network/Security Appliance Hostnames ---
    # PA-5260-EDGE-01, ASA-FW-01, FortiGate-200F-01, WLC-MAIN-01, etc.
    # Pattern: 2-4 segments of ALPHA/NUM joined by hyphens, ending in digits
    PatternDef(
        entity_type="HOSTNAME",
        pattern=re.compile(
            r"\b(?:PA|ASA|FG|FGT|FortiGate|WLC|ISE|IDS|IPS|WAF|NAC|VPN|LB|F5)"
            r"[\-_]"
            r"(?:[A-Za-z0-9]+[\-_]){1,4}"
            r"[A-Za-z0-9]+\b",
            re.IGNORECASE,
        ),
        confidence=0.82,
        entity_subtype="APPLIANCE",
    ),

    # =====================================================================
    # Street Addresses
    # =====================================================================

    # --- US Street Address with standard suffix ---
    # Matches: "123 Main Street", "5678 N. Oak Ave, Suite 100"
    # Requires: street number + 1-4 name words + recognized street suffix
    PatternDef(
        entity_type="ADDRESS",
        pattern=re.compile(
            r"(?<!\.)\b\d{1,6}\s+"                                       # Street number (not after dot, e.g. IP)
            r"(?:(?:N|S|E|W|NE|NW|SE|SW|North|South|East|West)\.?\s+)?"  # Optional directional
            r"(?:"
            r"(?:\d{1,3}(?:st|nd|rd|th)\s+)"                             # Ordinal street name (e.g. "45th")
            r"|"
            r"(?:[A-Za-z][A-Za-z']+\s+)"                                 # Word street name
            r"){1,4}"
            r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|"
            r"Lane|Ln|Way|Court|Ct|Place|Pl|Circle|Cir|Trail|Trl|"
            r"Terrace|Ter|Parkway|Pkwy|Highway|Hwy|Pike|Loop|Run|"
            r"Path|Crossing|Xing|Commons|Point|Square|Sq|Alley|Aly)"
            r"\b\.?"
            r"(?:\s*,?\s*"                                                # Optional unit (Apt, Suite, etc.)
            r"(?:Suite|Ste|Apt|Apartment|Unit|#|Bldg|Building|Floor|Fl|Room|Rm)"
            r"\.?\s*#?\s*\w{1,6})?"
            r"(?:\s*,\s*[A-Za-z][A-Za-z\s\.]{1,30}?"                     # Optional City
            r",\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?",                        # Optional State + ZIP
            re.IGNORECASE,
        ),
        confidence=0.92,
    ),

    # --- PO Box ---
    PatternDef(
        entity_type="ADDRESS",
        pattern=re.compile(
            r"\bP\.?\s*O\.?\s*Box\s+\d{1,10}\b",
            re.IGNORECASE,
        ),
        confidence=0.95,
        entity_subtype="PO_BOX",
    ),

    # --- City, State ZIP (standalone, e.g. "Springfield, IL 62701") ---
    PatternDef(
        entity_type="ADDRESS",
        pattern=re.compile(
            r"\b[A-Z][a-z]{2,20}(?:\s+[A-Z][a-z]{2,20})?"               # City (1-2 words)
            r",\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\b",                        # State + ZIP
        ),
        confidence=0.80,
        entity_subtype="CITY_STATE_ZIP",
    ),

    # =====================================================================
    # Person Names (context-based — NER handles free-form names)
    # =====================================================================

    # --- Honorific + Name: "Mr. John Smith", "Dr. Jane Doe" ---
    PatternDef(
        entity_type="PERSON",
        pattern=re.compile(
            r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Professor|Rev|Reverend|Hon|Judge|"
            r"Sgt|Cpl|Lt|Capt|Maj|Col|Gen)"
            r"\.?[ \t]+"
            r"[A-Z][a-z]{1,20}"                                          # First name
            r"(?:[ \t]+[A-Z]\.)?"                                         # Optional middle initial (period required)
            r"(?:[ \t]+[A-Z][a-z]{1,20})?",                               # Optional last name
        ),
        confidence=0.85,
        entity_subtype="HONORIFIC",
    ),

    # --- Label + Name: "Name: John Smith", "Patient: Jane Doe" ---
    PatternDef(
        entity_type="PERSON",
        pattern=re.compile(
            r"(?:(?:full[ \t]+)?name|patient|client|employee|applicant|borrower|"
            r"insured|defendant|plaintiff|beneficiary|contact|attn|attention|"
            r"recipient|resident|tenant|owner|guarantor|claimant|witness|"
            r"subscriber|member|policyholder|cardholder|account[ \t]*holder)"
            r"[ \t]*[:=][ \t]*"
            r"[A-Z][a-z]{1,20}"                                          # First name
            r"(?:[ \t]+[A-Z]\.)?"                                         # Optional middle initial (period required)
            r"(?:[ \t]+[A-Z][a-z]{1,20}){1,2}",                           # Last name (1-2 parts)
            re.IGNORECASE,
        ),
        confidence=0.85,
        entity_subtype="LABEL",
    ),

    # --- "Dear [Name]" salutation ---
    PatternDef(
        entity_type="PERSON",
        pattern=re.compile(
            r"\bDear[ \t]+"
            r"(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?[ \t]+)?"                  # Optional honorific
            r"[A-Z][a-z]{1,20}"                                          # First/last name
            r"(?:[ \t]+[A-Z][a-z]{1,20})?",                               # Optional second name
        ),
        confidence=0.80,
        entity_subtype="SALUTATION",
    ),
]


class RegexDetector(BaseDetector):
    """Detects sensitive entities using regex patterns with optional validation."""

    def __init__(self, extra_patterns: list[PatternDef] | None = None):
        self._patterns = PATTERNS.copy()
        if extra_patterns:
            self._patterns.extend(extra_patterns)

    @property
    def name(self) -> str:
        return "regex"

    def detect(self, text: str) -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []

        for pdef in self._patterns:
            for match in pdef.pattern.finditer(text):
                matched_text = match.group(0)

                # Run optional validator
                if pdef.validator and not pdef.validator(matched_text):
                    continue

                entities.append(
                    DetectedEntity(
                        entity_type=pdef.entity_type,
                        value=matched_text,
                        start=match.start(),
                        end=match.end(),
                        confidence=pdef.confidence,
                        detection_method="regex",
                        entity_subtype=pdef.entity_subtype,
                    )
                )

        # Resolve overlaps: longer matches win, then higher confidence
        entities = self._resolve_overlaps(entities)
        return entities

    def _resolve_overlaps(self, entities: list[DetectedEntity]) -> list[DetectedEntity]:
        """Remove overlapping detections. Longer match wins; on tie, higher confidence wins."""
        if not entities:
            return entities

        # Sort by length desc, then confidence desc
        entities.sort(key=lambda e: (-(e.end - e.start), -e.confidence))

        result: list[DetectedEntity] = []
        occupied: list[tuple[int, int]] = []

        for entity in entities:
            overlaps = any(
                entity.start < occ_end and entity.end > occ_start
                for occ_start, occ_end in occupied
            )
            if not overlaps:
                result.append(entity)
                occupied.append((entity.start, entity.end))

        # Sort by position for consistent output
        result.sort(key=lambda e: e.start)
        return result
