import "./bar.css";
import { h } from "./dom.ts";
import { clamp, type Param } from "./params.ts";

// "post" is a channel level after its fader, "dbfs" is an input level, and "bus" is a mix output.
export type Scale = "post" | "dbfs" | "bus";

// Positions from 0 to 1 on the bar.
export type Band = { peak: number; avg: number };

export type BarOptions = {
  param: Param;
  label: string;
  color: string;
  aria: string;
  small?: boolean;
  current?: boolean;
  meter?: { scale: Scale; sides: number };
  change(value: number): void;
  clearClip?(): void;
};

export type Bar = {
  el: HTMLElement;
  readonly value: number;
  show(value: number): void;
  paint(bands: Band[], hold: number, clipped: boolean, note: string): void;
};

const precision = (offset: number) => offset > 120 ? 0.1 : offset > 60 ? 0.25 : 1;

export function bar(options: BarOptions): Bar {
  const { param, meter, small = false } = options;
  const el = h("div", {
    class: `ctl${small ? " sm" : ""}${meter ? ` metered scale-${meter.scale}` : ""}${options.current ? " current" : ""}`,
    tabindex: 0, role: "slider", "aria-label": options.aria, "aria-valuemin": param.min, "aria-valuemax": param.max,
    style: `--c:${options.color}`,
  });
  const layer = (extra: string) =>
    h("div", { class: `t${extra}` }, h("span", { class: "name" }, options.label), h("span", { class: "v" }));
  const layers = [layer(""), layer(" dark")];
  const outputs = layers.map(element => element.querySelector(".v")!);
  const badge = h("div", { class: "badge" });
  const cap = h("i", { class: "cap", hidden: true });
  const stereo = (meter?.sides ?? 0) > 1;
  const bands = Array.from({ length: meter?.sides ?? 0 }, (_, index) => {
    const style = stereo ? `bottom:${4 + (1 - index) * 7}px;height:5px` : `bottom:4px;height:${small ? 6 : 9}px`;
    return { peak: h("i", { class: "band peak", style }), avg: h("i", { class: "band avg", style }) };
  });
  const hold = h("i", { class: "hold", style: `bottom:4px;height:${stereo ? 12 : small ? 6 : 9}px` });
  el.append(h("div", { class: "fill" }));
  if (meter) el.append(...bands.flatMap(band => [band.peak, band.avg]), hold);
  el.append(h("div", { class: "unity", style: `--u:${param.toPos(param.home)}` }), ...layers, badge);
  if (meter) el.append(cap);

  let value = param.home, text = "", note = "", fine = "", dragging = false, editing = false;

  function place(next: number) {
    value = next;
    const position = param.toPos(value);
    const [a, b] = param.bipolar ? [Math.min(0.5, position), Math.max(0.5, position)] : [0, position];
    el.style.setProperty("--a", String(a));
    el.style.setProperty("--b", String(b));
    el.setAttribute("aria-valuenow", String(value));
    el.setAttribute("aria-valuetext", param.format(value));
    draw();
  }

  function draw() {
    const next = param.format(value) + note;
    if (next !== text) {
      text = next;
      for (const output of outputs) output.textContent = next;
    }
    badge.textContent = fine;
  }

  function input(next: number) {
    next = clamp(Math.round(next), param.min, param.max);
    if (next === value) return;
    place(next);
    options.change(next);
  }

  function reset() {
    input(param.home);
    navigator.vibrate?.(10);
  }

  // A tap never changes a value. A second tap within 320 ms opens the text field.
  let drag: { x: number; y: number; moved: boolean; factor: number; start: number; origin: number; width: number;
              edge: boolean } | null = null;
  let press = 0, lastTap = -Infinity;
  el.oncontextmenu = event => event.preventDefault();
  el.onpointerdown = event => {
    if (editing) return;
    el.setPointerCapture(event.pointerId);
    drag = { x: event.clientX, y: event.clientY, moved: false, factor: 1, start: value, origin: value,
             width: el.clientWidth, edge: event.clientX > el.getBoundingClientRect().right - 28 };
    if (event.pointerType !== "mouse") {
      press = setTimeout(() => {
        if (drag && !drag.moved) reset();
        end();
      }, 550);
    }
  };
  el.onpointermove = event => {
    if (!drag) return;
    if (!drag.moved) {
      if (Math.abs(event.clientX - drag.x) <= 3) return;
      drag.moved = dragging = true;
      clearTimeout(press);
    }
    const factor = event.shiftKey ? 0.1 : event.pointerType === "touch" ? precision(Math.abs(event.clientY - drag.y)) : 1;
    if (factor !== drag.factor) Object.assign(drag, { factor, x: event.clientX, start: value });
    let next = clamp(Math.round(param.fromPos(param.toPos(drag.start) + (event.clientX - drag.x) / drag.width * factor)),
                     param.min, param.max);
    if (factor === 1 && Math.abs(param.toPos(next) - param.toPos(param.home)) * drag.width < 6) next = param.home;
    if (next === param.home && value !== param.home) navigator.vibrate?.(5);
    fine = factor < 1 ? `fine \u00d7${factor}` : "";
    input(next);
    draw();
  };
  el.onpointerup = event => {
    if (!drag) return;
    clearTimeout(press);
    if (!drag.moved) {
      if (event.altKey) {
        reset();
      } else if (drag.edge && !cap.hidden) {
        options.clearClip?.();
      } else if (event.timeStamp - lastTap < 320) {
        lastTap = -Infinity;
        edit();
      } else {
        lastTap = event.timeStamp;
      }
    }
    end();
  };
  el.onpointercancel = () => {
    if (!drag) return;
    clearTimeout(press);
    if (drag.moved) input(drag.origin);
    end();
  };
  el.onkeydown = event => {
    if (editing) return;
    if (event.key === "Enter") {
      event.preventDefault();
      edit();
    } else if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      reset();
    } else {
      const move = ({ ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 } as Record<string, number>)[event.key];
      const page = ({ PageUp: 10, PageDown: -10 } as Record<string, number>)[event.key];
      if (!move && !page) return;
      event.preventDefault();
      input(value + (page ? page * param.step : move * (event.shiftKey ? param.fine : param.step)));
    }
  };

  function end() {
    drag = null;
    dragging = false;
    fine = "";
    draw();
  }

  function edit() {
    editing = true;
    const field = h("input", { class: "edit", value: param.raw(value), "aria-label": `${options.aria} value`,
                               autocomplete: "off", autocapitalize: "off", spellcheck: "false", enterkeyhint: "done" });
    let open = true;
    const apply = () => {
      const parsed = param.parse(field.value);
      if (parsed === null) return false;
      input(parsed);
      return true;
    };
    const close = (commit: boolean) => {
      if (!open) return;
      if (commit && !apply()) {
        field.classList.add("bad");
        field.focus();
        return;
      }
      open = editing = false;
      field.remove();
      el.focus({ preventScroll: true });
    };
    field.onpointerdown = event => event.stopPropagation();
    field.onkeydown = event => {
      event.stopPropagation();
      if (event.key === "Enter") close(true);
      if (event.key === "Escape") close(false);
    };
    field.onblur = () => {
      if (!open) return;
      apply();
      close(false);
    };
    el.append(field);
    field.focus();
    field.select();
  }

  return {
    el,
    get value() {
      return value;
    },
    show(next) {
      if (!dragging) place(next);
    },
    paint(levels, peak, clipped, extra) {
      levels.forEach((level, index) => {
        bands[index].peak.style.width = `${level.peak * 100}%`;
        bands[index].avg.style.width = `${level.avg * 100}%`;
      });
      hold.hidden = !peak;
      hold.style.left = `calc(${peak * 100}% - 2px)`;
      cap.hidden = !clipped;
      note = extra;
      draw();
    },
  };
}
