'''
# Script: AtoM_METS_Data_Merger.py
# Description: This script extracts and merges metadata from AtoM (CSV) and METS (XML) files. It standardizes, parses, and combines data
# into a unified, enriched CSV file ready for further processing or import into AtoM.
#
# Author: Yonathan Seibt, Archives de la construction moderne – EPFL
# Date: November 2024
#
# License: This script is distributed under the GNU General Public License v3. You may redistribute and/or modify it under the terms 
#          of the GNU GPL as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
#
#          This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty 
#          of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
#          You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
'''
import pandas as pd
import re
import xml.etree.ElementTree as ET
from datetime import datetime

# ---- Partie 1 : Extraire les UUID du fichier CSV ----

# Lire le fichier CSV
df_csv = pd.read_csv('isad_0000000001.csv')  # Remplacez par le nom de votre fichier CSV

# Ajouter une colonne d'index pour conserver l'ordre
df_csv['index'] = df_csv.index

# Fonction pour extraire l'UUID
def extract_uuid(url):
    if isinstance(url, str):
        match = re.search(r'/([0-9a-fA-F-]{36})-', url)
        if match:
            return match.group(1)
    return None

# Appliquer la fonction à la colonne contenant les URLs
df_csv['UUID'] = df_csv['digitalObjectURI'].apply(extract_uuid)  # Remplacez par le nom de votre colonne

# ---- Partie 2 : Extraire les données du fichier XML ----

# Charger le fichier XML
xml_file = 'METS.07fdd110-6ae2-49c4-989d-6394c152be9c.xml'
tree = ET.parse(xml_file)
root = tree.getroot()

# Définir l'espace de noms utilisé dans le fichier XML
ns = {'mets': 'http://www.loc.gov/METS/'}

# Fonction pour extraire toutes les données des balises <mets:amdSec> et les structurer
def extract_all_amdSec_data(root, ns):
    amdSec_data = []
    
    # Trouver toutes les balises <mets:amdSec>
    for amdSec in root.findall('.//mets:amdSec', ns):
        data = {}
        
        # Extraire l'attribut 'ID' de la balise <mets:amdSec>
        data['ID'] = amdSec.attrib.get('ID', None)

        # Extraire toutes les sous-balises pertinentes
        for element in amdSec.iter():
            # Si l'élément est une balise avec un texte (et non l'attribut)
            if element.tag != '{http://www.loc.gov/METS/}amdSec' and element.text:
                # Enlever l'espace de noms de la balise
                tag = element.tag.split('}')[1] if '}' in element.tag else element.tag
                data[tag] = element.text.strip()
        
        # Ajouter les données extraites à la liste
        amdSec_data.append(data)
    
    return amdSec_data

# Extraire toutes les données des balises <mets:amdSec>
amdSec_data = extract_all_amdSec_data(root, ns)

# Créer un DataFrame avec les données extraites
df_xml = pd.DataFrame(amdSec_data)

# Filtrer les colonnes non pertinentes
columns_to_keep = [
    'ID', 'objectIdentifierValue', 'size', 'messageDigestAlgorithm', 'messageDigest', 'formatName', 'formatVersion', 
    'formatRegistryKey', 'dateCreatedByApplication', 'created', 
    'creatingApplicationName', 'FileName', 'FileType', 'FileTypeExtension', 'MIMEType', 'originalName'
]

# Garder uniquement les colonnes pertinentes
df_filtered = df_xml[columns_to_keep]

# ---- Partie 3 : Fusionner les données des deux DataFrames ----

# Fusionner les deux DataFrames sur les colonnes correspondantes
# Ici, on suppose que les noms des colonnes à fusionner sont respectivement 'objectIdentifierValue' et 'UUID'
df_merged = pd.merge(df_filtered, df_csv, left_on='objectIdentifierValue', right_on='UUID', how='inner')

# Réordonner le DataFrame fusionné selon l'index original
df_merged = df_merged.sort_values(by='index')

# ---- Partie 4 : Transformation et duplication des données ----

# Initialiser les nouvelles colonnes
df_merged['urls'] = 'https://morphe-test.epfl.ch/index.php/' + df_merged['slug'] + '/edit'
df_merged['titre'] = df_merged['title'] + ' (fichier numérique)'
df_merged['editEvents_0_type'] = 'creation'

# Corriger le format de date
def format_date(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')
    except ValueError:
        return ''

df_merged['dateCreation'] = df_merged['dateCreatedByApplication'].apply(format_date)
df_merged['levelOfDescription'] = 'item'
df_merged['scopeAndContent'] = 'Chemin d’accès du fichier sur le support original : ' + df_merged['originalName'].str.replace('%transferDirectory%objects/', '')
df_merged['extentAndMedium'] = '1 fichier numérique ' + df_merged['formatName'] + ' de ' + df_merged['size'] + ' octets'
df_merged['identifier'] = ['0219.01.0130/04.01.01.' + str(i+1).zfill(2) for i in range(len(df_merged))]

# Dupliquer chaque enregistrement avec modification de la colonne urls
df_duplicated = df_merged.copy()
df_duplicated['urls'] = 'https://morphe-test.epfl.ch/index.php/' + df_duplicated['slug'] + '/edit?sf_culture=fr&template=isad'

# Combiner les DataFrames
df_final = pd.concat([df_merged, df_duplicated], ignore_index=True)

# Réordonner le DataFrame final selon l'index original
df_final = df_final.sort_values(by='index')

# Sélectionner les colonnes nécessaires
columns_to_keep = ['urls', 'titre', 'editEvents_0_type', 'dateCreation', 'levelOfDescription', 'scopeAndContent', 'extentAndMedium', 'identifier']
df_final = df_final[columns_to_keep]

# Sauvegarder dans le fichier CSV final
output_file = 'urls.csv'
df_final.to_csv(output_file, index=False)

print(f"Le fichier '{output_file}' a été créé avec succès.")
