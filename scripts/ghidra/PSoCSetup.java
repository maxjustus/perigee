// Maps the PSoC 5LP address space, names its registers, and marks the
// vector table. Ghidra runs it as a pre-script, before auto-analysis.
// Arguments: <dir with config.bin> <cydevice_trm.h>
// @category Ensemble

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class PSoCSetup extends GhidraScript {
    private static final long APPLICATION = 0x10000;
    // PSoC Creator keeps only SP, reset, NMI, and HardFault in flash. The
    // startup code builds the full table in SRAM (CyRamVectors).
    private static final int VECTORS = 4;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Memory memory = currentProgram.getMemory();
        MemoryBlock flash = memory.getBlock(toAddr(APPLICATION));
        flash.setName("flash");
        // A read-only block lets the decompiler fold literal-pool loads into
        // constant addresses.
        flash.setPermissions(true, false, true);

        byte[] config = Files.readAllBytes(Path.of(args[0], "config.bin"));
        MemoryBlock ecc = memory.createInitializedBlock("flash_ecc_config", toAddr(0x48000000L),
            new ByteArrayInputStream(config), config.length, monitor, false);
        ecc.setPermissions(true, false, false);

        ram("sram", 0x1FFF8000L, 0x10000);
        io("dma", 0x20008000L, 0x8000);
        io("periph", 0x40000000L, 0x100000);
        io("flash_hidden", 0x49000000L, 0x200);
        io("emif", 0x60000000L, 0x1000000);
        io("ppb", 0xE0000000L, 0x100000);

        labelRegisters(Path.of(args[1]));
        markVectors();
    }

    private void ram(String name, long start, long size) throws Exception {
        currentProgram.getMemory().createUninitializedBlock(name, toAddr(start), size, false)
            .setPermissions(true, true, false);
    }

    private void io(String name, long start, long size) throws Exception {
        MemoryBlock block = currentProgram.getMemory()
            .createUninitializedBlock(name, toAddr(start), size, false);
        block.setPermissions(true, true, false);
        block.setVolatile(true);
    }

    private void labelRegisters(Path header) throws Exception {
        Pattern define = Pattern.compile("^#define (CYREG_\\w+) 0x([0-9a-fA-F]+)u");
        for (String line : Files.readAllLines(header)) {
            Matcher m = define.matcher(line);
            if (!m.find() || m.group(1).endsWith("_MSIZE")) {
                continue;
            }
            Address address = toAddr(Long.parseLong(m.group(2), 16));
            if (address.getOffset() >= 0x40000000L || address.getOffset() < 0x1FFF8000L) {
                if (currentProgram.getMemory().contains(address)) {
                    createLabel(address, m.group(1), false, SourceType.IMPORTED);
                }
            }
        }
    }

    private void markVectors() throws Exception {
        Address table = toAddr(APPLICATION);
        createLabel(table, "vector_table", true, SourceType.ANALYSIS);
        for (int i = 0; i < VECTORS; i++) {
            Address slot = table.add(4L * i);
            createDWord(slot);
            long target = getInt(slot) & 0xFFFFFFFFL;
            if (i == 0 || (target & 1) == 0 || target < APPLICATION || target >= 0x40000) {
                continue;
            }
            Address entry = toAddr(target & ~1L);
            new DisassembleCommand(entry, null, true).applyTo(currentProgram, monitor);
            createFunction(entry, i == 1 ? "Reset_Handler" : String.format("vector_%02d", i));
        }
    }
}
