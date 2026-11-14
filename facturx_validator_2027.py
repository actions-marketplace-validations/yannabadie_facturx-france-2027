#!/usr/bin/env python3
"""
Factur-X France 2026–2027 — Validateur CLI & Audit Réglementaire (EN 16931 CII / PDF-A3)
========================================================================================
Outil Open-Source (Licence MIT) en Python 3 standard — ZÉRO dépendance externe.
Édité par YGN — FacturKit : https://yannabadie.github.io/facturkit-2027/

Contrôles effectués localement (100 % hors-ligne, confidentiel RGPD) :
  1. Conteneur hybride PDF/A-3 : extraction de `factur-x.xml` depuis `/EmbeddedFiles`,
     présence de `/AF` (Associated Files) et cohérence XMP `fx:ConformanceLevel`.
  2. Norme européenne EN 16931 / UN-CEFACT CrossIndustryInvoice (CII D16B) :
     profils Factur-X 1.0.07 (`MINIMUM`, `BASIC WL`, `BASIC`, `EN 16931`, `EXTENDED`),
     en-tête documentaire, arithmétique stricte des totaux HT / TVA / TTC (`Decimal`).
  3. Les 4 nouvelles mentions obligatoires françaises 2026–2027 (Décret n° 2022-1299 /
     CGI art. 242 nonies A) :
       [1/4] Numéro SIREN du client professionnel (contrôle mathématique de Luhn).
       [2/4] Catégorie de l'opération (Prestation de services, Livraison de biens, Mixte).
       [3/4] Adresse de livraison des biens si distincte (`ShipToTradeParty`) & date d'opération.
       [4/4] Exigibilité TVA explicite : Option TVA sur les débits (`DueDateTypeCode=5`),
             encaissements (`72`) ou Franchise en base (`VATEX-FR-FRANCHISE` / art. 293 B CGI).
  4. Sécurité financière B2B : validation Luhn SIREN/SIRET vendeur (y compris règle INSEE
     La Poste), clé de TVA intracommunautaire FR, contrôle anti-fraude IBAN Modulo-97,
     et mentions légales Code de commerce (pénalités + indemnité forfaitaire de 40 EUR).

Exemples d'utilisation :
  python3 facturx_validator_2027.py ./examples/facture_conforme_2027.pdf
  python3 facturx_validator_2027.py ./examples/ --strict-2027
  python3 facturx_validator_2027.py ./examples/facture_conforme_2027.pdf --json
  python3 facturx_validator_2027.py ./examples/facture_conforme_2027.pdf --extract-xml ./extrait.xml
  python3 facturx_validator_2027.py --check-siren 732829320 552100554
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zlib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__version__ = "1.0.0"
__author__ = "YGN — FacturKit"
__url__ = "https://yannabadie.github.io/facturkit-2027/"
__audit_url__ = "https://yannabadie.github.io/facturkit-2027/audit-facture-gratuit.html"

# ---------------------------------------------------------------------------
# Constantes UN/CEFACT CII D16B & Factur-X 1.0.07 (EN 16931)
# ---------------------------------------------------------------------------

NS_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS_QDT = "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
NS_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
NS_UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

PROFILES_BY_URN: Dict[str, Dict[str, Any]] = {
    "urn:factur-x.eu:1p0:minimum": {
        "code": "MINIMUM",
        "xmp_levels": {"MINIMUM"},
        "has_lines": False,
        "has_tax_breakdown": False,
        "has_notes": False,
    },
    "urn:factur-x.eu:1p0:basicwl": {
        "code": "BASIC_WL",
        "xmp_levels": {"BASIC WL", "BASIC_WL"},
        "has_lines": False,
        "has_tax_breakdown": True,
        "has_notes": True,
    },
    "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic": {
        "code": "BASIC",
        "xmp_levels": {"BASIC"},
        "has_lines": True,
        "has_tax_breakdown": True,
        "has_notes": True,
    },
    "urn:cen.eu:en16931:2017": {
        "code": "EN16931",
        "xmp_levels": {"EN 16931", "EN16931", "COMFORT"},
        "has_lines": True,
        "has_tax_breakdown": True,
        "has_notes": True,
    },
    "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended": {
        "code": "EXTENDED",
        "xmp_levels": {"EXTENDED"},
        "has_lines": True,
        "has_tax_breakdown": True,
        "has_notes": True,
    },
}

VALID_INVOICE_TYPE_CODES = {
    "380": "Facture commerciale",
    "381": "Avoir (Note de crédit)",
    "384": "Facture rectificative",
    "386": "Facture d'acompte",
    "389": "Facture auto-facturée",
    "326": "Facture partielle",
    "261": "Avoir auto-facturé",
    "383": "Note de débit",
}

DUE_DATE_TYPE_LABELS = {
    "5": "TVA sur les débits (date d'émission de la facture)",
    "3": "TVA sur les débits (date de facture)",
    "29": "TVA à la livraison",
    "72": "TVA sur les encaissements (date de paiement effectif)",
    "432": "TVA à l'encaissement du prix",
}


# ---------------------------------------------------------------------------
# Validations mathématiques & réglementaires (Luhn, SIREN/SIRET, TVA FR, IBAN)
# ---------------------------------------------------------------------------

def dec2(val: Any) -> Decimal:
    """Conversion monétaire exacte à 2 décimales (ROUND_HALF_UP)."""
    if isinstance(val, Decimal):
        d = val
    else:
        s = str(val or "0").strip().replace(",", ".").replace(" ", "").replace("\u00a0", "")
        d = Decimal(s or "0")
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clean_digits(value: str) -> str:
    """Supprime espaces, tirets et points d'un identifiant numérique."""
    return re.sub(r"[\s.\-]+", "", str(value or ""))


def validate_luhn(digits: str) -> bool:
    """Contrôle algorithmique standard de Luhn (ISO/IEC 7812-1)."""
    if not digits or not digits.isdigit():
        return False
    total = 0
    for idx, ch in enumerate(digits[::-1]):
        n = ord(ch) - 48
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (total % 10) == 0


def validate_siren(siren: str) -> bool:
    """Valide un numéro SIREN français (9 chiffres non nuls + clé de Luhn)."""
    cleaned = clean_digits(siren)
    if len(cleaned) != 9 or not cleaned.isdigit() or cleaned == "000000000":
        return False
    return validate_luhn(cleaned)


