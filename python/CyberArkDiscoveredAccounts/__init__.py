import logging
import json
import requests
import math
import copy
import os
import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError

ALLOWED_ADMIN_GROUPS = {"Administrators", "Administrateurs", "Administradores", "Gli amministratori", "Beheerders", "Administratorzy"}

def logon_to_cyberark():
    logon_query_url = "https://<IIS_Server_Ip>/PasswordVault/API/auth/Cyberark/Logon/"
    logon_json_values = {'username': os.environ["CYBERARK_API_USERNAME"], 'password': os.environ["CYBERARK_API_PASSWORD"]}
    cyberark_api_token = requests.post(logon_query_url, json=logon_json_values).json()
    logging.info("Obtained Authorization Token Key from CyberArk")
    return cyberark_api_token

def get_current_account_count(cyberark_api_token):
    account_count_url = "https://<IIS_Server_Ip>/PasswordVault/API/DiscoveredAccounts"
    account_count_response = requests.get(account_count_url, headers={'Authorization': cyberark_api_token}).json()
    offset = math.floor(account_count_response["count"] / 1000)
    logging.info(f"Calculated offset: {offset}")
    return offset

def get_current_account_id_list(cyberark_api_token, offset):
  # Current Account ID list 
  current_account_id_list = set()
  current_offset = 0
  while current_offset <= offset:
     account_id_url = f"https://<IIS_Server_Ip>/PasswordVault/API/DiscoveredAccounts?offset={1000 * current_offset}&limit=1000"
     account_id_response = requests.get(account_id_url, headers={'Authorization': cyberark_api_token}).json()
     for account in account_id_response["value"]:
        current_account_id_list.add(account["id"])
     current_offset+=1
  logging.info("Obtained current account id list from CyberArk")
  return current_account_id_list

def get_account_details(cyberark_api_token, old_account_id_list, old_account_details, new_account_id_list, current_account_id_list, current_account_details, new_account_details, updated_old_account_details):
    
    for current_account_id in current_account_id_list:
        account_details_url = f"https://<IIS_Server_Ip>/PasswordVault/API/DiscoveredAccounts/{current_account_id}"
        account_details_response = requests.get(account_details_url, headers={'Authorization': cyberark_api_token})
        if account_details_response.status_code == 200:
            account_details_response_json = account_details_response.json()
            current_account_details[current_account_id] = account_details_response_json
            if old_account_id_list and old_account_details:
                current_account = copy.deepcopy(account_details_response_json)
                if current_account_id in new_account_id_list:
                    process_new_accounts(current_account, new_account_details)
                elif current_account_id in old_account_id_list:
                    process_old_account(current_account, old_account_details[current_account_id], updated_old_account_details)
            logging.info(f"Retrieved Account details: {current_account_id}")
        else:
            logging.warning(f"Error fetching details for account ID {current_account_id}: HTTP {account_details_response.status_code}")
            raise requests.HTTPError(f"Failed to fetch details for account ID {current_account_id}: HTTP {account_details_response.status_code}")

def process_new_accounts(current_account, new_account_details):
    os_groups = current_account.get('osGroups', '').split(',')
    has_new_dependencies = current_account.get('numberOfDependencies') != 0
    is_added_to_admin_group = any(group.strip() in ALLOWED_ADMIN_GROUPS for group in os_groups)

    if has_new_dependencies or is_added_to_admin_group:
        if is_added_to_admin_group:
            admin_groups = [group.strip() for group in os_groups if group.strip() in ALLOWED_ADMIN_GROUPS]
            current_account['osGroups'] = ', '.join(admin_groups)
        new_account_details.append(current_account)

def process_old_account(current_account, old_account, updated_old_account_details):
    current_os_groups = set(current_account.get('osGroups', '').split(','))
    previous_os_groups = set(old_account.get('osGroups', '').split(','))
    new_os_groups = list(current_os_groups - previous_os_groups & set(ALLOWED_ADMIN_GROUPS))
    new_dependencies = []

    if current_account.get('numberOfDependencies') != 0:
        current_account_dependencies = current_account.get('dependencies', [])

        if old_account.get('numberOfDependencies') == 0:
            new_dependencies = current_account['dependencies']
        elif old_account.get('numberOfDependencies') != 0:
            old_account_dependencies = old_account.get('dependencies', [])
            new_dependencies = [dependency for dependency in current_account_dependencies if dependency not in old_account_dependencies]

    if new_dependencies or new_os_groups:
        if new_dependencies:
            current_account['dependencies'] = new_dependencies
            current_account['numberOfDependencies'] = len(new_dependencies)
        if new_os_groups:
            current_account['osGroups'] = ', '.join(new_os_groups)
        updated_old_account_details.append(current_account)

