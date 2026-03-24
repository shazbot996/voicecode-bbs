PYTHON ?= python3
VENV := venv

.DEFAULT_GOAL := help

help: ## Show available commands
	@echo ""
	@echo "  VoiceCode BBS -- voice-driven AI prompt workshop"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'
	@echo ""
	@echo "  First-time setup: make init -> make voicecode"
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

voicecode: ## Launch the BBS voice prompt workshop
	. $(VENV)/bin/activate && python voicecode_bbs.py

init-sub: ## Add a 'make voicecode' shortcut to the parent Makefile
	@SUBDIR=$$(basename "$$PWD"); \
	PARENT="$$(cd .. && pwd)"; \
	TAB=$$(printf '\t'); \
	if [ -f "$$PARENT/Makefile" ]; then \
		if grep -q '^voicecode:' "$$PARENT/Makefile"; then \
			echo "  Target 'voicecode' already exists in $$PARENT/Makefile -- skipping."; \
		else \
			echo "" >> "$$PARENT/Makefile"; \
			echo "voicecode: ## Launch VoiceCode BBS" >> "$$PARENT/Makefile"; \
			echo "$${TAB}. $${SUBDIR}/$(VENV)/bin/activate && python $${SUBDIR}/voicecode_bbs.py" >> "$$PARENT/Makefile"; \
			echo "  Added 'voicecode' target to $$PARENT/Makefile"; \
		fi; \
	else \
		echo '.DEFAULT_GOAL := help' > "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo 'help: ## Show available commands' >> "$$PARENT/Makefile"; \
		printf '%s\n' "$${TAB}"'@grep -E '"'"'^[a-zA-Z_-]+:.*?## .*$$$$'"'"' $$(MAKEFILE_LIST) | awk '"'"'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$$$1, $$$$2}'"'"'' >> "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo "voicecode: ## Launch VoiceCode BBS" >> "$$PARENT/Makefile"; \
		echo "$${TAB}. $${SUBDIR}/$(VENV)/bin/activate && python $${SUBDIR}/voicecode_bbs.py" >> "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo '.PHONY: help voicecode' >> "$$PARENT/Makefile"; \
		echo "  Created $$PARENT/Makefile with help and voicecode targets"; \
	fi

test: ## Run the smoke test suite
	. $(VENV)/bin/activate && python -m pytest -q

clean: ## Delete the venv (re-run 'make init' to recreate)
	rm -rf $(VENV)

.PHONY: help check-deps init init-sub voicecode test clean
