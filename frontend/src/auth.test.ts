import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockGetCurrentUser = vi.fn();
const mockSignInWithRedirect = vi.fn();
const mockSignOut = vi.fn();
const mockFetchAuthSession = vi.fn();

vi.mock('aws-amplify/auth', () => ({
  getCurrentUser: (...args: unknown[]) => mockGetCurrentUser(...args),
  signInWithRedirect: (...args: unknown[]) => mockSignInWithRedirect(...args),
  signOut: (...args: unknown[]) => mockSignOut(...args),
  fetchAuthSession: (...args: unknown[]) => mockFetchAuthSession(...args),
}));

import { checkAuth, login, logout, getAccessToken } from './auth';

describe('auth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('checkAuth', () => {
    it('returns true when user is authenticated', async () => {
      mockGetCurrentUser.mockResolvedValue({ username: 'testuser' });
      expect(await checkAuth()).toBe(true);
    });

    it('returns false when no user session', async () => {
      mockGetCurrentUser.mockRejectedValue(new Error('No user'));
      expect(await checkAuth()).toBe(false);
    });
  });

  describe('login', () => {
    it('calls signInWithRedirect', async () => {
      mockSignInWithRedirect.mockResolvedValue(undefined);
      await login();
      expect(mockSignInWithRedirect).toHaveBeenCalledOnce();
    });
  });

  describe('logout', () => {
    it('calls signOut', async () => {
      mockSignOut.mockResolvedValue(undefined);
      await logout();
      expect(mockSignOut).toHaveBeenCalledOnce();
    });
  });

  describe('getAccessToken', () => {
    it('returns access token string when session exists', async () => {
      mockFetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { toString: () => 'test-jwt-token' },
        },
      });
      expect(await getAccessToken()).toBe('test-jwt-token');
    });

    it('returns null when no tokens in session', async () => {
      mockFetchAuthSession.mockResolvedValue({});
      expect(await getAccessToken()).toBeNull();
    });

    it('returns null when fetchAuthSession throws', async () => {
      mockFetchAuthSession.mockRejectedValue(new Error('No session'));
      expect(await getAccessToken()).toBeNull();
    });
  });
});
