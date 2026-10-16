import { bar, type Bar } from "../bar.ts";
import { h } from "../dom.ts";
import { toDb } from "../meters.ts";
import { BALANCE, FADER, PAN, balanceDb, clamp, gainParam } from "../params.ts";
import { description, get, set } from "../store.ts";
import { MIXES, channelName, enabled, inputPath, linkPath, pairable, partner, stereoFlag, strip,
         unitName } from "./channels.ts";
import { picker, toggle, type View } from "./controls.ts";
import { bus, clearKeys, dbfs, meterKey } from "./levels.ts";

export function row(view: View, unit: number[], color: string, open: boolean, onExpand: () => void) {
  const [channel] = unit;
  const { mix } = view;
  const name = unitName(unit);
  const element = h("div", { class: `row${open ? " open" : ""}` });
  element.append(
    h("button", { class: "more", "aria-expanded": String(open), "aria-label": `${name} details`, onclick: onExpand },
      chevron()),
    faderBar(view, strip(mix, channel, "fader"), { label: name + (unit.length > 1 ? " \u21c6" : ""), color,
                                                   aria: `${name} level` }, { channels: unit, scale: "post" }).el,
    toggle(view, [strip(mix, channel, "mute")], "M", "mute", `Mute ${name}`));
  if (mix === 1) element.append(toggle(view, [strip(1, channel, "solo")], "S", "solo", `Solo ${name}`));
  if (open) element.append(details(view, unit, name, color));
  return element;
}

type Options = { label: string; color: string; aria: string; small?: boolean; current?: boolean };
type Metered = { channels: number[]; scale: "post" | "bus" };

// The service writes the partner of a stereo pair, so a row writes only its first channel.
export function faderBar(view: View, path: string, options: Options, metered?: Metered, paths = [path]) {
  const keys = metered?.channels.map(channel => meterKey(channel, view.mix)) ?? [];
  const control = bar({
    ...options, param: FADER, meter: metered && { scale: metered.scale, sides: keys.length },
    clearClip: () => clearKeys(keys), change: value => set(Object.fromEntries(paths.map(each => [each, value]))),
  });
  view.watch(path, value => control.show(Number(value)));
  if (metered) {
    const position = metered.scale === "bus" ? bus : post(control, metered.channels, view.mix);
    view.meters.push({ bar: control, keys, position });
  }
  return control;
}

// The unit has no meter after a channel fader, so the UI calculates it from the input meter, the fader and, for
// a stereo pair, the balance.
function post(control: Bar, channels: number[], mix: number) {
  const [first] = channels;
  return (amplitude: number, side: number) => {
    if (!amplitude || control.value === 0) return 0;
    if (get(strip(mix, first, "mute")) === true || get(enabled(first)) === false) return 0;
    const balance = channels.length > 1 ? balanceDb(Number(get(strip(mix, first, "pan")) ?? 64), side) : 0;
    return FADER.toPos(clamp(600 + (toDb(amplitude) + (control.value - 600) / 10 + balance) * 10, 0, 720));
  };
}

function chevron() {
  const span = h("span");
  span.innerHTML = '<svg viewBox="0 0 12 12" width="14" height="14"><path d="M4 1.5 8.5 6 4 10.5" fill="none" ' +
                   'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  return span;
}

function details(view: View, unit: number[], name: string, color: string) {
  const [channel] = unit;
  const { mix } = view;
  const stereo = unit.length > 1;
  const pan = strip(mix, channel, "pan");
  const position = bar({
    param: stereo ? BALANCE : PAN, label: stereo ? "Balance" : "Pan", color, small: true,
    aria: `${name} ${stereo ? "balance" : "pan"}`, change: value => set({ [pan]: value }),
  });
  view.watch(pan, value => position.show(Number(value)));
  const toggles = h("div", { class: "toggles" }, toggle(view, [enabled(channel)], "On", "", `${name} on`));
  if (pairable(channel)) toggles.append(toggle(view, [stereoFlag(channel)], "Stereo", "", `${name} stereo`));
  if (mix === 1) toggles.append(toggle(view, [strip(1, channel, "soloSafe")], "Solo safe", "", `${name} solo safe`));
  const sends = h("div", { class: "section" }, h("h3", {}, `${name} in each mix`));
  for (const other of MIXES) {
    const level = faderBar(view, strip(other, channel, "fader"), {
      label: `Mix ${other}`, color, small: true, current: other === mix, aria: `${name} level in Mix ${other}`,
    });
    sends.append(h("div", { class: "send" }, level.el,
      toggle(view, [strip(other, channel, "mute")], "M", "mute", `Mute ${name} in Mix ${other}`)));
  }
  return h("div", { class: "detail" },
    inputControls(view, unit, name, color),
    h("div", { class: "section" }, h("h3", {}, `Mix ${mix}`), position.el, toggles,
      h("p", { class: "note" }, "On and Stereo apply to all four mixes. A Stereo change sets pan to center in all four mixes.")),
    sends);
}

