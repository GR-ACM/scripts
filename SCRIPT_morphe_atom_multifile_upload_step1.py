"""
SCRIPT_morphe_atom_multifile_upload_step1
Script d’automatisation de l’import par lots de documents numérisés dans
Morphé (AtoM – Access to Memory), correspondant à l’étape 1 du workflow :
téléversement initial (« Importer des documents numériques ») et création 
des descriptions liées. L’étape 2, traitée par un script distinct, consiste 
à compléter les métadonnées des descriptions créées.

Date de création : 2026-04-06
Auteur : Barbara Galimberti (Archives de la construction moderne – EPFL)
Modèle utilisé : ChatGPT (GPT-5.3, avril 2026), utilisé comme assistant pour
la génération et l’optimisation du code

Contexte d’exécution :
- Application cible : AtoM 2.10.1 (build 197)
- Système : macOS Sequoia 15.4.1
- Langage : Python 3.x
- Dépendances Python :
    - pathlib
    - pandas
    - playwright
    - urllib.parse (standard library)
    - datetime (standard library)
    - time (standard library)

Fichiers source attendus :
- records.csv   -> contient au minimum les colonnes :
    - record_url
    - referenceCode
- dossier images/
    -> contient les fichiers à téléverser, par exemple :
       0143.04.0044_01_small.jpg
       0143.04.0044_02_small.jpg

Fichiers de sortie :
- upload_log_multi.csv
- created_descriptions_summary.csv
- dossier screenshots/
    -> créé uniquement si des captures d’erreur sont produites

Description :
Ce script automatise, via Playwright, l’étape 1 du traitement par lots de
documents numérisés dans Morphé (AtoM) (« Plus » > « Importer des documents 
numériques »): le téléversement initial des fichiers et la création des descriptions 
associées. En amont, les notices à enrichir sont sélectionnées dans Morphé, 
ajoutées au presse-papiers, puis exportées en CSV. Ce fichier sert de base de 
préparation : la colonne `referenceCode` est conservée et la colonne `slug` est 
transformée en URL absolue (`record_url`) par ajout de la racine de l’application 
(`https://morphe.epfl.ch/`).
Le script valide les entrées, recherche dans `images/` les fichiers dont le nom
commence par le `referenceCode`, ouvre pour chaque notice la page
`multiFileUpload`, renseigne le titre, définit le niveau de description à
« Pièce », injecte les fichiers via le file chooser natif, puis déclenche le
téléversement. Il attend ensuite la page `multiFileUpdate`, extrait les
descriptions créées (titres, slugs, URLs et `referenceCode` dérivés des noms de
fichiers source), enregistre ces informations dans un CSV de synthèse, puis
sauvegarde les modifications. Le script intègre un mécanisme de reprise,
journalise les traitements, évite les retraitements déjà validés et produit, en
cas d’erreur, des captures d’écran pour vérification.

Remarque :
Le login à Morphe est effectué manuellement dans le navigateur avant le
lancement du traitement automatisé.

Workflow (préparation des données) :
1. sélectionner les notices cibles dans Morphe (AtoM)
2. ajouter les notices au presse-papiers
3. exporter le presse-papiers au format CSV
4. préparer `records.csv` :
   - conserver la colonne `referenceCode`
   - construire `record_url` à partir du `slug` en ajoutant la racine
     `https://morphe.epfl.ch/`
   - ex. `slug` : `maison-dubois`
     -> `record_url` : `https://morphe.epfl.ch/maison-dubois`
5. préparer les fichiers à téléverser dans le dossier `images/`
6. vérifier que le préfixe du nom de fichier corresponde à la cote de la
   description (`referenceCode`)
   - ex. `referenceCode` : `0143.04.0044`
     -> noms de fichiers possibles :
        `0143.04.0044_01_small.jpg`
        `0143.04.0044_02_small.jpg`

Workflow (script – étape 1 : upload) :
1. vérifier la présence des fichiers et dossiers nécessaires (`records.csv`,
   `images/`)
2. charger le fichier `records.csv`
3. contrôler la présence des colonnes obligatoires (`record_url`,
   `referenceCode`)
4. charger le log existant pour identifier les notices déjà traitées avec
   succès
5. lancer le navigateur automatisé et ouvrir Morphé
6. attendre le login manuel de l’utilisateur
7. parcourir les lignes du CSV
8. rechercher, pour chaque `referenceCode`, les fichiers locaux correspondants
   dans `images/`
9. construire l’URL `multiFileUpload` à partir de `record_url`
10. ouvrir la page d’import multiple
11. renseigner le champ "Titre"
12. définir le niveau de description à "Pièce"
13. injecter les fichiers via le file chooser natif
14. vérifier la présence des noms de fichiers dans l’interface
15. déclencher le téléversement ("Téléverser")
16. attendre la redirection vers `multiFileUpdate`
17. extraire les titres, slugs, URLs et `referenceCode` des descriptions créées
18. enregistrer les lignes de synthèse dans
    `created_descriptions_summary.csv`
19. sauvegarder les modifications ("Sauvegarder")
20. enregistrer le résultat du traitement dans `upload_log_multi.csv`
21. gérer les erreurs et timeouts avec reprise et capture d’écran si nécessaire
22. afficher un résumé final de validation et d’exécution en console

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
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime
import time
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------

# Répertoire du script
BASE_DIR = Path(__file__).resolve().parent

# Fichiers
CSV_FILE = BASE_DIR / "records.csv"
IMAGES_DIR = BASE_DIR / "images"
LOG_FILE = BASE_DIR / "upload_log_multi.csv"
SUMMARY_FILE = BASE_DIR / "created_descriptions_summary.csv"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

# Extensions autorisées
EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}

# Réglages d'exécution
HEADLESS = False                  # True = navigateur invisible ; False = visible
SLOW_MO_MS = 300                 # ralentit légèrement les actions pour plus de stabilité
RETRY_COUNT = 2                  # nombre total de tentatives par notice
SKIP_ALREADY_LOGGED_OK = True    # si True, saute les notices déjà traitées avec succès dans le log
TAKE_SCREENSHOT_ON_FAILURE = True
STABILITY_WAIT_MS = 1500         # petite pause entre deux notices
MAX_RECORDS = None               # mettre un entier pour limiter le nombre de notices en test


# ----------------------------------------------------------------------
# FONCTIONS UTILITAIRES
# ----------------------------------------------------------------------

def now_iso() -> str:
    """Retourne un horodatage ISO pour les logs."""
    return datetime.now().isoformat(timespec="seconds")


def build_multi_upload_url(record_url: str) -> str:
    """Construit l'URL de la page d'import multiple."""
    return record_url.rstrip("/") + "/informationobject/multiFileUpload"


def find_local_files(reference_code: str):
    """
    Trouve tous les fichiers du dossier images/ commençant par
    <referenceCode>_
    """
    reference_code = str(reference_code).strip()

    matches = []
    for f in IMAGES_DIR.glob(f"{reference_code}_*"):
        if f.is_file() and f.suffix.lower() in EXTENSIONS:
            matches.append(f)

    matches = sorted(matches, key=lambda x: x.name.lower())
    print(f"[DEBUG] fichiers trouvés : {[f.name for f in matches]}")
    return matches


def source_filename_to_referencecode(file_path: Path) -> str:
    """
    Transforme un nom de fichier source en referenceCode de résumé.

    Exemples :
    - 0143.04.0050_01_small.jpg         -> 0143.04.0050_01
    - 0143.04.0050_5_175-104C_small.jpg -> 0143.04.0050_5_175-104C
    - 0143.04.0050_01.jpg               -> 0143.04.0050_01
    """
    stem = file_path.stem
    if stem.lower().endswith("_small"):
        stem = stem[:-6]
    return stem


def append_csv_row(file_path: Path, data: dict):
    """
    Ajoute une ligne à un CSV. Si le fichier existe déjà, on concatène.
    """
    df_new = pd.DataFrame([data])

    if file_path.exists():
        df_old = pd.read_csv(file_path, dtype=str).fillna("")
        df_new = pd.concat([df_old, df_new], ignore_index=True)

    df_new.to_csv(file_path, index=False, encoding="utf-8")


def append_log(data: dict):
    """Ajoute une ligne au log principal."""
    append_csv_row(LOG_FILE, data)


def append_summary_rows(rows: list[dict]):
    """
    Ajoute plusieurs lignes au CSV de résumé des descriptions créées.

    Colonnes attendues :
    - title
    - record_url
    - referenceCode
    """
    if not rows:
        return

    df_new = pd.DataFrame(rows, columns=["title", "record_url", "referenceCode"])

    if SUMMARY_FILE.exists():
        df_old = pd.read_csv(SUMMARY_FILE, dtype=str).fillna("")
        for col in ["title", "record_url", "referenceCode"]:
            if col not in df_old.columns:
                df_old[col] = ""
        df_old = df_old[["title", "record_url", "referenceCode"]]
        df_new = pd.concat([df_old, df_new], ignore_index=True)

    df_new.to_csv(SUMMARY_FILE, index=False, encoding="utf-8")


def load_already_processed_codes():
    """
    Lit le log existant et retourne l'ensemble des referenceCode déjà
    traités avec succès.
    """
    if not LOG_FILE.exists():
        return set()

    try:
        df_log = pd.read_csv(LOG_FILE, dtype=str).fillna("")
        ok_codes = set(
            df_log.loc[df_log["status"] == "ok", "referenceCode"]
            .astype(str)
            .str.strip()
            .tolist()
        )
        return ok_codes
    except Exception:
        return set()


def ensure_screenshots_dir():
    """Crée le dossier screenshots si nécessaire."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def take_failure_screenshot(page, code: str, suffix: str):
    """
    Enregistre une capture d'écran en cas d'erreur ou timeout.
    """
    if not TAKE_SCREENSHOT_ON_FAILURE:
        return ""

    ensure_screenshots_dir()
    filename = f"{code}_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    screenshot_path = SCREENSHOTS_DIR / filename

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"[DEBUG] capture enregistrée : {screenshot_path}")
        return str(screenshot_path)
    except Exception:
        return ""


