# Reporte: Arquitectura Serverless para Ingesta de Telemetría desde Aplicaciones Móviles

**Fecha:** 20 de Marzo de 2026  
**Ubicación:** Buenos Aires, Argentina  
**Contexto:** Ingesta de datos de telemetría desde miles de teléfonos móviles hacia AWS Lambda

---

## 1. Problema Inicial

Se requiere construir una arquitectura escalable para enviar datos de telemetría continua desde **miles de dispositivos móviles** hacia un pool de funciones AWS Lambda. Los datos incluyen:

- Coordenadas GPS en tiempo real
- Velocidad actual y límite de velocidad
- Puntuaciones de seguridad (aceleración, frenado, etc.)
- Timestamps de alta precisión

**Volumen:** Potencialmente cientos de miles de mensajes por segundo desde aplicaciones React Native en teléfonos repartidos geográficamente.

**Payload típico:** Entre 100 KB y 150 KB por batch.

---

## 2. Análisis de Protocolos: HTTP, REST y WebSocket

### 2.1 HTTP y REST - Problemas de Overhead


| Aspecto                 | Impacto                                                                                                                             | Magnitud                        |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Handshake TCP + TLS** | Se requiere en cada conexión nueva (móviles pierden cobertura frecuentemente y el flujo de mensajes es intrínsecamente discontínuo) | +200-500ms de latencia          |
| **Headers HTTP**        | Para un payload de 50 bytes, los headers pueden exceder 500 bytes                                                                   | 10x más datos de los necesarios |
| **Consumo de batería**  | Conectar/reconectar drena recursos del dispositivo rápidamente                                                                      | Impacto significativo en UX     |
| **Datos móviles**       | Overhead afecta el plan de datos del usuario                                                                                        | Mala experiencia de usuario     |


**Conclusión:** HTTP/REST no son ideales para aplicaciones de telemetría continua en móviles.

### 2.2 WebSocket - Mejora pero con costo

**Ventajas:**

- Conexión persistente bidireccional
- Overhead por mensaje mínimo después del upgrade inicial

**Desventajas:**

- **Costo de conexión abierta:** AWS API Gateway cobra por minuto de conexión abierta
- **Complejidad de reconexión:** Móviles en redes inestables necesitan lógica de reintento
- **Gestión de estado:** Difícil mantener estado de miles de conexiones abiertas

**Conclusión:** WebSocket es viable pero costoso para este caso de uso.

---

## 3. Solución Recomendada: AWS IoT Core + MQTT

### 3.1 ¿Por qué MQTT?

MQTT es el protocolo estándar de la industria IoT, diseñado específicamente para dispositivos en redes inestables:

