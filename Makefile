# Build, test and install the open driver and the control service, or switch back to the vendor driver.
# README.md explains the targets. install and uninstall ask for sudo.

host := driver/build/Build/Products/Debug/EnsembleHost.app/Contents/MacOS/EnsembleHost
service := control/.build/release/ensemble-control
ctl := control/.build/release/ensemblectl
bootloader := control/.build/release/ensemble-bootloader
agent := $(HOME)/Library/LaunchAgents/dev.ensemble.control.plist
log := $(HOME)/Library/Logs/ensemble-control.log
apps := $(HOME)/Applications
mixer := $(apps)/Ensemble Mixer.app
gui := gui/$(shell id -u)
swift := env -u CC -u CXX -u LLVM_CONFIG swift
web := control/web
page := control/Sources/ensemble-control/Public/index.html
# fpga-reconstruction-test.py needs an external Mistral checkout, so it is not in the list.
pytests := $(filter-out scripts/firmware/fpga-reconstruction-test.py,$(wildcard scripts/*-test.py scripts/firmware/*-test.py))
FUZZ_SECONDS ?= 30

.PHONY: build install uninstall status service web dext bootloader test lint fuzz check dev

build: service dext

install: build
	$(host) activate
	sudo scripts/system.sh install
	sed -e 's|@SERVICE@|$(CURDIR)/$(service)|' -e 's|@LOG@|$(log)|' launchd/dev.ensemble.control.plist > $(agent)
	launchctl bootout $(gui)/dev.ensemble.control 2> /dev/null || true
	launchctl bootstrap $(gui) $(agent)
	mkdir -p "$(apps)"
	rm -rf "$(mixer)"
	osacompile -o "$(mixer)" -e 'open location "http://localhost:8737"'

uninstall:
	launchctl bootout $(gui)/dev.ensemble.control 2> /dev/null || true
	rm -f $(agent)
	rm -rf "$(mixer)"
	sudo scripts/system.sh uninstall

status:
	@systemextensionsctl list | grep dev.ensemble || echo "dext: not installed"
	@ioreg -r -n EnsembleDriver | grep -q . && echo "device: open driver" || \
		{ ioreg -r -c com_apogeedigital_Ensemble2Device | grep -q . && echo "device: vendor driver" || echo "device: no driver"; }
	@launchctl print system/dev.ensemble.rematch > /dev/null 2>&1 && echo "boot daemon: on" || echo "boot daemon: off"
	@launchctl print $(gui)/dev.ensemble.control > /dev/null 2>&1 && echo "control service: on" || echo "control service: off"
	@scripts/vendor-hal.sh status | head -1 | sed 's/^bundle/vendor HAL plugin/'

service: web
	cd control && $(swift) build -c release
	codesign --force --sign - --entitlements control/user-client.entitlements $(service)
	codesign --force --sign - --entitlements control/user-client.entitlements $(ctl)

web: $(web)/node_modules
	npm --prefix $(web) run build

$(web)/node_modules: $(web)/package-lock.json
	npm --prefix $(web) ci
	touch $@

dext:
	driver/build.sh

bootloader:
	cd control && $(swift) build -c release --product ensemble-bootloader
	codesign --force --sign - --entitlements control/user-client.entitlements $(bootloader)

test: $(web)/node_modules
	npm --prefix $(web) test
	cd control && $(swift) test
	driver/test.sh
	cd probe && cargo test --quiet
	for test in $(pytests); do uv run --quiet --with unicorn==2.1.4 --with websockets==12.0 --with pillow==12.3.0 python "$$test" || exit 1; done

lint: $(web)/node_modules
	npm --prefix $(web) run check
	cd control && $(swift) build -Xswiftc -warnings-as-errors
	cd probe && cargo clippy --quiet --all-targets -- -D warnings
	uvx --quiet ruff@0.11.6 check scripts

fuzz:
	driver/fuzz.sh $(FUZZ_SECONDS)

check: lint test fuzz

# The service holds the ports, so dev stops the launch agent and runs the service in the foreground. The service
# reads the page on each request, so a browser reload shows each rebuild. Ctrl-C starts the launch agent again.
dev: service
	launchctl bootout $(gui)/dev.ensemble.control 2> /dev/null || true
	(cd $(web) && exec node build.js --watch) & watch=$$!; \
	trap 'kill $$watch; launchctl bootstrap $(gui) $(agent)' EXIT; \
	trap 'exit 130' INT TERM; \
	ENSEMBLE_WEB_PAGE=$(CURDIR)/$(page) $(service)
