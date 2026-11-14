# Factur-X France 2026–2027 — Validateur Factur-X Python Gratuit (EN 16931 CII / PDF-A3) & GitHub Action

[![CI — Factur-X France 2027](https://github.com/yannabadie/facturx-france-2027/actions/workflows/ci.yml/badge.svg)](https://github.com/yannabadie/facturx-france-2027/actions/workflows/ci.yml)
[![Release v1.0.0](https://img.shields.io/github/v/release/yannabadie/facturx-france-2027?color=2563eb&label=Release)](https://github.com/yannabadie/facturx-france-2027/releases/latest)
[![Python 3.8+ | Zero Dependency](https://img.shields.io/badge/Python-3.8%2B%20%7C%20Z%C3%A9ro%20d%C3%A9pendance-0f766e)](./facturx_validator_2027.py)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-1e293b)](./LICENSE)
[![Audit Facture en Ligne Gratuit](https://img.shields.io/badge/Testeur%20Web%20Gratuit-Audit%2030s%20(100%25%20Navigateur)-dc2626)](https://yannabadie.github.io/facturkit-2027/audit-facture-gratuit.html)

**`facturx-france-2027`** est un **validateur Factur-X gratuit en Python** (fichier unique `facturx_validator_2027.py`, **zéro dépendance externe**, bibliothèque standard Python 3 uniquement) accompagné d'une **GitHub Action réutilisable** pour auditer localement ou en CI/CD :

1. Les **factures hybrides PDF/A-3 Factur-X** (extraction native de `factur-x.xml` depuis `/EmbeddedFiles`, vérification `/AF` et métadonnées XMP `fx:ConformanceLevel`) ;
2. Les **flux XML UN/CEFACT CrossIndustryInvoice (CII D16B)** selon les profils officiels **Factur-X 1.0.07 / norme européenne EN 16931** (`MINIMUM`, `BASIC WL`, `BASIC`, `EN 16931`, `EXTENDED`) ;
3. Les **4 nouvelles mentions obligatoires facture 2026–2027** imposées en France par le Décret n° 2022-1299 et l'article 242 nonies A du CGI (SIREN client validé par Luhn, catégorie de l'opération, adresse de livraison distincte, option TVA sur les débits ou franchise art. 293 B).

> **Pas de terminal sous la main ? Testez une facture en 30 secondes dans votre navigateur :**
> - **[Audit Éclair Conformité Facture 2026–2027 (Testeur Web 100 % Gratuit & Local)](https://yannabadie.github.io/facturkit-2027/audit-facture-gratuit.html)** — aucune donnée envoyée sur un serveur.
> - **Besoin d'un générateur Factur-X sans abonnement ?** Découvrez **[FacturKit 2027 & Studio Factur-X Local 2027](https://yannabadie.github.io/facturkit-2027/)** : création hors-ligne de devis et factures PDF/A-3 + XML Factur-X conformes EN 16931, carnet clients SIREN Luhn, inspecteur visuel et automatisations TPE en paiement unique (zéro abonnement mensuel).

---

## Sommaire

1. [Calendrier officiel de la facturation électronique en France (2026–2027)](#1-calendrier-officiel-de-la-facturation-électronique-en-france-20262027)
2. [Les 4 nouvelles mentions obligatoires sur les factures 2026–2027 & mapping XML Factur-X](#2-les-4-nouvelles-mentions-obligatoires-sur-les-factures-20262027--mapping-xml-factur-x)
3. [Démarrage rapide — Validateur Factur-X Python (CLI zéro dépendance)](#3-démarrage-rapide--validateur-factur-x-python-cli-zéro-dépendance)
4. [Utilisation comme module Python (`factur-x python`)](#4-utilisation-comme-module-python-factur-x-python)
5. [Intégration CI/CD — GitHub Action réutilisable](#5-intégration-cicd--github-action-réutilisable)
6. [Liste complète des 14 contrôles techniques, comptables et fiscaux](#6-liste-complète-des-14-contrôles-techniques-comptables-et-fiscaux)
7. [Générateur Factur-X sans abonnement : aller plus loin avec FacturKit 2027](#7-générateur-factur-x-sans-abonnement--aller-plus-loin-avec-facturkit-2027)
8. [FAQ — Factur-X, Python & Réforme 2026–2027](#8-faq--factur-x-python--réforme-20262027)
9. [English Summary](#9-english-summary--factur-x-france-2027-python-validator--github-action)

---

## 1. Calendrier officiel de la facturation électronique en France (2026–2027)

Conformément à l'**article 91 de la Loi de finances pour 2024** (n° 2023-1322), la réforme de la facturation électronique B2B domestique (*e-invoicing*) et de la transmission des données de transaction (*e-reporting*) s'applique à **toutes les entreprises assujetties à la TVA établies en France, y compris les micro-entreprises en franchise en base de TVA (art. 293 B du CGI)** :

| Échéance légale | Entreprises concernées | Obligations applicables |
| :--- | :--- | :--- |
| **1er septembre 2026** | **Toutes les entreprises françaises** (Micro-entreprises, EI, TPE, PME, ETI, Grandes Entreprises) | **Obligation universelle de RÉCEPTION** des factures électroniques fournisseurs aux formats socles (**Factur-X**, UBL, CII) via une Plateforme Agréée (PA, ex-PDP). Un simple PDF « image » ou bureautique envoyé par email par une GE/ETI n'est plus une facture fiscale conforme. |
| **1er septembre 2026** | Grandes Entreprises (GE) & Entreprises de Taille Intermédiaire (ETI) | **Obligation d'ÉMISSION** des factures électroniques B2B structurées + *e-reporting*. |
| **1er septembre 2027** | **PME, TPE, artisans, professions libérales & micro-entrepreneurs** | **Obligation d'ÉMISSION** des factures électroniques B2B au format structuré (**Factur-X EN 16931**, UBL ou CII) + *e-reporting* B2C et international + application stricte des 4 nouvelles mentions obligatoires. |

> **Sanctions fiscales prévues (CGI art. 1737 & art. 1788 D) :**
> - **15 € d'amende par facture** non émise sous forme électronique structurée (plafonnée à 15 000 € par année civile) ;
> - **250 € d'amende par transmission** d'*e-reporting* manquante (plafonnée à 15 000 € par an) ;
> - **15 € par mention obligatoire manquante ou inexacte** sur une facture, en sus des sanctions pénales et commerciales de l'article L441-9 du Code de commerce (jusqu'à **75 000 €** pour une personne physique et **375 000 €** pour une société).

---

## 2. Les 4 nouvelles mentions obligatoires sur les factures 2026–2027 & mapping XML Factur-X

Au-delà des mentions habituelles (numérotation chronologique continue, identité de l'émetteur, mention `EI` pour un entrepreneur individuel, pénalités de retard et indemnité forfaitaire de `40 €` en B2B), le **Décret n° 2022-1299** impose **4 nouvelles mentions obligatoires** que toute Plateforme Agréée (PA/PDP) contrôle dans le fichier `factur-x.xml` :

| # | Nouvelle mention obligatoire (CGI art. 242 nonies A) | Règle métier & contrôle `facturx_validator_2027.py` | Chemin XPath exact dans `factur-x.xml` (UN/CEFACT CII D16B) |
| :-: | :--- | :--- | :--- |
| **1** | **Numéro SIREN du client professionnel** | 9 chiffres exactement, non nul, validé mathématiquement par l'**algorithme de Luhn** (attribut `schemeID="0002"` obligatoire en France). | `rsm:SupplyChainTradeTransaction / ram:ApplicableHeaderTradeAgreement / ram:BuyerTradeParty / ram:SpecifiedLegalOrganization / ram:ID[@schemeID="0002"]` |
| **2** | **Catégorie (nature) de l'opération** | Distinction explicite entre : **`Livraison de biens`**, **`Prestation de services`** ou **`Opération mixte`** (biens et services). | `rsm:ExchangedDocument / ram:IncludedNote / ram:Content` (recommandé avec `ram:SubjectCode = REG` ou `AAI`) |
| **3** | **Adresse de livraison des biens (si différente)** | Si le lieu de livraison diffère de l'adresse de facturation du client, bloc complet code postal, voie, ville et pays + date d'opération. | `ram:ApplicableHeaderTradeDelivery / ram:ShipToTradeParty / ram:PostalTradeAddress` + `ram:ActualDeliverySupplyChainEvent` |
| **4** | **Option pour le paiement de la TVA d'après les débits** *(ou régime d'exonération)* | Code d'exigibilité explicite (`5` = TVA sur les débits, `72` = TVA sur les encaissements) ou code de franchise en base (`VATEX-FR-FRANCHISE` + mention *« TVA non applicable, art. 293 B du CGI »*). | `ram:ApplicableHeaderTradeSettlement / ram:ApplicableTradeTax / ram:DueDateTypeCode` (`5` ou `72`) ou `ram:ExemptionReasonCode` (`VATEX-FR-FRANCHISE`) |

---

## 3. Démarrage rapide — Validateur Factur-X Python (CLI zéro dépendance)

Aucune installation `pip`, aucun compilateur C (`lxml`, `poppler`, `Ghostscript`) n'est nécessaire. Un simple environnement **Python 3.8+** (macOS, Linux, Windows, conteneur Alpine ou runner CI) suffit.

### Téléchargement en une ligne

```bash
curl -sSLO https://raw.githubusercontent.com/yannabadie/facturx-france-2027/main/facturx_validator_2027.py
chmod +x facturx_validator_2027.py
```

*(Ou clonez le dépôt complet avec les factures d'exemple PDF/A-3 et XML :)*

```bash
git clone https://github.com/yannabadie/facturx-france-2027.git
cd facturx-france-2027
```

### Exemples de commandes CLI

```bash
# 1. Auditer une facture PDF/A-3 Factur-X hybride reçue d'un fournisseur (extrait et valide factur-x.xml)
python3 facturx_validator_2027.py ./examples/facture_conforme_2027.pdf

# 2. Auditer un fichier XML CII EN 16931 (TVA sur les débits + adresse ShipTo distincte)
python3 facturx_validator_2027.py ./examples/facture_conforme_tva_debits_en16931.xml

# 3. Auditer un dossier complet de factures en lot (retourne le code 1 si au moins une facture échoue)
python3 facturx_validator_2027.py ./dossier_factures_fournisseurs/ --strict-2027

# 4. Obtenir un rapport JSON structuré (idéal pour un ERP, n8n, Make ou un webhook interne)
python3 facturx_validator_2027.py ./examples/facture_conforme_2027.pdf --json

# 5. Extraire la pièce jointe XML cachée dans un PDF Factur-X vers un fichier lisible
python3 facturx_validator_2027.py ./examples/facture_conforme_2027.pdf --extract-xml ./factur-x-extrait.xml

# 6. Vérifier instantanément des numéros SIREN / SIRET (Luhn + règle INSEE La Poste) et calculer la TVA FR
python3 facturx_validator_2027.py --check-siren 732829320 552100554 443061841
```

### Aperçu de la sortie terminal

```text
======================================================================
 [CONFORME 2026-2027] facture_conforme_2027.pdf — Score : 100/100
======================================================================
  Document  : Facture commerciale N° FAC-2026-0104 du 14/11/2026 | Profil : BASIC
  Émetteur  : Claire Moreau Conseil (SIREN 732829320)
  Acheteur  : Atelier Mécanique Rhodanien SAS (SIREN 552100554)
  Montants  : HT 1790.00 EUR | TVA 0.00 EUR | TTC 1790.00 EUR
  --------------------------------------------------------------------
  [OK] Pièce jointe XML Factur-X extractible (factur-x.xml)
  [OK] Balise PDF/A-3 Associated Files (/AF) présente
  [OK] Métadonnées XMP PDF/A-3B & schéma d'extension Factur-X présents
  [OK] Racine UN/CEFACT rsm:CrossIndustryInvoice (CII D16B) conforme
  [OK] Profil officiel Factur-X / EN 16931 reconnu (BASIC)
  [OK] En-tête facture valide (N° FAC-2026-0104, TypeCode 380, date 102)
  [OK] SIREN/SIRET vendeur valide par Luhn (732829320)
  [OK] Équilibre comptable strict (Somme lignes = Base HT, HT + TVA = TTC)
  [OK] [Mention 1/4] SIREN acheteur B2B & clé de Luhn (552100554)
  [OK] [Mention 2/4] Catégorie de l'opération (Prestation de services)
  [OK] [Mention 3/4] Lieu de livraison / exécution (conforme)
  [OK] [Mention 4/4] Exigibilité TVA / Débits ou Franchise 293 B (conforme)
  [OK] Mentions B2B art. L441-10 (pénalités de retard + indemnité forfaitaire de 40 EUR)
```

---

## 4. Utilisation comme module Python (`factur-x python`)

Vous pouvez importer `facturx_validator_2027.py` directement dans une application Django, FastAPI, Flask, Odoo ou un script comptable :

```python
from pathlib import Path
from facturx_validator_2027 import (
    compute_french_vat,
    extract_facturx_xml_from_pdf,
    validate_facturx_bytes,
    validate_siren,
)

# 1. Validation SIREN (Luhn) & calcul automatique du N° de TVA intracommunautaire français
assert validate_siren("732829320") is True
print(compute_french_vat("732829320"))  # -> "FR44732829320"

# 2. Audit complet d'un PDF Factur-X hybride ou d'un XML CII
pdf_bytes = Path("examples/facture_conforme_2027.pdf").read_bytes()
report = validate_facturx_bytes(pdf_bytes, source_name="facture_fournisseur.pdf", strict_2027=True)

print("Conforme :", report["valid"], "| Score :", report["score"])
print("Mentions 2027 :", report["mentions_2027"])

# 3. Extraction brute du XML embarqué depuis un PDF/A-3
xml_bytes, pdf_metadata = extract_facturx_xml_from_pdf(pdf_bytes)
print("Niveau XMP :", pdf_metadata["xmp_conformance_level"], "| Taille XML :", len(xml_bytes))
```

---

## 5. Intégration CI/CD — GitHub Action réutilisable

Empêchez toute régression sur votre moteur de facturation en ajoutant cette **GitHub Action** dans `.github/workflows/facturx.yml` : elle annote automatiquement les fichiers en erreur dans les Pull Requests et génère un tableau récapitulatif Markdown dans l'onglet **Summary** de GitHub Actions.

```yaml
name: Contrôle Conformité Factur-X 2027

on: [push, pull_request]

jobs:
  audit-facturx:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Valider les factures PDF/A-3 & XML Factur-X ( Norme EN 16931 + France 2027 )
        uses: yannabadie/facturx-france-2027@v1.0.0
        with:
          target: "./mes-factures-test/"
          strict-2027: "true"
          allow-b2c: "false"
```

---

## 6. Liste complète des 14 contrôles techniques, comptables et fiscaux

| Identifiant du contrôle | Catégorie | Ce qui est vérifié mathématiquement |
| :--- | :--- | :--- |
| `pdf_embedded_xml` | PDF/A-3 | Décompression `/FlateDecode` & `/ObjStm` et extraction effective du XML dans `/EmbeddedFiles`. |
| `pdf_af_tag` | PDF/A-3 | Présence de l'entrée `/AF` (*Associated Files*) exigée par la norme ISO 19005-3 (PDF/A-3). |
| `pdf_xmp_metadata` | PDF/A-3 | Métadonnées XMP `pdfaid:part=3` et concordance entre `fx:ConformanceLevel` et le profil XML. |
| `xml_root_cii` | EN 16931 | Syntaxe XML UTF-8 et espace de noms `urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100`. |
| `profile_urn` | EN 16931 | Conformité URN aux profils `MINIMUM`, `BASIC WL`, `BASIC`, `EN 16931` ou `EXTENDED`. |
| `doc_header` | EN 16931 | Numéro `ram:ID`, code UNTDID 1001 (`380`, `381`, `384`, `386`, `389`) et date calendaire `format="102"`. |
| `seller_siren_luhn` | EN 16931 | SIREN (9 chiffres) ou SIRET (14 chiffres, y compris règle INSEE La Poste `356000000`) + clé TVA FR. |
| `totals_math` | Comptabilité | Arithmétique `Decimal` stricte : `Somme lignes = LineTotalAmount`, `Base HT + TVA = TTC`, `Net à payer`. |
| `mention_2027_buyer_siren` | France 2027 | **[Mention 1/4]** Présence et validité Luhn du SIREN client B2B (`schemeID="0002"`). |
| `mention_2027_operation_category` | France 2027 | **[Mention 2/4]** Qualification explicite *Prestation de services*, *Livraison de biens* ou *Opération mixte*. |
| `mention_2027_delivery_address` | France 2027 | **[Mention 3/4]** Intégrité `ShipToTradeParty` si adresse distincte + date d'opération (`ActualDeliverySupplyChainEvent`). |
| `mention_2027_vat_regime` | France 2027 | **[Mention 4/4]** Cohérence `DueDateTypeCode` (`5` débits / `72` encaissements) ou `VATEX-FR-FRANCHISE` (art. 293 B). |
| `b2b_penalties_40eur` | Code de commerce | Pénalités de retard et indemnité forfaitaire de recouvrement de `40 €` (art. L441-10 et D441-5 C. com.). |
| `iban_mod97` | Anti-fraude | Vérification ISO 13616 Modulo-97 de l'IBAN bénéficiaire lorsqu'il figure dans le XML. |

---

## 7. Générateur Factur-X sans abonnement : aller plus loin avec FacturKit 2027

Ce dépôt open-source MIT couvre l'**audit et la vérification** de vos flux Factur-X.
Si vous cherchez un **générateur Factur-X sans abonnement** prêt à l'emploi pour **créer vos devis et factures PDF/A-3 + XML conformes** sans payer 20 à 35 €/mois de SaaS ni exposer votre chiffre d'affaires dans le cloud :

| Outil / Édition | Usage principal | Modèle & Confidentialité | Lien d'accès |
| :--- | :--- | :--- | :--- |
| **Audit Éclair Facture 2026–2027** | Tester gratuitement la conformité d'une facture existante en 30 secondes dans le navigateur | **Gratuit (0 €)** — 100 % local | **[Lancer le testeur gratuit](https://yannabadie.github.io/facturkit-2027/audit-facture-gratuit.html)** |
| **Pack Pilotage Micro & TPE 2027** *(Aperçu PDF gratuit joint dans [Releases](https://github.com/yannabadie/facturx-france-2027/releases/latest))* | Tableur complet `.xlsx` (livre des recettes, seuils franchise TVA 2026–2027, simulateur URSSAF/IR) + checklists + modèles | **19 € paiement unique** (zéro abonnement) | **[Voir le Pack Pilotage](https://yannabadie.github.io/facturkit-2027/)** |
| **Studio Factur-X Local 2027** *(Le générateur Factur-X sans abonnement)* | Application web monopage **100 % hors-ligne** + CLI lot JSON/CSV : génère de vraies factures **PDF/A-3 hybrides embarquant `factur-x.xml`**, carnet clients SIREN Luhn, devis & factures, inspecteur visuel | **49 € paiement unique** (100 % local & confidentiel RGPD) | **[Découvrir Studio Factur-X Local](https://yannabadie.github.io/facturkit-2027/)** |
| **Suite Opérations & Automatisation TPE 2027 (Édition Pro)** | Inclut les 2 outils ci-dessus + **3 workflows n8n / Make** prêts à importer (tri factures reçues, relances impayés, pré-comptabilité) + Kit Registre IA (EU AI Act PME) | **119 € paiement unique** | **[Voir la Suite Complète](https://yannabadie.github.io/facturkit-2027/)** |

---

## 8. FAQ — Factur-X, Python & Réforme 2026–2027

### Un PDF classique généré sur Word, Excel ou Canva est-il une facture Factur-X valide ?
**Non.** Un PDF bureautique standard ne contient qu'une couche graphique. Une facture **Factur-X** est un fichier **PDF/A-3 hybride** qui embarque en pièce jointe interne (`/EmbeddedFiles` + `/AF`) un fichier XML normalisé `factur-x.xml` structuré selon la norme **UN/CEFACT CrossIndustryInvoice (EN 16931)**. Vous pouvez le vérifier immédiatement avec `python3 facturx_validator_2027.py ma_facture.pdf` ou sur le [testeur gratuit en ligne](https://yannabadie.github.io/facturkit-2027/audit-facture-gratuit.html).

### Les micro-entrepreneurs (auto-entrepreneurs) en franchise de TVA (art. 293 B) sont-ils concernés ?
**Oui, intégralement.** Le fait d'être non redevable de la TVA (franchise en base, article 293 B du CGI) ne dispense ni de l'**obligation de réception au 1er septembre 2026**, ni de l'**obligation d'émission au 1er septembre 2027** pour vos clients professionnels (B2B), ni de l'*e-reporting* pour vos clients particuliers (B2C). Dans le XML Factur-X, la franchise en base se traduit par `CategoryCode = E`, `RateApplicablePercent = 0.00` et `ExemptionReasonCode = VATEX-FR-FRANCHISE`.

### Comment lancer les tests unitaires du validateur ?
```bash
PYTHONDONTWRITEBYTECODE=1 python3 test_validator.py -v
```

---

## 9. English Summary — Factur-X France 2027 Python Validator & GitHub Action

**`facturx-france-2027`** is a lightweight, **zero-dependency Python 3 CLI & library** (MIT License) plus a **reusable GitHub Action** designed to validate hybrid **Factur-X 1.0.07 PDF/A-3 invoices** (compatible with ZUGFeRD 2.2 / EN 16931 UN/CEFACT CII) and audit compliance with the **French 2026–2027 mandatory e-invoicing reform**:

- **Zero external dependencies**: uses Python's standard library only (`xml.etree.ElementTree`, `zlib`, `decimal`, `re`) — runs anywhere in `< 20 ms`.
- **Hybrid PDF/A-3 extractor**: extracts embedded `factur-x.xml` streams (`/EmbeddedFiles`, `/AF`, `/FlateDecode`, `/ObjStm`) and cross-checks XMP `fx:ConformanceLevel`.
- **Audits all 4 new French 2026–2027 mandatory invoice fields** (CGI art. 242 nonies A / Decree 2022-1299):
  1. Buyer 9-digit **SIREN** mathematical Luhn validation (`schemeID="0002"`), plus INSEE La Poste SIRET rule & French intra-EU VAT key calculation;
  2. Explicit **operation category** (*Prestation de services*, *Livraison de biens*, or *Opération mixte*);
  3. Distinct **delivery address** (`ShipToTradeParty`) and actual supply date;
  4. Explicit **VAT exigigibility / exemption** (`DueDateTypeCode` `5` debits / `72` cash basis, or `VATEX-FR-FRANCHISE` art. 293 B CGI).
- **Need an offline, subscription-free Factur-X generator?** Try our [free browser-based invoice auditor](https://yannabadie.github.io/facturkit-2027/audit-facture-gratuit.html) or explore **[FacturKit 2027 & Studio Factur-X Local 2027](https://yannabadie.github.io/facturkit-2027/)**.

---

## Licence

Distribué sous [Licence MIT](./LICENSE) — Copyright (c) 2026 **YGN — FacturKit** ([yannabadie.github.io/facturkit-2027](https://yannabadie.github.io/facturkit-2027/)).
