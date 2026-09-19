# Despliegue del servicio de scoring en Azure Container Apps (Windows / PowerShell).
# No necesitas Docker: la imagen se construye en Azure con `az acr build`.
#
#   .\deploy\azure\deploy.ps1 -Nombre cajarural360 -Region eastus
param(
  [string]$Nombre = "cajarural360",
  [string]$Region = "eastus"
)
$ErrorActionPreference = "Stop"
$Grupo = "$Nombre-rg"
$Tag = "v" + (Get-Date -Format "yyyyMMddHHmm")

Write-Host "1/5 Grupo de recursos"
az group create -n $Grupo -l $Region -o none

Write-Host "2/5 Infraestructura (ACR, Log Analytics, Container Apps)"
az deployment group create -g $Grupo -f deploy/azure/main.bicep -p nombre=$Nombre imagenTag=$Tag -o none

$Acr = az acr list -g $Grupo --query "[0].name" -o tsv

Write-Host "3/5 Construccion de la imagen en Azure"
az acr build -r $Acr -t "$Nombre-api:$Tag" -f Dockerfile . -o none

Write-Host "4/5 Actualizacion de la aplicacion"
$Server = az acr show -n $Acr --query loginServer -o tsv
az containerapp update -n "$Nombre-api" -g $Grupo --image "$Server/$Nombre-api:$Tag" -o none

Write-Host "5/5 Verificacion"
$Fqdn = az containerapp show -n "$Nombre-api" -g $Grupo --query properties.configuration.ingress.fqdn -o tsv
Start-Sleep -Seconds 15
Write-Host "Servicio publicado: https://$Fqdn"
Write-Host "  Interfaz:      https://$Fqdn/"
Write-Host "  Documentacion: https://$Fqdn/docs"
Write-Host "  Para borrarlo:  az group delete -n $Grupo --yes --no-wait"
