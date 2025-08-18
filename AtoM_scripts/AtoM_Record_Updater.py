'''
# Script: AtoM_Record_Updater.py
# Description: This script automates the update of archival records in AtoM by interacting with its web interface. It uses HTTP requests to modify
# records based on enriched metadata from a merged CSV file.
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
import requests
import csv
from bs4 import BeautifulSoup

# Charger les informations d'identifiants depuis le fichier login.csv
def load_login_credentials(login_file):
    credentials = []
    with open(login_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            credentials.append({
                'email': row['Email'],
                'password': row['Password']
            })
    return credentials

# Se connecter à la page avec les identifiants
def login_to_site(session, login_url, email, password):
    response = session.get(login_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    csrf_token = soup.find('input', {'name': '_csrf_token'}).get('value')
    if not csrf_token:
        print("Erreur : CSRF token non trouvé.")
        return False

    login_data = {
        '_csrf_token': csrf_token,
        'email': email,
        'password': password,
        'next': 'https://morphe-test.epfl.ch/index.php/user/login'
    }
    
    login_response = session.post(login_url, data=login_data, allow_redirects=True)

    if "Bienvenue" in login_response.text or login_response.status_code == 200:
        print(f"Connexion réussie avec {email}!")
        return True
    else:
        print(f"Échec de la connexion avec {email}.")
        return False

# Traiter les URLs du fichier urls.csv
def process_urls(session, urls_file):
    with open(urls_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            url = row['urls']
            date_creation = row['dateCreation']
            scope_and_content = row['scopeAndContent']
            edit_events_type = row['editEvents_0_type']
            level_of_description = row['levelOfDescription']
            extent_and_medium = row['extentAndMedium']
            titre = row['titre']
            identifier = row['identifier']
            

            print(f"Accès à l'URL: {url}")

            try:
                response = session.get(url)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"Erreur lors de l'accès à l'URL {url}: {e}")
                continue

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                form_elements = soup.find_all(['input', 'textarea', 'select'])
                print(f"\nChamps trouvés sur {url} :")
                
                form_data = {}
                
                for element in form_elements:
                    name = element.get('name')
                    id = element.get('id')

                    print(f"Champ trouvé: {name}, ID: {id}")

                    if id == 'editEvents_0_type':
                        select_element = element
                        options = select_element.find_all('option')
                        for option in options:
                            if option['value'] == f"/index.php/{edit_events_type}":
                                option['selected'] = 'selected'
                                form_data[name] = option['value']
                                print(f"Option mise à jour : {option}")

                    elif id == 'editEvents_0_date':
                        print(f"Remplissage du champ 'editEvents_0_date' avec : {date_creation}")
                        element['value'] = date_creation
                        form_data[name] = element['value']

                    elif id == 'levelOfDescription':
                        print(f"Remplissage du champ 'levelOfDescription' avec : {level_of_description}")
                        option_element = element.find('option', value=f"/index.php/{level_of_description}")
                        if option_element:
                            option_element['selected'] = 'selected'
                            form_data[name] = f"/index.php/{level_of_description}"
                            print(f"Option sélectionnée : {option_element}")
                        else:
                            print(f"Option avec la valeur '/index.php/{level_of_description}' non trouvée pour le champ 'levelOfDescription'.")

                    elif id == 'extentAndMedium':
                        print(f"Remplissage du champ 'extentAndMedium' avec : {extent_and_medium}")
                        element.string = extent_and_medium
                        form_data[name] = element.string

                    elif id == 'scopeAndContent':
                        print(f"Remplissage du champ 'scopeAndContent' avec : {scope_and_content}")
                        element.string = scope_and_content
                        form_data[name] = element.string

                    elif id == 'title':
                        print(f"Remplissage du champ 'title' avec : {titre}")
                        element['value'] = titre
                        form_data[name] = element['value']

                    elif id == 'identifier':
                        print(f"Remplissage du champ 'identifier' avec : {identifier}")
                        element['value'] = identifier
                        form_data[name] = element['value']

                submit_url = url
                csrf_token = soup.find('input', {'name': '_csrf_token'})
                if csrf_token:
                    form_data['_csrf_token'] = csrf_token.get('value')
                else:
                    print(f"Erreur : CSRF token non trouvé pour l'URL {url}")
                    continue

                # Convert form data to the correct format for submission
                data_to_submit = {key: value for key, value in form_data.items()}

                print(f"Données envoyées : {data_to_submit}")

                try:
                    submit_response = session.post(submit_url, data=data_to_submit)
                    submit_response.raise_for_status()
                except requests.RequestException as e:
                    print(f"Erreur lors de la soumission du formulaire pour {url}: {e}")
                    continue

                if submit_response.status_code == 200:
                    print(f"Formulaire soumis avec succès pour {url}")
                else:
                    print(f"Erreur lors de la soumission du formulaire pour {url}. Code : {submit_response.status_code}")
            
            print("\n---\n")

# Principal
def main():
    login_file = 'login.csv'
    urls_file = 'urls.csv'
    login_url = "https://morphe-test.epfl.ch/index.php/user/login"

    session = requests.Session()
    credentials = load_login_credentials(login_file)

    for cred in credentials:
        email = cred['email']
        password = cred['password']
        
        if login_to_site(session, login_url, email, password):
            process_urls(session, urls_file)
            break
        else:
            print("Essai de connexion échoué pour cet utilisateur.")

# Exécuter le script
if __name__ == "__main__":
    main()

