import { AssertNoExtras, StorageBase, StorageItemValue } from "./storage-base";

/** Tiny browser-only storage adapter; avoids shipping AsyncStorage on web. */
export class BrowserStorage extends StorageBase {
  async getItem<Fallback extends StorageItemValue>(key: string, fallback: Fallback): Promise<Fallback | null> {
    try {
      return this.retrieve(globalThis.localStorage?.getItem(key) ?? null, fallback);
    } catch (error) {
      this.warn("getItem", key, error);
      return fallback;
    }
  }

  async setItem<Value extends StorageItemValue>(key: string, value: Value): Promise<boolean> {
    try {
      globalThis.localStorage?.setItem(key, JSON.stringify(value));
      return true;
    } catch (error) {
      this.warn("setItem", key, error);
      return false;
    }
  }

  async removeItem(key: string): Promise<boolean> {
    try {
      globalThis.localStorage?.removeItem(key);
      return true;
    } catch (error) {
      this.warn("removeItem", key, error);
      return false;
    }
  }

  async secureGet<Fallback extends StorageItemValue>(key: string, fallback: Fallback): Promise<Fallback | null> {
    return this.getItem(key, fallback);
  }

  async secureSet<Value extends StorageItemValue>(key: string, value: Value): Promise<boolean> {
    return this.setItem(key, value);
  }

  async secureRemove(key: string): Promise<boolean> {
    return this.removeItem(key);
  }
}

// Compile-time guard: BrowserStorage must expose only the shared storage API.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
type _NoExtras = AssertNoExtras<Exclude<keyof BrowserStorage, keyof StorageBase>>;

export const browserStorage = new BrowserStorage();