def get_title_input(page):
    """
    Cible l'input associé au label visible 'Titre',
    sans toucher à la barre de recherche du header.
    """
    candidates = [
        "xpath=//label[normalize-space()='Titre']/following::input[1]",
        "xpath=//*[normalize-space()='Titre']/following::input[1]",
    ]

    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first

    raise RuntimeError("Champ 'Titre' introuvable.")


def get_level_select(page):
    """
    Cible le select associé au label visible 'Niveau de description'.
    """
    candidates = [
        "xpath=//label[contains(normalize-space(),'Niveau de description')]/following::select[1]",
        "xpath=//*[contains(normalize-space(),'Niveau de description')]/following::select[1]",
    ]

    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first

    raise RuntimeError("Champ 'Niveau de description' introuvable.")


def get_browse_files_link(page):
    """
    Cible le lien visible 'browse files' dans la zone 'Documents numériques'.
    """
    candidates = [
        "text=browse files",
        "text=Browse files",
        "xpath=//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'browse files')]",
    ]

    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first

    raise RuntimeError("Lien 'browse files' introuvable dans la zone d'upload.")


def upload_files_via_browse_files(page, files):
    """
    Clique sur 'browse files' et injecte les fichiers via le file chooser natif.
    """
    if not files:
        raise ValueError("Aucun fichier à téléverser.")

    browse_link = get_browse_files_link(page)
    browse_link.wait_for(timeout=15000)

    print("[DEBUG] clic sur 'browse files'")

    with page.expect_file_chooser(timeout=15000) as fc_info:
        browse_link.click()

    file_chooser = fc_info.value
    file_chooser.set_files([str(f) for f in files])

    print("[DEBUG] fichiers envoyés via file chooser")

    # On laisse le composant JS générer les aperçus
    page.wait_for_timeout(6000)


