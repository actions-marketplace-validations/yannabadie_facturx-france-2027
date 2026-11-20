#!/usr/bin/env python3
"""
Suite de tests unitaires & réglementaires — facturx_validator_2027.py
Couvre : Luhn SIREN/SIRET (dont exception La Poste), clé TVA FR, IBAN Modulo-97 dynamique,
extraction PDF/A-3 sans dépendance, normes EN 16931 CII et les 4 mentions France 2026-2027.
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import facturx_validator_2027 as fv

ROOT_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = ROOT_DIR / "examples"


def _build_dynamic_valid_iban(country: str, bban: str) -> str:
    """Construit dynamiquement en mémoire un IBAN ISO 13616 valide (évite toute chaîne statique)."""
    rearranged = bban.upper() + country.upper() + "00"
    digits = "".join(ch if ch.isdigit() else str(ord(ch) - 55) for ch in rearranged)
    check = 98 - (int(digits) % 97)
    return f"{country.upper()}{check:02d}{bban.upper()}"


class TestFacturXValidator2027(unittest.TestCase):
    def test_siren_and_siret_luhn_including_la_poste(self) -> None:
        self.assertTrue(fv.validate_siren("732829320"))
        self.assertTrue(fv.validate_siren("552 100 554"))
        self.assertTrue(fv.validate_siren("443-061-841"))
        self.assertFalse(fv.validate_siren("000000000"))
        self.assertFalse(fv.validate_siren("552100559"))
        self.assertFalse(fv.validate_siren("12345"))

        # SIRET standard Luhn
        self.assertTrue(fv.validate_siret("73282932000074"))
        self.assertFalse(fv.validate_siret("73282932000075"))

        # Exception officielle INSEE La Poste (SIREN 356000000 : somme des 14 chiffres multiple de 5)
        # 3+5+6+0+0+0+0+0+0 + 4+8+0+0+4 = 30 (multiple de 5, mais non Luhn)
        self.assertTrue(fv.validate_siret("35600000048004"))
        self.assertFalse(fv.validate_siret("35600000048003"))

    def test_french_vat_computation_and_validation(self) -> None:
        self.assertEqual(fv.compute_french_vat("732829320"), "FR44732829320")
        self.assertEqual(fv.compute_french_vat("443061841"), "FR64443061841")
        self.assertTrue(fv.validate_french_vat("FR44732829320", expected_siren="732829320"))
        self.assertFalse(fv.validate_french_vat("FR99732829320", expected_siren="732829320"))
        self.assertFalse(fv.validate_french_vat("FR44732829320", expected_siren="552100554"))

    def test_iban_modulo97_dynamic(self) -> None:
        # BBAN français synthétique de 23 caractères -> IBAN total 27 caractères
        valid_iban = _build_dynamic_valid_iban("FR", "20041010050500013M02606")
        self.assertEqual(len(valid_iban), 27)
        self.assertTrue(fv.validate_iban(valid_iban))
        corrupted = valid_iban[:-1] + ("7" if valid_iban[-1] != "7" else "8")
        self.assertFalse(fv.validate_iban(corrupted))
        # Longueur incorrecte pour FR
        short_fr = _build_dynamic_valid_iban("FR", "123456789012345")
        self.assertFalse(fv.validate_iban(short_fr))

    def test_hybrid_pdf_facturx_extraction_and_audit(self) -> None:
        pdf_path = EXAMPLES_DIR / "facture_conforme_2027.pdf"
        raw_pdf = pdf_path.read_bytes()
        xml_bytes, meta = fv.extract_facturx_xml_from_pdf(raw_pdf)
        self.assertIsNotNone(xml_bytes)
        self.assertTrue(meta["has_embedded_files"])
        self.assertTrue(meta["has_af_tag"])
        self.assertEqual(meta["pdfa_part"], 3)
        self.assertEqual(meta["xmp_conformance_level"], "BASIC")

        report = fv.validate_facturx_bytes(raw_pdf, source_name=pdf_path.name, strict_2027=True)
        self.assertTrue(report["valid"])
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["errors"], [])
        self.assertTrue(all(m["passed"] for m in report["mentions_2027"].values()))

    def test_en16931_tva_debits_and_distinct_shipto(self) -> None:
        xml_path = EXAMPLES_DIR / "facture_conforme_tva_debits_en16931.xml"
        report = fv.validate_facturx_bytes(xml_path.read_bytes(), source_name=xml_path.name, strict_2027=True)
        self.assertTrue(report["valid"])
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["summary"]["profile"], "EN16931")
        self.assertTrue(report["summary"]["distinct_delivery_address"])
        self.assertIn("Opération mixte", report["summary"]["operation_category"])
        self.assertIn("Code 5", report["mentions_2027"]["vat_regime"]["detail"])

    def test_non_compliant_fixture_catches_all_2027_errors(self) -> None:
        bad_path = EXAMPLES_DIR / "facture_non_conforme_2027.xml"
        report = fv.validate_facturx_bytes(bad_path.read_bytes(), source_name=bad_path.name, strict_2027=True)
        self.assertFalse(report["valid"])
        self.assertLess(report["score"], 60)
        failed_ids = {c["id"] for c in report["checks"] if not c["passed"]}
        self.assertIn("totals_math", failed_ids)
        self.assertIn("mention_2027_buyer_siren", failed_ids)
        self.assertIn("mention_2027_operation_category", failed_ids)
        self.assertIn("mention_2027_delivery_address", failed_ids)
        self.assertIn("mention_2027_vat_regime", failed_ids)

    def test_plain_pdf_without_xml_is_rejected(self) -> None:
        fake_pdf = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
        report = fv.validate_facturx_bytes(fake_pdf, source_name="simple.pdf")
        self.assertFalse(report["valid"])
        self.assertTrue(any("factur-x.xml" in e for e in report["errors"]))

    def test_vat_contradiction_debits_note_vs_code_72(self) -> None:
        xml_text = (EXAMPLES_DIR / "facture_conforme_tva_debits_en16931.xml").read_text(encoding="utf-8")
        contradictory = xml_text.replace(
            "<ram:DueDateTypeCode>5</ram:DueDateTypeCode>",
            "<ram:DueDateTypeCode>72</ram:DueDateTypeCode>",
        )
        report = fv.validate_facturx_bytes(contradictory.encode("utf-8"), strict_2027=True)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Contradiction TVA" in e for e in report["errors"]))

    def test_cli_json_extract_siren_and_github_summary(self) -> None:
        # 1. --check-siren
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fv.main(["--check-siren", "732829320", "552100554"])
        self.assertEqual(code, 0)
        self.assertIn("FR44732829320", buf.getvalue())

        # 2. --json + --extract-xml
        with tempfile.TemporaryDirectory() as tmpdir:
            extracted_xml = Path(tmpdir) / "extrait.xml"
            out_json = io.StringIO()
            with redirect_stdout(out_json):
                code = fv.main([
                    str(EXAMPLES_DIR / "facture_conforme_2027.pdf"),
                    "--extract-xml",
                    str(extracted_xml),
                    "--json",
                ])
            self.assertEqual(code, 0)
            self.assertTrue(extracted_xml.exists())
            parsed = json.loads(out_json.getvalue())
            self.assertTrue(parsed["valid"])
            self.assertEqual(parsed["summary"]["invoice_number"], "FAC-2026-0104")

            # 3. GitHub Actions Step Summary integration
            summary_md = Path(tmpdir) / "step_summary.md"
            old_gha = os.environ.get("GITHUB_ACTIONS")
            old_sum = os.environ.get("GITHUB_STEP_SUMMARY")
            try:
                os.environ["GITHUB_ACTIONS"] = "true"
                os.environ["GITHUB_STEP_SUMMARY"] = str(summary_md)
                human_out = io.StringIO()
                with redirect_stdout(human_out):
                    code2 = fv.main(["verify", str(EXAMPLES_DIR / "facture_conforme_2027.pdf")])
                self.assertEqual(code2, 0)
                md_text = summary_md.read_text(encoding="utf-8")
                self.assertIn("FAC-2026-0104", md_text)
                self.assertIn("CONFORME", md_text)
            finally:
                if old_gha is None:
                    os.environ.pop("GITHUB_ACTIONS", None)
                else:
                    os.environ["GITHUB_ACTIONS"] = old_gha
                if old_sum is None:
                    os.environ.pop("GITHUB_STEP_SUMMARY", None)
                else:
                    os.environ["GITHUB_STEP_SUMMARY"] = old_sum

        # 4. Cible introuvable -> exit code 2
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            code_missing = fv.main(["./introuvable_404.pdf"])
        self.assertEqual(code_missing, 2)

    def test_cli_csv_batch_export_file_and_stdout(self) -> None:
        # 1. Export lot complet vers un fichier CSV UTF-8-SIG (Excel-ready)
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "rapport_lot.csv"
            out_buf = io.StringIO()
            with redirect_stdout(out_buf):
                code = fv.main([str(EXAMPLES_DIR), "--csv", str(csv_file), "--quiet-footer"])
            # examples/ contient 2 factures conformes + 1 non conforme -> code 1
            self.assertEqual(code, 1)
            self.assertTrue(csv_file.exists())
            raw_bytes = csv_file.read_bytes()
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"), "CSV file must carry UTF-8-SIG BOM for Excel")

            with csv_file.open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 4)
            self.assertEqual(list(rows[0].keys()), list(fv.CSV_FIELDNAMES))

            by_name = {Path(r["source"]).name: r for r in rows}
            self.assertEqual(by_name["facture_conforme_2027.pdf"]["valid"], "True")
            self.assertEqual(by_name["facture_conforme_2027.pdf"]["score"], "100")
            self.assertEqual(by_name["facture_conforme_2027.pdf"]["buyer_siren"], "552100554")
            self.assertEqual(by_name["facture_conforme_tva_debits_en16931.xml"]["valid"], "True")
            self.assertEqual(by_name["facture_non_conforme_2027.xml"]["valid"], "False")
            self.assertGreater(int(by_name["facture_non_conforme_2027.xml"]["errors_count"]), 0)

        # 2. Export CSV direct sur stdout (--csv sans argument ou --csv -)
        stdout_csv = io.StringIO()
        with redirect_stdout(stdout_csv):
            code_ok = fv.main([str(EXAMPLES_DIR / "facture_conforme_2027.pdf"), "--csv", "-"])
        self.assertEqual(code_ok, 0)
        parsed_rows = list(csv.DictReader(io.StringIO(stdout_csv.getvalue())))
        self.assertEqual(len(parsed_rows), 1)
        self.assertEqual(parsed_rows[0]["invoice_number"], "FAC-2026-0104")
        self.assertEqual(parsed_rows[0]["valid"], "True")


if __name__ == "__main__":
    unittest.main()
