# WhatsApp Webhook Server

Servidor Flask standalone para processar webhooks do WhatsApp via WAHA (WhatsApp HTTP API).

## Características

- **Servidor independente**: Roda sem dependências do Celery ou da aplicação principal
- **Processamento síncrono**: Processa mensagens de forma síncrona usando asyncio
- **Integração AI**: Usa OpenRouter (Gemini 2.0 Flash) para gerar respostas inteligentes
- **Health checks**: Endpoints para monitoramento de saúde e estatísticas
- **Logging robusto**: Logs detalhados em console e arquivo
- **Filtragem inteligente**: Ignora mensagens próprias e eventos não relevantes

## Estrutura de Arquivos

```
api/
├── whatsapp_webhook_server.py    # Servidor principal
├── requirements-webhook.txt       # Dependências mínimas
├── .env.webhook.example          # Exemplo de configuração
├── start_webhook_server.sh       # Script de inicialização
├── test_webhook_server.py        # Suite de testes
└── README_WEBHOOK.md             # Esta documentação
```

## Instalação

### 1. Copiar exemplo de configuração

```bash
cd /Users/caiovicentino/Desktop/sells/api
cp .env.webhook.example .env.webhook
```

### 2. Configurar variáveis de ambiente

Edite `.env.webhook` com suas configurações:

```bash
# Server settings
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=5002
DEBUG=true

# OpenRouter AI API
OPENROUTER_API_KEY=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

# WAHA API Configuration
WAHA_BASE_URL=http://waha:3000
WAHA_API_KEY=your-secure-key-here
```

### 3. Instalar dependências

```bash
# Opção 1: Usar script de inicialização (recomendado)
./start_webhook_server.sh

# Opção 2: Instalação manual
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-webhook.txt
```

## Uso

### Iniciar servidor

```bash
# Usando script (recomendado)
./start_webhook_server.sh

# Ou manualmente
source venv/bin/activate
python whatsapp_webhook_server.py
```

O servidor estará disponível em: `http://0.0.0.0:5002`

### Testar servidor

```bash
# Testar com suite completa
python test_webhook_server.py

# Testar em servidor customizado
python test_webhook_server.py http://localhost:5002
```

## Endpoints

### POST /api/v1/whatsapp/webhook

Recebe e processa mensagens do WhatsApp via WAHA.

**Request:**
```json
{
  "event": "message",
  "session": "default",
  "payload": {
    "id": "message_123",
    "timestamp": 1703001234,
    "from": "5511999887766@c.us",
    "fromMe": false,
    "body": "Olá, quero informações",
    "type": "text",
    "chatId": "5511999887766@c.us"
  }
}
```

**Response (Success):**
```json
{
  "status": "processed",
  "result": {
    "status": "success",
    "from_number": "5511999887766@c.us",
    "response_sent": true,
    "message_id": "ABC123"
  },
  "timestamp": "2025-12-24T12:00:00.000000"
}
```

**Response (Ignored):**
```json
{
  "status": "ignored",
  "reason": "Message filtered (not processable)"
}
```

### GET /api/v1/whatsapp/webhook

Health check do webhook (usado pelo WAHA para verificação).

**Response:**
```json
{
  "status": "ok",
  "service": "whatsapp_webhook",
  "timestamp": "2025-12-24T12:00:00.000000"
}
```

### GET /health

Health check completo do servidor.

**Response:**
```json
{
  "status": "healthy",
  "service": "whatsapp_webhook_server",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "stats": {
    "messages_received": 150,
    "messages_processed": 145,
    "messages_failed": 5,
    "server_started_at": "2025-12-24T10:00:00.000000"
  },
  "timestamp": "2025-12-24T12:00:00.000000"
}
```

### GET /stats

Estatísticas de processamento.

**Response:**
```json
{
  "stats": {
    "messages_received": 150,
    "messages_processed": 145,
    "messages_failed": 5,
    "server_started_at": "2025-12-24T10:00:00.000000"
  },
  "timestamp": "2025-12-24T12:00:00.000000"
}
```

## Fluxo de Processamento

1. **Webhook recebe mensagem** do WAHA
2. **Extrai dados** da mensagem
3. **Filtra mensagens** (ignora próprias mensagens, eventos não relevantes)
4. **Gera resposta AI** usando OpenRouter (Gemini 2.0 Flash)
5. **Envia resposta** de volta via WAHA
6. **Atualiza estatísticas** de processamento

## Integração com WAHA

### Configurar webhook no WAHA

```bash
# Via API
curl -X POST http://waha:3000/api/webhooks \
  -H "X-Api-Key: your-secure-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://whatsapp-webhook:5002/api/v1/whatsapp/webhook",
    "events": ["message"],
    "session": "default"
  }'
```

### Docker Compose Integration

