import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./auth', () => ({
  getAccessToken: vi.fn(),
}));

vi.mock('./config', () => ({
  API_BASE_URL: 'https://api.example.com',
}));

import apiClient from './api';
import { getAccessToken } from './auth';

const mockGetAccessToken = vi.mocked(getAccessToken);

describe('apiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('attaches Bearer token when access token is available', async () => {
    mockGetAccessToken.mockResolvedValue('my-jwt-token');

    const config = await apiClient.interceptors.request.handlers[0].fulfilled!({
      headers: {} as any,
    } as any);

    expect(config.headers.Authorization).toBe('Bearer my-jwt-token');
  });

  it('does not attach Authorization header when no token', async () => {
    mockGetAccessToken.mockResolvedValue(null);

    const config = await apiClient.interceptors.request.handlers[0].fulfilled!({
      headers: {} as any,
    } as any);

    expect(config.headers.Authorization).toBeUndefined();
  });

  it('uses the configured base URL', () => {
    expect(apiClient.defaults.baseURL).toBe('https://api.example.com');
  });
});
