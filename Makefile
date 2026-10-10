.PHONY: install test build demo up down
install:
	python -m venv .venv
	.venv/bin/pip install -r backend/requirements.lock
	.venv/bin/pip install --no-deps -e backend
	cd frontend && npm ci

test:
	.venv/bin/python -m pytest backend/tests -q
	.venv/bin/ruff check backend
	cd frontend && npm test

build:
	cd frontend && npm run build

demo:
	.venv/bin/python -m orbit_sentinel.cli --scenario crossing --output frontend/public/demo/crossing.json
	.venv/bin/python -m orbit_sentinel.cli --scenario uncertain --output frontend/public/demo/uncertain.json
	.venv/bin/python -m orbit_sentinel.cli --scenario clear --output frontend/public/demo/clear.json

up:
	docker compose up --build -d --wait

down:
	docker compose down
