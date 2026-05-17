$raw = [Console]::In.ReadToEnd()
try {
    $data = $raw | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Output '{}'
    exit 0
}

$editTools = @(
    'replace_string_in_file',
    'multi_replace_string_in_file',
    'create_file'
)

$filePath = $data.toolInput.filePath
$toolName = $data.toolName

if ($toolName -in $editTools -and $filePath -match '(trading_bot[\\/]|trading_ui[\\/]src|llm_training[\\/])') {
    $msg = 'Code changed. Run /sync-docs to keep .github/instructions/ up to date.'
    Write-Output "{`"systemMessage`": `"$msg`"}"
} else {
    Write-Output '{}'
}
exit 0
