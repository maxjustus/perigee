# Switch the Ensemble between the open driver and the vendor driver.
# README.md explains the targets. install and uninstall ask for sudo.

host := driver/build/Build/Products/Debug/EnsembleHost.app/Contents/MacOS/EnsembleHost
service := control/.build/release/ensemble-control
ctl := control/.build/release/ensemblectl
agent := $(HOME)/Library/LaunchAgents/dev.ensemble.control.plist
log := $(HOME)/Library/Logs/ensemble-control.log
apps := $(HOME)/Applications
mixer := $(apps)/Ensemble Mixer.app
gui := gui/$(shell id -u)

.PHONY: install uninstall status service

install: service
	driver/build.sh
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

service:
	cd control && env -u CC -u CXX -u LLVM_CONFIG swift build -c release
	codesign --force --sign - --entitlements control/user-client.entitlements $(service)
	codesign --force --sign - --entitlements control/user-client.entitlements $(ctl)
