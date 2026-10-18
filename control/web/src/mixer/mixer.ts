import "./mixer.css";
import { h } from "../dom.ts";
import { get, set, watch, watchAll } from "../store.ts";
import { mixName, mixSource } from "../names.ts";
import { appNames, fixedPair, homeOf, options, pairsOf, place } from "./capture.ts";
import { MIXES, OUTPUTS, OUTPUT_COLOR, enabled, groups, strip, units, type Group } from "./channels.ts";
import { toggle, type View } from "./controls.ts";
import { anyClipped, clearAll, meterKey, paint, paintMini, settleAll } from "./levels.ts";
import { faderBar, row } from "./row.ts";

type Prefs = { mix: number; hideOff: boolean; collapsed: string[] };
type Section = { units: number[][]; stat: HTMLElement; rows: { element: HTMLElement; channel: number }[] };
type Task = "render" | "decorate";

const PREFS = "mixer-layout";
const prefs: Prefs = { mix: 1, hideOff: false, collapsed: [], ...load() };
const open = new Set<number>();
const container = document.getElementById("groups")!;
const mixTabs = document.getElementById("mix-tabs")!;
const preFader = document.getElementById("pre-fader")!;
const clearSolo = document.getElementById("clear-solo")!;
const clearClips = document.getElementById("clear-clips")!;
const hideOff = document.getElementById("hide-off")!;
let view: View;
let sections: Section[] = [];
let unwatch: (() => void)[] = [];
let queued: Task | null = null;
let captureNames: string[] = [];

function load(): Partial<Prefs> {
  try {
    return JSON.parse(localStorage.getItem(PREFS) ?? "{}");
  } catch {
    return {};
  }
}

