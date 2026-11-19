// Unit test for AppStore signal initialization

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { appStore } from './app.store';
import { ApiService } from '../services/api.service';

// Mock fetch globally to prevent real network calls during test
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({})
  } as Response));
});

describe('AppStore', () => {
  it('should have null status initially', () => {
    // The store is a singleton; its status signal starts as null.
    expect(appStore.status()).toBeNull();
  });

  it('should have empty quotes array initially', () => {
    expect(appStore.quotes()).toEqual([]);
  });
});
