"""
SCRIPT_morphe_atom_multifile_metadata_update_step2
Script d’automatisation de la mise à jour des métadonnées descriptives dans
Morphé (AtoM – Access to Memory), correspondant à l’étape 2 du workflow :
complément des champs descriptifs des notices créées lors de l’étape 1
(téléversement initial et création des descriptions liées).

Date de création : 2026-04-06
Auteur : Barbara Galimberti (Archives de la construction moderne – EPFL)
Modèle utilisé : ChatGPT (GPT-5.3, avril 2026), utilisé comme
assistant pour la génération et l’optimisation du code

Contexte d’exécution :
- Application cible : AtoM 2.10.1 (build 197)
- Système : macOS Sequoia 15.4.1
- Langage : Python 3.x
- Dépendances Python :
    - pathlib
    - pandas
    - playwright
    - urllib.parse (standard library)

Fichiers source attendus :
- descriptions_update.csv   -> contient au minimum les colonnes :
    - record_url
    - referenceCode
    - extentAndMedium
    - scopeAndContent
    - locationOfCopies

Fichier de sortie :
- update_log.csv

Description :
Ce script automatise, via Playwright, l’étape 2 du traitement par lots dans
Morphé (AtoM) : la mise à jour des métadonnées descriptives des notices créées
à l’étape 1 (STEP1). En amont, le fichier `descriptions_update.csv` est préparé à
partir du fichier `created_descriptions_summary.csv` produit lors du script
précédent (SCRIPT_morphe_atom_multifile_upload_step1.py) : les colonnes `record_url` 
et `referenceCode` y sont reprises, puis complétées avec les champs descriptifs 
à renseigner (`extentAndMedium`, `scopeAndContent`, `locationOfCopies`).
Le script lit ce fichier, vérifie sa structure, normalise les URLs de notices,
puis ouvre directement les sections d’édition concernées au moyen d’URLs avec
ancre (`identity`, `content`, `allied`). Il met à jour uniquement les champs
renseignés dans le CSV, limite les modifications à la section ciblée et
déclenche une sauvegarde immédiate après chaque section traitée. Les champs
concernés sont `referenceCode`, `extentAndMedium`, `scopeAndContent` et
`locationOfCopies`. Chaque opération est journalisée dans `update_log.csv`,
avec distinction entre succès probable, sauvegarde à vérifier manuellement,
notice ignorée, timeout ou erreur. Un résumé quantifié est affiché en console
à la fin de l’exécution.

Extension / adaptation :
Ce script peut être étendu à d’autres champs descriptifs de Morphe. Pour ajouter
un nouveau champ à mettre à jour, il faut :
1. ajouter une nouvelle colonne dans `descriptions_update.csv`
2. ajouter cette colonne dans `CSV_COLUMNS`
3. identifier la section Morphe correspondante (`identity`, `content`,
   `allied`, etc.)
4. ajouter un appel à `fill_field_in_section(...)` dans la fonction de
   traitement de la section concernée
5. ajouter le nom du champ dans `updated_fields` afin d’assurer sa traçabilité
   dans `update_log.csv`

Remarque :
Le login à Morphé est effectué manuellement dans le navigateur avant le
lancement du traitement automatisé. Le champ Titre n’est pas modifié par ce
script.

Workflow (préparation des données) :
1. exécuter l’étape 1 (STEP1) de téléversement multiple dans Morphe (AtoM)
   via SCRIPT_morphe_atom_multifile_upload_step1.py
2. récupérer le fichier `created_descriptions_summary.csv` généré à l’issue de
   l’étape 1
3. construire `descriptions_update.csv` à partir de ce fichier :
   - reprendre les colonnes `record_url` et `referenceCode`
   - ajouter les colonnes :
     `extentAndMedium`, `scopeAndContent`, `locationOfCopies`
4. renseigner, pour chaque notice, les métadonnées descriptives à compléter
5. vérifier la présence et le nommage exact des colonnes attendues dans
   `descriptions_update.csv`

Workflow (script – étape 2 : mise à jour des métadonnées) :
1. vérifier la présence du fichier `descriptions_update.csv`
2. lire le CSV avec contrôle d’encodage et validation des colonnes obligatoires
3. lancer le navigateur automatisé et ouvrir Morphe
4. attendre le login manuel de l’utilisateur
5. parcourir les lignes du CSV
6. normaliser `record_url` et construire l’URL de base d’édition
7. ouvrir directement la section `identity` si `referenceCode` ou
   `extentAndMedium` sont renseignés
8. mettre à jour les champs « Identifiant » et/ou
   « Étendue matérielle et support »
9. sauvegarder la section `identity`
10. ouvrir directement la section `content` si `scopeAndContent` est renseigné
11. mettre à jour le champ « Portée et contenu »
12. sauvegarder la section `content`
13. ouvrir directement la section `allied` si `locationOfCopies` est renseigné
14. mettre à jour le champ
    « Existence et lieu de conservation des copies »
15. sauvegarder la section `allied`
16. vérifier souplement les indices de succès après chaque sauvegarde
17. enregistrer le résultat du traitement dans `update_log.csv`
18. afficher un résumé final de validation et d’exécution en console

# License: This script is distributed under the GNU General Public License
# v3. You may redistribute and/or modify it under the terms of the GNU GPL as
# published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.
"""

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ----------------------------------------------------------------------
# Définition des chemins de travail
# ----------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "descriptions_update.csv"
LOG_FILE = BASE_DIR / "update_log.csv"


