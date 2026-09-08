param(
    [Parameter(Mandatory=$true)][string]$GroundTruth,
    [Parameter(Mandatory=$true)][string]$PredictionDir,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [string]$SourceRoot = '',
    [string]$Image = 'ghcr.io/zeng-weijun/omnidocbench-eval@sha256:6116ad72172e763b5c43e963d5efebf2093f2362b975f58156ce4f6c9142e617',
    [int]$Workers = 4
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Get-Location).Path
if ($SourceRoot) { $repoRoot = (Resolve-Path -LiteralPath $SourceRoot).Path }
$gtPath = (Resolve-Path -LiteralPath $GroundTruth).Path
$predPath = (Resolve-Path -LiteralPath $PredictionDir).Path
$pages = Get-Content -LiteralPath $gtPath -Raw -Encoding utf8 | ConvertFrom-Json
$expected = @($pages | ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_.page_info.image_path) + '.md' })
$actual = @(Get-ChildItem -LiteralPath $predPath -File -Filter '*.md' | ForEach-Object Name)
if ($expected.Count -ne $actual.Count -or @(Compare-Object $expected $actual).Count -gt 0) {
    throw "Predictions do not match GT page set: expected=$($expected.Count) actual=$($actual.Count)"
}
if (Test-Path -LiteralPath $OutputDir) { throw 'Evaluation output already exists. Use a new directory.' }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$outPath = (Resolve-Path -LiteralPath $OutputDir).Path
$imageId = docker image inspect $Image --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Evaluation image is not available' }
$config = @{
    end2end_eval = @{
        metrics = @{
            text_block = @{metric=@('Edit_dist')}
            display_formula = @{metric=@('Edit_dist','CDM'); cdm_workers=$Workers}
            table = @{metric=@('TEDS','Edit_dist'); teds_workers=$Workers}
            reading_order = @{metric=@('Edit_dist')}
        }
        dataset = @{
            dataset_name='end2end_dataset'
            ground_truth=@{data_path='/workspace/gt/OmniDocBench.json'}
            prediction=@{data_path='/workspace/data_md/predictions'}
            match_method='quick_match'; match_workers=$Workers
            quick_match_truncated_timeout_sec=300; match_timeout_sec=420
            timeout_fallback_max_chunk_span=10; timeout_fallback_order_penalty=0.10
        }
    }
}
$configPath = Join-Path $outPath 'config.json'
$config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $configPath -Encoding utf8
$binding = @{
    image_id=$imageId; source_commit=(git rev-parse HEAD)
    gt_sha256=(Get-FileHash -LiteralPath $gtPath -Algorithm SHA256).Hash
    prediction_pages=$actual.Count
    empty_predictions=@(Get-ChildItem -LiteralPath $predPath -File -Filter '*.md' | Where-Object Length -eq 0).Count
    workers=$Workers
}
$binding | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $outPath 'evaluation-binding.json') -Encoding utf8
$dockerArgs = @('run','--rm','--entrypoint','bash','--workdir','/workspace',
    '-e','PYTHONPATH=/workspace','-e','PYTHONUNBUFFERED=1',
    '-v',"${gtPath}:/workspace/gt/OmniDocBench.json:ro",
    '-v',"${predPath}:/workspace/data_md/predictions:ro",
    '-v',"${outPath}:/workspace/result",
    '-v',"${configPath}:/workspace/configs/benchmark.json:ro",
    '-v',"${repoRoot}/src:/workspace/src:ro",
    '-v',"${repoRoot}/metrics:/workspace/metrics:ro",
    '-v',"${repoRoot}/pdf_validation.py:/workspace/pdf_validation.py:ro",
    $imageId,'-lc','python pdf_validation.py --config configs/benchmark.json')
$dockerArgs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outPath 'docker-args.json') -Encoding utf8
# Windows PowerShell 5 treats native stderr progress lines as errors under Stop.
# Capture the actual native exit code and preserve both streams independently.
$priorPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & docker @dockerArgs 1> (Join-Path $outPath 'eval.log') 2> (Join-Path $outPath 'eval.stderr.log')
    $evaluationExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $priorPreference
}
if ($evaluationExitCode -ne 0) { throw "Evaluation failed; see $outPath/eval.log and eval.stderr.log" }
Write-Output "EVALUATION_COMPLETE=$outPath"
