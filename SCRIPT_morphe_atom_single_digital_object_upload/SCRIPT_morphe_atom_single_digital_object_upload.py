"""
SCRIPT_morphe_atom_single_digital_object_upload
Script d’automatisation du téléversement de documents numérisés (« Plus » >
« Lier document numérisé ») dans Morphe (AtoM – Access to Memory).

Date de création : 2026-04-05
Auteur : Barbara Galimberti (Archives de la construction moderne – EPFL)
Modèle utilisé : ChatGPT (GPT-5.4 Thinking, avril 2026), utilisé comme
assistant pour la génération et l’optimisation du code

Contexte d’exécution :
- Application cible : AtoM 2.10.1 (build 197)
- Système : macOS Sequoia 15.4.1
- Langage : Python 3.x
- Dépendances Python :
    - pathlib
    - pandas
    - playwright

Fichiers source attendus :
- records.csv   -> contient au minimum les colonnes :
    - record_url
    - referenceCode
- dossier images/
    -> contient les fichiers à téléverser, par exemple :
       0143.04.0044.jpg
       0143.04.0045.pdf

Fichier de sortie :
- upload_log.csv

Description :
Ce script automatise l’ajout d’un objet numérique local à des notices de
description dans Morphe (AtoM) à partir d’un fichier `records.csv` et d’un
dossier `images/`. En amont, les notices à enrichir sont sélectionnées dans
Morphe, ajoutées au presse-papiers, puis exportées en CSV. 
Ce fichier sert de base de préparation : la colonne `referenceCode` est
conservée et la colonne `slug` est transformée en URL absolue (`record_url`)par 
ajout de la racine de l’application (https://morphe.epfl.ch/).
Le script valide les entrées, recherche pour chaque notice un fichier local
correspondant au `referenceCode` (nom du fichier = cote archivistique) dans
le dossier `images/`, puis ouvre la page d’ajout d’objet numérique associée
à la notice. Il injecte le fichier dans le champ de téléversement, soumet le
formulaire avec le bouton « Ajouter » et vérifie de manière souple si
l’opération semble aboutie à partir d’indices présents dans l’interface de
résultat. 
Chaque traitement est journalisé dans `upload_log.csv`, avec distinction
entre succès présumé, vérification manuelle requise, absence de fichier local,
timeout ou erreur. Un résumé quantifié est affiché en console à la fin de
l’exécution.

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
      - ex. `slug`: maison-dubois
        --> `record_url`: `https://morphe.epfl.ch/maison-dubois`
5. sauvegarder les objets numériques correspondants dans le dossier images/
6. vérifier que le nom des fichiers (objets numériques) soit identique à la
   cote de la description (`referenceCode`) 
   - ex. : `referenceCode`: `0143.04.0044`
        --> nom du fichier dans images/: 0143.04.0044.jpg

Workflow (script):
1. vérifier la présence des fichiers et dossiers nécessaires (`records.csv`,
   `images/`)
2. charger le fichier `records.csv`
3. contrôler la présence des colonnes obligatoires (`record_url`,
   `referenceCode`)
4. lancer le navigateur automatisé et ouvrir Morphe
5. attendre le login manuel de l’utilisateur
6. parcourir les lignes du CSV
7. rechercher, pour chaque `referenceCode`, le fichier local correspondant dans
   `images/`
8. construire l’URL d’ajout d’objet numérique à partir de `record_url`
9. ouvrir la page `object/addDigitalObject` et vérifier qu’elle est correctement
   chargée
10. téléverser le fichier local et soumettre le formulaire
11. vérifier la présence d’indices de succès dans la page de résultat
12. enregistrer le résultat du traitement dans `upload_log.csv`
13. afficher un résumé final de validation et d’exécution en console

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
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ----------------------------------------------------------------------
# Définition des chemins de travail
# ----------------------------------------------------------------------

# Répertoire du script courant
BASE_DIR = Path(__file__).resolve().parent

# Fichier CSV source contenant les notices à traiter
CSV_FILE = BASE_DIR / "records.csv"

# Dossier contenant les fichiers à téléverser
IMAGES_DIR = BASE_DIR / "images"

# Fichier journal de sortie
LOG_FILE = BASE_DIR / "upload_log.csv"


# ----------------------------------------------------------------------
# Extensions autorisées pour la recherche des fichiers locaux
# ----------------------------------------------------------------------

EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"]


# ----------------------------------------------------------------------
# Fonctions utilitaires
# ----------------------------------------------------------------------

def find_local_file(code: str):
    """
    Recherche dans le dossier images/ un fichier correspondant au referenceCode.

    Le script teste successivement toutes les extensions déclarées dans EXTENSIONS.
    Exemple : si le code vaut 'ABC123', il cherchera :
        - ABC123.jpg
        - ABC123.jpeg
        - ABC123.png
        - etc.

    Paramètres :
        code (str) : code de référence de la notice

    Retour :
        Path | None : chemin du fichier trouvé, ou None si aucun fichier ne correspond
    """
    code = str(code).strip()
    for ext in EXTENSIONS:
        candidate = IMAGES_DIR / f"{code}{ext}"
        if candidate.exists():
            return candidate
    return None


def build_add_digital_object_url(record_url: str) -> str:
    """
    Construit l'URL de la page d'ajout d'objet numérique à partir de l'URL de la notice.

    Paramètres :
        record_url (str) : URL de base de la notice

    Retour :
        str : URL complète vers la page d'ajout d'objet numérique
    """
    return record_url.rstrip("/") + "/object/addDigitalObject"


def append_log(row_dict):
    """
    Ajoute une ligne au fichier upload_log.csv.

    Si le fichier existe déjà, les anciennes lignes sont relues puis la nouvelle
    ligne est concaténée avant réécriture du fichier complet.

    Paramètres :
        row_dict (dict) : dictionnaire représentant une ligne de log
    """
    df_new = pd.DataFrame([row_dict])
    if LOG_FILE.exists():
        df_old = pd.read_csv(LOG_FILE, dtype=str).fillna("")
        df_new = pd.concat([df_old, df_new], ignore_index=True)
    df_new.to_csv(LOG_FILE, index=False, encoding="utf-8")


def open_add_digital_object_page(page, record_url: str):
    """
    Ouvre la page 'ajout d'objet numérique' pour une notice donnée et vérifie
    que la page attendue est bien chargée.

    Vérifications effectuées :
    - présence du texte 'Lier document numérisé'
    - présence du texte 'Téléverser un document numérisé'

    Paramètres :
        page : objet page Playwright
        record_url (str) : URL de la notice

    Retour :
        str : URL réellement utilisée pour l'ajout d'objet numérique
    """
    add_url = build_add_digital_object_url(record_url)
    page.goto(add_url, wait_until="networkidle", timeout=60000)

    # Vérification de la bonne page cible avant de continuer
    page.locator("text=Lier document numérisé").first.wait_for(timeout=15000)
    page.locator("text=Téléverser un document numérisé").first.wait_for(timeout=15000)

    return add_url


def upload_local_file(page, file_path: Path):
    """
    Téléverse un fichier local dans le formulaire d'ajout d'objet numérique,
    puis clique sur le bouton 'Ajouter'.

    Étapes :
    1. repérer le champ input[type='file']
    2. injecter le fichier local
    3. attendre brièvement pour laisser le temps au navigateur de prendre en compte le fichier
    4. cliquer sur le bouton 'Ajouter'
    5. attendre la fin du chargement réseau

    Paramètres :
        page : objet page Playwright
        file_path (Path) : chemin du fichier à téléverser
    """
    # Champ de sélection du fichier local
    file_input = page.locator('input[type="file"]').first
    file_input.wait_for(timeout=10000)
    file_input.set_input_files(str(file_path))

    # Petite pause pour laisser le temps au formulaire d'intégrer le fichier
    page.wait_for_timeout(1200)

    # Bouton de soumission 'Ajouter'
    add_button = page.locator(
        'button:has-text("Ajouter"), input[type="submit"][value="Ajouter"]'
    ).first
    add_button.wait_for(timeout=10000)
    add_button.click()

    # Attendre que la page ait terminé ses échanges réseau
    page.wait_for_load_state("networkidle")


def verify_upload_result(page):
    """
    Tente de vérifier si le téléversement semble réussi en recherchant divers
    éléments caractéristiques d'une page de résultat positive.

    La vérification reste volontairement souple : si l'un des sélecteurs ci-dessous
    est détecté, le script considère que l'opération semble réussie.

    Paramètres :
        page : objet page Playwright

    Retour :
        bool : True si un indice de succès est détecté, sinon False
    """
    possible_success_selectors = [
        "text=Modifier le document numérisé",
        "text=Edit digital object",
        "text=Métadonnées de l’objet numérique",
        "text=Digital object metadata",
        "text=Reference copy",
        "text=Thumbnail copy",
        "img"
    ]

    for sel in possible_success_selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                return True
        except Exception:
            pass

    return False


# ----------------------------------------------------------------------
# Fonction principale
# ----------------------------------------------------------------------

def main():
    """
    Fonction principale du script.

    Déroulement :
    1. Vérifie l'existence des fichiers et dossiers nécessaires
    2. Charge le CSV
    3. Vérifie la présence des colonnes obligatoires
    4. Lance Playwright et ouvre Morphe
    5. Attend que l'utilisateur effectue le login manuellement
    6. Parcourt chaque ligne du CSV
    7. Cherche le fichier local correspondant
    8. Téléverse le fichier si possible
    9. Enregistre le résultat dans le fichier log
    10. Affiche un résumé de validation en console
    """
    # ------------------------------------------------------------------
    # Vérifications préalables : présence du CSV et du dossier images
    # ------------------------------------------------------------------
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"CSV introuvable: {CSV_FILE}")

    if not IMAGES_DIR.exists():
        raise FileNotFoundError(f"Dossier images introuvable: {IMAGES_DIR}")

    # Lecture du CSV en forçant toutes les colonnes en texte
    df = pd.read_csv(CSV_FILE, dtype=str).fillna("")

    # Vérification des colonnes indispensables au traitement
    required_columns = {"record_url", "referenceCode"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans records.csv : {missing}")

    # ------------------------------------------------------------------
    # Bloc de validation initiale des données d'entrée
    # ------------------------------------------------------------------
    total_rows = len(df)

    valid_record_url_count = df["record_url"].astype(str).str.strip().ne("").sum()
    valid_reference_code_count = df["referenceCode"].astype(str).str.strip().ne("").sum()

    fully_valid_input_count = (
        df["record_url"].astype(str).str.strip().ne("") &
        df["referenceCode"].astype(str).str.strip().ne("")
    ).sum()

    invalid_input_count = total_rows - fully_valid_input_count

    # Compteurs d'exécution
    found_local_file_count = 0
    missing_local_file_count = 0
    ok_count = 0
    submitted_check_manually_count = 0
    timeout_count = 0
    error_count = 0

    # ------------------------------------------------------------------
    # Lancement du navigateur Playwright
    # ------------------------------------------------------------------
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=350)
        context = browser.new_context()
        page = context.new_page()

        # Ouverture de la page d'accueil Morphe
        page.goto("https://morphe.epfl.ch", wait_until="networkidle")

        # Login manuel demandé à l'utilisateur
        print("Veuillez effectuer le login manuellement dans le navigateur.")
        input("Quand le login est terminé, appuyez sur ENTRÉE ici... ")

        # ------------------------------------------------------------------
        # Boucle principale sur les lignes du CSV
        # ------------------------------------------------------------------
        for _, row in df.iterrows():
            record_url = row["record_url"].strip()
            code = row["referenceCode"].strip()

            # Recherche du fichier local correspondant au code de référence
            local_file = find_local_file(code)

            # Si aucun fichier local n'est trouvé, on journalise et on passe à la suite
            if not local_file:
                missing_local_file_count += 1
                print(f"[SKIP] Aucun fichier trouvé pour {code}")
                append_log({
                    "record_url": record_url,
                    "referenceCode": code,
                    "add_url": "",
                    "file": "",
                    "status": "missing_local_file",
                    "message": "fichier local non trouvé"
                })
                continue

            found_local_file_count += 1
            print(f"[START] {code} -> {local_file.name}")

            try:
                # Ouvrir la page d'ajout d'objet numérique
                add_url = open_add_digital_object_page(page, record_url)

                # Téléverser le fichier local
                upload_local_file(page, local_file)

                # Vérifier si le résultat semble concluant
                success = verify_upload_result(page)

                # Écriture dans le journal d'exécution
                append_log({
                    "record_url": record_url,
                    "referenceCode": code,
                    "add_url": add_url,
                    "file": local_file.name,
                    "status": "ok" if success else "submitted_check_manually",
                    "message": "upload envoyé"
                })

                if success:
                    ok_count += 1
                else:
                    submitted_check_manually_count += 1

                print(f"[OK] {code}")

            except PlaywrightTimeoutError:
                timeout_count += 1
                print(f"[TIMEOUT] {code}")
                append_log({
                    "record_url": record_url,
                    "referenceCode": code,
                    "add_url": build_add_digital_object_url(record_url),
                    "file": local_file.name,
                    "status": "timeout",
                    "message": "timeout pendant l'upload"
                })

            except Exception as e:
                error_count += 1
                print(f"[ERROR] {code}: {e}")
                append_log({
                    "record_url": record_url,
                    "referenceCode": code,
                    "add_url": build_add_digital_object_url(record_url),
                    "file": local_file.name,
                    "status": "error",
                    "message": str(e)
                })

        # Fermeture du navigateur en fin de traitement
        browser.close()

    # ------------------------------------------------------------------
    # Bloc de validation / résumé final affiché en console
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("RÉSUMÉ DE VALIDATION ET D'EXÉCUTION")
    print("=" * 70)
    print(f"Nombre total de lignes dans records.csv           : {total_rows}")
    print(f"record_url valides (non vides)                    : {valid_record_url_count}")
    print(f"referenceCode valides (non vides)                 : {valid_reference_code_count}")
    print(f"Lignes entièrement valides en entrée              : {fully_valid_input_count}")
    print(f"Lignes incomplètes / potentiellement invalides    : {invalid_input_count}")
    print("-" * 70)
    print(f"Fichiers locaux trouvés                           : {found_local_file_count}")
    print(f"Fichiers locaux manquants                         : {missing_local_file_count}")
    print("-" * 70)
    print(f"Uploads confirmés / présumés réussis              : {ok_count}")
    print(f"Uploads soumis à vérifier manuellement            : {submitted_check_manually_count}")
    print(f"Timeouts                                          : {timeout_count}")
    print(f"Erreurs                                           : {error_count}")
    print(f"Journal généré                                    : {LOG_FILE}")
    print("=" * 70 + "\n")


# ----------------------------------------------------------------------
# Point d'entrée du script
# ----------------------------------------------------------------------

if __name__ == "__main__":
    main()
