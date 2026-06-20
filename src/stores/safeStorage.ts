/**
 * SafeStorage — 三级降级存储适配器
 * localStorage → sessionStorage → 内存 Map
 * 所有访问包裹 try-catch，永不抛出 SecurityError
 */

import type { StateStorage } from 'zustand/middleware';

type StorageBackend = 'localStorage' | 'sessionStorage' | 'memory';

class SafeStorageAdapter implements StateStorage {
  private backend: StorageBackend;
  private memory = new Map<string, string>();

  constructor() {
    this.backend = this.detect();
  }

  /** 检测可用的最高优先级存储后端 */
  private detect(): StorageBackend {
    try {
      const k = '__safe_storage_test__';
      localStorage.setItem(k, '1');
      localStorage.removeItem(k);
      return 'localStorage';
    } catch {
      // pass
    }
    try {
      const k = '__safe_storage_test__';
      sessionStorage.setItem(k, '1');
      sessionStorage.removeItem(k);
      return 'sessionStorage';
    } catch {
      // pass
    }
    return 'memory';
  }

  /** 当前使用的存储后端名称 */
  getBackend(): StorageBackend {
    return this.backend;
  }

  /** 是否降级到了非 localStorage */
  isDegraded(): boolean {
    return this.backend !== 'localStorage';
  }

  getItem(name: string): string | null {
    try {
      if (this.backend === 'memory') {
        return this.memory.get(name) ?? null;
      }
      const storage = this.backend === 'localStorage' ? localStorage : sessionStorage;
      return storage.getItem(name);
    } catch {
      return this.memory.get(name) ?? null;
    }
  }

  setItem(name: string, value: string): void {
    try {
      if (this.backend === 'memory') {
        this.memory.set(name, value);
        return;
      }
      const storage = this.backend === 'localStorage' ? localStorage : sessionStorage;
      storage.setItem(name, value);
    } catch {
      this.memory.set(name, value);
    }
  }

  removeItem(name: string): void {
    try {
      if (this.backend === 'memory') {
        this.memory.delete(name);
        return;
      }
      const storage = this.backend === 'localStorage' ? localStorage : sessionStorage;
      storage.removeItem(name);
    } catch {
      this.memory.delete(name);
    }
  }
}

export const safeStorage = new SafeStorageAdapter();
