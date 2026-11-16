param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint,
    [Parameter(Mandatory=$true)][string]$SignTool,
    [string]$TimestampUrl
)
$ErrorActionPreference='Stop'
$resolvedExecutable=(Resolve-Path -LiteralPath $Executable).Path
$resolvedSignTool=(Resolve-Path -LiteralPath $SignTool).Path
if ([IO.Path]::GetExtension($resolvedExecutable) -ne '.exe') { throw 'Select the final packaged Windows EXE.' }
$thumbprint=$CertificateThumbprint.Replace(' ','')
if ($thumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Use the legitimate certificate thumbprint from the Windows certificate store.' }
# Certificate private keys remain in the Windows certificate store/HSM.
# No PFX password or private key is accepted on the command line or in Git.
$signArguments=@('sign','/sha1',$thumbprint,'/fd','SHA256')
if ($TimestampUrl) { $signArguments+=@('/tr',$TimestampUrl,'/td','SHA256') }
$signArguments+=$resolvedExecutable
& $resolvedSignTool @signArguments
if ($LASTEXITCODE -ne 0) { throw 'Authenticode signing failed; do not distribute this release as signed.' }
& $resolvedSignTool verify /pa /v $resolvedExecutable
if ($LASTEXITCODE -ne 0) { throw 'Authenticode verification failed.' }
Write-Output 'Signature verified. Regenerate/sign the external release manifest AFTER this step.'