def validate_siret(siret: str) -> bool:
    """Valide un numéro SIRET français (14 chiffres + Luhn + exception officielle INSEE La Poste)."""
    cleaned = clean_digits(siret)
    if len(cleaned) != 14 or not cleaned.isdigit() or cleaned == "00000000000000":
        return False
    siren_part = cleaned[:9]
    if not validate_siren(siren_part):
        return False
    if validate_luhn(cleaned):
        return True
    # Exception INSEE pour les établissements de La Poste (SIREN 356000000) : somme des chiffres multiple de 5
    if siren_part == "356000000":
        return (sum(ord(c) - 48 for c in cleaned) % 5) == 0
    return False


def validate_siren_or_siret(identifier: str) -> bool:
    cleaned = clean_digits(identifier)
    if len(cleaned) == 9:
        return validate_siren(cleaned)
    if len(cleaned) == 14:
        return validate_siret(cleaned)
    return False


def extract_siren(identifier: str) -> str:
    cleaned = clean_digits(identifier)
    if len(cleaned) == 14 and validate_siret(cleaned):
        return cleaned[:9]
    if len(cleaned) == 9 and validate_siren(cleaned):
        return cleaned
    return cleaned[:9]


def compute_french_vat(siren_or_siret: str) -> str:
    """Calcule le numéro de TVA intracommunautaire français (FR + clé 2 chiffres + SIREN)."""
    siren = extract_siren(siren_or_siret)
    if not validate_siren(siren):
        raise ValueError(f"SIREN invalide au contrôle de Luhn : {siren_or_siret!r}")
    key = (12 + 3 * (int(siren) % 97)) % 97
    return f"FR{key:02d}{siren}"


def validate_french_vat(vat_number: str, expected_siren: Optional[str] = None) -> bool:
    """Vérifie la structure et la clé mathématique d'un numéro de TVA français FRxx999999999."""
    cleaned = re.sub(r"[\s.\-]+", "", str(vat_number or "")).upper()
    if not re.match(r"^FR\d{11}$", cleaned):
        return False
    siren = cleaned[4:]
    if not validate_siren(siren):
        return False
    if expected_siren:
        exp = extract_siren(expected_siren)
        if exp and siren != exp:
            return False
    return compute_french_vat(siren) == cleaned


def validate_iban(iban: str) -> bool:
    """Validation internationale ISO 13616 Modulo-97 d'un IBAN (27 caractères si FR)."""
    cleaned = re.sub(r"\s+", "", str(iban or "")).upper()
    if len(cleaned) < 15 or len(cleaned) > 34:
        return False
    if not re.match(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]+$", cleaned):
        return False
    if cleaned.startswith("FR") and len(cleaned) != 27:
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    digits_parts: List[str] = []
    for ch in rearranged:
        digits_parts.append(ch if ch.isdigit() else str(ord(ch) - 55))
    return (int("".join(digits_parts)) % 97) == 1


# ---------------------------------------------------------------------------
# Extraction sans dépendance du XML Factur-X depuis un PDF/A-3
# ---------------------------------------------------------------------------

def _decompress_pdf_stream(raw_stream: bytes, dict_header: bytes) -> bytes:
    is_flate = (b"/FlateDecode" in dict_header) or bool(re.search(rb"/Fl\b", dict_header))
    if not is_flate:
        return raw_stream
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        for candidate in (raw_stream, raw_stream.strip(b"\r\n")):
            try:
                return zlib.decompress(candidate, wbits)
            except zlib.error:
                continue
    return raw_stream


def extract_facturx_xml_from_pdf(pdf_bytes: bytes) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """
    Extrait le flux XML Factur-X (`factur-x.xml`, `zugferd-invoice.xml` ou `xrechnung.xml`)
    depuis un fichier PDF hybride PDF/A-3 en utilisant uniquement `zlib` et `re`.
    """
    xmp_level_match = re.search(
        rb"<(?:fx|zf):ConformanceLevel>\s*([^<]+?)\s*</(?:fx|zf):ConformanceLevel>",
        pdf_bytes,
    )
    pdfa_part_match = re.search(rb"<pdfaid:part>\s*(\d+)\s*</pdfaid:part>", pdf_bytes)

    meta: Dict[str, Any] = {
        "has_embedded_files": b"/EmbeddedFiles" in pdf_bytes,
        "has_af_tag": bool(re.search(rb"/AF\b", pdf_bytes)),
        "has_pdfa_xmp": pdfa_part_match is not None,
        "pdfa_part": int(pdfa_part_match.group(1)) if pdfa_part_match else None,
        "has_facturx_xmp": (
            b"CrossIndustryDocument:invoice" in pdf_bytes
            or xmp_level_match is not None
        ),
        "xmp_conformance_level": (
            xmp_level_match.group(1).decode("utf-8", errors="replace").strip()
            if xmp_level_match
            else None
        ),
        "filename": None,
    }

    obj_pattern = re.compile(rb"(\d+)\s+\d+\s+obj\b(.*?)endobj", re.DOTALL)
    objects_raw: Dict[int, bytes] = {
        int(m.group(1)): m.group(2) for m in obj_pattern.finditer(pdf_bytes)
    }
    stream_pattern = re.compile(
        rb"(<<.*?>>)\s*stream(?:\r\n|\n)(.*?)(?:\r\n|\n)?endstream",
        re.DOTALL,
    )

    # 1. Support des Object Streams PDF 1.5+ (/Type /ObjStm)
    for body in list(objects_raw.values()):
        sm = stream_pattern.search(body)
        if sm and b"/ObjStm" in sm.group(1):
            unpacked = _decompress_pdf_stream(sm.group(2), sm.group(1))
            if b"CrossIndustryInvoice" in unpacked:
                idx = unpacked.find(b"<?xml")
                if idx != -1:
                    meta["filename"] = "factur-x.xml"
                    return unpacked[idx:].strip(), meta

    # 2. Résolution explicite via dictionnaire /Filespec -> /EF << /F X 0 R >>
    filespec_re = re.compile(
        rb"/(?:UF|F)\s*\(([^)]+\.xml)\).*?/EF\s*<<[^>]*/(?:UF|F)\s+(\d+)\s+\d+\s+R",
        re.DOTALL | re.IGNORECASE,
    )
    for body in objects_raw.values():
        fm = filespec_re.search(body)
        if fm:
            fname = fm.group(1).decode("latin-1", errors="replace")
            ef_obj_id = int(fm.group(2))
            meta["filename"] = fname
            if ef_obj_id in objects_raw:
                sm = stream_pattern.search(objects_raw[ef_obj_id])
                if sm:
                    xml_candidate = _decompress_pdf_stream(sm.group(2), sm.group(1))
                    if b"CrossIndustryInvoice" in xml_candidate or b"Invoice" in xml_candidate:
                        return xml_candidate.strip(), meta

    # 3. Balayage de secours sur tous les flux PDF (compressés FlateDecode ou bruts)
    for sm in stream_pattern.finditer(pdf_bytes):
        candidate = _decompress_pdf_stream(sm.group(2), sm.group(1))
        if b"CrossIndustryInvoice" in candidate:
            for marker in (b"<?xml", b"<rsm:CrossIndustryInvoice", b"<CrossIndustryInvoice"):
                start = candidate.find(marker)
                if start != -1:
                    meta["filename"] = meta["filename"] or "factur-x.xml"
                    return candidate[start:].strip(), meta

    return None, meta