# ----------------------------------------------------------------------
# Colonnes attendues dans le CSV
# ----------------------------------------------------------------------

CSV_COLUMNS = [
    "record_url",
    "referenceCode",
    "extentAndMedium",
    "scopeAndContent",
    "locationOfCopies",
]


# ----------------------------------------------------------------------
# Configuration des sections Morphe
# ----------------------------------------------------------------------

SECTION_HASHES = {
    "identity": "identity-collapse",
    "content": "content-collapse",
    "allied": "allied-collapse",
}

SECTION_CONTAINERS = {
    "identity": "#identity-collapse",
    "content": "#content-collapse",
    "allied": "#allied-collapse",
}


# ----------------------------------------------------------------------
# Fonctions utilitaires
# ----------------------------------------------------------------------

def normalize_text(value) -> str:
    """
    Convertit une valeur en texte propre.
    """
    if value is None:
        return ""
    return str(value).strip()


def append_log(row_dict):
    """
    Ajoute une ligne au fichier update_log.csv.
    """
    df_new = pd.DataFrame([row_dict])
    if LOG_FILE.exists():
        df_old = pd.read_csv(LOG_FILE, dtype=str).fillna("")
        df_new = pd.concat([df_old, df_new], ignore_index=True)
    df_new.to_csv(LOG_FILE, index=False, encoding="utf-8")


def read_input_csv(csv_file: Path) -> pd.DataFrame:
    """
    Lit le CSV avec l’encodage attendu et vérifie les colonnes.
    """
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV introuvable : {csv_file}")

    encodings = ["utf-8-sig", "utf-8", "latin1"]
    last_error = None

    for encoding in encodings:
        try:
            df = pd.read_csv(csv_file, dtype=str, sep=",", encoding=encoding).fillna("")
            df.columns = [str(c).strip() for c in df.columns]

            missing_columns = set(CSV_COLUMNS) - set(df.columns)
            if missing_columns:
                raise ValueError(
                    f"Colonnes manquantes : {missing_columns}. "
                    f"Colonnes détectées : {list(df.columns)}"
                )

            print(f"[INFO] CSV lu avec encoding={encoding!r} et sep=','")
            print(f"[INFO] Colonnes détectées : {list(df.columns)}")
            return df

        except Exception as e:
            last_error = e

    raise ValueError(f"Impossible de lire correctement descriptions_update.csv : {last_error}")


