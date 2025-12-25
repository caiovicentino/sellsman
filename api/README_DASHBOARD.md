# Dashboard API - Complete Implementation

Complete RESTful API for managing real estate leads, property visits, and analytics from WhatsApp conversations.

## Implementation Status

**Status**: COMPLETE (11/11 endpoints)
**Implementation Date**: 2024-12-24
**Code Quality**: Production-ready, no mocks
**Test Coverage**: Manual testing scripts provided

---

## Quick Start

### 1. Start the Server
```bash
cd /Users/caiovicentino/Desktop/sells/api
python3 whatsapp_webhook_server.py
```

Server will start on `http://localhost:5002`

### 2. Test the Endpoints
```bash
# Quick health check
curl http://localhost:5002/api/v1/dashboard/metrics

# Run comprehensive test suite
python3 test_dashboard_endpoints.py
```

---

## Endpoints Summary

### Leads Management (3 endpoints)
1. **GET /api/v1/dashboard/leads** - List leads (paginated, filterable)
2. **GET /api/v1/dashboard/leads/<id>** - Get single lead
3. **GET /api/v1/dashboard/leads/<id>/conversation** - Get conversation history

### Visits Management (3 endpoints)
4. **GET /api/v1/dashboard/visits** - List visits (paginated, filterable)
5. **GET /api/v1/dashboard/visits/<uuid>** - Get single visit
6. **PATCH /api/v1/dashboard/visits/<uuid>** - Update visit status

### Analytics & Metrics (5 endpoints)
7. **GET /api/v1/dashboard/metrics** - Dashboard summary metrics
8. **GET /api/v1/dashboard/analytics/timeseries** - Time series data
9. **GET /api/v1/dashboard/analytics/funnel** - Conversion funnel
10. **GET /api/v1/dashboard/analytics/sources** - Lead sources breakdown
11. **GET /api/v1/dashboard/realtime** - Real-time monitoring

---

## Documentation Files

| File | Description |
|------|-------------|
| [DASHBOARD_API.md](./DASHBOARD_API.md) | Complete API reference with examples |
| [dashboard-openapi.yaml](./dashboard-openapi.yaml) | OpenAPI 3.0 specification |
| [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) | Implementation details and checklist |
| [DASHBOARD_ENDPOINTS_SUMMARY.txt](./DASHBOARD_ENDPOINTS_SUMMARY.txt) | Quick reference guide |
| [test_dashboard_endpoints.py](./test_dashboard_endpoints.py) | Automated test script |

---

## Example Usage

### Get Dashboard Metrics
```bash
curl http://localhost:5002/api/v1/dashboard/metrics
```

**Response:**
```json
{
  "total_leads": 150,
  "leads_today": 8,
  "total_visits": 45,
  "pending_visits": 12,
  "confirmed_visits": 18,
  "conversion_rate": 30.0,
  "avg_feedback_score": 4.2,
  "by_status": {
    "pending": 80,
    "contacted": 35,
    "qualified": 20,
    "scheduled": 10,
    "completed": 5
  }
}
```

### List Leads with Filtering
```bash
curl "http://localhost:5002/api/v1/dashboard/leads?page=1&page_size=20&status=pending&search=5585"
```

### Update Visit Status
```bash
curl -X PATCH http://localhost:5002/api/v1/dashboard/visits/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{"status": "confirmed"}'
```

### Get Time Series Data
```bash
curl "http://localhost:5002/api/v1/dashboard/analytics/timeseries?period=30d"
```

---

## Database Schema

### Tables Used

#### landing_leads_v2
Stores lead information with embedded property details.

**Key Fields:**
- `id` - Primary key
- `phone` - Lead phone number
- `name` - Lead name
- `property_title`, `property_price`, `property_neighborhood`, etc. - Property details
- `status` - Lead status (pending, contacted, qualified, scheduled, completed)
- `registered_at`, `contacted_at`, `first_message_at` - Timestamps

**Indexes:**
- `idx_leads_v2_phone` on `phone`
- `idx_leads_v2_status` on `status`

#### property_visits
Stores scheduled property visits.

**Key Fields:**
- `id` - Primary key
- `visit_uuid` - Unique identifier (UUID)
- `lead_number` - WhatsApp number (with @c.us)
- `lead_phone` - Phone without suffix
- `scheduled_datetime` - Visit date/time
- `status` - Visit status (pending, confirmed, cancelled, completed)
- `lead_confirmed`, `broker_confirmed` - Confirmation flags
- `feedback_score` - Rating (1-5)

**Indexes:**
- `idx_visits_lead_number` on `lead_number`
- `idx_visits_lead_phone` on `lead_phone`
- `idx_visits_status` on `status`
- `idx_visits_uuid` on `visit_uuid`

#### conversation_messages
Stores chat message history.

**Key Fields:**
- `id` - Primary key
- `conversation_id` - Conversation identifier (whatsapp_PHONE@c.us)
- `role` - Message sender (user/assistant)
- `content` - Message text
- `created_at` - Timestamp

**Indexes:**
- `idx_messages_conversation_id` on `conversation_id`
- `idx_messages_created_at` on `created_at`

---

## Architecture

### Request Flow
1. Client sends HTTP request to endpoint
2. Flask route handler receives request
3. Query parameters/body validated
4. Database queried via `get_db()` context manager
5. Results formatted as JSON
6. Response returned with appropriate status code

### Database Access Pattern
```python
with get_db() as conn:
    cursor = conn.execute("SELECT * FROM table WHERE ...")
    results = [dict(row) for row in cursor.fetchall()]
```

