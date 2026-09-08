PYTHON ?= python3
VENV := venv

.DEFAULT_GOAL := help

help: ## Show available commands
	@echo ""
	@echo "  VoiceCode BBS - Available Commands"
	@echo "  =================================="
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-14s %s\n", $$1, $$2}'
	@echo ""

check-deps: ## Verify system libraries (PortAudio, aplay) are installed
	@echo "Checking system dependencies..."
	@ok=true; \
	if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then \
		echo ""; \
		echo "  ERROR: libportaudio2 not found"; \
		echo "    The 'sounddevice' Python package requires the PortAudio C library."; \
		echo "    Without it, pip install succeeds but importing sounddevice fails at runtime."; \
		echo ""; \
		echo "    To fix (Debian/Ubuntu/Chromebook Crostini):"; \
		echo "      sudo apt install libportaudio2 portaudio19-dev"; \
		echo ""; \
		echo "    To fix (Fedora/RHEL):"; \
		echo "      sudo dnf install portaudio portaudio-devel"; \
		echo ""; \
		echo "    To fix (Arch):"; \
		echo "      sudo pacman -S portaudio"; \
		echo ""; \
		ok=false; \
	fi; \
	if ! command -v aplay >/dev/null 2>&1; then \
		echo "  WARNING: aplay not found (optional)"; \
		echo "    Text-to-speech playback uses aplay from ALSA utilities."; \
		echo "    TTS will not work without it."; \
		echo ""; \
		echo "    To fix (Debian/Ubuntu/Chromebook Crostini):"; \
		echo "      sudo apt install alsa-utils"; \
		echo ""; \
	fi; \
	if [ "$$ok" = false ]; then \
		echo "  Install the missing libraries above, then re-run 'make init'."; \
		echo ""; \
		exit 1; \
	fi; \
	echo "  OK: All required system dependencies found."

init: check-deps ## Create venv, install PyTorch (CPU) and requirements
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
	$(VENV)/bin/pip install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then $(VENV)/bin/pip install -r requirements-dev.txt; fi
	@echo ""
	@echo "  VoiceCode BBS environment initialized successfully."
	@echo "  Run 'make voicecode' to launch."
	@echo ""

update: ## Pull latest updates from Git, update dependencies, and preserve local settings
	@if ! command -v git >/dev/null 2>&1; then \
		echo "ERROR: git is not installed or not found in PATH."; \
		exit 1; \
	fi; \
	if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		echo "ERROR: Current directory is not a git repository."; \
		exit 1; \
	fi; \
	echo "Updating VoiceCode BBS..."; \
	BRANCH=$$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"); \
	REMOTE=$$(git config "branch.$$BRANCH.remote" 2>/dev/null || echo "origin"); \
	echo "Fetching latest changes from $$REMOTE/$$BRANCH..."; \
	git fetch "$$REMOTE" "$$BRANCH" || exit 1; \
	STASHED=0; \
	if ! git diff --quiet || ! git diff --cached --quiet; then \
		echo "Stashing local uncommitted changes..."; \
		git stash push -m "voicecode-auto-update-$$(date +%s)"; \
		STASHED=1; \
	fi; \
	echo "Pulling updates from Git (local settings and prompts are preserved)..."; \
	git pull --ff-only "$$REMOTE" "$$BRANCH" || git pull "$$REMOTE" "$$BRANCH" || exit 1; \
	if [ "$$STASHED" -eq 1 ]; then \
		echo "Restoring local changes..."; \
		git stash pop || echo "NOTE: Local changes restored. Check 'git stash list' if there were conflicts."; \
	fi; \
	if [ -d "$(VENV)" ]; then \
		echo "Updating Python dependencies in $(VENV)..."; \
		$(VENV)/bin/pip install --upgrade pip; \
		$(VENV)/bin/pip install -r requirements.txt; \
		if [ -f requirements-dev.txt ]; then $(VENV)/bin/pip install -r requirements-dev.txt; fi; \
	else \
		echo "Virtual environment not found. Creating one..."; \
		$(MAKE) init; \
	fi; \
	echo ""; \
	if [ -f "$(VENV)/bin/python" ]; then \
		$(VENV)/bin/python -c "from version import __version__; print('  ✓ Successfully updated VoiceCode BBS to v' + __version__)"; \
	else \
		echo "  ✓ Successfully updated VoiceCode BBS from Git."; \
	fi; \
	echo ""

voicecode: ## Launch the BBS voice prompt workshop
	. $(VENV)/bin/activate && python voicecode_bbs.py

test: ## Run the test suite
	. $(VENV)/bin/activate && PYTHONPATH=. python -m pytest -q

clean: ## Delete the venv and build caches (re-run 'make init' to recreate)
	rm -rf $(VENV) .pytest_cache build dist *.egg-info

.PHONY: help check-deps init update voicecode test clean
