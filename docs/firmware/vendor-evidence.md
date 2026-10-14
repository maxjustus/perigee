# Vendor and community evidence

External sources that corroborate or extend the offline map. Nothing here
replaces primary chip documents. The unit still needs a physical inspection
for board identity.

## Firmware release status

**Verified:** the Apogee knowledge base lists the final Ensemble Thunderbolt
firmware as PSoC `1.5.3`, FPGA `0.56`, and resource `6`
([versions list](https://knowledge.apogeedigital.com/apogee-product-software-firmware-versions-list-current-products)).
Our unit reports exactly those three values, and our updater bundle ships
the same images. The installed firmware is the last vendor release.

**Verified:** the final software release is
`Ensemble_Element_Release.3.6`, described as the final release with
Thunderbolt recognition changes for macOS Tahoe
([Element downloads article](https://knowledge.apogeedigital.com/element-thunderbolt-series-users-guide-documentation-downloads)).
The article lists releases 3.6, 3.5.2, 3.0, and 2.0.
The firmware versions above are unchanged across them, so the later
installers differ in host software, not in the images we analyze.

**Inferred:** no newer firmware image exists to analyze. The 2022 updater
we hold contains the final PSoC, FPGA, and resource images.

## Vendor recovery procedure, and what it proves

**Verified:** Apogee documents a recovery procedure for a half-loaded boot
state, quoted from the knowledge base: if the front-panel display stops on
the logo, three dots, or any half-loaded display, the customer must quit
all applications, remove power and Thunderbolt, connect power first, then
Thunderbolt, power up, and run the firmware updater to confirm or reinstall
the firmware
([frozen boot article](https://knowledge.apogeedigital.com/the-ensemble-is-frozen-in-the-middle-of-the-boot-up-with-the-apogee-a-logo-and%2For-3-dots-on-the-screen)).

Two consequences for this work:

- The vendor treats a half-loaded image as recoverable through the normal
  update path. This matches the map's finding that the loader holds itself
  reachable when the application checksum fails.
- Connect power before Thunderbolt. The article states this as a permanent
  rule and the frozen state as the consequence of the wrong order. Our
  recovery ladder must follow the same order.

**Verified:** a panel factory reset exists. Hold the Output Controller
knob through the splash screen until the level meters appear
([factory reset article](https://knowledge.apogeedigital.com/ensemble-thunderbolt-factory-hardware-reset-/-initialize)).

## Chip identification

Source: a first-hand review by an SAE-trained engineer, April 2017
([Audiofader](https://www.audiofader.com/test-apogee-ensemble-thunderbolt-ridisegnata-per-lasciare-il-segno/)).
Status is **Inferred (medium)**: reported from the hardware, with no
legible chip photograph in the article.

| Function | Part | Cross-check against our map |
|---|---|---|
| Rear analog preamps, 8 channels | OPA1612 opamps, each with a THAT 5171 digitally controlled preamp | Our map has eight SPI preamps with per-channel gain and range registers |
| A/D conversion | AK5388AEQ, two devices, four channels each, 120 dB dynamic range | Eight analog inputs in our channel map |
| Front Hi-Z inputs | A separate Cirrus Logic 5361 converter, 114 dB | The map already separates the front paths from the rear |
| D/A conversion | ES9016 SABRE, 32-bit, 124 dB | Our map has two I2C devices at `0x49`, each with eight attenuation registers and a global mute bit. ES9016 is an eight-channel DAC |
| Logic | Altera Cyclone V FPGA | Our bitstream analysis identifies a Cyclone V GX C3 |
| Input protection | FET soft limiter before the A/D | Our map has a SoftLimit command |
| Line inputs | Automatic relay that bypasses the preamp in Line mode | Matches the mapped input-type behavior |

The two mappings that matter most are the ES9016 pair and the THAT 5171
set. Both match the register structure our firmware analysis found, which
raises confidence in the identification.

**Unknown:** the device at I2C `0x29`, mapped earlier as a dual guitar gain
control. The review does not name it.

## Community repair evidence

**Verified as reported:** a user recovered a failed update by installing
the PSoC image and the FPGA image in separate attempts, one at a time
([firmware update tip](https://gearspace.com/threads/apogee-ensemble-firmware-update-tip.774166/)).

**Verified as reported:** the vendor updater offers a downgrade or reinstall
path after firmware corruption
([kernel panic thread](https://gearspace.com/threads/help-apogee-ensemble-kernel-panic-when-switching-it-on.162901/page-3)).
This matches `ElementsUpdateVersionInfo.plist`, which carries a `force`
flag per component.

**Verified as reported:** the front panel runs a light show during a
firmware update, described by users as "vegas mode". A running update is
visible on the panel, which is useful for a supervised session.

**Contrast, not evidence for our unit:** a detailed teardown and repair
exists for the 2007 FireWire Ensemble
([Khron's Cave](https://khronscave.blogspot.com/2019/11/56-apogee-ensemble-firewire-teardown.html)).
That model carries CS4272 codecs and a different architecture. Do not
apply its parts or procedures here.

## Not found

- FCC filing with internal photographs. The FCC identifier is printed on
  the unit label, so the owner can read it and search with it directly.
- Board photographs of the Thunderbolt model at readable resolution.
- Any service manual, schematic, or debug pinout.
- Any community firmware, patch, or teardown of the Thunderbolt unit.

## Owner actions these enable

1. Read the FCC identifier from the unit label. Then search the FCC
   database for internal photos and any test report.
2. Follow the power-first rule in every future session.
3. If the display freezes, use the vendor procedure before any other step.