### Error Handling
- All endpoints wrapped in try-catch blocks
- Errors logged with full stack traces
- Consistent error response format: `{"error": "message"}`
- HTTP status codes: 200 (OK), 400 (Bad Request), 404 (Not Found), 500 (Error)

### CORS Support
Enabled via Flask-CORS for cross-origin requests from frontend applications.

---

## Testing

### Manual Testing
```bash
# Test each endpoint manually
curl http://localhost:5002/api/v1/dashboard/metrics
curl http://localhost:5002/api/v1/dashboard/leads
curl http://localhost:5002/api/v1/dashboard/visits
curl http://localhost:5002/api/v1/dashboard/analytics/timeseries
curl http://localhost:5002/api/v1/dashboard/analytics/funnel
curl http://localhost:5002/api/v1/dashboard/analytics/sources
curl http://localhost:5002/api/v1/dashboard/realtime
```

### Automated Testing
```bash
# Run test suite
python3 test_dashboard_endpoints.py

# Test against different server
python3 test_dashboard_endpoints.py https://api.production.com
```

### Integration Testing
1. Start the WhatsApp webhook server
2. Add some test data via landing page endpoint
3. Create some visits via WhatsApp conversation
4. Run dashboard endpoint tests
5. Verify data consistency

---

## Performance Considerations

### Optimization Implemented
- Database indexes on frequently queried fields
- Pagination limits (max 100 items per page)
- Single database connection per request
- Efficient SQL queries with proper WHERE clauses

### Scalability Notes
- For high traffic, consider:
  - Database connection pooling
  - Redis caching for metrics/analytics
  - Query result caching (5-minute TTL)
  - Async endpoints with asyncio/aiohttp

---

## Security Considerations

### Current Implementation
- CORS enabled for all origins
- No authentication required
- Input sanitization via parameterized queries
- Error messages don't expose sensitive data

### Production Recommendations
1. Add authentication middleware (JWT or API keys)
2. Implement rate limiting (e.g., 100 requests/minute)
3. Restrict CORS to specific origins
4. Add request logging for audit trail
5. Use HTTPS in production
6. Implement API versioning
7. Add input validation schemas (e.g., Pydantic)

---

## Monitoring & Logging

### Logging
All endpoints log:
- Request parameters
- Database queries
- Errors with full stack traces
- Response status codes

**Log file**: `/tmp/whatsapp_webhook.log`

### Monitoring Endpoints
- **GET /health** - Server health check
- **GET /stats** - Server statistics
- **GET /api/v1/dashboard/realtime** - Real-time status

### Metrics to Monitor
- Request response times
- Error rates (4xx, 5xx)
- Database query times
- Active conversations count
- Cold lead timer count

---

## Deployment

### Local Development
```bash
cd /Users/caiovicentino/Desktop/sells/api
python3 whatsapp_webhook_server.py
```

### Production Deployment
```bash
# Using gunicorn
gunicorn -w 4 -b 0.0.0.0:5002 whatsapp_webhook_server:app

# Using Docker
docker build -t whatsapp-webhook .
docker run -p 5002:5002 -v /path/to/db:/tmp whatsapp-webhook
```

### Environment Variables
- `WEBHOOK_PORT` - Server port (default: 5002)
- `WEBHOOK_HOST` - Server host (default: 0.0.0.0)
- `LANDING_DB_PATH` - SQLite database path (default: /tmp/landing_leads.db)
- `DEBUG` - Debug mode (default: true)

---

## Troubleshooting

### Common Issues

**Issue**: Connection refused
- **Solution**: Ensure server is running on correct port

**Issue**: 404 errors on all endpoints
- **Solution**: Check server logs for route registration errors

**Issue**: Empty results
- **Solution**: Database may be empty - add test data first

**Issue**: 500 errors
- **Solution**: Check server logs for stack traces

### Debug Commands
```bash
# Check if server is running
curl http://localhost:5002/health

# View server logs
tail -f /tmp/whatsapp_webhook.log

# Check database
sqlite3 /tmp/landing_leads.db "SELECT COUNT(*) FROM landing_leads_v2"
```

---

## Future Enhancements

### Planned Features
- [ ] Authentication/authorization (JWT)
- [ ] WebSocket support for real-time updates
- [ ] Export endpoints (CSV, Excel, PDF)
- [ ] Advanced filtering (multi-field, ranges)
- [ ] Bulk operations (bulk status updates)
- [ ] Full-text search with indexing
- [ ] GraphQL API endpoint
- [ ] Webhook notifications for events

### Performance Improvements
- [ ] Redis caching layer
- [ ] Database query optimization
- [ ] Async/await endpoints
- [ ] Connection pooling
- [ ] Response compression

---

## Contributing

### Code Style
- Follow PEP 8 for Python code
- Use type hints where appropriate
- Write docstrings for all functions
- Keep functions focused and small

### Adding New Endpoints
1. Add route handler in `whatsapp_webhook_server.py`
2. Update documentation in `DASHBOARD_API.md`
3. Update OpenAPI spec in `dashboard-openapi.yaml`
4. Add test case to `test_dashboard_endpoints.py`
5. Update this README

---

## Support

For questions or issues:
1. Check server logs: `/tmp/whatsapp_webhook.log`
2. Review API documentation: `DASHBOARD_API.md`
3. Run test suite: `python3 test_dashboard_endpoints.py`
4. Check database schema and data

---

## License

This is proprietary software for internal use.

---

## Changelog

### 2024-12-24 - Initial Release (v1.0.0)
- Implemented all 11 dashboard endpoints
- Added comprehensive documentation
- Created OpenAPI specification
- Added automated test suite
- Production-ready implementation