def normalize_record_url(record_url: str) -> str:
    """
    Normalise record_url en supprimant :
    - un éventuel /edit final
    - une éventuelle ancre
    - une éventuelle query string
    - les slashs finaux inutiles
    """
    raw = normalize_text(record_url)
    if not raw:
        return ""

    parts = urlsplit(raw)
    path = parts.path.rstrip("/")

    if path.endswith("/edit"):
        path = path[:-5].rstrip("/")

    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def build_edit_base_url(record_url: str) -> str:
    """
    Construit l’URL de base de la page d’édition.
    """
    base_record_url = normalize_record_url(record_url)
    if not base_record_url:
        return ""
    return base_record_url.rstrip("/") + "/edit"


def build_section_url(record_url: str, section_key: str) -> str:
    """
    Construit l’URL directe d’une section d’édition.
    """
    return f"{build_edit_base_url(record_url)}#{SECTION_HASHES[section_key]}"


def open_section(page, record_url: str, section_key: str) -> str:
    """
    Ouvre directement une section via son URL avec ancre.
    """
    section_url = build_section_url(record_url, section_key)
    page.goto(section_url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1000)

    save_candidates = [
        'button:has-text("Sauvegarder")',
        'input[type="submit"][value="Sauvegarder"]',
    ]

    for sel in save_candidates:
        try:
            page.locator(sel).first.wait_for(timeout=4000)
            return section_url
        except Exception:
            pass

    raise RuntimeError(
        f"Section '{section_key}' non ouverte correctement. URL tentée : {section_url}"
    )


def get_section_root(page, section_key: str):
    """
    Retourne le conteneur principal d’une section.
    """
    return page.locator(SECTION_CONTAINERS[section_key]).first


def clear_fill_and_blur(locator, value: str, page):
    """
    Vide un champ, insère une nouvelle valeur puis déclenche un blur.
    """
    locator.click(timeout=3000)
    locator.fill("")
    locator.fill(value)
    locator.press("Tab")
    page.wait_for_timeout(350)


def read_locator_value(locator) -> str:
    """
    Lit la valeur actuelle d’un champ.
    """
    try:
        return locator.input_value().strip()
    except Exception:
        try:
            return locator.evaluate(
                "(el) => (el.value !== undefined && el.value !== null) ? String(el.value).trim() : ''"
            )
        except Exception:
            return ""


def fill_locator_and_verify(page, loc, value: str, field_name: str, errors: list):
    """
    Remplit un locator et vérifie que la valeur a bien été enregistrée.
    """
    try:
        loc.wait_for(timeout=4000)

        if not loc.is_visible():
            return False

        clear_fill_and_blur(loc, value, page)
        current_value = read_locator_value(loc)

        if current_value == value.strip():
            return True

        try:
            loc.click(timeout=3000)
            page.keyboard.press("Meta+A")
            page.keyboard.type(value, delay=20)
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)
            current_value = read_locator_value(loc)

            if current_value == value.strip():
                return True
        except Exception as inner_e:
            errors.append(f"{field_name} fallback clavier : {inner_e}")

        errors.append(
            f"{field_name} trouvé mais valeur non confirmée "
            f"(attendu='{value.strip()}', obtenu='{current_value}')"
        )
        return False

    except Exception as e:
        errors.append(str(e))
        return False


def fill_field_in_section(page, section_key: str, label_text: str, value: str):
    """
    Remplit un champ uniquement à l’intérieur d’une section précise.
    """
    if not value:
        return

    root = get_section_root(page, section_key)
    errors = []

    candidates = [
        root.get_by_label(label_text, exact=True).first,
        root.get_by_label(label_text, exact=False).first,
        root.locator(
            f'xpath=.//label[contains(normalize-space(.), "{label_text}")]/following::input[1]'
        ).first,
        root.locator(
            f'xpath=.//label[contains(normalize-space(.), "{label_text}")]/following::textarea[1]'
        ).first,
    ]

    for candidate in candidates:
        if fill_locator_and_verify(page, candidate, value, label_text, errors):
            return

    raise RuntimeError(
        f"Champ introuvable ou non mis à jour pour le libellé '{label_text}' "
        f"dans la section '{section_key}'. Détails : {errors}"
    )


