$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$questionsPath = Join-Path $root "geoquerybench_v0.1\questions\geoquerybench_questions_EN.csv"
$logDir = Join-Path $root "validation_batch_logs"
$summaryPath = Join-Path $root "validation_batch_summary.csv"
$env:PYTHONIOENCODING = "utf-8"

$ids = @(
    "CD1-016", "CD1-017", "CD1-023", "CD1-024", "CD1-026", "CD1-029", "CD1-036", "CD1-038", "CD1-043",
    "CD2-021", "CD2-028", "CD2-031", "CD2-034", "CD2-037", "CD2-047", "CD2-050",
    "CD3-022", "CD3-031", "CD3-036", "CD3-039", "CD3-046", "CD3-049", "CD3-050", "CD3-051",
    "CD4-017", "CD4-022", "CD4-029", "CD4-032", "CD4-039", "CD4-044", "CD4-048", "CD4-051",
    "NS1-019", "NS1-023", "NS1-026", "NS1-034", "NS1-041", "NS1-045",
    "NS2-017", "NS2-021", "NS2-029", "NS2-032", "NS2-039", "NS2-042", "NS2-046", "NS2-050", "NS2-052", "NS2-053",
    "NS3-022", "NS3-026", "NS3-027", "NS3-038", "NS3-041", "NS3-049",
    "NS4-019", "NS4-028", "NS4-036", "NS4-038", "NS4-042", "NS4-046", "NS4-047", "NS4-049",
    "NS5-019", "NS5-020", "NS5-031", "NS5-034", "NS5-049", "NS5-051", "NS5-052", "NS5-054"
)

$validatorByTask = @{
    sql = "validate_sql.py"
    python = "validate_python.py"
    geopandas = "validate_geopandas.py"
    viz = "validate_viz.py"
    refusal = "validate_refusal.py"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$questions = Import-Csv $questionsPath
$results = [System.Collections.Generic.List[object]]::new()

foreach ($qid in $ids) {
    $question = $questions | Where-Object { $_.qid -eq $qid }
    $started = Get-Date

    if ($null -eq $question) {
        $results.Add([pscustomobject]@{ qid = $qid; task = ""; validator = ""; exit_code = 2; status = "MISSING_QUESTION"; output_file = "" })
        continue
    }

    $validatorName = $validatorByTask[$question.task]
    $logPath = Join-Path $logDir "$qid.log"

    if ($null -eq $validatorName) {
        "Unsupported task: $($question.task)" | Set-Content $logPath
        $results.Add([pscustomobject]@{ qid = $qid; task = $question.task; validator = ""; exit_code = 2; status = "UNSUPPORTED_TASK"; output_file = "" })
        continue
    }

    $validatorPath = Join-Path $root "manual_validation\$validatorName"
    $temporaryLogPath = Join-Path $env:TEMP "$qid-validation.log"
    & python $validatorPath $qid *> $temporaryLogPath
    $exitCode = $LASTEXITCODE
    Copy-Item $temporaryLogPath $logPath -Force
    Remove-Item $temporaryLogPath -Force -ErrorAction SilentlyContinue

    $expectedExtension = if ($question.task -eq "viz") { "png" } elseif ($question.task -eq "refusal") { "txt" } else { "csv" }
    $outputPath = Join-Path $root "validation_results\${qid}_rerun.$expectedExtension"
    $status = if ($exitCode -eq 0) { "PASS_EXECUTION" } else { "FAILED_EXECUTION" }

    $results.Add([pscustomobject]@{
        qid = $qid
        scenario = $question.scenario
        task = $question.task
        validator = $validatorName
        exit_code = $exitCode
        status = $status
        output_file = if (Test-Path $outputPath) { $outputPath } else { "" }
        duration_seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    })
}

$results | Export-Csv -NoTypeInformation -Path $summaryPath
$results | Group-Object status | Select-Object Name, Count | Format-Table -AutoSize
Write-Host "Summary: $summaryPath"
Write-Host "Logs:    $logDir"
