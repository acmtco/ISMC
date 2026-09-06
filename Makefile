.PHONY: setup synth run eval demo test lint generate-api

setup:
	pip install -e ".[dev]"
	npm --prefix web install

generate-api:
	python -c "import json; from services.api.main import app; json.dump(app.openapi(), open('openapi.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)"
	npm --prefix web run generate-api

synth:
	python scripts/make_synthetic.py

run:
	docker compose --profile dev up --build

eval:
	python scripts/eval_end2end.py

demo:
	HG_MODE=replay docker compose --profile demo up --build

test:
	pytest

lint:
	ruff check .
