SHELL := /bin/sh

.PHONY: help test

help:
	@echo "Targets:"
	@echo "  make test - Run pytest in Debian 13 Docker container"

test:
	docker compose run --build --rm test
