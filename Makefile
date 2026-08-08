.PHONY: dev-start dev-stop dev-status dev-restart test lint

dev-start:
	./scripts/run.sh

dev-stop:
	./scripts/stop.sh

dev-status:
	./scripts/dev-status.sh

dev-restart: dev-stop dev-start

test:
	pytest tests/ -q

lint:
	ruff check hacklog tests
	ruff format --check hacklog tests
