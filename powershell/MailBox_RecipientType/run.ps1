# Input bindings are passed in via param block.
param($Timer)

# Get the current universal time in the default string format.
$currentUTCtime = (Get-Date).ToUniversalTime()

# The 'IsPastDue' property is 'true' when the current function invocation is later than scheduled.
if ($Timer.IsPastDue) {
    Write-Host "PowerShell timer is running late!"
}

# Write an information log with the current time.
Write-Host "MailBox_RecipientType timer trigger function ran! TIME: $currentUTCtime"

Import-Module ExchangeOnlineManagement
Import-Module Az.Accounts.psd1
Import-Module Az.Storage.psd1

# Define Credentials
$username = "ENTER YOUR USERNAME/MAIL ADDRESS"
$password = "ENTER YOUR PASSWORD HERE"

# Create a PSCredential object
$securePassword = ConvertTo-SecureString -String $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($username, $securePassword)

Connect-ExchangeOnline -Credential $credential

$mailboxList = Get-Mailbox -ResultSize unlimited | Select-Object Name, primarysmtpaddress, recipienttypedetails 

# Convert the mailbox list to CSV and save it to a temporary file
$tempFile = New-TemporaryFile
$mailboxList | ConvertTo-Csv -NoTypeInformation | Out-File -FilePath $tempFile.FullName

Disconnect-ExchangeOnline -Confirm:$false

Connect-AzAccount -Credential $credential

$storageConnectionString = "ENTER YOUR STORAGE ACCOUNT CONNECTION STRING HERE"
$containerName = "ENTER YOUR CONTAINER NAME HERE"
$blobName = "ENTER YOUR BLOB NAME HERE"   #example: "MailBox_RecipientType.Csv"

$storageContext = (New-AzStorageContext -ConnectionString $storageConnectionString)

# Upload the content of the temporary file to Azure Storage
Set-AzStorageBlobContent -Context $storageContext -Container $containerName -Blob $blobName -BlobType Block -Force -File $tempFile.FullName

# Remove the temporary file
Remove-Item $tempFile.FullName

Disconnect-AzAccount 