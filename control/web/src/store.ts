import { call } from "./rpc.ts";

export type Value = boolean | number | string;

export type Description = {
  path: string;
  kind: "bool" | "int" | "choice";
  min?: number;
  max?: number;
  choices?: string[];
};

type Update = (value: Value) => void;

const descriptions = new Map<string, Description>();
const values = new Map<string, Value>();
const watchers = new Map<string, Set<Update>>();
const listeners: ((path: string) => void)[] = [];
let queued: Record<string, Value> | null = null;

export function describe(list: Description[]) {
  for (const description of list) descriptions.set(description.path, description);
}

export const description = (path: string) => descriptions.get(path);
export const get = (path: string) => values.get(path);

export function load(changes: Record<string, Value>) {
  for (const [path, value] of Object.entries(changes)) {
    if (values.get(path) === value) continue;
    values.set(path, value);
    for (const update of watchers.get(path) ?? []) update(value);
    for (const listener of listeners) listener(path);
  }
}

export function watch(path: string, update: Update): () => void {
  const set = watchers.get(path) ?? new Set();
  watchers.set(path, set);
  set.add(update);
  const value = values.get(path);
  if (value !== undefined) update(value);
  return () => set.delete(update);
}

export function watchAll(listener: (path: string) => void) {
  listeners.push(listener);
}

export function set(changes: Record<string, Value>) {
  if (!queued) {
    queued = {};
    requestAnimationFrame(flush);
  }
  Object.assign(queued, changes);
}

function flush() {
  const changes = queued ?? {};
  queued = null;
  call("set", changes).catch(() => {
    for (const path of Object.keys(changes)) {
      const value = values.get(path);
      if (value === undefined) continue;
      for (const update of watchers.get(path) ?? []) update(value);
    }
  });
}
