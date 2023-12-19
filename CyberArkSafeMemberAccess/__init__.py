import logging
import json
import requests
import math
import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError


def get_cyberark_token():
    username = "ENTER YOUR USERNAME HERE"
    password = "ENTER YOUR USERNAME HERE"
    logon_query_url = "https://<IIS_Server_Ip>/PasswordVault/API/auth/Cyberark/Logon/"  # Replace IIS_Server_IP with your company cyberArk website
    logon_json_values = {'username': username, 'password': password}
    cyberark_api_token = requests.post(logon_query_url, json=logon_json_values).json()
    print("Obtained Authorization Token Key from CyberArk")
    return cyberark_api_token

def get_safe_count(cyberark_api_token, URL_endpoint):
    count_url = f"https://<IIS_Server_Ip>/PasswordVault/API/{URL_endpoint}"
    count_response = requests.get(count_url, headers={'Authorization': cyberark_api_token}).json()
    offset = math.floor(count_response["count"] / 1000)
    logging.info(f"Calculated offset: {offset}")
    return offset

def get_safeUrlId_list(cyberark_api_token):
    safeUrlId_list = set()
    current_offset = 0
    offset = get_safe_count(cyberark_api_token, "Safes/")
    
    while current_offset <= offset:
        safes_url = f"https://<IIS_Server_Ip>/PasswordVault/API/Safes?offset={1000 * current_offset}&limit=1000"
        safe_id_response = requests.get(safes_url, headers={'Authorization': cyberark_api_token}).json()
        for safe in safe_id_response["value"]:
            safeUrlId_list.add(safe["safeUrlId"])
        current_offset+=1
    logging.info("Obtained current safe id list from CyberArk")
    return safeUrlId_list

def get_safe_members(cyberark_api_token, safeUrlId_list):
    safe_members_list = list()
    for safeUrlId in safeUrlId_list:
        all_safe_members_url = f"https://<IIS_Server_Ip>/PasswordVault/API/Safes/{safeUrlId}/Members?offset=0&limit=1000"
        all_safe_members_response = requests.get(all_safe_members_url, headers={'Authorization': cyberark_api_token})
        if all_safe_members_response.status_code == 200:
            all_safe_members_response_json = all_safe_members_response.json()
            for member in all_safe_members_response_json["value"]:
                safe_members_list.append(member)
        else:
            print(f"Error fetching details of members from {safeUrlId} safe: HTTP {all_safe_members_response.status_code}")
    return safe_members_list       

def get_groupId(cyberark_api_token):
    groupId_list = set()
    current_offset = 0
    offset = get_safe_count(cyberark_api_token, "UserGroups/")
    
    while current_offset <= offset:
        group_url = f"https://<IIS_Server_Ip>/PasswordVault/API/UserGroups?offset={1000 * current_offset}&limit=1000"
        group_id_response = requests.get(group_url, headers={'Authorization': cyberark_api_token}).json()
        for group in group_id_response["value"]:
            groupId_list.add(group["id"])
        current_offset+=1
    logging.info("Obtained current group id list from CyberArk")
    return groupId_list 

def get_group_members(cyberark_api_token, groupId_list):
    group_members_list = list()
    for groupId in groupId_list:
        group_members_url = f"https://<IIS_Server_Ip>/PasswordVault/API/UserGroups/{groupId}"
        group_members_response = requests.get(group_members_url, headers={'Authorization': cyberark_api_token})
        if group_members_response.status_code == 200:
            group_members_response_json = group_members_response.json()
            group_members_list.append(group_members_response_json)
        else:
            print(f"Error fetching details of members from group id: {groupId} : HTTP {group_members_response.status_code}")
    return group_members_list  

def save_json_to_blob(blob_name, members_list):
    try:
        blob_connection_string = "ENTER YOUR STORAGE ACCOUNT CONNECTION STRING HERE"
        container_name = "ENTER YOUR CONTAINER NAME HERE"
        json_data = json.dumps(members_list, indent=4)
        blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
        blob_client = blob_service_client.get_blob_client(container = container_name, blob=blob_name)
        blob_client.upload_blob(json_data, overwrite=True)
        print(f"JSON data saved to Blob Storage as: {blob_name}")
    except Exception as e:
        print(f"Error saving {blob_name} to blob: {str(e)}")

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    
    # Getting an Access token from CyberArk
    cyberArk_apiToken = get_cyberark_token()
    
    # Get Current Safe Ids
    safeUrlId_list = get_safeUrlId_list(cyberArk_apiToken)

    # Get Safe Members with their access details
    safe_members_list = get_safe_members(cyberArk_apiToken, safeUrlId_list)

    # Save the members list in a json file to blob storage
    save_json_to_blob("CyberArkSafeMembersAccess.json", safe_members_list)

    # Get Current Group Ids
    groupId_list = get_groupId(cyberArk_apiToken)

    # Get Group members from their group
    group_members_list = get_group_members(cyberArk_apiToken, groupId_list)
    
    # Save the members list in a json file to blob storage
    save_json_to_blob("CyberArkGroupMembers.json", group_members_list)

    return func.HttpResponse(
            "This HTTP triggered function executed successfully.",
            status_code=200
    )