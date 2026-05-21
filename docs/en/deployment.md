# Deployment Guide

This document covers deploying Chameleon: local Docker, production single-node, and pushing images to a private registry.

## I. Local Docker (recommended / fastest)

### 1. Setup

```bash
git clone https://github.com/your-org/chameleon.git
cd chameleon

# Image tags (default 0.1.0)
cp docker/images/.env.example docker/images/.env

# Runtime secrets — **REQUIRED on first run**
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
```

Four values **must** be set in `.env`:

| Variable | Generation |
|---|---|
| `PG_PASSWORD` | any strong password |
| `REDIS_PASSWORD` | any strong password |
| `CHAMELEON_JWT_SECRET` | `python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` |
| `CHAMELEON_CRYPTO_KEY` | same as above |

### 2. Start

```bash
./docker/scripts/run-local.sh
```

Steps:
1. Auto-create `data/{pg,redis,resources,logs}` dirs
2. `build-images.sh` builds base / code / ui
3. `docker compose up -d` starts 5 services
4. Wait for backend healthy (up to 90s)
5. Print access banner

### 3. Access

- UI: http://localhost:6006
- API docs: http://localhost:7009/docs
- Initial admin credentials: `docker/containers/data/logs/initial-admin-credentials.txt`

### 4. Incremental rebuild

```bash
./docker/scripts/run-local.sh code      # rebuild backend only
./docker/scripts/run-local.sh ui        # rebuild frontend only
```

### 5. Stop / reset

```bash
./docker/scripts/stop-local.sh           # stop, keep data
./docker/scripts/stop-local.sh -v        # stop + wipe data (DESTRUCTIVE)
```

## II. Production

### Push images to private registry

```bash
cp docker/scripts/.registry.env.example docker/scripts/.registry.env
vim docker/scripts/.registry.env

./docker/scripts/push-images.sh
```

### On the production host

Only two files needed in the same directory:

```
/apps/chameleon/
├── docker-compose.yml    # from docker/containers/prod/docker-compose.yml
├── .env                  # tags + DB/Redis/JWT/Crypto secrets
└── initdb/               # from docker/containers/prod/initdb/
```

```bash
cd /apps/chameleon
docker login <registry>
docker compose pull
docker compose up -d
```

### Upgrade (backend only, the most common case)

```bash
sed -i 's/^CHAMELEON_CODE_TAG=.*/CHAMELEON_CODE_TAG=0.2.0/' .env
docker compose pull
docker compose up -d
```

Backend container auto-runs `alembic upgrade head` on restart; no manual migration needed.

## III. Without Docker

### Backend

```bash
cd backend
uv sync
# Run your own PG + Redis

cp config/example/component.example.json config/component.json
vim config/component.json

export CHAMELEON_JWT_SECRET="$(python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")"
export CHAMELEON_CRYPTO_KEY="$(python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")"

uv run alembic upgrade head
uv run uvicorn chameleon.app.main:app --host 0.0.0.0 --port 7009 --reload
```

### Frontend

```bash
cd frontend
yarn install
yarn dev   # http://localhost:6006, proxies /v1 to 127.0.0.1:7009
```

## IV. Configuration Strategy

Chameleon uses a **hybrid configuration strategy**:

| Config | Location | Modify by | Use case |
|---|---|---|---|
| DB / Redis conn, JWT / Crypto keys, ports, log level | `.env` → compose env | edit .env + restart | containerized deploy |
| Business seed (model.json / agents.yaml / chameleon.json) | `backend/config/*.json` bind mount | edit file + restart | first-time seed |
| Providers / Agents / Users / Roles / Permissions | PostgreSQL | admin UI (live) | day-to-day ops |
| Provider api_key (AES-256-GCM) | DB `providers.api_key_encrypted` | admin UI (live) | rotation |

Rationale:
- **Conn/keys → env**: 12-factor compliant, easy to integrate with K8s Secrets / Vault
- **Seed → JSON**: nested structures don't flatten into env well
- **Runtime → DB**: admin edits without restart, multi-instance share state

## V. Health checks

| Path | Purpose |
|---|---|
| `GET http://<ui>/healthz` | nginx liveness |
| `GET http://<backend>:7009/docs` | backend liveness |
| `docker compose ps` | container status overview |

## VI. Security checklist

- [ ] Replace ALL `change-this-*` defaults before deploy
- [ ] `CHAMELEON_JWT_SECRET` / `CHAMELEON_CRYPTO_KEY` ≥ 32 random bytes
- [ ] Don't expose PG/Redis ports to public internet (prod compose hides them by default)
- [ ] `chmod 600` on `.env`, never commit to git
- [ ] HTTPS: terminate at a front nginx / caddy / traefik
- [ ] Regular backup of `pg-data` named volume
