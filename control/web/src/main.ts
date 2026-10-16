import "./base.css";
import "./tabs/tabs.css";
import type { Bank } from "./meters.ts";
import { receive } from "./mixer/levels.ts";
import { start as startMixer } from "./mixer/mixer.ts";
import { call, connect } from "./rpc.ts";
import { describe, load, type Description, type Value } from "./store.ts";
import * as meters from "./tabs/meters.ts";
import { start as startMonitor } from "./tabs/monitor.ts";
import * as presets from "./tabs/presets.ts";
import { layout } from "./tabs/settings.ts";

// main.swift fills in this object in the page.
type Config = { rpcPort: number; monitorPort: number; captureNames: string[] };
const config = (window as unknown as { ensemble: Config }).ensemble;

const tabs: Record<string, string> = {
  mixer: "Mixer", meters: "Meters", inputs: "Inputs", outputs: "Outputs", routing: "Routing", device: "Device",
  presets: "Presets", monitor: "Monitor",
};
const header = document.querySelector("header")!;
const status = document.getElementById("status")!;
let described = false;

for (const [id, name] of Object.entries(tabs)) {
  document.getElementById("tabs")!.append(Object.assign(document.createElement("a"), { href: `#${id}`, textContent: name }));
}

function showTab() {
  const tab = tabs[location.hash.slice(1)] ? location.hash.slice(1) : "mixer";
  document.querySelectorAll(".view").forEach(view => view.classList.toggle("shown", view.id === tab));
  document.querySelectorAll<HTMLAnchorElement>("nav a").forEach(link => link.classList.toggle("shown", link.hash === `#${tab}`));
  document.getElementById("mixbar")!.hidden = tab !== "mixer";
}

window.onhashchange = showTab;
showTab();
new ResizeObserver(() => document.documentElement.style.setProperty("--head", `${header.offsetHeight}px`))
  .observe(header);
meters.layout();
startMonitor(config.monitorPort, config.captureNames);

function showStatus(text: string) {
  status.title = text;
  status.setAttribute("aria-label", text);
  status.classList.toggle("live", text === "connected");
}

connect(`ws://${location.hostname}:${config.rpcPort}`, {
  async open() {
    showStatus("connected");
    if (!described) {
      const list = await call<Description[]>("describe");
      describe(list);
      layout(list);
      startMixer();
      described = true;
    }
    load(await call<Record<string, Value>>("get"));
    presets.show(await call<string[]>("presets.list"));
  },
  close() {
    showStatus("reconnecting");
  },
  notify(method, params) {
    if (method === "changed") load(params as Record<string, Value>);
    else if (method === "meters") {
      meters.show(params as Bank);
      receive(params as Bank);
    } else if (method === "presets") presets.show((params as { names: string[] }).names);
  },
});
