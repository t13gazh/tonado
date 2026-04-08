/**
 * Reactive auth store — polls /api/auth/status periodically
 * and provides reactive getters for authorization checks.
 */

import { authApi, setAuthToken, type AuthStatus } from '$lib/api';

const POLL_INTERVAL = 30_000; // 30s
const INACTIVITY_TIMEOUT = 5 * 60_000; // 5 minutes

let authStatus = $state<AuthStatus | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;
let inactivityTimer: ReturnType<typeof setTimeout> | null = null;

async function fetchAuth(): Promise<void> {
	try {
		authStatus = await authApi.status();
	} catch {
		// API not reachable — keep last known state
	}
}

function resetInactivityTimer(): void {
	if (inactivityTimer) clearTimeout(inactivityTimer);
	// Only set timer if actually authenticated
	if (authStatus?.authenticated) {
		inactivityTimer = setTimeout(() => {
			setAuthToken(null);
			fetchAuth();
		}, INACTIVITY_TIMEOUT);
	}
}

function onActivity(): void {
	if (authStatus?.authenticated) resetInactivityTimer();
}

/** Start polling auth status. Call once from layout. */
export function startAuthPolling(): void {
	if (pollTimer) return;
	fetchAuth();
	pollTimer = setInterval(fetchAuth, POLL_INTERVAL);
	// Listen for user activity to reset inactivity timer
	if (typeof window !== 'undefined') {
		for (const evt of ['pointerdown', 'scroll', 'keydown'] as const) {
			window.addEventListener(evt, onActivity, { passive: true });
		}
	}
}

/** Stop polling (cleanup). */
export function stopAuthPolling(): void {
	if (pollTimer) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
	if (inactivityTimer) {
		clearTimeout(inactivityTimer);
		inactivityTimer = null;
	}
	if (typeof window !== 'undefined') {
		for (const evt of ['pointerdown', 'scroll', 'keydown'] as const) {
			window.removeEventListener(evt, onActivity);
		}
	}
}

/** Force a refresh now (e.g. after login). */
export function refreshAuth(): void {
	fetchAuth().then(resetInactivityTimer);
}

// Reactive getters
export function isAuthenticated(): boolean {
	if (!authStatus) return false;
	return authStatus.authenticated;
}

export function getAuthTier(): string {
	if (!authStatus) return 'open';
	return authStatus.tier;
}

/**
 * True when the current user may manage library content (upload, create/delete folders).
 * Allowed when:
 * - tier is "parent" or "expert" (logged in with sufficient privileges), OR
 * - no parent PIN is set (open access — no restriction configured)
 */
export function canManageLibrary(): boolean {
	if (!authStatus) return true; // not loaded yet — assume open
	if (!authStatus.parent_pin_set) return true;
	return authStatus.tier === 'parent' || authStatus.tier === 'expert';
}

/** True when a parent PIN is configured (library is access-restricted). */
export function isParentPinSet(): boolean {
	if (!authStatus) return false;
	return authStatus.parent_pin_set;
}