```text
╔════════════════════════════════════════════════════════════════╗
║                  Comparativa de Protocolos                     ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  HTTP/REST:                                                    ║
║  ├─ Overhead de headers: 500+ bytes                            ║
║  ├─ Handshake por mensaje: SÍ                                  ║
║  └─ Adecuado para: APIs tradicionales, webhooks                ║
║                                                                ║
║  WebSocket:                                                    ║
║  ├─ Overhead de headers: ~2-10 bytes (después del upgrade)     ║
║  ├─ Handshake por mensaje: NO (reutiliza conexión)             ║
║  ├─ Costo de conexión abierta: ALTO (por minuto)               ║
║  └─ Adecuado para: Chats, dashboards en tiempo real            ║
║                                                                ║
║  MQTT:                                                         ║
║  ├─ Overhead de headers: 2 bytes por mensaje (mínimo)          ║
║  ├─ Conexión persistente: SÍ (manejo automático de drops)      ║
║  ├─ QoS (Quality of Service): Garantías de entrega             ║
║  ├─ Costo: Basado en mensajes, no en tiempo de conexión        ║
║  └─ Adecuado para: IoT, telemetría continua, movilidad         ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

### 3.2 Límites de Tamaño en AWS

Antes de recomendar MQTT, debe considerarse el tamaño del payload:


| Servicio            | Límite Máximo                   | Notas                                    |
| ------------------- | ------------------------------- | ---------------------------------------- |
| AWS IoT Core (MQTT) | 128 KB                          | Hard limit por mensaje                   |
| API Gateway (HTTP)  | 10 MB                           | Soporta payloads grandes                 |
| API Gateway (REST)  | Configurable, típicamente 10 MB |                                          |
| AWS Lambda          | 6 MB                            | Si se invoca directamente                |
| Amazon SQS          | 256 KB                          | Nativo; se puede usar S3 Extended Client |


**Tu caso:** 145 KB > 128 KB del MQTT limit

**Solución:** Comprimir el payload con GZIP o Zstandard (reduce ~145 KB a ~10-15 KB)

---

## 4. Arquitectura Serverless Propuesta

```text
┌──────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA COMPLETA                         │
└──────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────┐
                    │   Smartphone 1      │
                    │  (React Native)     │
                    │  ┌───────────────┐  │
                    │  │ MQTT Client   │  │
                    │  │ (Paho/MQTT.js)│  │
                    │  │ Certificado   │  │
                    │  └───────────────┘  │
                    └──────────┬──────────┘
                               │ TCP:8883
                               │ TLS
                               │
        ┌──────────────────────┴──────────────────────┐
        │                                             │
        │  Smartphone 2, 3, 4, ... 1000s              │
        │  (Todos con MQTT Client)                    │
        │                                             │
        └──────────────────────┬──────────────────────┘
                               │
                               ▼
                ┌────────────────────────────┐
                │   AWS IoT Core             │
                │  (MQTT Broker Gestionado)  │
                │                            │
                │  Endpoint:                 │
                │  abc12345.iot.us-east-1    │
                │  .amazonaws.com            │
                └────────────────────────────┘
                          │
                          │ Regla IoT
                          │ SELECT * FROM
                          │ 'telemetry/#'
                          │
                          ▼
                ┌────────────────────────────┐
                │   IoT Rules Engine         │
                │                            │
                │  Acción: Enviar a SQS      │
                └────────────────────────────┘
                          │
                          ▼
              ┌──────────────────────────┐
              │  Amazon SQS Queue        │
              │  (Standard o FIFO)       │
              │                          │
              │ Rol: Buffer de ingesta   │
              │ Mejora confiabilidad     │
              │ Desacopla Lambda         │
              └──────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │  Pool de Lambda Functions           │
        │  (Procesamiento en paralelo)        │
        │                                     │
        │  ┌──────────────┐                   │
        │  │ Lambda-1     │                   │
        │  │ Procesa 10   │                   │
        │  │ mensajes     │                   │
        │  └──────────────┘                   │
        │                                     │
        │  ┌──────────────┐                   │
        │  │ Lambda-2     │                   │
        │  │ Procesa 10   │                   │
        │  │ mensajes     │                   │
        │  └──────────────┘                   │
        │                                     │
        │  ┌──────────────┐                   │
        │  │ Lambda-N     │                   │
        │  │ ...          │                   │
        │  └──────────────┘                   │
        │                                     │
        └─────────────────────────────────────┘
                          │
                          ▼
              ┌──────────────────────────┐
              │  Base de Datos           │
              │  (RDS/DynamoDB)          │
              │  o                       │
              │  S3 (Lake)               │
              └──────────────────────────┘
```

---

## 5. Componentes de la Arquitectura

### 5.1 Cliente MQTT en React Native

**Librerías recomendadas:**

1. **sp-react-native-mqtt** (RECOMENDADA para tu caso)
  ```javascript
   // Usa backend nativo (CocoaMQTT en iOS, Paho Java en Android)
   // - Soporta TCP puro en puerto 8883 (mejor que WebSocket)
   // - Manejo robusto de desconexiones de red
   // - Funciona en background (crucial para telemetría)
   // - Comprime y envía batches de waypoints
  ```
2. **mqtt.js** (alternativa, más moderna)
  ```javascript
   // WebSocket basado, más ligero pero menos robusto en background
  ```
3. **react-native-paho-mqtt** (Eclipse Paho)
  ```javascript
   // Confiable, muy documentado, WebSocket compatible
  ```

### 5.2 AWS IoT Core - El Broker MQTT Gestionado

**No necesitas desarrollar ni mantener un servidor MQTT.** AWS proporciona un endpoint MQTT totalmente escalable:

- **Endpoint:** `{device-id}.iot.{region}.amazonaws.com:8883`
- **Escalabilidad:** Maneja millones de conexiones simultáneas
- **Seguridad:** Autenticación con certificados X.509
- **Costo:** Basado en mensajes publicados/suscritos

**Autenticación (para React Native):**

```text
┌─────────────────────────────────────────────────────┐
│     Opciones de Autenticación en IoT Core           │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 1. CERTIFICADOS X.509 (RECOMENDADO)                 │
│    ├─ Cada dispositivo: certificado + clave privada │
│    ├─ Almacenar en Keychain (iOS) o Keystore (And)  │
│    ├─ AWS genera o traes tu propia CA               │
│    └─ Seguridad: Excelente                          │
│                                                     │
│ 2. AMAZON COGNITO (para desarrollo)                 │
│    ├─ Usuario/contraseña + sesión                   │
│    ├─ Más fácil de implementar inicialmente          │
│    ├─ Preocupaciones de escala en prod              │
│    └─ Seguridad: Buena                              │
│                                                     │
│ 3. AUTORIZACIÓN PERSONALIZADA (Custom Authorizer)   │
│    ├─ Token bearer personalizado                    │
│    ├─ Útil para migrar sistemas existentes          │
│    └─ Requiere Lambda para validar tokens           │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 5.3 IoT Rules Engine

