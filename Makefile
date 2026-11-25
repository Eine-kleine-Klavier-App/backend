.PHONY: infra full status migrate run up smoke down lint typecheck test check docker-build

# Data services only: system Postgres (5434), draft Postgres (5433), Redis (6380).
# Waits until all three report healthy. The backend and frontend are not started.
infra:
	docker compose up -d --wait postgres draft-postgres redis

# Backend and frontend in containers next to the data services (profile `full`).
# Ports 8000 and 5173 must be free: stop a native `make run` / `npm run dev` first.
full:
	docker compose --profile full up -d --build --wait

# Who listens on the project ports and which containers are alive. Run it before
# starting anything: what already runs is used, a second copy is never started.
status:
	@lsof -iTCP:8000,5173,5433,5434,6380 -sTCP:LISTEN -P -n || echo "nothing listens on 8000, 5173, 5433, 5434, 6380"
	@docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# Applies all pending Alembic migrations (idempotent — safe to re-run).
migrate:
	.venv/bin/alembic upgrade head
	.venv/bin/alembic -c alembic-draft.ini upgrade head

# Starts the API on http://127.0.0.1:8000 (python -m piano_app).
run:
	.venv/bin/python -m piano_app

# One command: infra -> migrate -> run. Ctrl-C stops the API; containers keep running
# (see `make down` to also tear those down).
up: infra migrate run

# Full-app smoke: needs infra+migrate already applied (run `make infra migrate` first,
# or `make up` in another terminal). Exercises drafts/edit/save end-to-end.
smoke:
	DRAFT_HISTORY_BACKEND=redis .venv/bin/python scripts/smoke.py

# Stops and removes the containers, `full` profile included. Volumes are kept
# (never add -v: the volumes hold the only copy of the local data).
down:
	docker compose --profile full down

# ruff check + format check (no fixes applied).
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

# mypy --strict-ish over src (see pyproject [tool.mypy]).
typecheck:
	.venv/bin/mypy src

# Runs the test suite.
test:
	.venv/bin/pytest

# lint + typecheck + test, same checks CI runs.
check: lint typecheck test

# Builds the backend image (Dockerfile) without starting anything.
docker-build:
	docker compose --profile full build app