def wait_for_uploaded_file_names(page, files, timeout_ms=20000):
    """
    Attend que les noms des fichiers apparaissent dans l'interface.
    """
    names = [f.name for f in files]
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        found = 0
        for name in names:
            try:
                if page.locator(f"text={name}").count() > 0:
                    found += 1
            except Exception:
                pass

        if found > 0:
            print(f"[DEBUG] fichiers visibles dans l'UI : {found}/{len(names)}")
            return True

        page.wait_for_timeout(500)

    return False


def get_upload_button(page):
    """Récupère le bouton 'Téléverser'."""
    candidates = [
        "button:has-text('Téléverser')",
        "input[type='submit'][value='Téléverser']",
        "button:has-text('Upload')",
    ]

    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first

    raise RuntimeError("Bouton 'Téléverser' introuvable.")


def get_save_button(page):
    """Récupère le bouton 'Sauvegarder'."""
    candidates = [
        "button:has-text('Sauvegarder')",
        "input[type='submit'][value='Sauvegarder']",
        "button:has-text('Save')",
    ]

    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first

    raise RuntimeError("Bouton 'Sauvegarder' introuvable.")


def extract_created_descriptions_from_multifileupdate(page, reference_code: str, source_files: list[Path]):
    """
    Extrait la liste des nouvelles descriptions créées à partir de :
    - l'URL multiFileUpdate?items=...
    - les titres visibles dans la page, si possible
    - les fichiers source, pour produire une colonne referenceCode

    Retourne une liste de dictionnaires :
    [
        {
            "title": "0143.04.0050 : Reproduction numérique 04",
            "record_url": "https://morphe.epfl.ch/index.php/0143-04-0050-reproduction-numerique-04",
            "referenceCode": "0143.04.0050_04"
        },
        ...
    ]
    """
    current_url = page.url
    parsed = urlparse(current_url)
    query = parse_qs(parsed.query)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    item_values = query.get("items", [])
    if not item_values:
        return []

    # Les slugs sont séparés par des virgules dans le paramètre items
    slug_string = unquote(item_values[0])
    slugs = [slug.strip() for slug in slug_string.split(",") if slug.strip()]

    # On essaie d'abord de lire les titres dans les inputs de la page update
    titles = []
    try:
        text_inputs = page.locator("input[type='text']")
        count = text_inputs.count()

        for i in range(count):
            value = text_inputs.nth(i).input_value().strip()
            if value and "reproduction numérique" in value.lower():
                titles.append(value)
    except Exception:
        pass

    # Si on n'a pas trouvé autant de titres que de slugs, on reconstruit
    if len(titles) != len(slugs):
        titles = [
            f"{reference_code} : Reproduction numérique {i:02d}"
            for i in range(1, len(slugs) + 1)
        ]

    # On dérive les referenceCode à partir des fichiers source
    source_referencecodes = [source_filename_to_referencecode(f) for f in source_files]

    # Si jamais il y a un écart, on complète avec des valeurs vides
    max_len = max(len(slugs), len(titles), len(source_referencecodes))

    while len(slugs) < max_len:
        slugs.append("")
    while len(titles) < max_len:
        titles.append("")
    while len(source_referencecodes) < max_len:
        source_referencecodes.append("")

    rows = []
    for slug, title, source_ref in zip(slugs, titles, source_referencecodes):
        rows.append({
            "title": title,
            "record_url": f"{origin}/index.php/{slug}" if slug else "",
            "referenceCode": source_ref
        })

    return rows