**¿Qué hace?** Inspecciona mensajes MQTT y los enruta automáticamente.

```sql
-- Regla SQL en AWS IoT Core
SELECT *
FROM 'telemetry/+/waypoints'
WHERE speed > 0
```

**Acciones disponibles:**

- Enviar a SQS ✓ (nuestra solución)
- Enviar a Kinesis
- Invocar Lambda
- Almacenar en S3
- Almacenar en DynamoDB
- Publicar en SNS

### 5.4 Amazon SQS - Buffer Confiable

**¿Por qué SQS?**

```text
Patrón sin SQS (acoplado):
  MQTT → Invoke Lambda
  
  Problema: Si Lambda está saturado o se reinicia,
  los mensajes MQTT que llegan se pierden

Patrón con SQS (desacoplado):
  MQTT → (IoT Rule) → SQS → Poll Lambda
  
  Ventaja: SQS almacena mensajes temporalmente.
  Lambda procesa a su propio ritmo.
  Confiabilidad: 99.99%
```

**Opciones:**

- **Standard Queue:** Best effort, ordena aproximadamente (cheaper)
- **FIFO Queue:** Estricto orden FIFO, deduplicación automática

Si necesitas **garantías de orden temporal** para los eventos:

```text
FIFO será necesario, pero:
- Throughput máximo: 300 mensajes/segundo (batch)
- Costo ligeramente mayor
- Debes proporcionar: MessageGroupId (ej: deviceId)

El IoT Rule action configurable para incluir
el device ID como group ID automáticamente.
```

### 5.5 AWS Lambda - Procesamiento

```text
Configuración recomendada:

┌─────────────────────────────────────┐
│ Lambda Function (Event Processor)   │
├─────────────────────────────────────┤
│ Trigger: SQS (Batch de 10-100)      │
│ Timeout: 60 segundos                │
│ Memory: 512 MB mínimo               │
│ Concurrencia Reservada: 100-500     │
│                                     │
│ Código:                             │
│ 1. Deserializa mensaje (JSON)       │
│ 2. Valida campos                    │
│ 3. Transforma si es necesario       │
│ 4. Inserta en BD o S3               │
│ 5. Retorna ACK a SQS                │
│                                     │
│ Escala automáticamente si la cola   │
│ crece → más Lambdas en paralelo     │
└─────────────────────────────────────┘
```

---

## 6. Flujo de Datos Completo

```text
PASO 1: CAPTURA EN DISPOSITIVO
────────────────────────────────
Cuando se dispara un listener:
  └─► Comprimir JSON a GZIP
  └─► Publicar a MQTT topic "telemetry/{deviceId}/waypoints"


PASO 2: TRANSMISIÓN MQTT
────────────────────────
React Native app → MQTT Client
  ├─ Autenticación: certificado X.509
  ├─ Conexión TLS al endpoint IoT Core
  ├─ Publica payload comprimido (~15 KB)
  ├─ IoT Core recibe el mensaje
  └─ Reconexión automática si la red cae


PASO 3: RUTEO CON IOT RULES ENGINE
───────────────────────────────────
IoT Core Rule ejecuta SQL:
  SELECT * FROM 'telemetry/+/waypoints'

Acción configurada:
  └─► Enviar mensaje a SQS queue


PASO 4: ALMACENAMIENTO EN SQS
─────────────────────────────
SQS recibe y almacena el mensaje:
  ├─ Retiene por 14 días (default)
  ├─ Replica a 3 AZs para durabilidad
  ├─ Visibilidad: Invisible mientras Lambda procesa
  └─ Si Lambda falla → mensaje vuelve a la cola


PASO 5: PROCESAMIENTO POR LAMBDA
─────────────────────────────────
SQS dispara Lambda (cuando hay mensajes):
  ├─ Batch de 10 mensajes por invocación
  ├─ Lambda descomprime el payload
  ├─ Valida e integra datos
  ├─ Escribe a base de datos
  ├─ Si éxito → confirma a SQS (delete)
  └─ Si error → mensaje reentra a cola


PASO 6: ALMACENAMIENTO PERSISTENTE
──────────────────────────────────
Datos en BD / Data Lake:
  ├─ Disponibles para análisis
  ├─ Trazabilidad histórica
  ├─ Integraciones downstream (BI, ML)
  └─ Consultas en tiempo real
```

