#!/usr/bin/env bash
# Despliegue del servicio de scoring en Azure Container Apps.
# No necesitas Docker instalado: la imagen se construye en Azure con `az acr build`.
#
#   bash deploy/azure/deploy.sh [nombre] [region]
set -euo pipefail

NOMBRE="${1:-cajarural360}"
REGION="${2:-eastus}"
GRUPO="${NOMBRE}-rg"
TAG="v$(date +%Y%m%d%H%M)"

echo "▶ 1/5 Grupo de recursos"
az group create -n "$GRUPO" -l "$REGION" -o none

echo "▶ 2/5 Infraestructura (ACR, Log Analytics, Container Apps)"
az deployment group create -g "$GRUPO" -f deploy/azure/main.bicep \
  -p nombre="$NOMBRE" imagenTag="$TAG" -o none

ACR=$(az acr list -g "$GRUPO" --query "[0].name" -o tsv)

echo "▶ 3/5 Construcción de la imagen en Azure (sin Docker local)"
az acr build -r "$ACR" -t "${NOMBRE}-api:${TAG}" -f Dockerfile . -o none

echo "▶ 4/5 Actualización de la aplicación a la imagen nueva"
az containerapp update -n "${NOMBRE}-api" -g "$GRUPO" \
  --image "$(az acr show -n "$ACR" --query loginServer -o tsv)/${NOMBRE}-api:${TAG}" -o none

echo "▶ 5/5 Verificación"
URL="https://$(az containerapp show -n "${NOMBRE}-api" -g "$GRUPO" --query properties.configuration.ingress.fqdn -o tsv)"
sleep 15
curl -sf "${URL}/health" | head -c 400 || echo "(el primer arranque puede tardar; reintenta en un minuto)"
echo
echo "✓ Servicio publicado: ${URL}"
echo "  Interfaz:      ${URL}/"
echo "  Documentación: ${URL}/docs"
echo "  Para borrarlo todo:  az group delete -n ${GRUPO} --yes --no-wait"
