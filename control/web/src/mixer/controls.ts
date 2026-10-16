import { h } from "../dom.ts";
import { get, set, type Value } from "../store.ts";
import type { Meter, Mini } from "./levels.ts";

// One render of the mixer. A new render drops the watches and meters of the last one.
export type View = {
  mix: number;
  watch(path: string, update: (value: Value) => void): void;
  meters: Meter[];
  minis: Mini[];
};

export function toggle(view: View, paths: string[], text: string, className: string, label: string) {
  const button = h("button", { class: className, "aria-label": label, onclick: () => {
    const next = !paths.every(path => get(path) === true);
    set(Object.fromEntries(paths.map(path => [path, next])));
  } }, text);
  const show = () => {
    const on = paths.filter(path => get(path) === true).length;
    button.setAttribute("aria-pressed", on === 0 ? "false" : on === paths.length ? "true" : "mixed");
  };
  paths.forEach(path => view.watch(path, show));
  return button;
}

export function picker(view: View, paths: string[], choices: string[], label: string) {
  const select = h("select", { "aria-label": label, onchange: () => {
    set(Object.fromEntries(paths.map(path => [path, select.value])));
  } });
  const mixed = new Option("Mixed", "");
  mixed.disabled = true;
  select.append(mixed, ...choices.map(choice => new Option(choice, choice)));
  const show = () => {
    const values = new Set(paths.map(path => get(path)));
    select.value = values.size === 1 ? String([...values][0]) : "";
  };
  paths.forEach(path => view.watch(path, show));
  return select;
}
