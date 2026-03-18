PYTHON ?= python3
VENV := venv

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

check-deps: ## Check for required system libraries
	@echo "Checking system dependencies..."
	@ok=true; \
	if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then \
		echo ""; \
		echo "  \033[31m✗ libportaudio2 not found\033[0m"; \
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
		echo "  \033[33m⚠ aplay not found (optional)\033[0m"; \
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
	echo "  \033[32m✓ All required system dependencies found.\033[0m"

init: check-deps ## Create venv and install all dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
	$(VENV)/bin/pip install -r requirements.txt

voicecode: ## Run the BBS application
	. $(VENV)/bin/activate && python voicecode_bbs.py

clean: ## Remove the virtual environment
	rm -rf $(VENV)

.PHONY: help check-deps init voicecode clean
