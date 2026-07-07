$env:DEER_FLOW_PROJECT_ROOT = "d:\AOS\external\deer-flow"
$env:DEER_FLOW_HOME = "d:\AOS\external\deer-flow\.deer-flow"
$env:DEER_FLOW_CONFIG_PATH = "d:\AOS\external\deer-flow\config.yaml"
$env:DEER_FLOW_EXTENSIONS_CONFIG_PATH = "d:\AOS\external\deer-flow\extensions_config.json"
$env:DEER_FLOW_SKILLS_PATH = "d:\AOS\external\deer-flow\skills"
$env:DEER_FLOW_REPO_ROOT = "d:\AOS\external\deer-flow"
$env:DEER_FLOW_AUTH_DISABLED = "1"
$env:BETTER_AUTH_SECRET = "deerflow-secret-key-12345"
$env:DEER_FLOW_INTERNAL_AUTH_TOKEN = "internal-token-12345"
$env:PORT = "2026"

Write-Host "Starting DeerFlow with Docker..."
Write-Host "Project Root: $($env:DEER_FLOW_PROJECT_ROOT)"
Write-Host "Config Path: $($env:DEER_FLOW_CONFIG_PATH)"

Set-Location "d:\AOS\external\deer-flow"
docker-compose -f docker/docker-compose.yaml up -d