def get_old_account_id_list_from_blob(blob_connection_string):
    try:
        # Initialize BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
        blob_client = blob_service_client.get_blob_client(container="cyberark-accounts", blob="old_account_ids.txt")
        blob_data = blob_client.download_blob()
        lines = blob_data.readall().decode('utf-8').split('\n')
        # old Account ID list 
        old_account_id_list = set()
        old_account_id_list.update(account_id.strip() for account_id in lines if account_id)
        logging.info(f"Retrieved Old Account ID from old_account_ids.txt")
        return old_account_id_list
    except ResourceNotFoundError:
        logging.warning("Blob not found: old_account_ids.txt")
    except Exception as e:
        logging.error(f"Error loading account IDs from old_account_ids.txt blob: {str(e)}")

def write_current_account_id_list_to_blob(blob_connection_string, current_account_id_list):
    try:
        content = '\n'.join(current_account_id_list)
        blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)       
        blob_client = blob_service_client.get_blob_client(container="cyberark-accounts", blob="old_account_ids.txt")
        blob_client.upload_blob(content, overwrite=True)
        logging.info(f"Saved current account IDs: old_account_ids.txt blob")
    except Exception as e:
        logging.error(f"Error writing current account IDs to old_account_ids.txt blob: {str(e)}")

def get_old_account_details_from_blob(blob_connection_string):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
        blob_client = blob_service_client.get_blob_client(container="cyberark-accounts", blob="CyberArk_Discovered_Accounts.json")
        blob_data = blob_client.download_blob()
        content = blob_data.readall()
        return json.loads(content)
    except ResourceNotFoundError:
        logging.warning("Blob not found: old_account_details.json")
        return {}
    except Exception as e:
        logging.error(f"Error retrieving old_account_details.json: {str(e)}")
        return {}

def save_json_to_blob(blob_name, blob_connection_string, account_details):
    try:
        json_data = json.dumps(account_details, indent=4)
        blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
        blob_client = blob_service_client.get_blob_client(container="cyberark-accounts", blob=blob_name)
        blob_client.upload_blob(json_data, overwrite=True)
        logging.info(f"JSON data saved to Blob Storage as: {blob_name}")
    except Exception as e:
        logging.error(f"Error saving {blob_name} to blob: {str(e)}")

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('cyberArk-discovered-accounts logic app has triggered an HTTP request')
    
    # Getting an Access token from CyberArk
    cyberArk_apiToken = logon_to_cyberark()
    
    # Get offset which calculate number of times to send GET req for account details
    offset = get_current_account_count(cyberArk_apiToken)
    
    # Get Current Account Ids
    current_account_id_list = get_current_account_id_list(cyberArk_apiToken, offset)
    
    # Azure Blob Storage Connection String for Configuration
    blob_connection_string  = os.environ["BLOB_CONNECTION_STRING"]
    
    # Get Old Account IDs
    old_account_id_list = get_old_account_id_list_from_blob(blob_connection_string)
    
    # Get Old Account Details
    old_account_details = get_old_account_details_from_blob(blob_connection_string)

    # Initialize a list for new account IDs
    new_account_id_list = set()

    # Find new account ids by comparing old account ids and current account ids
    if old_account_id_list and old_account_details:                
        new_account_id_list.update(account_id for account_id in current_account_id_list if account_id not in old_account_id_list)
        logging.info(f"New Account Id's Detected: {new_account_id_list}")
    else:
        logging.warning("Discovering New Account ID is Skipped")

    # Create a dict to store account details
    current_account_details = {}
   
    # Create a list to store new account details
    new_account_details = []

    # Create a list to store the updated dependecies and OsGroup of old account 
    updated_old_account_details =[]
    
    # Get Account details 
    get_account_details(cyberArk_apiToken, old_account_id_list, old_account_details, new_account_id_list, current_account_id_list, current_account_details, new_account_details, updated_old_account_details)
    
    # Save the all CyberArk Account details to keep track of the data
    save_json_to_blob("CyberArk_Discovered_Accounts.json", blob_connection_string, current_account_details)
    
    # Save account id to keep of the data
    write_current_account_id_list_to_blob(blob_connection_string, current_account_id_list)
    
    # New accounts populated with dependencies and admin groups
    save_json_to_blob("New_CyberArk_Discovered_Accounts.json", blob_connection_string, new_account_details)
    
    # Old accounts which is updated with new dependencies and added to and admin groups
    save_json_to_blob("Updated_CyberArk_Discovered_Old_Accounts.json", blob_connection_string, updated_old_account_details)
    
    return func.HttpResponse("Function executed successfully.", status_code=200)