---

## 7. Comparativa: HTTP/REST vs MQTT

```text
┌─────────────────────────────────────────────────────────────┐
│              COMPARATIVA FINAL                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ MÉTRICA                HTTP/REST          MQTT              │
│ ─────────────────────────────────────────────────────────── │
│ Overhead/msg           500-1000 bytes     2-10 bytes        │
│ Manejo de caídas       Manual+reintento   Automático        │
│ Persistencia msg       NO (timeout)       SÍ (QoS niveles)  │
│ Costo conexión         Por request        Por mensaje       │
│ Consumo batería        ALTO               BAJO              │
│ Concurrencia           Difícil >1000      Nativa >1M        │
│ Background (iOS/And)   Limitado           Bueno             │
│ Compresión             Necesaria          Recomendada       │
│ Escalabilidad          Media (API Gw)     Excelente (IoT)   │
│ Latencia               100-500 ms         10-50 ms          │
│                                                             │
│ RECOMENDACIÓN: ► MQTT + AWS IoT Core ◄                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Checklist de Implementación

### Fase 1: Preparación (Semana 1)

- [ ] Crear política IAM para dispositivos
- [ ] Generar certificados X.509 para dispositivos
  - [ ] Crear/usar AWS IoT CA
  - [ ] Emitir certificado por dispositivo
  - [ ] Distribuir certificados a app
- [ ] Crear Thing Resource en AWS IoT Core por dispositivo
- [ ] Preparar política IoT Core (permisos: publish/subscribe)

### Fase 2: Backend AWS (Semana 2)

- [ ] Crear SQS Queue (standard o FIFO según necesidad)
- [ ] Crear Regla IoT para rutear MQTT → SQS
  - [ ] Configurar SQL query
  - [ ] Asignar acción SQS
  - [ ] Crear IAM role para la regla
- [ ] Crear Lambda function para procesar mensajes
  - [ ] Trigger: SQS (batch 10-50)
  - [ ] Código: descomprimir, validar, escribir BD
  - [ ] Testing con mensajes simulados

### Fase 3: Cliente React Native (Semana 2-3)

- [ ] Instalar librería MQTT (sp-react-native-mqtt recomendado)
- [ ] Integrar certificados en app
  - [ ] Almacenar en Keychain/Keystore
  - [ ] Cargar en tiempo de inicialización
- [ ] Implementar cliente MQTT
  - [ ] Conectar al endpoint IoT Core
  - [ ] Manejar reconexiones
  - [ ] Implementar QoS 1 o 2 si es crítico
- [ ] Agregar compresión GZIP antes de publicar
- [ ] Testing en dispositivo real (conectado/desconectado)

### Fase 4: Testing & Monitoreo (Semana 4)

- [ ] Load testing: simular 1000+ dispositivos concurrentes
- [ ] Verificar latencia end-to-end
- [ ] Monitoring: CloudWatch logs, SQS metrics, Lambda duration
- [ ] Alertas: SQS queue depth, Lambda errors
- [ ] Rollout gradual: 1% → 10% → 100% de dispositivos

---

## 9. Estimaciones de Costo (USD/mes)

Asumiendo **10,000 dispositivos** enviando datos cada 15 minutos:

```text
CÁLCULO:
- 10,000 dispositivos
- 1 mensaje MQTT cada 15 minutos
- 96 mensajes/dispositivo/día
- 960,000 mensajes/día totales

DESGLOSE DE COSTOS:

AWS IoT Core (MQTT Publish):
  960,000 msgs/día × 30 días = 28,800,000 msgs/mes
  Precio: $1.00 por millón de mensajes
  Costo: 28,800,000 / 1,000,000 × $1 = $28.80

Amazon SQS:
  28,800,000 requests
  Free tier: 1 millón gratis
  28,800,000 - 1,000,000 = 27,800,000 billables
  Precio: $0.40 por millón
  Costo: 27,800,000 / 1,000,000 × $0.40 = $11.20

