# Claudeway - Deployment Guide

Complete guide for deploying and running the Claudeway agent platform.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Development Setup](#development-setup)
4. [Configuration](#configuration)
5. [Running the Platform](#running-the-platform)
6. [API Reference](#api-reference)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| **Python** | 3.11+ | Backend API |
| **Node.js** | 18+ | Frontend dashboard |
| **pnpm/npm** | 9.0+ / 8.0+ | Package manager |
| **Docker** | Latest | Infrastructure services |
| **Git** | Latest | Version control |

### Verify Installation

```bash
python --version   # Should be 3.11+
py --version       # Windows alternative
node --version     # Should be 18+
docker --version   # Should run
git --version      # Should run
```

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Navigate to project
cd E:/dev/projects/personal/claudeway

# 2. Copy environment file
cp .env.example .env

# 3. Start Docker Desktop (manual step)
# - Open Docker Desktop application
# - Wait for "Docker Desktop is running"

# 4. Start infrastructure
docker-compose -f infra/docker-compose.yml up -d

# 5. Install Python dependencies
py -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # Linux/Mac
pip install -e .

# 6. Install dashboard dependencies
cd dashboard
npm install --legacy-peer-deps
cd ..

# 7. Start API (Terminal A)
uvicorn claudeway.api.main:app --reload --host 0.0.0.0 --port 8000

# 8. Start Dashboard (Terminal B)
cd dashboard && npm run dev
```

### Access URLs

| Service | URL | Description |
|---------|-----|-------------|
| **Dashboard** | http://localhost:3000 | Main web UI |
| **API Docs** | http://localhost:8000/docs | Interactive API docs |
| **API** | http://localhost:8000 | REST API endpoint |
| **Adminer** | http://localhost:8090 | Database admin (optional) |

---

## Development Setup

### Backend Development

```bash
# Activate virtual environment
.venv\Scripts\activate

# Run with auto-reload
uvicorn claudeway.api.main:app --reload

# Run with specific host/port
uvicorn claudeway.api.main:app --host 0.0.0.0 --port 8080

# Run tests
pytest

# Format code
black .
ruff check .
```

### Frontend Development

```bash
cd dashboard

# Development server
npm run dev

# Build for production
npm run build

# Start production server
npm start

# Lint
npm run lint
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Copy example
cp .env.example .env
```

#### Key Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDWAY_API_HOST` | 0.0.0.0 | API bind address |
| `CLAUDWAY_API_PORT` | 8000 | API port |
| `CLAUDWAY_DATABASE_URL` | postgresql://... | PostgreSQL connection |
| `CLAUDWAY_REDIS_URL` | redis://... | Redis connection |
| `CLAUDWAY_CLAUDE_FLOW_URL` | http://localhost:8080 | Claude-Flow API |
| `CLAUDWAY_STRIPE_API_KEY` | - | Stripe for payments (optional) |
| `CLAUDWAY_ANTHROPIC_API_KEY` | - | Anthropic API key |

### Docker Services

The `infra/docker-compose.yml` includes:

| Service | Port | Description |
|---------|------|-------------|
| **postgres** | 5432 | PostgreSQL database |
| **redis** | 6379 | Cache & rate limiting |
| **nats** | 4222, 8222 | Message bus |
| **claude-flow** | 8080, 9090 | Orchestration layer |
| **adminer** | 8090 | DB admin UI (optional) |

---

## Running the Platform

### Start Order

1. **Docker Desktop** - Start the application manually
2. **Infrastructure** - `docker-compose up -d`
3. **Backend API** - `uvicorn claudeway.api.main:app --reload`
4. **Frontend** - `cd dashboard && npm run dev`

### Stop Order

1. **Frontend** - Ctrl+C in terminal
2. **Backend** - Ctrl+C in terminal
3. **Infrastructure** - `docker-compose -f infra/docker-compose.yml down`
4. **Docker Desktop** - Close the application

### Check Service Health

```bash
# Check Docker containers
docker ps

# Check API health
curl http://localhost:8000/health

# Check database
docker exec claudeway-postgres pg_isready -U claudeway

# Check Redis
docker exec claudeway-redis redis-cli ping
```

---

## API Reference

### Base URL

```
http://localhost:8000
```

### Authentication

Currently using `X-Tenant-ID` header for multi-tenancy:

```bash
curl -H "X-Tenant-ID: your-tenant-id" http://localhost:8000/v1/agents/
```

### Core Endpoints

#### Tenants

```bash
# Create tenant
POST /v1/tenants/
  ?name=Acme+Corp
  &email=admin@acme.com
  &tier=free

# List tenants
GET /v1/tenants/

# Get tenant
GET /v1/tenants/{tenant_id}

# Update tier
PUT /v1/tenants/{tenant_id}/tier?tier=pro
```

#### Agents

```bash
# Deploy agent
POST /v1/agents/?tenant_id={tenant_id}
  Content-Type: application/json
  {
    "name": "my-researcher",
    "template_id": "researcher",
    "config": {}
  }

# List agents
GET /v1/agents/?tenant_id={tenant_id}

# Get agent
GET /v1/agents/{agent_id}

# Stop agent
POST /v1/agents/{agent_id}/stop

# Delete agent
DELETE /v1/agents/{agent_id}

# Send message
POST /v1/agents/{agent_id}/message
  Content-Type: application/json
  {
    "message": "Research AI trends"
  }
```

#### Templates

```bash
# List templates
GET /v1/templates/

# Get template
GET /v1/templates/{template_id}

# Create template
POST /v1/templates/
  Content-Type: application/json
  {
    "name": "my-template",
    "display_name": "My Template",
    "description": "Custom agent",
    "config": {...},
    "category": "custom",
    "tags": ["custom"]
  }
```

#### Billing

```bash
# Get usage
GET /v1/billing/usage?tenant_id={tenant_id}

# List invoices
GET /v1/billing/invoices?tenant_id={tenant_id}

# Generate invoice
POST /v1/billing/invoices/generate
  ?tenant_id={tenant_id}
  &period_start=2024-01-01
  &period_end=2024-01-31
```

### Interactive Docs

Visit http://localhost:8000/docs for Swagger UI with try-it-out functionality.

---

## Troubleshooting

### Docker Issues

**Problem**: `error during connect: Get .../pipe/dockerDesktopLinuxEngine`

**Solution**: Start Docker Desktop application

**Problem**: Port already in use

**Solution**:
```bash
# Find process using port
netstat -ano | findstr :8000

# Kill the process
taskkill /PID <pid> /F
```

### Python Issues

**Problem**: `ModuleNotFoundError: No module named 'claudeway'`

**Solution**:
```bash
pip install -e .
```

**Problem**: PostgreSQL connection refused

**Solution**:
```bash
# Check Docker container
docker ps | grep postgres

# Restart container
docker restart claudeway-postgres
```

### Dashboard Issues

**Problem**: `npm ERR! peer dep missing`

**Solution**:
```bash
npm install --legacy-peer-deps
```

**Problem**: Cannot connect to API

**Solution**: Check that:
1. API is running (`curl http://localhost:8000/health`)
2. `.env.local` has correct `NEXT_PUBLIC_API_URL`
3. No firewall blocking the connection

### Database Issues

**Problem**: Tables don't exist

**Solution**:
```bash
# The API auto-creates tables on startup
# Restart the API server
```

**Problem**: Need to reset database

**Solution**:
```bash
# Stop containers
docker-compose -f infra/docker-compose.yml down

# Remove volumes
docker volume rm claudeway_postgres_data

# Restart
docker-compose -f infra/docker-compose.yml up -d
```

---

## Production Deployment

### Environment Setup

```bash
# Use production .env
cp .env.example .env.production

# Edit with production values
nano .env.production
```

### Build for Production

```bash
# Frontend
cd dashboard
npm run build
npm start

# Backend (use gunicorn instead of uvicorn)
pip install gunicorn
gunicorn claudeway.api.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Docker Production

```bash
# Build production images
docker-compose -f infra/docker-compose.yml build

# Run production stack
docker-compose -f infra/docker-compose.yml up -d
```

---

## Support

- **Documentation**: [README.md](../README.md)
- **Quick Start**: [QUICKSTART.md](../QUICKSTART.md)
- **Issues**: Create issue in repository

---

**Last Updated**: 2026-02-07