```yaml
services:
  waha:
    image: devlikeapro/waha-plus
    ports:
      - "3000:3000"
    environment:
      - WAHA_API_KEY=your-secure-key-here

  whatsapp-webhook:
    build: ./api
    command: python whatsapp_webhook_server.py
    ports:
      - "5002:5002"
    environment:
      - WEBHOOK_PORT=5002
      - WAHA_BASE_URL=http://waha:3000
      - WAHA_API_KEY=your-secure-key-here
      - OPENROUTER_API_KEY=sk-or-v1-xxx
    depends_on:
      - waha
```

## Logs

Logs são gravados em dois locais:

1. **Console/stdout**: Logs em tempo real
2. **Arquivo**: `/tmp/whatsapp_webhook.log`

### Visualizar logs

```bash
# Logs em tempo real
tail -f /tmp/whatsapp_webhook.log

# Últimas 100 linhas
tail -n 100 /tmp/whatsapp_webhook.log

# Filtrar erros
grep ERROR /tmp/whatsapp_webhook.log
```

## Troubleshooting

### Porta já em uso

```bash
# Verificar qual processo está usando a porta
lsof -i :5002

# Matar processo
kill $(lsof -t -i:5002)
```

### Servidor não responde

```bash
# Verificar se está rodando
ps aux | grep whatsapp_webhook_server

# Verificar logs
tail -n 50 /tmp/whatsapp_webhook.log

# Testar health check
curl http://localhost:5002/health
```

### Mensagens não são processadas

1. Verificar se WAHA está enviando webhooks:
   ```bash
   # Ver logs do WAHA
   docker logs waha
   ```

2. Verificar configuração do webhook no WAHA:
   ```bash
   curl http://waha:3000/api/webhooks \
     -H "X-Api-Key: your-key"
   ```

3. Verificar logs do servidor webhook:
   ```bash
   tail -f /tmp/whatsapp_webhook.log
   ```

### Respostas AI não funcionam

1. Verificar chave OpenRouter:
   ```bash
   echo $OPENROUTER_API_KEY
   ```

2. Testar API diretamente:
   ```bash
   curl https://openrouter.ai/api/v1/models \
     -H "Authorization: Bearer $OPENROUTER_API_KEY"
   ```

## Monitoramento

### Prometheus Metrics (futuro)

O servidor pode ser estendido para exportar métricas Prometheus:

- `webhook_messages_received_total`
- `webhook_messages_processed_total`
- `webhook_messages_failed_total`
- `webhook_processing_duration_seconds`

### Health Check Script

```bash
#!/bin/bash
# health_check.sh

WEBHOOK_URL="http://localhost:5002"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $WEBHOOK_URL/health)

if [ $RESPONSE -eq 200 ]; then
    echo "Webhook server is healthy"
    exit 0
else
    echo "Webhook server is unhealthy (HTTP $RESPONSE)"
    exit 1
fi
```

## Desenvolvimento

### Adicionar novo endpoint

```python
@app.route("/api/v1/whatsapp/custom", methods=["POST"])
def custom_endpoint():
    """Custom endpoint example."""
    data = request.json
    # Process data
    return jsonify({"status": "ok"}), 200
```

### Modificar prompt AI

Edite a variável `system_prompt` na função `get_ai_response()`:

```python
system_prompt = """Seu novo prompt aqui..."""
```

### Adicionar novo filtro de mensagens

Edite a função `extract_message_data()`:

```python
# Exemplo: Ignorar mensagens de grupos
if "@g.us" in from_number:
    logger.debug("Ignoring group message")
    return None
```

## Segurança

### Considerações

1. **API Keys**: Nunca commitar chaves no código
2. **HTTPS**: Usar HTTPS em produção (nginx/traefik)
3. **Rate Limiting**: Implementar rate limiting para prevenir abuso
4. **Autenticação**: Adicionar autenticação no webhook se necessário

### Exemplo com autenticação

```python
from functools import wraps

def require_webhook_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Webhook-Token')
        if token != os.getenv('WEBHOOK_SECRET_TOKEN'):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/v1/whatsapp/webhook", methods=["POST"])
@require_webhook_token
def webhook():
    # ...
```

## Performance

### Otimizações

1. **Async processing**: Já usa asyncio para I/O assíncrono
2. **Connection pooling**: httpx usa connection pooling automaticamente
3. **Timeout configuration**: Timeouts configurados para evitar hangs
4. **Resource limits**: Considerar usar gunicorn para produção

### Produção com Gunicorn

```bash
# Instalar gunicorn
pip install gunicorn

# Rodar com múltiplos workers
gunicorn -w 4 -b 0.0.0.0:5002 \
  --worker-class sync \
  --timeout 120 \
  whatsapp_webhook_server:app
```

## Referências

- [WAHA Documentation](https://waha.devlike.pro/)
- [OpenRouter API](https://openrouter.ai/docs)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [httpx Documentation](https://www.python-httpx.org/)
