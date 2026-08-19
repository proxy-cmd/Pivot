export function readStoredJson(key) {
  try {
    const storedValue = localStorage.getItem(key);
    return JSON.parse(storedValue || "{}");
  } catch {
    return {};
  }
}


export function saveStoredJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}


export function removeStoredValue(key) {
  localStorage.removeItem(key);
}
