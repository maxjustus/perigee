import { call } from "../rpc.ts";

const names = document.getElementById("preset-names") as HTMLSelectElement;
const nameField = document.getElementById("preset-name") as HTMLInputElement;
const status = document.getElementById("preset-status") as HTMLOutputElement;

export function show(list: string[]) {
  const selected = names.value;
  names.replaceChildren(...list.map(name => new Option(name, name)));
  if (list.includes(selected)) names.value = selected;
}

async function presetCall<T>(method: string, name: string, done: (result: T) => void | Promise<void>) {
  try {
    await done(await call<T>(method, { name }));
  } catch (error) {
    status.value = (error as Error).message;
  }
}

document.getElementById("preset-save")!.onclick = () => {
  const name = nameField.value.trim();
  const taken = [...names.options].some(option => option.value === name);
  if (!name || (taken && !confirm(`Replace ${name}?`))) return;
  presetCall("presets.save", name, async () => {
    show(await call<string[]>("presets.list"));
    names.value = name;
    nameField.value = "";
    status.value = `Saved ${name}`;
  });
};
document.getElementById("preset-load")!.onclick = () => {
  const name = names.value;
  if (!name || !confirm(`Load ${name}? This sets every saved value on the unit.`)) return;
  presetCall<{ skipped: string[] }>("presets.load", name, ({ skipped }) => {
    status.value = skipped.length ? `Loaded ${name}. Skipped: ${skipped.join(", ")}` : `Loaded ${name}`;
  });
};
document.getElementById("preset-delete")!.onclick = () => {
  const name = names.value;
  if (!name || !confirm(`Delete ${name}?`)) return;
  presetCall("presets.delete", name, () => { status.value = `Deleted ${name}`; });
};
