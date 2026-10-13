// Writes the decompiled C of every function and a function index.
// Arguments: <out dir>
// @category Ensemble

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import java.io.PrintWriter;
import java.nio.file.Path;

public class ExportDecompiled extends GhidraScript {
    @Override
    public void run() throws Exception {
        Path out = Path.of(getScriptArgs()[0]);
        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        options.grabFromProgram(currentProgram);
        options.setRespectReadOnly(true);
        decompiler.setOptions(options);
        decompiler.openProgram(currentProgram);
        try (PrintWriter c = new PrintWriter(out.resolve("decompiled.c").toFile());
             PrintWriter index = new PrintWriter(out.resolve("functions.tsv").toFile())) {
            index.println("entry\tname\tbytes\tcallers\tcallees");
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                index.printf("%s\t%s\t%d\t%d\t%d%n", f.getEntryPoint(), f.getName(),
                    f.getBody().getNumAddresses(), f.getCallingFunctions(monitor).size(),
                    f.getCalledFunctions(monitor).size());
                DecompileResults r = decompiler.decompileFunction(f, 60, monitor);
                c.printf("// %s %s%n", f.getEntryPoint(), f.getName());
                c.println(r.decompileCompleted() ? r.getDecompiledFunction().getC()
                    : "// decompile failed: " + r.getErrorMessage());
            }
        } finally {
            decompiler.dispose();
        }
    }
}