// A stereo flag, an input type or a gain link changes which rows and bars exist. Mutes, solos and enables
// change only the row styles and the group stats.
export function start(names: string[]) {
  captureNames = names;
  for (const mix of MIXES) {
    const name = mixName(mixSource(mix));
    mixTabs.append(h("button", { "data-mix": mix, "aria-label": name, title: name, onclick: () => update({ mix }) },
      h("span", { class: "word" }, "Mix "), String(mix)));
  }
  hideOff.onclick = () => update({ hideOff: !prefs.hideOff });
  preFader.onclick = () => set({ [`mixers/${prefs.mix}/preFader`]: get(`mixers/${prefs.mix}/preFader`) !== true });
  clearSolo.onclick = () => set(Object.fromEntries(soloed().map(channel => [strip(1, channel, "solo"), false])));
  clearClips.onclick = clearAll;
  watchAll(path => {
    if (/\/stereo$|^inputs\/.*\/(type|link)$|^capture\//.test(path)) schedule("render");
    else if (/^mixers\/(channels\/\d+\/enabled|\d+\/channels\/\d+\/(solo|soloSafe|mute))$/.test(path)) schedule("decorate");
  });
  render();
  requestAnimationFrame(frame);
}

function update(changes: Partial<Prefs>) {
  Object.assign(prefs, changes);
  localStorage.setItem(PREFS, JSON.stringify(prefs));
  render();
}

function schedule(task: Task) {
  if (queued === null) {
    queueMicrotask(() => {
      const next = queued;
      queued = null;
      next === "render" ? render() : decorate();
    });
  }
  if (queued !== "render") queued = task;
}

function render() {
  unwatch.forEach(stop => stop());
  unwatch = [];
  sections = [];
  view = { mix: prefs.mix, watch: (path, update) => { unwatch.push(watch(path, update)); }, meters: [], minis: [] };
  const { mix } = view;
  mixTabs.querySelectorAll("button").forEach(button =>
    button.setAttribute("aria-pressed", String(Number(button.dataset.mix) === mix)));
  hideOff.setAttribute("aria-pressed", String(prefs.hideOff));
  preFader.hidden = mix === 1;
  if (mix > 1) view.watch(`mixers/${mix}/preFader`, value => preFader.setAttribute("aria-pressed", String(value)));
  container.className = `groups${prefs.hideOff ? " hide-off" : ""}${mix === 1 ? "" : " no-solo"}`;
  container.replaceChildren(...groups.map(renderGroup));
  renderOutput();
  decorate();
}

function renderGroup(group: Group) {
  const collapsed = prefs.collapsed.includes(group.id);
  const section: Section = { units: units(group), stat: h("span", { class: "gstat" }), rows: [] };
  sections.push(section);
  const mini = h("span", { class: "gmeters", "aria-hidden": "true", style: `--c:${group.color}` });
  for (const unit of section.units) {
    const level = h("b");
    const cell = h("i", {}, level);
    mini.append(cell);
    view.minis.push({ keys: unit.map(channel => meterKey(channel, view.mix)), cell, level });
  }
  const head = h("button", { class: "ghead", "aria-expanded": String(!collapsed), onclick: () => update({
    collapsed: collapsed ? prefs.collapsed.filter(id => id !== group.id) : [...prefs.collapsed, group.id],
  }) }, h("span", { class: "caret" }, "\u25be"), h("span", { class: "title" }, group.title), mini, section.stat);
  const rows = h("div", { class: "rows", hidden: collapsed });
  if (!collapsed) {
    for (const unit of section.units) {
      const [channel] = unit;
      const element = row(view, unit, group.color, open.has(channel), () => {
        open.has(channel) ? open.delete(channel) : open.add(channel);
        render();
      });
      section.rows.push({ element, channel });
      rows.append(element);
    }
  }
  return h("section", { class: "group" }, head, rows);
}

// The mix output has no host pair, so the output bar and its mute write both channels.
function renderOutput() {
  const { mix } = view;
  const [left, right] = OUTPUTS.map(channel => strip(mix, channel, "fader"));
  document.getElementById("masters")!.replaceChildren(
    faderBar(view, left, { label: `Mix ${mix} out \u21c6`, color: OUTPUT_COLOR, aria: `Mix ${mix} output level` },
             { channels: OUTPUTS, scale: "bus" }, [left, right]).el,
    toggle(view, OUTPUTS.map(channel => strip(mix, channel, "mute")), "M", "mute", `Mute Mix ${mix} output`),
    ...destination(mix));
}

// A mix takes the place of an input on the computer, so the note names the input that the computer loses.
function destination(mix: number) {
  const pairs = pairsOf(mix, get);
  const select = h("select", { "aria-label": `Send Mix ${mix} to the computer`,
                               onchange: () => set(place(mix, select.value || null, get)) });
  select.append(...options(mix, get).map(({ value, text }) => new Option(text, value)));
  if (pairs.length > 1) {
    const several = new Option("Several channels", "several");
    several.disabled = true;
    select.prepend(several);
  }
  select.value = pairs.length > 1 ? "several" : pairs[0] ?? "";
  const listed = pairs.length === 1 ? pairs[0] : pairs.length === 0 ? fixedPair(mix) : undefined;
  const names = listed && appNames(listed, captureNames);
  const note = pairs.length > 1 ? `Mix ${mix} is on ${pairs.length} channel pairs. The Routing tab lists them.`
    : [names && `Apps list Mix ${mix} as ${names}.`,
       pairs.length && `${homeOf(pairs[0])} still feeds the mixes, but not the computer.`].filter(Boolean).join(" ");
  const line = h("label", { class: "dest" }, h("span", { class: "lbl" }, "To computer"), select);
  return note ? [line, h("p", { class: "note dest" }, note)] : [line];
}

const soloed = () => sections.flatMap(section => section.units.map(([channel]) => channel))
  .filter(channel => get(strip(1, channel, "solo")) === true);

function decorate() {
  const { mix } = view;
  const solos = soloed();
  clearSolo.hidden = mix !== 1 || solos.length === 0;
  clearSolo.textContent = `Solo ${solos.length} \u2715`;
  for (const section of sections) {
    let on = 0, hidden = 0, muted = 0, soloing = 0;
    for (const [channel] of section.units) {
      const enable = get(enabled(channel)) === true;
      on += Number(enable);
      hidden += Number(prefs.hideOff && !enable);
      muted += Number(get(strip(mix, channel, "mute")) === true);
      soloing += Number(mix === 1 && get(strip(1, channel, "solo")) === true);
    }
    section.stat.replaceChildren(...[
      muted ? h("span", { class: "m" }, `M ${muted}`) : null,
      soloing ? h("span", { class: "s" }, `S ${soloing}`) : null,
      h("span", {}, hidden ? `${on} on \u00b7 ${hidden} off hidden` : `${on}/${section.units.length} on`),
    ].filter(child => child !== null));
    for (const { element, channel } of section.rows) {
      element.classList.toggle("off", get(enabled(channel)) === false);
      element.classList.toggle("implied", mix === 1 && solos.length > 0 && get(strip(1, channel, "solo")) !== true &&
                                          get(strip(1, channel, "soloSafe")) !== true);
    }
  }
}

let last = performance.now();

function frame(now: number) {
  settleAll((now - last) / 1000, now);
  last = now;
  view.meters.forEach(paint);
  view.minis.forEach(paintMini);
  clearClips.hidden = !anyClipped();
  requestAnimationFrame(frame);
}
