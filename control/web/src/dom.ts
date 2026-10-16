type Props = Record<string, string | number | boolean | null | undefined | ((event: never) => void)>;
type Child = Node | string | null | false;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, props: Props = {}, ...children: Child[]) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (name.startsWith("on")) Object.assign(element, { [name]: value });
    else if (value !== false && value != null) element.setAttribute(name, value === true ? "" : String(value));
  }
  element.append(...children.filter(child => child !== null && child !== false));
  return element;
}
