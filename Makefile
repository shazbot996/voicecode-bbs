PYTHON ?= python3
VENV := venv

.DEFAULT_GOAL := help

help: ## Show available commands
	@echo ""
	@echo "  VoiceCode BBS - Execution & Security"
	@echo "  ===================================="
	@echo "  voicecode-sandbox  : [RECOMMENDED] Launches the BBS in a secure Bubblewrap sandbox."
	@echo "                       Hides your HOME directory (~/.ssh, etc.) from agents."
	@echo "                       Use this when running agents in --yolo mode."
	@echo ""
	@echo "  voicecode          : [UNPROTECTED] Launches the BBS with full system access."
	@echo "                       Agents can read/write any file your user can access."
	@echo ""
	@echo "  Setup & Maintenance"
	@echo "  -------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -vE '^(voicecode|help)' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'
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

voicecode: ## Launch the BBS voice prompt workshop (Standard/Unprotected)
	. $(VENV)/bin/activate && python voicecode_bbs.py

voicecode-sandbox: ## Launch the BBS voice prompt workshop (Secure Sandbox)
	../sandbox-launch.sh

init-sub: ## Add secure launch shortcuts and help text to the parent Makefile
	@SUBDIR=$$(basename "$$PWD"); \
	PARENT="$$(cd .. && pwd)"; \
	TAB=$$(printf '\t'); \
	if [ -f "$$PARENT/Makefile" ]; then \
		if grep -q '^voicecode-sandbox:' "$$PARENT/Makefile"; then \
			echo "  Target 'voicecode-sandbox' already exists in $$PARENT/Makefile -- skipping."; \
		else \
			echo "" >> "$$PARENT/Makefile"; \
			echo "VENV := venv" >> "$$PARENT/Makefile"; \
			echo "" >> "$$PARENT/Makefile"; \
			echo "voicecode: ## Launch VoiceCode BBS (Standard/Unprotected)" >> "$$PARENT/Makefile"; \
			echo "$${TAB}. $${SUBDIR}/\$$(VENV)/bin/activate && python $${SUBDIR}/voicecode_bbs.py" >> "$$PARENT/Makefile"; \
			echo "" >> "$$PARENT/Makefile"; \
			echo "voicecode-sandbox: ## Launch VoiceCode BBS (Secure Sandbox)" >> "$$PARENT/Makefile"; \
			echo "$${TAB}./sandbox-launch.sh" >> "$$PARENT/Makefile"; \
			echo "  Added secure launch targets to $$PARENT/Makefile"; \
		fi; \
	else \
		echo '.DEFAULT_GOAL := help' > "$$PARENT/Makefile"; \
		echo 'VENV := venv' >> "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo 'help: ## Show this help message' >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"  VoiceCode BBS - Execution & Security\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"  ====================================\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"  voicecode-sandbox  : [RECOMMENDED] Launches the BBS in a secure Bubblewrap sandbox.\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"                       Hides your HOME directory (~/.ssh, etc.) from agents.\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"                       Use this when running agents in --yolo mode.\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"  voicecode          : [UNPROTECTED] Launches the BBS with full system access.\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"                       Agents can read/write any file your user can access.\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"  Support & Utilities\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"  -------------------\"\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@grep -E '^[a-zA-Z_-]+:.*?## .*$$$$' \$$(MAKEFILE_LIST) | grep -vE '^(voicecode|help)' | sort | awk 'BEGIN {FS = \":.*?## \"}; {printf \"  %%-18s %%s\\\\n\", $$$$1, $$$$2}'\n" >> "$$PARENT/Makefile"; \
		printf "$${TAB}@echo \"\"\n" >> "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo "voicecode: ## Launch VoiceCode BBS (Standard/Unprotected)" >> "$$PARENT/Makefile"; \
		echo "$${TAB}. $${SUBDIR}/\$$(VENV)/bin/activate && python $${SUBDIR}/voicecode_bbs.py" >> "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo "voicecode-sandbox: ## Launch VoiceCode BBS (Secure Sandbox)" >> "$$PARENT/Makefile"; \
		echo "$${TAB}./sandbox-launch.sh" >> "$$PARENT/Makefile"; \
		echo '' >> "$$PARENT/Makefile"; \
		echo '.PHONY: help voicecode voicecode-sandbox' >> "$$PARENT/Makefile"; \
		echo "  Created $$PARENT/Makefile with secure launch targets and help text"; \
	fi

test: ## Run the smoke test suite
	. $(VENV)/bin/activate && python -m pytest -q

clean: ## Delete the venv (re-run 'make init' to recreate)
	rm -rf $(VENV)

.PHONY: help check-deps init init-sub voicecode voicecode-sandbox test clean