def click_save(page):
    """
    Clique sur le bouton Sauvegarder.
    """
    save_selectors = [
        'button:has-text("Sauvegarder")',
        'input[type="submit"][value="Sauvegarder"]',
    ]

    last_error = None

    for sel in save_selectors:
        try:
            btn = page.locator(sel).first
            btn.wait_for(timeout=5000)
            btn.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(
        f"Bouton Sauvegarder introuvable ou non cliquable : {last_error}"
    )


def verify_save_result(page) -> bool:
    """
    Vérifie souplement si l’enregistrement semble réussi.
    """
    possible_success = [
        "text=Succès",
        "text=Modifications enregistrées",
        "text=Notice mise à jour",
        'button:has-text("Modifier")',
        'a:has-text("Modifier")',
        'button:has-text("Sauvegarder")',
    ]

    for sel in possible_success:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            pass

    return False


def save_current_section(page, section_name_for_log: str):
    """
    Sauvegarde la section courante et retourne un statut pour le log.
    """
    click_save(page)
    success = verify_save_result(page)

    if success:
        print(f"[SAVE OK] {section_name_for_log}")
        return "ok", f"section {section_name_for_log} sauvegardée"

    print(f"[SAVE CHECK] {section_name_for_log}")
    return "check", f"section {section_name_for_log} sauvegardée à vérifier"


# ----------------------------------------------------------------------
# Traitement par section
# ----------------------------------------------------------------------

def process_identity_section(page, record_url: str, reference_code: str, extent_and_medium: str):
    """
    Traite la section identity.
    """
    updated = []

    if not (reference_code or extent_and_medium):
        return updated, []

    open_section(page, record_url, "identity")

    if reference_code:
        fill_field_in_section(page, "identity", "Identifiant", reference_code)
        updated.append("referenceCode")

    if extent_and_medium:
        fill_field_in_section(
            page,
            "identity",
            "Étendue matérielle et support",
            extent_and_medium
        )
        updated.append("extentAndMedium")

    save_status, save_message = save_current_section(page, "identity")
    return updated, [(save_status, save_message)]


def process_content_section(page, record_url: str, scope_and_content: str):
    """
    Traite la section content.
    """
    updated = []

    if not scope_and_content:
        return updated, []

    open_section(page, record_url, "content")
    fill_field_in_section(page, "content", "Portée et contenu", scope_and_content)
    updated.append("scopeAndContent")

    save_status, save_message = save_current_section(page, "content")
    return updated, [(save_status, save_message)]


def process_allied_section(page, record_url: str, location_of_copies: str):
    """
    Traite la section allied.
    """
    updated = []

    if not location_of_copies:
        return updated, []

    open_section(page, record_url, "allied")
    fill_field_in_section(
        page,
        "allied",
        "Existence et lieu de conservation des copies",
        location_of_copies
    )
    updated.append("locationOfCopies")

    save_status, save_message = save_current_section(page, "allied")
    return updated, [(save_status, save_message)]


# ----------------------------------------------------------------------
# Fonction principale
# ----------------------------------------------------------------------

