PYTHON ?= python3
VENV := venv

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

init: ## Create venv and install all dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

voicecode: ## Run the BBS application
	. $(VENV)/bin/activate && python voicecode_bbs.py

clean: ## Remove the virtual environment
	rm -rf $(VENV)

.PHONY: help init voicecode clean
