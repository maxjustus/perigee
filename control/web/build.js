import { build } from "esbuild";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const target = "../Sources/ensemble-control/Public/index.html";
const { outputFiles } = await build({
  entryPoints: ["src/main.ts"],
  bundle: true,
  write: false,
  outdir: "out",
  format: "iife",
  target: "es2022",
});
const output = extension => outputFiles.find(file => file.path.endsWith(extension)).text;
const page = readFileSync("index.html", "utf8")
  .replace("<!-- style -->", () => `<style>\n${output(".css")}</style>`)
  .replace("<!-- script -->", () => `<script>\n${output(".js")}</script>`);
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, page);