# ---------------------------------------------------------------------------
# Moteur d'Audit Factur-X EN 16931 & Réforme Française 2026–2027
# ---------------------------------------------------------------------------

def _find_text(elem: Optional[ET.Element], path: str, ns: Dict[str, str]) -> str:
    if elem is None:
        return ""
    found = elem.find(path, ns)
    return (found.text or "").strip() if found is not None else ""


def _detect_operation_category(notes_text: str) -> Optional[str]:
    low = notes_text.lower()
    if (
        "opération mixte" in low
        or "operation mixte" in low
        or "double catégorie" in low
        or "double categorie" in low
        or ("livraison de biens" in low and "prestation de services" in low)
        or re.search(r"\bnature\b[^|]{0,40}\bmixte\b", low)
        or re.search(r"\bcat[ée]gorie\b[^|]{0,40}\bmixte\b", low)
    ):
        return "Opération mixte (biens et services)"
    if "prestation de services" in low or "prestations de services" in low:
        return "Prestation de services"
    if "livraison de biens" in low or "livraisons de biens" in low or "vente de marchandises" in low:
        return "Livraison de biens"
    return None


def _is_valid_date_102(date_str: str) -> bool:
    if len(date_str) != 8 or not date_str.isdigit():
        return False
    try:
        dt.datetime.strptime(date_str, "%Y%m%d")
        return True
    except ValueError:
        return False