# ----------------------------------------------------------------------
# FONCTION PRINCIPALE
# ----------------------------------------------------------------------

def main():
    # ------------------------------------------------------------------
    # VALIDATION DES FICHIERS D'ENTRÉE
    # ------------------------------------------------------------------
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"CSV introuvable : {CSV_FILE}")

    if not IMAGES_DIR.exists():
        raise FileNotFoundError(f"Dossier images introuvable : {IMAGES_DIR}")

    df = pd.read_csv(CSV_FILE, dtype=str).fillna("")

    required_columns = {"record_url", "referenceCode"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans records.csv : {missing}")

    # Si demandé, on saute les notices déjà traitées avec succès
    already_ok_codes = load_already_processed_codes() if SKIP_ALREADY_LOGGED_OK else set()

    # Limite facultative pour les tests
    if MAX_RECORDS is not None:
        df = df.head(MAX_RECORDS)

    # ------------------------------------------------------------------
    # COMPTEURS POUR LE RÉSUMÉ FINAL
    # ------------------------------------------------------------------
    total_rows = len(df)
    valid_rows = 0
    invalid_rows = 0
    skipped_already_done = 0
    missing_files = 0
    ok_count = 0
    timeout_count = 0
    error_count = 0
    retry_count_total = 0
    created_descriptions_total = 0

    # ------------------------------------------------------------------
    # BLOC DE VALIDATION CONSOLE
    # ------------------------------------------------------------------
    print("\n" + "=" * 76)
    print("VALIDATION DES DONNÉES D'ENTRÉE")
    print("=" * 76)
    print(f"CSV source                          : {CSV_FILE}")
    print(f"Dossier images                      : {IMAGES_DIR}")
    print(f"Log existant                        : {LOG_FILE if LOG_FILE.exists() else 'aucun'}")
    print(f"Résumé descriptions créées          : {SUMMARY_FILE}")
    print(f"Nombre total de lignes à traiter    : {total_rows}")
    print(f"Colonnes détectées                  : {list(df.columns)}")
    print(f"Mode headless                       : {HEADLESS}")
    print(f"Retry par notice                    : {RETRY_COUNT}")
    print(f"Skip déjà traités (log)             : {SKIP_ALREADY_LOGGED_OK}")
    print(f"Prise de capture sur erreur         : {TAKE_SCREENSHOT_ON_FAILURE}")
    print("=" * 76 + "\n")

    # ------------------------------------------------------------------
    # LANCEMENT DU NAVIGATEUR
    # ------------------------------------------------------------------
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO_MS)
        page = browser.new_page()

        page.goto("https://morphe.epfl.ch")

        print("👉 Login manuel requis dans le navigateur.")
        input("Appuie sur ENTER après le login... ")

        # ------------------------------------------------------------------
        # BOUCLE PRINCIPALE
        # ------------------------------------------------------------------
        for _, row in df.iterrows():
            record_url = str(row["record_url"]).strip()
            code = str(row["referenceCode"]).strip()

            print(f"[DEBUG] referenceCode = {code!r}")
            print(f"[DEBUG] record_url    = {record_url!r}")

            if not record_url or not code:
                invalid_rows += 1
                append_log({
                    "timestamp": now_iso(),
                    "record_url": record_url,
                    "referenceCode": code,
                    "status": "invalid_input",
                    "message": "record_url ou referenceCode vide"
                })
                continue

            # reprise intelligente basée sur le log
            if SKIP_ALREADY_LOGGED_OK and code in already_ok_codes:
                skipped_already_done += 1
                print(f"[SKIP] déjà traité avec succès selon le log : {code}")
                continue

            valid_rows += 1

            files = find_local_files(code)

            if not files:
                print(f"[SKIP] aucun fichier pour {code}")
                missing_files += 1
                append_log({
                    "timestamp": now_iso(),
                    "record_url": record_url,
                    "referenceCode": code,
                    "status": "missing_files",
                    "message": "aucun fichier local trouvé"
                })
                continue

            print(f"[START] {code} ({len(files)} fichiers)")

            # Retry automatique
            success_for_this_record = False
            created_rows_for_record = []

            for attempt in range(1, RETRY_COUNT + 1):
                if attempt > 1:
                    retry_count_total += 1
                    print(f"[RETRY] tentative {attempt}/{RETRY_COUNT} pour {code}")

                try:
                    # ------------------------------------------------------
                    # 1. OUVRIR LA PAGE MULTI UPLOAD
                    # ------------------------------------------------------
                    upload_url = build_multi_upload_url(record_url)
                    print(f"[DEBUG] ouverture : {upload_url}")

                    page.goto(upload_url, timeout=60000)
                    page.wait_for_timeout(4000)

                    # ------------------------------------------------------
                    # 2. REMPLIR LE CHAMP TITRE
                    # ------------------------------------------------------
                    title_value = f"{code} : Reproduction numérique %dd%"
                    title_input = get_title_input(page)
                    title_input.wait_for(timeout=15000)
                    title_input.fill(title_value)
                    print(f"[DEBUG] champ 'Titre' rempli avec : {title_value}")

                    # ------------------------------------------------------
                    # 3. SÉLECTIONNER LE NIVEAU DE DESCRIPTION
                    # ------------------------------------------------------
                    level_select = get_level_select(page)
                    level_select.wait_for(timeout=15000)

                    try:
                        level_select.select_option(label="Pièce")
                        print("[DEBUG] niveau 'Pièce' sélectionné par label")
                    except Exception:
                        options = level_select.locator("option")
                        found_piece = False
                        for i in range(options.count()):
                            option = options.nth(i)
                            txt = (option.text_content() or "").strip()
                            val = option.get_attribute("value") or ""
                            if "pièce" in txt.lower():
                                level_select.select_option(value=val)
                                print(f"[DEBUG] niveau sélectionné via fallback : {txt}")
                                found_piece = True
                                break

                        if not found_piece:
                            raise RuntimeError("Impossible de sélectionner 'Pièce'.")

                    # ------------------------------------------------------
                    # 4. UPLOAD VIA 'browse files'
                    # ------------------------------------------------------
                    upload_files_via_browse_files(page, files)

                    # ------------------------------------------------------
                    # 5. VÉRIFIER QUE LES FICHIERS APPARAISSENT
                    # ------------------------------------------------------
                    files_visible = wait_for_uploaded_file_names(page, files, timeout_ms=20000)
                    if not files_visible:
                        raise RuntimeError(
                            "Les fichiers n'apparaissent pas dans la zone 'Documents numériques' "
                            "après le file chooser."
                        )

                    # ------------------------------------------------------
                    # 6. CLIQUER SUR TÉLÉVERSER
                    # ------------------------------------------------------
                    upload_button = get_upload_button(page)
                    upload_button.wait_for(timeout=15000)
                    print("[DEBUG] clic sur 'Téléverser'")
                    upload_button.click()

                    # ------------------------------------------------------
                    # 7. ATTENDRE LA PAGE multiFileUpdate
                    # ------------------------------------------------------
                    page.wait_for_url("**/informationobject/multiFileUpdate**", timeout=120000)
                    print(f"[DEBUG] page multiFileUpdate atteinte : {page.url}")

                    # ------------------------------------------------------
                    # 8. EXTRAIRE LES NOUVELLES DESCRIPTIONS CRÉÉES
                    # ------------------------------------------------------
                    created_rows_for_record = extract_created_descriptions_from_multifileupdate(page, code, files)
                    created_descriptions_total += len(created_rows_for_record)
                    append_summary_rows(created_rows_for_record)
                    print(f"[DEBUG] descriptions créées détectées : {len(created_rows_for_record)}")

                    # ------------------------------------------------------
                    # 9. CLIQUER SUR SAUVEGARDER
                    # ------------------------------------------------------
                    save_button = get_save_button(page)
                    save_button.wait_for(timeout=20000)

                    print("[DEBUG] clic sur 'Sauvegarder'")
                    save_button.click()

                    # ------------------------------------------------------
                    # 10. ATTENDRE LE RETOUR HORS multiFileUpdate
                    # ------------------------------------------------------
                    page.wait_for_function(
                        "() => !window.location.href.includes('multiFileUpdate')",
                        timeout=120000
                    )

                    print(f"[OK] {code}")
                    ok_count += 1
                    success_for_this_record = True

                    append_log({
                        "timestamp": now_iso(),
                        "record_url": record_url,
                        "referenceCode": code,
                        "files": " | ".join([f.name for f in files]),
                        "created_descriptions_count": len(created_rows_for_record),
                        "status": "ok",
                        "message": f"{len(files)} fichier(s) téléversé(s)"
                    })

                    page.wait_for_timeout(STABILITY_WAIT_MS)
                    break

                except PlaywrightTimeoutError:
                    print(f"[TIMEOUT] {code} (tentative {attempt}/{RETRY_COUNT})")

                    screenshot_path = take_failure_screenshot(page, code, f"timeout_attempt{attempt}")

                    if attempt == RETRY_COUNT:
                        timeout_count += 1
                        append_log({
                            "timestamp": now_iso(),
                            "record_url": record_url,
                            "referenceCode": code,
                            "files": " | ".join([f.name for f in files]),
                            "status": "timeout",
                            "message": "timeout pendant le workflow web",
                            "screenshot": screenshot_path
                        })

                except Exception as e:
                    print(f"[ERROR] {code} (tentative {attempt}/{RETRY_COUNT}) : {e}")

                    screenshot_path = take_failure_screenshot(page, code, f"error_attempt{attempt}")

                    if attempt == RETRY_COUNT:
                        error_count += 1
                        append_log({
                            "timestamp": now_iso(),
                            "record_url": record_url,
                            "referenceCode": code,
                            "files": " | ".join([f.name for f in files]),
                            "status": "error",
                            "message": str(e),
                            "screenshot": screenshot_path
                        })

            # petite pause même après échec final
            if not success_for_this_record:
                page.wait_for_timeout(STABILITY_WAIT_MS)

        browser.close()

    # ------------------------------------------------------------------
    # RÉSUMÉ FINAL
    # ------------------------------------------------------------------
    print("\n" + "=" * 76)
    print("RÉSUMÉ FINAL")
    print("=" * 76)
    print(f"Nombre total de lignes à traiter          : {total_rows}")
    print(f"Lignes valides                            : {valid_rows}")
    print(f"Lignes invalides                          : {invalid_rows}")
    print(f"Notices déjà traitées (log)               : {skipped_already_done}")
    print(f"Notices sans fichiers locaux              : {missing_files}")
    print(f"Imports réussis                           : {ok_count}")
    print(f"Timeouts                                  : {timeout_count}")
    print(f"Erreurs                                   : {error_count}")
    print(f"Retrys effectués                          : {retry_count_total}")
    print(f"Nouvelles descriptions créées             : {created_descriptions_total}")
    print(f"Journal généré                            : {LOG_FILE}")
    print(f"Résumé descriptions créées                : {SUMMARY_FILE}")
    if TAKE_SCREENSHOT_ON_FAILURE:
        print(f"Captures d'erreur                         : {SCREENSHOTS_DIR}")
    print("=" * 76)


if __name__ == "__main__":
    main()
