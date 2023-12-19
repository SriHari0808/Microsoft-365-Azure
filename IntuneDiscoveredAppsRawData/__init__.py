import logging
import os
import azure.functions as func
import requests
import time
import shutil
import tempfile
from zipfile import ZipFile
from azure.storage.blob import BlobServiceClient

def get_auth_token(tenant_id, client_key, app_id):
    resource_url = "https://graph.microsoft.com"
    authority = f"https://login.windows.net/{tenant_id}/oauth2/token"
    encoded_key = requests.utils.quote(client_key)
    body = f"grant_type=client_credentials&client_id={app_id}&client_secret={encoded_key}&resource={resource_url}"

    response = requests.post(
        authority,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    response_data = response.json()
    if 'access_token' in response_data:
        return response_data['access_token']
    else:
        raise Exception("Failed to obtain access token")
    
def extract_csv_from_zip(zip_file_path, destination_path):
    with ZipFile(zip_file_path, 'r') as zip_ref:
        zip_ref.extractall(destination_path)

def upload_csv_to_blob(csv_file_path, container_name, blob_name, connection_string):
    # Create a BlobServiceClient using the connection string
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    # Get a BlobClient for the target blob
    container_client = blob_service_client.get_container_client(container_name)
    blob_client = container_client.get_blob_client(blob_name)

    # Upload the CSV file to Azure Blob Storage
    with open(csv_file_path, 'rb') as data:
        blob_client.upload_blob(data, overwrite=True)


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    tenant_id = "ENTER YOUR TENANT ID HERE"
    client_key = "ENTER YOUR CLIENT ID HERE"
    app_id = "ENTER YOUR APP ID HERE"

    # Obtain the authentication token using client credentials
    access_token = get_auth_token(tenant_id, client_key, app_id)

    # Build the JSON payload for the report request
    report_payload = {
        "reportName": "AppInvRawData",
        "localizationType": "LocalizedValuesAsAdditionalColumn"
    }

    graph_api_url = 'https://graph.microsoft.com/beta/deviceManagement/reports/exportJobs'

    # Initiate an export job and get the export job ID
    response = requests.post(
        graph_api_url,
        headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
        json=report_payload
    )
    response_data = response.json()
    export_job_id = response_data['id']

    # Get the initial status of the export job
    status_url = f"{graph_api_url}('{export_job_id}')"
    status_response = requests.get(status_url, headers={'Authorization': f'Bearer {access_token}'})
    status_data = status_response.json()
    status = status_data['status']

    # Loop until the export job is completed
    while status != 'completed':
        response = requests.get(status_url, headers={'Authorization': f'Bearer {access_token}'})
        status_data = response.json()
        status = status_data['status']
        time.sleep(2)

    # Download the ZIP file
    zip_url = status_data['url']

    temp_dir = tempfile.mkdtemp()
    zip_file_path = os.path.join(temp_dir, "intuneExport.zip")

    zip_response = requests.get(zip_url)
    with open(zip_file_path, 'wb') as zip_file:
        zip_file.write(zip_response.content)

    # Extract the CSV file from the ZIP file
    destination_path = temp_dir
    extract_csv_from_zip(zip_file_path, destination_path)

    # Identify the CSV file within the extracted folder
    csv_files = [f for f in os.listdir(destination_path) if f.endswith(".csv")]
    if csv_files:
        csv_file_name = csv_files[0]
    else:
        raise Exception("No CSV file found in the extracted folder")

    csv_file_path = os.path.join(destination_path, csv_file_name)

    connection_string = "ENTER YOUR STORAGE ACCOUNT CONNECTION STRING HERE"
    container_name = "ENTER YOUR CONTAINER NAME HERE"
    blob_name = "ENTER YOUR BLOB NAME HERE"   #example: IntuneDiscoveredAppsRawData.csv

    # Upload the CSV file to Azure Blob Storage
    upload_csv_to_blob(csv_file_path, container_name, blob_name, connection_string)

    # Clean up by removing the temporary directory and its contents
    if os.path.exists(temp_dir):
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if os.path.isfile(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        os.rmdir(temp_dir)

    return func.HttpResponse(
    f"Export completed. CSV file uploaded to Blob Storage: {blob_name}",
    status_code=200
)