def validate_facturx_bytes(
    data: bytes,
    source_name: str = "document",
    strict_2027: bool = True,
    allow_b2c: bool = False,
) -> Dict[str, Any]:
    """
    Audite un fichier PDF Factur-X ou XML CII selon :
      - Le standard hybride PDF/A-3 & Factur-X 1.0.07 (EN 16931 CII)
      - Les 4 mentions obligatoires françaises 2026–2027 (CGI art. 242 nonies A / Décret 2022-1299)
      - La cohérence mathématique stricte des montants, clés Luhn SIREN, TVA FR et IBAN Modulo-97.
    """
    is_pdf = data.lstrip().startswith(b"%PDF-")
    checks: List[Dict[str, Any]] = []
    errors: List[str] = []
    warnings: List[str] = []
    pdf_meta: Dict[str, Any] = {}

    # --- 1. Contrôle du conteneur PDF/A-3 si l'entrée est un PDF ---
    if is_pdf:
        xml_bytes, pdf_meta = extract_facturx_xml_from_pdf(data)
        embedded_ok = xml_bytes is not None and bool(pdf_meta.get("has_embedded_files"))
        checks.append({
            "id": "pdf_embedded_xml",
            "category": "PDF/A-3",
            "label": f"Pièce jointe XML Factur-X extractible ({pdf_meta.get('filename') or 'absente'})",
            "passed": embedded_ok,
        })
        checks.append({
            "id": "pdf_af_tag",
            "category": "PDF/A-3",
            "label": "Balise PDF/A-3 Associated Files (/AF) présente",
            "passed": bool(pdf_meta.get("has_af_tag")),
        })
        xmp_ok = bool(pdf_meta.get("has_pdfa_xmp") and pdf_meta.get("has_facturx_xmp"))
        checks.append({
            "id": "pdf_xmp_metadata",
            "category": "PDF/A-3",
            "label": "Métadonnées XMP PDF/A-3B & schéma d'extension Factur-X présents",
            "passed": xmp_ok,
        })
        if xml_bytes is None:
            errors.append(
                "Aucun fichier XML Factur-X (factur-x.xml) trouvé dans /EmbeddedFiles : "
                "un simple PDF visuel sans XML structuré est rejeté par les Plateformes Agréées (PA/PDP)."
            )
            return {
                "source": source_name,
                "is_pdf": True,
                "valid": False,
                "strict_2027": strict_2027,
                "score": 10,
                "pdf_metadata": pdf_meta,
                "checks": checks,
                "mentions_2027": {},
                "errors": errors,
                "warnings": warnings,
                "summary": {},
            }
        if not pdf_meta.get("has_af_tag"):
            warnings.append("Balise /AF absente du catalogue PDF/A-3.")
        if not xmp_ok:
            warnings.append("Métadonnées XMP PDF/A-3 ou schéma fx:ConformanceLevel incomplets.")
    else:
        xml_bytes = data

    # --- 2. Parsing syntaxique XML & espace de noms CII ---
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        errors.append(f"XML Factur-X mal formé (erreur syntaxique) : {exc}")
        return {
            "source": source_name,
            "is_pdf": is_pdf,
            "valid": False,
            "strict_2027": strict_2027,
            "score": 5,
            "pdf_metadata": pdf_meta,
            "checks": checks,
            "mentions_2027": {},
            "errors": errors,
            "warnings": warnings,
            "summary": {},
        }

    ns = {"rsm": NS_RSM, "ram": NS_RAM, "udt": NS_UDT, "qdt": NS_QDT}
    is_cii_root = root.tag == f"{{{NS_RSM}}}CrossIndustryInvoice" or root.tag.endswith("CrossIndustryInvoice")
    checks.append({
        "id": "xml_root_cii",
        "category": "EN16931",
        "label": "Racine UN/CEFACT rsm:CrossIndustryInvoice (CII D16B) conforme",
        "passed": is_cii_root,
    })
    if not is_cii_root:
        errors.append(f"Racine XML invalide : {root.tag!r} (attendu rsm:CrossIndustryInvoice).")

    # --- 3. Identification du profil Factur-X / EN 16931 ---
    profile_urn = _find_text(
        root,
        ".//rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
        ns,
    )
    prof_info = PROFILES_BY_URN.get(profile_urn)
    detected_profile = prof_info["code"] if prof_info else ("CUSTOM" if profile_urn else "MISSING")
    profile_ok = prof_info is not None
    checks.append({
        "id": "profile_urn",
        "category": "EN16931",
        "label": f"Profil officiel Factur-X / EN 16931 reconnu ({detected_profile})",
        "passed": profile_ok,
    })
    if not profile_urn:
        errors.append("Identifiant de profil GuidelineSpecifiedDocumentContextParameter/ram:ID manquant.")
    elif not prof_info:
        warnings.append(f"URN de profil non standard Factur-X 1.0.07 : {profile_urn}")

    if is_pdf and prof_info and pdf_meta.get("xmp_conformance_level"):
        xmp_lvl = pdf_meta["xmp_conformance_level"].upper()
        if xmp_lvl not in prof_info["xmp_levels"]:
            errors.append(
                f"Incohérence entre XMP fx:ConformanceLevel ({xmp_lvl!r}) "
                f"et le profil XML ({detected_profile})."
            )

    # --- 4. En-tête documentaire (Numéro, TypeCode, Date format 102) ---
    doc_id = _find_text(root, ".//rsm:ExchangedDocument/ram:ID", ns)
    type_code = _find_text(root, ".//rsm:ExchangedDocument/ram:TypeCode", ns)
    issue_date_elem = root.find(".//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString", ns)
    issue_date = (issue_date_elem.text or "").strip() if issue_date_elem is not None else ""
    issue_fmt = issue_date_elem.attrib.get("format", "102") if issue_date_elem is not None else ""

    header_ok = (
        bool(doc_id)
        and type_code in VALID_INVOICE_TYPE_CODES
        and issue_fmt == "102"
        and _is_valid_date_102(issue_date)
    )
    checks.append({
        "id": "doc_header",
        "category": "EN16931",
        "label": f"En-tête facture valide (N° {doc_id or 'absent'}, TypeCode {type_code or '?'}, date 102)",
        "passed": header_ok,
    })
    if not doc_id:
        errors.append("Numéro de facture séquentiel (ExchangedDocument/ram:ID) manquant.")
    if type_code not in VALID_INVOICE_TYPE_CODES:
        errors.append(f"TypeCode UNTDID 1001 invalide ou absent : {type_code!r} (ex. 380 facture, 381 avoir).")
    if not _is_valid_date_102(issue_date) or issue_fmt != "102":
        errors.append(
            f"Date d'émission invalide : {issue_date!r} (format attendu YYYYMMDD avec attribut format='102')."
        )

    # --- 5. Vendeur (SIREN Luhn + cohérence clé TVA FR) ---
    seller_elem = root.find(".//ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty", ns)
    buyer_elem = root.find(".//ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty", ns)

    seller_name = _find_text(seller_elem, "ram:Name", ns)
    seller_legal_id_elem = (
        seller_elem.find("ram:SpecifiedLegalOrganization/ram:ID", ns) if seller_elem is not None else None
    )
    seller_siren = (seller_legal_id_elem.text or "").strip() if seller_legal_id_elem is not None else ""
    seller_scheme = seller_legal_id_elem.attrib.get("schemeID", "") if seller_legal_id_elem is not None else ""
    seller_country = _find_text(seller_elem, "ram:PostalTradeAddress/ram:CountryID", ns) or "FR"

    seller_vat = ""
    if seller_elem is not None:
        for tax_reg in seller_elem.findall("ram:SpecifiedTaxRegistration/ram:ID", ns):
            if tax_reg.attrib.get("schemeID", "VA") == "VA" and (tax_reg.text or "").strip():
                seller_vat = (tax_reg.text or "").strip()
                break

    seller_siren_ok = validate_siren_or_siret(seller_siren)
    seller_vat_ok = True
    if seller_vat and seller_vat.upper().startswith("FR"):
        seller_vat_ok = validate_french_vat(seller_vat, expected_siren=seller_siren if seller_siren_ok else None)
        if not seller_vat_ok:
            errors.append(
                f"Numéro de TVA intracommunautaire vendeur invalide ou incohérent avec le SIREN : {seller_vat!r}."
            )
    if seller_country == "FR" and seller_scheme and seller_scheme != "0002":
        warnings.append(f"L'attribut schemeID du SIREN vendeur français devrait être '0002' (trouvé {seller_scheme!r}).")

    checks.append({
        "id": "seller_siren_luhn",
        "category": "EN16931",
        "label": f"SIREN/SIRET vendeur valide par Luhn ({seller_siren or 'absent'})",
        "passed": bool(seller_name) and seller_siren_ok and seller_vat_ok,
    })
    if not seller_name:
        errors.append("Raison sociale ou nom de l'émetteur (SellerTradeParty/ram:Name) manquant.")
    if not seller_siren_ok:
        errors.append(f"SIREN/SIRET vendeur manquant ou invalide au contrôle de Luhn : {seller_siren!r}.")

    # --- 6. Équilibre arithmétique strict des totaux & lignes ---
    settlement = root.find(".//ram:ApplicableHeaderTradeSettlement", ns)
    currency = _find_text(settlement, "ram:InvoiceCurrencyCode", ns) or "EUR"
    iban = _find_text(
        settlement,
        "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID",
        ns,
    )
    sums = (
        settlement.find("ram:SpecifiedTradeSettlementHeaderMonetarySummation", ns)
        if settlement is not None
        else None
    )

    line_total_str = _find_text(sums, "ram:LineTotalAmount", ns)
    allowance_total_str = _find_text(sums, "ram:AllowanceTotalAmount", ns)
    charge_total_str = _find_text(sums, "ram:ChargeTotalAmount", ns)
    tax_basis_str = _find_text(sums, "ram:TaxBasisTotalAmount", ns)
    tax_total_str = _find_text(sums, "ram:TaxTotalAmount", ns)
    grand_total_str = _find_text(sums, "ram:GrandTotalAmount", ns)
    prepaid_str = _find_text(sums, "ram:TotalPrepaidAmount", ns)
    due_payable_str = _find_text(sums, "ram:DuePayableAmount", ns)

    line_elems = root.findall(".//ram:IncludedSupplyChainTradeLineItem", ns)
    math_ok = False
    try:
        if tax_basis_str and grand_total_str:
            tb_d = dec2(tax_basis_str)
            tt_d = dec2(tax_total_str or "0.00")
            gt_d = dec2(grand_total_str)
            math_ok = (tb_d + tt_d) == gt_d
            if not math_ok:
                errors.append(
                    f"Incohérence comptable des totaux : Base HT ({tb_d}) + TVA ({tt_d}) != TTC ({gt_d})."
                )
            if line_total_str:
                lt_d = dec2(line_total_str)
                al_d = dec2(allowance_total_str or "0.00")
                ch_d = dec2(charge_total_str or "0.00")
                if (lt_d - al_d + ch_d) != tb_d:
                    math_ok = False
                    errors.append(
                        f"Incohérence entre LineTotalAmount ({lt_d}) et TaxBasisTotalAmount ({tb_d})."
                    )
                if line_elems:
                    sum_lines = sum(
                        (
                            dec2(
                                _find_text(
                                    li,
                                    "ram:SpecifiedLineTradeSettlement/"
                                    "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
                                    ns,
                                )
                                or "0.00"
                            )
                            for li in line_elems
                        ),
                        Decimal("0.00"),
                    )
                    if sum_lines != lt_d:
                        math_ok = False
                        errors.append(
                            f"La somme des lignes HT ({sum_lines}) diffère de LineTotalAmount ({lt_d})."
                        )
            if due_payable_str:
                dp_d = dec2(due_payable_str)
                pp_d = dec2(prepaid_str or "0.00")
                if (gt_d - pp_d) != dp_d:
                    math_ok = False
                    errors.append(
                        f"Net à payer incohérent : TTC ({gt_d}) - Acompte ({pp_d}) != DuePayableAmount ({dp_d})."
                    )
        else:
            errors.append("Montants obligatoires TaxBasisTotalAmount ou GrandTotalAmount absents.")
    except (InvalidOperation, ValueError) as exc:
        errors.append(f"Montant numérique invalide dans les totaux monétaires : {exc}")

    checks.append({
        "id": "totals_math",
        "category": "EN16931",
        "label": "Équilibre comptable strict (Somme lignes = Base HT, HT + TVA = TTC)",
        "passed": math_ok,
    })

    # =========================================================================
    # AUDIT DES 4 NOUVELLES MENTIONS OBLIGATOIRES FRANCE 2026–2027
    # (CGI art. 242 nonies A / Décret n° 2022-1299)
    # =========================================================================

    notes_elems = root.findall(".//rsm:ExchangedDocument/ram:IncludedNote", ns)
    notes_contents = [(n.findtext("ram:Content", default="", namespaces=ns) or "").strip() for n in notes_elems]
    notes_joined = " | ".join(c for c in notes_contents if c)
    is_minimum_profile = detected_profile == "MINIMUM"

    # --- Mention 1/4 : Numéro SIREN du client professionnel (Luhn + schemeID="0002") ---
    buyer_name = _find_text(buyer_elem, "ram:Name", ns)
    buyer_legal_elem = (
        buyer_elem.find("ram:SpecifiedLegalOrganization/ram:ID", ns) if buyer_elem is not None else None
    )
    buyer_siren = (buyer_legal_elem.text or "").strip() if buyer_legal_elem is not None else ""
    buyer_scheme = buyer_legal_elem.attrib.get("schemeID", "") if buyer_legal_elem is not None else ""
    buyer_country = _find_text(buyer_elem, "ram:PostalTradeAddress/ram:CountryID", ns) or "FR"
    buyer_vat = _find_text(buyer_elem, "ram:SpecifiedTaxRegistration/ram:ID", ns)

    if not buyer_name:
        errors.append("Nom ou raison sociale du client (BuyerTradeParty/ram:Name) manquant.")

    if buyer_siren:
        buyer_siren_valid = validate_siren_or_siret(buyer_siren)
        scheme_ok = (buyer_scheme == "0002") if buyer_country == "FR" else True
        if not buyer_siren_valid:
            errors.append(
                f"[Mention 2027 1/4] SIREN/SIRET client invalide au contrôle mathématique de Luhn : {buyer_siren!r}."
            )
        elif not scheme_ok:
            warnings.append(
                f"[Mention 2027 1/4] SIREN client français présent mais schemeID={buyer_scheme!r} (attendu '0002')."
            )
        if buyer_vat and buyer_vat.upper().startswith("FR") and buyer_siren_valid:
            if not validate_french_vat(buyer_vat, expected_siren=buyer_siren):
                errors.append(f"Numéro de TVA intracommunautaire acheteur incohérent : {buyer_vat!r}.")
        m1_passed = buyer_siren_valid
        m1_detail = f"SIREN/SIRET client valide Luhn ({buyer_siren}, schemeID={buyer_scheme or 'N/A'})"
    elif allow_b2c or buyer_country != "FR":
        m1_passed = True
        m1_detail = (
            f"Client hors France ({buyer_country}) ou B2C autorisé (--allow-b2c)"
            if buyer_country != "FR"
            else "Client particulier B2C (--allow-b2c)"
        )
    else:
        m1_passed = False
        m1_detail = "SIREN client absent (obligatoire sur toute facture B2B domestique 2026–2027)"
        msg_m1 = (
            "[Mention 2027 1/4] SIREN du client professionnel absent "
            "(BuyerTradeParty/SpecifiedLegalOrganization/ram:ID schemeID='0002')."
        )
        if strict_2027:
            errors.append(msg_m1)
        else:
            warnings.append(msg_m1 + " Toléré uniquement en B2C ou client étranger.")

    checks.append({
        "id": "mention_2027_buyer_siren",
        "category": "FRANCE_2027",
        "label": f"[Mention 1/4] SIREN acheteur B2B & clé de Luhn ({buyer_siren or 'absent'})",
        "passed": m1_passed,
    })

    # --- Mention 2/4 : Catégorie / Nature de l'opération ---
    op_category = _detect_operation_category(notes_joined)
    if op_category:
        m2_passed = True
        m2_detail = op_category
    elif is_minimum_profile and not strict_2027:
        m2_passed = True
        m2_detail = "Non applicable en profil MINIMUM (IncludedNote absent du schéma MINIMUM)"
        warnings.append(
            "Le profil MINIMUM ne permet pas d'embarquer IncludedNote pour la catégorie d'opération ; "
            "privilégiez BASIC WL, BASIC ou EN 16931."
        )
    else:
        m2_passed = False
        m2_detail = "Catégorie d'opération absente des notes réglementaires (ExchangedDocument/IncludedNote)"
        msg_m2 = (
            "[Mention 2027 2/4] Catégorie de l'opération absente : préciser 'Prestation de services', "
            "'Livraison de biens' ou 'Opération mixte' (CGI art. 242 nonies A, I-13° bis)."
        )
        if strict_2027:
            errors.append(msg_m2)
        else:
            warnings.append(msg_m2)

    checks.append({
        "id": "mention_2027_operation_category",
        "category": "FRANCE_2027",
        "label": f"[Mention 2/4] Catégorie de l'opération ({op_category or 'absente'})",
        "passed": m2_passed,
    })

    # --- Mention 3/4 : Adresse de livraison des biens (si distincte) & événement de livraison ---
    delivery_elem = root.find(".//ram:ApplicableHeaderTradeDelivery", ns)
    ship_to = delivery_elem.find("ram:ShipToTradeParty", ns) if delivery_elem is not None else None
    occ_date = _find_text(
        delivery_elem,
        "ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/udt:DateTimeString",
        ns,
    )
    buyer_addr_city = _find_text(buyer_elem, "ram:PostalTradeAddress/ram:CityName", ns)
    buyer_addr_zip = _find_text(buyer_elem, "ram:PostalTradeAddress/ram:PostcodeCode", ns)
    buyer_addr_line = _find_text(buyer_elem, "ram:PostalTradeAddress/ram:LineOne", ns)

    if ship_to is not None:
        ship_line = _find_text(ship_to, "ram:PostalTradeAddress/ram:LineOne", ns)
        ship_zip = _find_text(ship_to, "ram:PostalTradeAddress/ram:PostcodeCode", ns)
        ship_city = _find_text(ship_to, "ram:PostalTradeAddress/ram:CityName", ns)
        ship_country = _find_text(ship_to, "ram:PostalTradeAddress/ram:CountryID", ns)
        ship_complete = bool(ship_line and ship_zip and ship_city and ship_country)
        m3_passed = ship_complete
        m3_detail = (
            f"Adresse de livraison distincte renseignée ({ship_zip} {ship_city}, {ship_country})"
            if ship_complete
            else "Bloc ShipToTradeParty présent mais adresse postale de livraison incomplète"
        )
        if not ship_complete:
            errors.append(
                "[Mention 2027 3/4] ShipToTradeParty/PostalTradeAddress incomplet "
                "(LineOne, PostcodeCode, CityName et CountryID requis)."
            )
    elif is_minimum_profile:
        m3_passed = True
        m3_detail = "Profil MINIMUM (bloc PostalTradeAddress non requis par le schéma MINIMUM)"
    else:
        buyer_addr_complete = bool(buyer_addr_line and buyer_addr_zip and buyer_addr_city)
        has_delivery_date = _is_valid_date_102(occ_date)
        m3_passed = buyer_addr_complete and (has_delivery_date or not strict_2027)
        if m3_passed:
            m3_detail = (
                f"Identique à l'adresse client ({buyer_addr_zip} {buyer_addr_city}) "
                f"+ date d'opération {occ_date or 'non précisée'}"
            )
        else:
            m3_detail = "Adresse acheteur ou date d'opération/livraison (ActualDeliverySupplyChainEvent) absente"
            msg_m3 = (
                "[Mention 2027 3/4] Adresse complète du client/livraison ou date effective d'opération "
                "(ActualDeliverySupplyChainEvent) manquante dans ApplicableHeaderTradeDelivery."
            )
            if strict_2027:
                errors.append(msg_m3)
            else:
                warnings.append(msg_m3)

    checks.append({
        "id": "mention_2027_delivery_address",
        "category": "FRANCE_2027",
        "label": f"[Mention 3/4] Lieu de livraison / exécution ({'ShipTo distinct' if ship_to is not None else 'conforme' if m3_passed else 'incomplet'})",
        "passed": m3_passed,
    })

    # --- Mention 4/4 : Option TVA d'après les débits / encaissements OU Franchise art. 293 B ---
    tax_elems = settlement.findall("ram:ApplicableTradeTax", ns) if settlement is not None else []
    notes_low = notes_joined.lower()

    if is_minimum_profile and not tax_elems:
        m4_passed = not strict_2027
        m4_detail = "Ventilation ApplicableTradeTax absente (profil MINIMUM)"
        if strict_2027:
            errors.append(
                "[Mention 2027 4/4] En mode --strict-2027, la ventilation TVA ApplicableTradeTax "
                "(franchise 293 B ou code d'exigibilité débits/encaissements) est requise."
            )
    elif not tax_elems:
        m4_passed = False
        m4_detail = "Aucun bloc ApplicableTradeTax trouvé dans ApplicableHeaderTradeSettlement"
        errors.append("[Mention 2027 4/4] Bloc ApplicableTradeTax manquant.")
    else:
        m4_passed = True
        regime_parts: List[str] = []
        for tx in tax_elems:
            cat = _find_text(tx, "ram:CategoryCode", ns)
            rate_str = _find_text(tx, "ram:RateApplicablePercent", ns) or "0.00"
            ex_reason = _find_text(tx, "ram:ExemptionReason", ns)
            ex_code = _find_text(tx, "ram:ExemptionReasonCode", ns)
            due_code = _find_text(tx, "ram:DueDateTypeCode", ns)
            rate_d = dec2(rate_str)

            if cat in ("E", "Z", "AE", "K", "G", "O") or rate_d == Decimal("0.00"):
                has_exemption = bool(ex_code or ex_reason or "293 b" in notes_low or "autoliquidation" in notes_low)
                if not has_exemption:
                    m4_passed = False
                    errors.append(
                        "[Mention 2027 4/4] Taux TVA à 0 % sans motif légal d'exonération "
                        "(ex. VATEX-FR-FRANCHISE / 'TVA non applicable, art. 293 B du CGI')."
                    )
                else:
                    regime_parts.append(ex_code or ex_reason or "Exonération / Franchise 293 B")
            else:
                has_debits_note = "d'après les débits" in notes_low or "dapres les debits" in notes_low or "sur les débits" in notes_low
                has_enc_note = "encaissements" in notes_low
                if due_code in ("72", "432") and has_debits_note:
                    m4_passed = False
                    errors.append(
                        "[Mention 2027 4/4] Contradiction TVA : note 'TVA d'après les débits' mais "
                        f"DueDateTypeCode={due_code!r} (encaissements)."
                    )
                elif due_code in DUE_DATE_TYPE_LABELS:
                    regime_parts.append(f"Code {due_code} — {DUE_DATE_TYPE_LABELS[due_code]}")
                elif has_debits_note:
                    regime_parts.append("Option TVA acquittée d'après les débits (mention textuelle)")
                    warnings.append(
                        "Mention 'TVA d'après les débits' détectée : pensez à ajouter <ram:DueDateTypeCode>5</ram:DueDateTypeCode>."
                    )
                elif has_enc_note:
                    regime_parts.append("TVA sur les encaissements (mention textuelle)")
                else:
                    msg_m4 = (
                        "[Mention 2027 4/4] Exigibilité TVA non qualifiée dans ApplicableTradeTax : "
                        "préciser <ram:DueDateTypeCode>5</ram:DueDateTypeCode> (option TVA sur les débits) "
                        "ou 72 (TVA sur les encaissements)."
                    )
                    if strict_2027:
                        m4_passed = False
                        errors.append(msg_m4)
                    else:
                        warnings.append(msg_m4)
                        regime_parts.append(f"TVA {rate_d}% (DueDateTypeCode non précisé)")
        m4_detail = " ; ".join(regime_parts) if regime_parts else "Non déterminé"

    checks.append({
        "id": "mention_2027_vat_regime",
        "category": "FRANCE_2027",
        "label": f"[Mention 4/4] Exigibilité TVA / Débits ou Franchise 293 B ({'conforme' if m4_passed else 'à corriger'})",
        "passed": m4_passed,
    })

    # --- 7. Mentions B2B Code de commerce (Pénalités + Indemnité forfaitaire 40 EUR) ---
    if not is_minimum_profile:
        has_40eur = bool(re.search(r"\b40(?:[.,]00)?\s*(?:€|eur)\b", notes_low))
        has_penalties = ("pénalité" in notes_low or "penalite" in notes_low or "retard" in notes_low)
        b2b_legal_ok = has_40eur and has_penalties
        checks.append({
            "id": "b2b_penalties_40eur",
            "category": "CODE_COMMERCE",
            "label": "Mentions B2B art. L441-10 (pénalités de retard + indemnité forfaitaire de 40 EUR)",
            "passed": b2b_legal_ok,
        })
        if not b2b_legal_ok and not allow_b2c:
            msg_40 = (
                "Mentions légales B2B incomplètes dans IncludedNote : pénalités de retard et/ou "
                "indemnité forfaitaire pour frais de recouvrement de 40 EUR (art. L441-10 C. com.)."
            )
            if strict_2027:
                errors.append(msg_40)
            else:
                warnings.append(msg_40)

    # --- 8. Contrôle anti-fraude IBAN Modulo-97 (si un IBAN est présent) ---
    if iban:
        iban_ok = validate_iban(iban)
        checks.append({
            "id": "iban_mod97",
            "category": "SECURITE_PAIEMENT",
            "label": "Contrôle mathématique anti-fraude IBAN vendeur (clé ISO 13616 Modulo-97)",
            "passed": iban_ok,
        })
        if not iban_ok:
            errors.append("IBAN vendeur invalide au contrôle Modulo-97 (risque d'erreur de saisie ou fraude au RIB).")

    passed_count = sum(1 for c in checks if c["passed"])
    score = int(round(100 * passed_count / max(len(checks), 1)))
    valid = len(errors) == 0

    mentions_2027 = {
        "buyer_siren": {"passed": m1_passed, "detail": m1_detail},
        "operation_category": {"passed": m2_passed, "detail": m2_detail},
        "delivery_address": {"passed": m3_passed, "detail": m3_detail},
        "vat_regime": {"passed": m4_passed, "detail": m4_detail},
    }

    return {
        "source": source_name,
        "is_pdf": is_pdf,
        "valid": valid,
        "strict_2027": strict_2027,
        "score": score,
        "pdf_metadata": pdf_meta,
        "checks": checks,
        "mentions_2027": mentions_2027,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "profile": detected_profile,
            "profile_urn": profile_urn,
            "invoice_number": doc_id,
            "type_code": type_code,
            "type_label": VALID_INVOICE_TYPE_CODES.get(type_code, "Autre"),
            "issue_date": (
                f"{issue_date[6:8]}/{issue_date[4:6]}/{issue_date[0:4]}"
                if len(issue_date) == 8
                else issue_date
            ),
            "seller_name": seller_name,
            "seller_siren": seller_siren,
            "seller_vat": seller_vat,
            "seller_country": seller_country,
            "buyer_name": buyer_name,
            "buyer_siren": buyer_siren,
            "buyer_country": buyer_country,
            "operation_category": op_category,
            "distinct_delivery_address": ship_to is not None,
            "currency": currency,
            "tax_basis_ht": tax_basis_str,
            "tax_total": tax_total_str,
            "grand_total_ttc": grand_total_str,
            "due_payable": due_payable_str,
            "line_count": len(line_elems),
            "iban_present": bool(iban),
        },
    }


