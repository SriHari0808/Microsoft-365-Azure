# Input bindings are passed in via param block.
param($Timer)

# Get the current universal time in the default string format.
$currentUTCtime = (Get-Date).ToUniversalTime()

# The 'IsPastDue' property is 'true' when the current function invocation is later than scheduled.
if ($Timer.IsPastDue) {
    Write-Host "PowerShell timer is running late!"
}

# Write an information log with the current time.
Write-Host "PowerShell timer trigger function ran! TIME: $currentUTCtime"

Import-Module Az.Accounts
Import-Module Az.resources

# Define Credentials
$username = "ENTER YOUR USERNAME/MAIL ADDRESS"
$password = "ENTER YOUR PASSWORD HERE"

# Create a PSCredential object
$securePassword = ConvertTo-SecureString -String $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($username, $securePassword)

# Connect to Azure AD
Connect-AzAccount -Credential $credential

# Specify the Group Object ID
$groupA_ObjID = "ENTER YOUR GROUP 'A' OBJECT ID"
$groupB_ObjID = "ENTER YOUR GROUP 'B' OBJECT ID"
$groupC_ObjID = "ENTER YOUR GROUP 'C' OBJECT ID"
$targetGroup_ObjID = "ENTER YOUR TARGET GROUP'S OBJECT ID"

# Get the group members
$groupA_Members = Get-AzADGroupMember -GroupObjectId $groupA_ObjID 
$groupB_Members = Get-AzADGroupMember -GroupObjectId $groupB_ObjID 
$groupC_Members = Get-AzADGroupMember -GroupObjectId $groupC_ObjID 
$targetGroup_Members = Get-AzADGroupMember -GroupObjectId $targetGroup_ObjID 

# Combine members of Group A and Group B, excluding those in Group C
$newTargetGroupMembersList = ($groupA_Members + $groupB_Members) | Where-Object { $groupC_Members.ID -notcontains $_.ID }

# Add users to the Target Group if not already members
foreach($user in $newTargetGroupMembersList)
{
    if($user.ID -notin $targetGroup_Members.ID)
    {
        Add-AzADGroupMember -TargetGroupObjectId $targetGroup_ObjID -MemberObjectId $user.ID
        Write-Host "$($user.DisplayName) has been added to the Group"
    }
}

# Remove users from the Target Group if they are no longer members
foreach($user in $targetGroup_Members)
{
    if($user.ID -notin $newTargetGroupMembersList.ID)
    {
        Remove-AzADGroupMember -GroupObjectId $targetGroup_ObjID -MemberObjectId $user.ID
        Write-Host "$($user.DisplayName) has been removed from the Group"
    }
}

Write-Host "The group has been successfully updated"