AWS Lambda:
  28,800,000 invocations (1 por mensaje)
  Duración promedio: 100 ms
  Memory: 512 MB
  
  Free tier: 1 millón gratis
  Billable: 27,800,000 invocations
  Precio: $0.0000002 por ms + $0.20 por millón
  Cálculo: (27,800,000 × 100 ms × 512 MB / 1024) × $0.0000002
         + (27,800,000 / 1,000,000) × $0.20
         = ~$2.50 + $5.56 = $8.06

Data Transfer:
  Asumiendo < 1 GB/mes saliendo de AWS
  Costo: $0 (primer 1 GB gratis)

═════════════════════════════════════════
COSTO TOTAL ESTIMADO: ~$48-60 USD/mes
═════════════════════════════════════════
```

**Nota:** Este es un costo muy bajo para la escala. A medida que crece:

```text
Escala          Costo Mensual
────────────────────────────
10k devices     ~$50
100k devices    ~$500
1M devices      ~$5,000
```

---

## 10. Consideraciones de Seguridad

### 10.1 Autenticación

```text
┌──────────────────────────────────────────────────┐
│         Certificado X.509 en Dispositivo         │
├──────────────────────────────────────────────────┤
│                                                  │
│ 1. AWS IoT genera el certificado                 │
│                                                  │
│ 2. Se almacena en:                               │
│    ├─ iOS: Keychain (cifrado por SO)             │
│    └─ Android: Keystore (cifrado por SO)         │
│                                                  │
│ 3. App carga certificado en memoria en startup   │
│                                                  │
│ 4. TLS mutual authentication:                    │
│    ├─ Dispositivo verifica certificado AWS       │
│    └─ AWS verifica certificado del dispositivo   │
│                                                  │
│ 5. Comunicación cifrada (TLS 1.2+)               │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 10.2 Autorización

- **Política IoT Core:** Cada certificado solo puede publicar en su propio topic
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "iot:Publish",
        "Resource": "arn:aws:iot:*:*:topicfilter/telemetry/${iot:Connection.Thing.ThingName}/*"
      }
    ]
  }
  ```

### 10.3 Rotación de Certificados

```text
Periódicamente (cada 2-3 años):
  1. Generar nuevo certificado
  2. Distribuir OTA a dispositivos
  3. Deactivar certificado antiguo
  4. Después de período de gracia: eliminar
```

---

## 11. Próximos Pasos Recomendados

1. **Crear AWS IoT Core CA y emitir primeros certificados**
  - Testing con 10-50 dispositivos piloto
2. **Instalar sp-react-native-mqtt en tu app React Native**
  - Integrar certificados
  - Implementar publish/subscribe
3. **Configurar IoT Rule para rutear → SQS**
  - Testing manual con CLI mosquitto_pub
4. **Crear Lambda que procese SQS messages**
  - Deserializar, validar, escribir BD
5. **Load testing antes de production rollout**
  - Verificar scaling automático
  - Confirmar latencias end-to-end
6. **Monitoreo y alertas en CloudWatch**
  - Queue depth SQS
  - Lambda error rate
  - Latencias

---

## 12. Referencias y Documentación

### AWS Oficial

- **AWS IoT Core:** [https://docs.aws.amazon.com/iot/](https://docs.aws.amazon.com/iot/)
- **SQS:** [https://docs.aws.amazon.com/sqs/](https://docs.aws.amazon.com/sqs/)
- **Lambda:** [https://docs.aws.amazon.com/lambda/](https://docs.aws.amazon.com/lambda/)
- **IoT Rules:** [https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)

### Librerías MQTT React Native

- **sp-react-native-mqtt:** [https://www.npmjs.com/package/sp-react-native-mqtt](https://www.npmjs.com/package/sp-react-native-mqtt)
- **mqtt.js:** [https://github.com/mqttjs/MQTT.js](https://github.com/mqttjs/MQTT.js)
- **react-native-paho-mqtt:** [https://www.npmjs.com/package/react-native-paho-mqtt](https://www.npmjs.com/package/react-native-paho-mqtt)

### Protocolos IoT

- **MQTT 3.1.1 Spec:** [http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html](http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html)
- **MQTT sobre WebSocket:** RFC 6455

---

## Conclusión

La arquitectura recomendada es:

**React Native App → MQTT/IoT Core → SQS → Lambda → Base de Datos**

Esta solución:  
✓ Escala a millones de dispositivos  
✓ Minimiza overhead de comunicación  
✓ Maneja desconexiones automáticamente  
✓ Es rentable (~$50/mes para 10k devices)  
✓ Es segura (certificados X.509)  
✓ Usa servicios completamente gestionados (sin servers propios)  
✓ Proporciona confiabilidad empresarial (99.99% SLA)