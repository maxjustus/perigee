# probe

A command-line tool that reads the Ensemble through the vendor kext. It
answered the hardware questions before the dext existed.
`probe-results.md` records its results.

The tool opens the vendor kext user client and reads BAR0 with method 6
(`AccessBAR0Register`). It does not work with the open driver. Use it to
compare a register value or a behavior with the vendor driver.

## Requirements

- The vendor kext owns the Ensemble. Run `make uninstall` first.
- The vendor HAL is idle or off. A probe client replaces the vendor HAL
  client, and its close stops all DMA. `scripts/vendor-hal.sh` switches
  the vendor HAL. Run `scripts/vendor-hal.sh on` after a probe session to
  give the vendor HAL its client back.

## Commands

    cargo run --release -- <command>

| Command | Result |
|---------|--------|
| `regs` | Prints `ID`, `GENERAL`, `STATUS`, `INTERRUPT`, and `INFO` |
| `ring` | Starts a stream and samples the `CUR_*_ADDRESS_LOW` registers every 1 ms for 5 s |
| `getall` | Sends a Get-all and prints each PSoC report until 2 s pass with no report |
| `irq [mask]` | Starts a stream, ORs the hex mask into `INTERRUPT` for 2 s, and prints the MSI times |
