import { mixName } from "../names.ts";
import { set, watch, type Description } from "../store.ts";

export function layout(parameters: Description[]) {
  const groups = new Map<string, Description[]>();
  for (const parameter of parameters) {
    if (parameter.path.startsWith("mixers/")) continue;
    const group = parameter.path.slice(0, parameter.path.lastIndexOf("/"));
    groups.set(group, [...(groups.get(group) ?? []), parameter]);
  }
  for (const [group, list] of groups) {
    const tab = ({ inputs: "inputs", outputs: "outputs", routing: "routing", capture: "routing" } as
      Record<string, string>)[group.split("/")[0]]
      ?? "device";
    const numbered = group.match(/^(.*)\/(\d+)$/);
    const siblings = numbered ? [...groups.keys()].filter(other => other.startsWith(`${numbered[1]}/`)).length : 0;
    if (list.length === 1) {
      addRow(card(tab, `${tab}/more`, "More"), `${title(group)} ${label(list[0]).toLowerCase()}`, list);
    } else if (numbered && list.length <= 2 && siblings >= 3) {
      addRow(card(tab, numbered[1], title(numbered[1])), numbered[2], list);
    } else {
      const section = card(tab, group, title(group));
      const rows = Object.fromEntries(list.map(parameter =>
        [parameter.path.slice(group.length + 1), addRow(section, label(parameter), [parameter])]));
      if (rows.type) followType(`${group}/type`, rows);
    }
  }
  const more = document.querySelectorAll("[id$='/more']");
  more.forEach(section => section.parentElement!.append(section));
  document.querySelector("#card-capture h2")?.after(Object.assign(document.createElement("p"), { className: "tip",
    textContent: "Each pair carries its source to the computer in place of the default input. Apps keep the " +
                 "default channel names. Channels 31-34 always carry Mix 1 and Mix 4." }));
}

// The unit applies mic gain only to the Mic type and instrument gain only
// to the Instrument type (NOTES-vendor-driver.md 5.8).
function followType(path: string, rows: Record<string, HTMLElement>) {
  watch(path, type => {
    if (rows.micGain) rows.micGain.hidden = type !== "Mic";
    if (rows.instrumentGain) rows.instrumentGain.hidden = type !== "Instrument";
  });
}

const words: Record<string, string> = {
  spdif: "S/PDIF", frontMic: "Front mic", attenuation: "Volume", phantom: "48V", micGain: "Gain",
  instrumentGain: "Gain",
};

function human(segment: string) {
  if (words[segment]) return words[segment];
  const spaced = segment.replace(/([a-z])([A-Z0-9])/g, "$1 $2");
  return spaced[0].toUpperCase() + spaced.slice(1).toLowerCase();
}

function title(group: string) {
  const rest = group.split("/").slice(1);
  if (rest.length) return rest.map(human).join(" ");
  return ({ outputs: "Speakers", routing: "Output sources", capture: "Computer inputs" } as Record<string, string>)[group]
    ?? human(group);
}

function label(parameter: Description) {
  const segment = parameter.path.slice(parameter.path.lastIndexOf("/") + 1);
  return parameter.path.startsWith("capture/") ? `Channels ${segment}` : human(segment);
}

function card(tab: string, group: string, heading: string) {
  let section = document.getElementById(`card-${group}`);
  if (!section) {
    section = Object.assign(document.createElement("section"), { id: `card-${group}` });
    section.append(Object.assign(document.createElement("h2"), { textContent: heading }));
    document.getElementById(tab)!.append(section);
  }
  return section;
}

const tips: Record<string, string> = {
  wordClockTermination: "Puts a 75 Ω load on the word clock input. Turn on if this unit is the last device on " +
    "the word clock cable. Turn off if a T-connector passes the clock on to another device.",
  lockHome: "Keeps the front panel display on its home screen.",
  matchUnityGain: "Sets the guitar output level to the guitar input level, for re-amping.",
  softLimit: "Rounds off peaks in the analog stage before the A/D converter, to prevent clipping.",
  phase: "Inverts the polarity of this input.",
  highPass: "Cuts low-frequency rumble. Applies only when the type is Mic or Instrument.",
  link: "A gain change on one channel of the pair also changes the other channel.",
  insert: "Sends this input through the rear Insert Send and Return jacks.",
};

