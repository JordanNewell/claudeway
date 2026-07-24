# PORT AUTHORITY - Claudeway Integration

## Overview

Claudeway now includes **PORT AUTHORITY** for zero-conflict port management across all your local development projects.

## What It Does

- ✅ Automatically finds available ports
- ✅ Creates friendly DNS names (`*.pa.local`)
- ✅ Prevents port conflicts between projects
- ✅ Persists port state across restarts
- ✅ Verifies port availability on startup

## Usage

### Allocate Ports

```bash
# Activate venv first
.venv\Scripts\activate

# Allocate port for API
python scripts/port_authority.py claudeway api --port 8000

# Allocate port for Dashboard
python scripts/port_authority.py claudeway dashboard --port 3000

# Allocate port for Postgres
python scripts/port_authority.py claudeway postgres --port 5432

# Allocate port for Redis
python scripts/port_authority.py claudeway redis --port 6379
```

### View Allocations

```python
python -c "from scripts.port_authority import PortAuthority; PortAuthority('claudeway').print_status()"
```

Output:
```
============================================================
PORT AUTHORITY - CLAUDEWAY
============================================================
  api             ->  8001  claudeway-api.pa.local                   [OK]
  dashboard       ->  3000  claudeway-dashboard.pa.local             [OK]
  postgres        ->  5432  claudeway-postgres.pa.local              [OK]
  redis           ->  6379  claudeway-redis.pa.local                 [OK]
============================================================
```

### Update Hosts File (Optional)

```bash
# Run as Administrator on Windows, or sudo on Linux/Mac
python scripts/port_authority.py claudeway api --hosts
```

This adds entries to your hosts file:
```
127.0.0.1       claudeway-api.pa.local
127.0.0.1       claudeway-dashboard.pa.local
127.0.0.1       claudeway-postgres.pa.local
127.0.0.1       claudeway-redis.pa.local
```

Then you can use friendly URLs:
- `http://claudeway-api.pa.local` instead of `http://localhost:8001`
- `http://claudeway-dashboard.pa.local` instead of `http://localhost:3000`

## How It Works

1. **Port Discovery**: Scans for available ports in range 8000-9999
2. **State Persistence**: Stores allocations in `~/.port-authority/state.json`
3. **Verification**: Checks if previous allocations are still valid
4. **Conflict Resolution**: Automatically finds new ports if old ones are taken

## Claudeway Services

| Service | Default Port | Allocated Port | DNS Name |
|----------|-------------|---------------|----------|
| API | 8000 | 8001* | claudeway-api.pa.local |
| Dashboard | 3000 | 3000 | claudeway-dashboard.pa.local |
| Postgres | 5432 | 5432 | claudeway-postgres.pa.local |
| Redis | 6379 | 6379 | claudeway-redis.pa.local |
| NATS | 4222 | (auto) | claudeway-nats.pa.local |

*Port 8000 was taken, so PORT AUTHORITY allocated 8001 automatically.

## Starting Claudeway with PORT AUTHORITY

```bash
# 1. Allocate ports
python scripts/port_authority.py claudeway api
python scripts/port_authority.py claudeway dashboard
python scripts/port_authority.py claudeway postgres

# 2. Start services on allocated ports
docker-compose -f infra/docker-compose.yml up -d

# 3. Start API (on allocated port)
cd api && ../.venv/Scripts/python.exe -m uvicorn main:app --port 8001

# 4. Start Dashboard (on allocated port)
cd dashboard && npm run dev -- --port 3000

# 5. Access via friendly URLs (after updating hosts file)
http://claudeway-api.pa.local/docs
http://claudeway-dashboard.pa.local
```

## Multi-Project Compatibility

PORT AUTHORITY state is global across all projects. Each project gets its own namespace:

```
~/.port-authority/state.json:
{
  "claudeway-api": {"port": 8001, ...},
  "m0lhandz-api": {"port": 8002, ...},
  "molana-api": {"port": 8003, ...},
  ...
}
```

No more `EADDRINUSE` errors when running multiple projects!

## Troubleshooting

### Port showing as [TAKEN]

Run again - PORT AUTHORITY will automatically find a new port:

```bash
python scripts/port_authority.py claudeway api
```

### Flush DNS Cache

After updating hosts file, flush DNS:

**Windows:**
```bash
ipconfig /flushdns
```

**Linux:**
```bash
sudo systemd-resolve --flush-caches
```

**Mac:**
```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

### Reset All Allocations

Delete the state file:
```bash
rm ~/.port-authority/state.json
```