# ---------------------------------------------------------------------------
# Sortie Console, JSON & Intégration native GitHub Actions
# ---------------------------------------------------------------------------

def _emit_github_ci_integration(results: Sequence[Dict[str, Any]]) -> None:
    """Émet les annotations ::error / ::warning et alimente GITHUB_STEP_SUMMARY si actif."""
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return

    for r in results:
        src = r["source"]
        for err in r["errors"]:
            print(f"::error file={src}::{err}")
        for warn in r["warnings"]:
            print(f"::warning file={src}::{warn}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = [
            "### Audit Factur-X France 2026–2027",
            "",
            "| Fichier | Statut | Score | Profil | N° Facture | SIREN Client | Catégorie 2027 | Total TTC |",
            "| :--- | :---: | :---: | :---: | :--- | :---: | :--- | ---: |",
        ]
        for r in results:
            s = r.get("summary") or {}
            badge = "CONFORME" if r["valid"] else "NON CONFORME"
            ttc = f"{s.get('grand_total_ttc', '-')} {s.get('currency', '')}".strip()
            lines.append(
                f"| `{r['source']}` | **{badge}** | `{r['score']}/100` | `{s.get('profile', '-')}` | "
                f"`{s.get('invoice_number', '-')}` | `{s.get('buyer_siren') or 'absent'}` | "
                f"{s.get('operation_category') or '-'} | {ttc} |"
            )
        lines.extend([
            "",
            f"> Propulsé par [facturx-france-2027](https://github.com/yannabadie/facturx-france-2027) — "
            f"[Testeur en ligne gratuit]({__audit_url__}) · [Suite FacturKit 2027]({__url__})",
            "",
        ])
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError:
            pass


