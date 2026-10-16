export type Handlers = {
  open(): void;
  close(): void;
  notify(method: string, params: unknown): void;
};

type Pending = { resolve(result: unknown): void; reject(error: Error): void };

const pending = new Map<number, Pending>();
let socket: WebSocket | null = null;
let nextId = 1;

export function connect(url: string, handlers: Handlers) {
  const current = new WebSocket(url);
  socket = current;
  current.onopen = () => handlers.open();
  current.onmessage = event => {
    const message = JSON.parse(event.data);
    const call = pending.get(message.id);
    if (call) {
      pending.delete(message.id);
      message.error ? call.reject(new Error(message.error.message)) : call.resolve(message.result);
    } else if (message.method) {
      handlers.notify(message.method, message.params);
    }
  };
  current.onclose = () => {
    for (const call of pending.values()) call.reject(new Error("connection closed"));
    pending.clear();
    handlers.close();
    setTimeout(() => connect(url, handlers), 1000);
  };
}

export function call<T>(method: string, params?: object): Promise<T> {
  if (socket?.readyState !== WebSocket.OPEN) return Promise.reject(new Error("not connected"));
  const id = nextId++;
  socket.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
  return new Promise<T>((resolve, reject) => pending.set(id, { resolve: result => resolve(result as T), reject }));
}
