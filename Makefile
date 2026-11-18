# One-command entry points for the WhatsApp AI-voice demo. Everything also works without make:
# see scripts/demo.sh and scripts/doctor.py.
PY  ?= python3
TAG ?= demo

.PHONY: help demo demo-dry stop doctor sim install audio url

help:
	@echo "make demo      start audio + Chrome + auto_answer, print the noVNC URL, walk through the QR scan"
	@echo "make demo-dry  check preconditions and show what 'make demo' would do (changes nothing)"
	@echo "make doctor    read-only health check with a fix for every failure"
	@echo "make stop      stop auto_answer.py (Chrome keeps running; 'bash scripts/demo.sh stop --chrome' closes it)"
	@echo "make sim       simulated call against the AI (no phone, private audio devices; TAG=$(TAG))"
	@echo "make install   (re)install dependencies - idempotent, the devcontainer runs it on create"
	@echo "make url       print the noVNC desktop URL"

demo:
	@bash scripts/demo.sh

demo-dry:
	@bash scripts/demo.sh --dry-run

stop:
	@bash scripts/demo.sh stop

doctor:
	@$(PY) scripts/doctor.py $(ARGS)

sim:
	$(PY) scripts/sim_call.py experiments/E0/scripts/basic_qa.yaml --tag $(TAG)

install:
	bash scripts/install.sh

audio:
	bash scripts/audio_setup.sh

url:
	@$(PY) scripts/doctor.py --url