def _print_human_report(results: Sequence[Dict[str, Any]], quiet_footer: bool = False) -> None:
    for r in results:
        status = "CONFORME 2026-2027" if r["valid"] else "NON CONFORME"
        s = r.get("summary") or {}
        print(f"======================================================================")
        print(f" [{status}] {r['source']} — Score : {r['score']}/100")
        print(f"======================================================================")
        if s:
            print(
                f"  Document  : {s.get('type_label')} N° {s.get('invoice_number')} du {s.get('issue_date')} "
                f"| Profil : {s.get('profile')}"
            )
            print(f"  Émetteur  : {s.get('seller_name')} (SIREN {s.get('seller_siren') or 'absent'})")
            print(f"  Acheteur  : {s.get('buyer_name')} (SIREN {s.get('buyer_siren') or 'absent'})")
            print(
                f"  Montants  : HT {s.get('tax_basis_ht')} {s.get('currency')} | "
                f"TVA {s.get('tax_total') or '0.00'} {s.get('currency')} | "
                f"TTC {s.get('grand_total_ttc')} {s.get('currency')}"
            )
            print("  --------------------------------------------------------------------")
        for c in r["checks"]:
            icon = "[OK]" if c["passed"] else "[KO]"
            print(f"  {icon} {c['label']}")
        for e in r["errors"]:
            print(f"  [ERREUR] {e}")
        for w in r["warnings"]:
            print(f"  [AVIS]   {w}")
        print()

    if not quiet_footer:
        passed_files = sum(1 for r in results if r["valid"])
        print(
            f"Bilan : {passed_files}/{len(results)} fichier(s) conforme(s) "
            f"(mode {'strict 2027' if results and results[0]['strict_2027'] else 'standard EN 16931'})."
        )
        print(
            f"Besoin de GÉNÉRER vos devis & factures PDF/A-3 Factur-X hors-ligne sans abonnement ?\n"
            f"  -> Audit interactif gratuit : {__audit_url__}\n"
            f"  -> Studio Factur-X Local 2027 : {__url__}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="facturx_validator_2027.py",
        description=(
            "Validateur Open-Source Factur-X (EN 16931 CII / PDF-A3) & "
            "Audit des 4 mentions obligatoires France 2026-2027 (Zéro dépendance)."
        ),
    )
    p.add_argument(
        "targets",
        nargs="*",
        help="Chemin(s) d'un fichier .pdf, .xml ou d'un dossier de factures à auditer.",
    )
    p.add_argument(
        "--strict-2027",
        dest="strict_2027",
        action="store_true",
        default=True,
        help="Exige strictement les 4 nouvelles mentions B2B françaises 2026-2027 (activé par défaut).",
    )
    p.add_argument(
        "--no-strict-2027",
        dest="strict_2027",
        action="store_false",
        help="Assouplit les mentions spécifiques françaises 2026-2027 en simples avertissements.",
    )
    p.add_argument(
        "--allow-b2c",
        action="store_true",
        help="Autorise l'absence de SIREN acheteur (cas d'un client particulier B2C).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Affiche le rapport d'audit complet au format JSON structuré.",
    )
    p.add_argument(
        "--extract-xml",
        metavar="SORTIE_XML",
        help="Extrait la pièce jointe factur-x.xml d'un PDF Factur-X vers le chemin indiqué.",
    )
    p.add_argument(
        "--check-siren",
        nargs="+",
        metavar="SIREN_OU_SIRET",
        help="Vérifie un ou plusieurs numéros SIREN/SIRET (clé de Luhn) et calcule le N° TVA FR.",
    )
    p.add_argument(
        "--quiet-footer",
        action="store_true",
        help="Masque le pied de page récapitulatif dans la sortie texte.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"facturx-france-2027 v{__version__} ({__author__})",
    )
    return p