function addRow(section: HTMLElement, name: string, parameters: Description[]) {
  const row = Object.assign(document.createElement("div"), { className: "row" });
  row.append(Object.assign(document.createElement("span"), { className: "name", textContent: name }));
  for (const parameter of parameters) {
    const text = parameters.length > 1 ? label(parameter) : name;
    if (parameter.kind === "bool") {
      const button = toggle(parameter.path);
      button.setAttribute("aria-label", text);
      row.append(button);
    } else if (parameter.kind === "choice") {
      const select = picker(parameter.path, parameter.choices ?? []);
      select.setAttribute("aria-label", text);
      row.append(select);
    } else {
      row.append(...slider(parameter.path, parameter.min ?? 0, parameter.max ?? 0, text, format(parameter)));
    }
  }
  const tip = parameters.length === 1 && tips[parameters[0].path.split("/").pop()!];
  if (tip) addTip(row, name, tip);
  section.append(row);
  return row;
}

function addTip(row: HTMLElement, name: string, tip: string) {
  const text = Object.assign(document.createElement("p"), { className: "tip", textContent: tip, hidden: true });
  const help = Object.assign(document.createElement("button"), { className: "help", textContent: "?" });
  help.setAttribute("aria-label", `About ${name}`);
  help.setAttribute("aria-expanded", "false");
  help.onclick = () => {
    text.hidden = !text.hidden;
    help.setAttribute("aria-expanded", String(!text.hidden));
  };
  row.querySelector(".name")!.append(help);
  row.append(text);
}

function format(parameter: Description): (value: number) => string {
  const name = parameter.path.slice(parameter.path.lastIndexOf("/") + 1);
  if (name === "attenuation") return v => v === 0 ? "0 dB" : `−${v} dB`;
  if (name === "trim") return v => v === 0 ? "0.0 dB" : `−${(v / 10).toFixed(1)} dB`;
  if (/gain$/i.test(name)) return v => `${v} dB`;
  return v => `${v}`;
}

function toggle(path: string) {
  const button = Object.assign(document.createElement("button"), { className: "switch" });
  button.setAttribute("aria-pressed", "false");
  button.onclick = () => set({ [path]: button.getAttribute("aria-pressed") !== "true" });
  watch(path, value => button.setAttribute("aria-pressed", String(value)));
  return button;
}

function picker(path: string, choices: string[]) {
  const select = document.createElement("select");
  select.append(...choices.map(choice => new Option(mixName(choice), choice)));
  select.onchange = () => set({ [path]: select.value });
  watch(path, value => { select.value = String(value); });
  return select;
}

// A tap must never jump a level, so a slider moves only by a relative drag.
function slider(path: string, min: number, max: number, label: string, format: (value: number) => string) {
  const element = Object.assign(document.createElement("div"), { className: "slider", tabIndex: 0 });
  const thumb = Object.assign(document.createElement("div"), { className: "thumb" });
  const output = document.createElement("output");
  element.setAttribute("role", "slider");
  element.setAttribute("aria-label", label);
  element.setAttribute("aria-valuemin", String(min));
  element.setAttribute("aria-valuemax", String(max));
  element.append(thumb);
  let value = min;
  let drag: { start: number; from: number; moved: boolean; span: number } | null = null;

  const place = (next: number) => {
    value = Math.round(Math.min(max, Math.max(min, next)));
    element.style.setProperty("--at", String((value - min) / (max - min)));
    element.setAttribute("aria-valuenow", String(value));
    element.setAttribute("aria-valuetext", format(value));
    output.value = format(value);
  };
  const change = (next: number) => {
    const before = value;
    place(next);
    if (value !== before) set({ [path]: value });
  };

  element.onpointerdown = event => {
    element.setPointerCapture(event.pointerId);
    drag = { start: event.clientX, from: value, moved: false, span: element.clientWidth };
  };
  element.onpointermove = event => {
    if (!drag) return;
    const moved = event.clientX - drag.start;
    if (Math.abs(moved) > 3) drag.moved = true;
    if (drag.moved) change(drag.from + moved / drag.span * (max - min));
  };
  element.onpointerup = () => {
    drag = null;
  };
  element.onpointercancel = () => {
    if (drag) change(drag.from);
    drag = null;
  };
  element.onkeydown = event => {
    const steps = ({ ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1, PageUp: 10, PageDown: -10 } as
      Record<string, number>)[event.key];
    if (!steps) return;
    event.preventDefault();
    change(value + steps);
  };
  watch(path, next => { if (!drag) place(Number(next)); });
  place(min);
  return [output, element];
}