def main():
    """
    Fonction principale du script.
    """
    df = read_input_csv(CSV_FILE)

    total_rows = len(df)
    ok_count = 0
    check_count = 0
    skipped_count = 0
    timeout_count = 0
    error_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://morphe.epfl.ch", wait_until="networkidle")
        print("Veuillez effectuer le login manuellement dans Morphe.")
        input("Quand le login est terminé, appuyez sur ENTRÉE ici... ")

        for _, row in df.iterrows():
            record_url = normalize_text(row["record_url"])
            reference_code = normalize_text(row["referenceCode"])
            extent_and_medium = normalize_text(row["extentAndMedium"])
            scope_and_content = normalize_text(row["scopeAndContent"])
            location_of_copies = normalize_text(row["locationOfCopies"])

            if not record_url:
                skipped_count += 1
                append_log({
                    "record_url": "",
                    "referenceCode": reference_code,
                    "edit_url": "",
                    "status": "skipped_missing_record_url",
                    "message": "record_url manquant",
                    "updated_fields": "",
                    "save_steps": ""
                })
                print(f"[SKIP] record_url manquant pour {reference_code}")
                continue

            try:
                clean_record_url = normalize_record_url(record_url)
                edit_base_url = build_edit_base_url(record_url)

                print(f"[START] {reference_code or '(sans referenceCode)'}")
                print(f"[DEBUG] record_url original : {record_url}")
                print(f"[DEBUG] record_url nettoyé : {clean_record_url}")
                print(f"[DEBUG] edit_base_url      : {edit_base_url}")

                updated_fields = []
                save_steps = []

                identity_updated, identity_save_steps = process_identity_section(
                    page,
                    record_url,
                    reference_code,
                    extent_and_medium
                )
                updated_fields.extend(identity_updated)
                save_steps.extend(identity_save_steps)

                content_updated, content_save_steps = process_content_section(
                    page,
                    record_url,
                    scope_and_content
                )
                updated_fields.extend(content_updated)
                save_steps.extend(content_save_steps)

                allied_updated, allied_save_steps = process_allied_section(
                    page,
                    record_url,
                    location_of_copies
                )
                updated_fields.extend(allied_updated)
                save_steps.extend(allied_save_steps)

                if not updated_fields:
                    skipped_count += 1
                    append_log({
                        "record_url": clean_record_url,
                        "referenceCode": reference_code,
                        "edit_url": edit_base_url,
                        "status": "skipped_no_fields_to_update",
                        "message": "aucun champ renseigné à mettre à jour",
                        "updated_fields": "",
                        "save_steps": ""
                    })
                    print(f"[SKIP] Aucun champ à mettre à jour pour {reference_code}")
                    continue

                statuses = [x[0] for x in save_steps]
                messages = [x[1] for x in save_steps]

                if all(s == "ok" for s in statuses):
                    final_status = "ok"
                    ok_count += 1
                    print(f"[OK] {reference_code}")
                else:
                    final_status = "saved_check_manually"
                    check_count += 1
                    print(f"[CHECK] {reference_code}")

                append_log({
                    "record_url": clean_record_url,
                    "referenceCode": reference_code,
                    "edit_url": edit_base_url,
                    "status": final_status,
                    "message": " | ".join(messages),
                    "updated_fields": ",".join(updated_fields),
                    "save_steps": " | ".join([f"{s}:{m}" for s, m in save_steps])
                })

            except PlaywrightTimeoutError:
                timeout_count += 1
                append_log({
                    "record_url": normalize_record_url(record_url),
                    "referenceCode": reference_code,
                    "edit_url": build_edit_base_url(record_url),
                    "status": "timeout",
                    "message": "timeout pendant la mise à jour",
                    "updated_fields": "",
                    "save_steps": ""
                })
                print(f"[TIMEOUT] {reference_code}")

            except Exception as e:
                error_count += 1
                append_log({
                    "record_url": normalize_record_url(record_url),
                    "referenceCode": reference_code,
                    "edit_url": build_edit_base_url(record_url),
                    "status": "error",
                    "message": str(e),
                    "updated_fields": "",
                    "save_steps": ""
                })
                print(f"[ERROR] {reference_code}: {e}")

        browser.close()

    print("\n" + "=" * 70)
    print("RÉSUMÉ D’EXÉCUTION")
    print("=" * 70)
    print(f"Nombre total de lignes                      : {total_rows}")
    print(f"Mises à jour réussies / probables          : {ok_count}")
    print(f"Sauvegardes à vérifier                     : {check_count}")
    print(f"Notices ignorées                           : {skipped_count}")
    print(f"Timeouts                                   : {timeout_count}")
    print(f"Erreurs                                    : {error_count}")
    print(f"Journal généré                             : {LOG_FILE}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
