## AtoM_METS_Data_Merger.py

This script automates the integration of metadata from AtoM (CSV) and Archivematica (METS XML) files to produce a unified, enriched CSV ready for use in AtoM.
It begins by extracting UUIDs from an AtoM CSV export, parsing the digitalObjectURI column to identify and structure unique identifiers.
Simultaneously, it processes the METS XML file, extracting detailed metadata such as file size, format, and checksum from `<mets:amdSec>` tags.
The script merges these datasets using the UUID and objectIdentifierValue as keys, combining file-level technical metadata with archival record information.
Additional transformations enrich the dataset by formatting dates, generating descriptive fields, and creating unique identifiers for each record.
It also duplicates entries to generate alternate metadata configurations tailored for AtoM’s interface.
Finally, the script outputs a structured CSV file, `urls.csv`, containing enriched metadata and URLs for direct integration or import into AtoM.
This ensures seamless synchronization of technical and archival metadata across systems.

Ce script automatise l’intégration des métadonnées provenant d’AtoM (CSV) et d’Archivematica (METS XML) pour produire un fichier CSV enrichi et unifié, prêt à être utilisé dans AtoM.
Il extrait d’abord les UUID d’un export CSV d’AtoM en analysant la colonne digitalObjectURI pour identifier et structurer les identifiants uniques.
Parallèlement, il traite le fichier METS XML, en récupérant des métadonnées détaillées comme la taille, le format et les sommes de contrôle à partir des balises `<mets:amdSec>`.
Les deux ensembles de données sont ensuite fusionnés à l’aide des clés UUID et objectIdentifierValue, combinant des métadonnées techniques au niveau des fichiers avec des informations descriptives archivistiques.
Le script enrichit les données en formatant les dates, en générant des champs descriptifs, et en créant des identifiants uniques pour chaque notice.
Il duplique également les enregistrements afin de produire des configurations alternatives adaptées à l’interface d’AtoM.
Enfin, il génère un fichier CSV structuré, `urls.csv`, contenant des métadonnées enrichies et des URLs prêtes pour une intégration ou un import direct dans AtoM.
Ce processus garantit une synchronisation fluide des métadonnées techniques et archivistiques entre les systèmes.

## AtoM_Record_Updater.py

The script automates the modification of archival records in AtoM by interacting with its web interface.
It uses a combination of HTTP requests and HTML parsing to access, edit, and update archival information based on enriched metadata stored in a preprocessed CSV file.
After loading credentials from the `login.csv` file, the program establishes a secure session with the AtoM portal, extracting and utilizing a CSRF token for authentication.
Once logged in, the script processes the `urls.csv` file, which lists the archival records to be updated. For each record, it retrieves the corresponding page, identifies and populates the relevant HTML form fields (e.g., `title`, `scopeAndContent`, `extentAndMedium`), and submits the updated form via a secure POST request.
Using `BeautifulSoup`, the program navigates the page elements to locate necessary fields and handle selectable options.
Updates include modifying titles, descriptions, identifiers, and other archival metadata to ensure consistency between the stored information and the provided data.
Finally, the program checks the server's response to confirm the success of each update, ensuring precise synchronization between local metadata and the AtoM system.

Ce script automatise la modification des notices archivistiques dans AtoM en interagissant avec son interface web.
Il utilise une combinaison de requêtes HTTP et de parsing HTML pour accéder, modifier et mettre à jour les informations archivistiques en se basant sur les métadonnées enrichies contenues dans un fichier CSV prétraité.
Après avoir chargé les identifiants depuis le fichier `login.csv`, le programme établit une session sécurisée avec le portail AtoM, en extrayant et utilisant un token CSRF pour s'authentifier.
Une fois connecté, le script traite le fichier `urls.csv`, qui répertorie les notices archivistiques à modifier.
Pour chaque notice, il télécharge la page correspondante, identifie et remplit les champs pertinents du formulaire HTML (par exemple, `title`, `scopeAndContent`, `extentAndMedium`), puis soumet le formulaire mis à jour via une requête POST sécurisée.
Grâce à `BeautifulSoup`, le programme navigue dans les éléments de la page pour localiser les champs nécessaires et gérer les options disponibles.
Les modifications incluent la mise à jour des titres, descriptions, identifiants et autres métadonnées archivistiques, garantissant une cohérence entre les informations stockées et les données fournies.
Enfin, le programme vérifie la réponse du serveur pour confirmer le succès de chaque mise à jour, assurant ainsi une synchronisation précise entre les métadonnées locales et le système AtoM.