// A stereo row writes both input channels, except Phase. A linked input pair shows one gain bar, because the unit
// applies a gain change to both channels of the pair.
function inputControls(view: View, unit: number[], name: string, color: string) {
  const prefixes = unit.map(inputPath).filter(prefix => prefix !== null);
  if (!prefixes.length) return null;
  const stereo = prefixes.length > 1;
  const paths = (control: string) => prefixes.map(prefix => `${prefix}/${control}`);
  const has = (control: string) => description(`${prefixes[0]}/${control}`) !== undefined;
  const section = h("div", { class: "section" }, h("h3", {}, "Input"));
  if (has("type")) {
    section.append(h("div", { class: "line" }, h("span", { class: "lbl" }, "Type"),
      picker(view, paths("type"), description(`${prefixes[0]}/type`)?.choices ?? [], `${name} type`)));
  }
  const link = linkPath(unit[0]);
  const gains = prefixes.map(gainPath);
  const shared = stereo && link !== null && get(link) === true && gains[0] !== null &&
                 gains[0].split("/").pop() === gains[1]?.split("/").pop();
  const single = shared || gains.every(path => path === null);
  (single ? [gains[0]] : gains).forEach((path, index) => {
    const side = stereo && !single ? (index ? " R" : " L") : "";
    if (path === null) {
      section.append(h("p", { class: "note" }, "Line level has no preamp gain."));
      return;
    }
    const keys = (single ? unit : [unit[index]]).map(channel => meterKey(channel, view.mix));
    const gain = bar({
      param: gainParam(description(path)?.max ?? 0), label: `Gain${side}`, color, small: true,
      aria: `${name}${side} gain`, meter: { scale: "dbfs", sides: keys.length },
      clearClip: () => clearKeys(keys), change: value => set({ [path]: value }),
    });
    view.watch(path, value => gain.show(Number(value)));
    view.meters.push({ bar: gain, keys, position: dbfs, peakText: true });
    section.append(gain.el);
  });
  const toggles = h("div", { class: "toggles" });
  if (has("phantom")) toggles.append(toggle(view, paths("phantom"), "48V", "", `${name} 48V`));
  if (has("phase")) {
    prefixes.forEach((prefix, index) => {
      const side = stereo ? (index ? " R" : " L") : "";
      toggles.append(toggle(view, [`${prefix}/phase`], `Phase${side}`, "", `${name} phase${side}`));
    });
  }
  if (has("highPass")) toggles.append(toggle(view, paths("highPass"), "High-pass", "", `${name} high-pass`));
  if (has("softLimit")) toggles.append(toggle(view, paths("softLimit"), "Soft limit", "", `${name} soft limit`));
  if (has("insert")) toggles.append(toggle(view, paths("insert"), "Insert", "", `${name} insert`));
  if (link !== null) {
    const text = stereo ? "Link gain" : `Link gain with ${channelName(partner(unit[0]))}`;
    toggles.append(toggle(view, [link], text, "", `${name} gain link`));
  }
  if (toggles.children.length) section.append(toggles);
  return section;
}

// The unit applies mic gain only to the Mic type and instrument gain only to the Instrument type.
function gainPath(prefix: string) {
  if (description(`${prefix}/type`) === undefined) return `${prefix}/gain`;
  return ({ Mic: `${prefix}/micGain`, Instrument: `${prefix}/instrumentGain` } as Record<string, string>)
    [String(get(`${prefix}/type`))] ?? null;
}
