// Infraestructura mínima para publicar el servicio de scoring en Azure Container Apps.
// Despliegue:  az deployment group create -g <grupo> -f main.bicep -p nombre=cajarural360
@description('Prefijo para los recursos (minúsculas, sin espacios)')
param nombre string = 'cajarural360'

@description('Región de Azure')
param ubicacion string = resourceGroup().location

@description('Etiqueta de la imagen en el Container Registry')
param imagenTag string = 'v1'

var acrNombre = toLower('${nombre}acr')
var entornoNombre = '${nombre}-env'
var appNombre = '${nombre}-api'
var logsNombre = '${nombre}-logs'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrNombre
  location: ubicacion
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logsNombre
  location: ubicacion
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource entorno 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: entornoNombre
  location: ubicacion
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appNombre
  location: ubicacion
  properties: {
    managedEnvironmentId: entorno.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      registries: [ { server: acr.properties.loginServer, username: acr.listCredentials().username, passwordSecretRef: 'acr-password' } ]
      secrets: [ { name: 'acr-password', value: acr.listCredentials().passwords[0].value } ]
    }
    template: {
      containers: [
        {
          name: 'scoring'
          image: '${acr.properties.loginServer}/${nombre}-api:${imagenTag}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 20, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 10 }
          ]
        }
      ]
      // Escala a cero cuando no hay tráfico: en originación el consumo es por ráfagas
      scale: { minReplicas: 0, maxReplicas: 3, rules: [ { name: 'http', http: { metadata: { concurrentRequests: '50' } } } ] }
    }
  }
}

output urlDelServicio string = 'https://${app.properties.configuration.ingress.fqdn}'
output registry string = acr.properties.loginServer
