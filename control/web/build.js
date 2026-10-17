import { context } from "esbuild";
import { mkdirSync, readFileSync, watch, writeFileSync } from "node:fs";
import { dirname } from "node:path";

// --watch rebuilds the page on each source change, for the service's ENSEMBLE_WEB_PAGE mode.
const target = "../Sources/ensemble-control/Public/index.html";
const watching = process.argv.includes("--watch");

const write = {
  name: "page",
  setup(build) {
    build.onEnd(({ errors, outputFiles }) => {
      if (errors.length) return;
      const output = extension => outputFiles.find(file => file.path.endsWith(extension)).text;
      const page = readFileSync("index.html", "utf8")
        .replace("<!-- style -->", () => `<style>\n${output(".css")}</style>`)
        .replace("<!-- script -->", () => `<script>\n${output(".js")}</script>`);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, page);
      if (watching) console.log(`wrote ${target}`);
    });
  },
};

const build = await context({
  entryPoints: ["src/main.ts"],
  bundle: true,
  write: false,
  outdir: "out",
  format: "iife",
  target: "es2022",
  plugins: [write],
});
if (watching) {
  await build.watch();
  watch("index.html", () => build.rebuild().catch(() => {}));
} else {
  await build.rebuild();
  await build.dispose();
}
