.PHONY: install dev web test release demo
install:
	python -m pip install .
dev:
	python -m pip install -e '.[dev]'
web:
	cd clients/web && npm ci && npm run build
test:
	python -m pytest
	cd clients/web && npm test
release:
	python scripts/build_release.py
demo:
	python scripts/create_demo.py ./demo-stories