def _collect_files(raw_targets: Sequence[str]) -> List[Path]:
    # Tolère le mot-clé optionnel `verify` en premier argument (`python3 facturx_validator_2027.py verify ...`)
    cleaned_targets = list(raw_targets)
    if len(cleaned_targets) >= 2 and cleaned_targets[0].lower() == "verify" and not Path("verify").exists():
        cleaned_targets = cleaned_targets[1:]

    collected: List[Path] = []
    for item in cleaned_targets:
        p = Path(item)
        if not p.exists():
            raise FileNotFoundError(f"Chemin introuvable : {item}")
        if p.is_dir():
            dir_files = sorted(
                sub for sub in p.rglob("*") if sub.is_file() and sub.suffix.lower() in (".pdf", ".xml")
            )
            collected.extend(dir_files)
        else:
            collected.append(p)
    return collected


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.check_siren:
        exit_code = 0
        for raw_num in args.check_siren:
            cleaned = clean_digits(raw_num)
            if len(cleaned) == 9 and validate_siren(cleaned):
                print(f"[VALIDE] SIREN {cleaned} -> TVA intracommunautaire : {compute_french_vat(cleaned)}")
            elif len(cleaned) == 14 and validate_siret(cleaned):
                siren = cleaned[:9]
                print(
                    f"[VALIDE] SIRET {cleaned} (SIREN {siren}) -> "
                    f"TVA intracommunautaire : {compute_french_vat(siren)}"
                )
            else:
                print(f"[INVALIDE] {raw_num} (longueur incorrecte ou échec de la clé de Luhn)")
                exit_code = 1
        return exit_code

    if not args.targets:
        parser.print_help(sys.stderr)
        return 2

    try:
        files = _collect_files(args.targets)
    except FileNotFoundError as exc:
        print(f"[ERREUR] {exc}", file=sys.stderr)
        return 2

    if not files:
        print("[ERREUR] Aucun fichier .pdf ou .xml trouvé dans la cible spécifiée.", file=sys.stderr)
        return 2

    if args.extract_xml:
        if len(files) != 1:
            print("[ERREUR] --extract-xml requiert un unique fichier PDF en entrée.", file=sys.stderr)
            return 2
        raw_bytes = files[0].read_bytes()
        if not raw_bytes.lstrip().startswith(b"%PDF-"):
            print("[ERREUR] --extract-xml attend un fichier PDF Factur-X en entrée.", file=sys.stderr)
            return 2
        xml_out, meta = extract_facturx_xml_from_pdf(raw_bytes)
        if xml_out is None:
            print(f"[ERREUR] Aucun flux XML Factur-X trouvé dans {files[0]}.", file=sys.stderr)
            return 1
        out_path = Path(args.extract_xml)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(xml_out)
        if not args.json:
            print(f"[EXTRACTION OK] {meta.get('filename') or 'factur-x.xml'} -> {out_path} ({len(xml_out)} octets)")

    results = [
        validate_facturx_bytes(
            f.read_bytes(),
            source_name=str(f.name) if len(files) == 1 else str(f),
            strict_2027=args.strict_2027,
            allow_b2c=args.allow_b2c,
        )
        for f in files
    ]

    if args.json:
        payload = results[0] if len(results) == 1 else {"count": len(results), "results": results}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human_report(results, quiet_footer=args.quiet_footer)
        _emit_github_ci_integration(results)

    return 0 if all(r["valid"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
