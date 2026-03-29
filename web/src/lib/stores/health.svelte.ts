/**
 * Reactive health store — polls /api/system/health periodically
 * and provides reactive getters for component-level degraded states.
 */

import { systemApi, type SystemHealth } from '$lib/api';

const POLL_INTERVAL = 30_000; // 30s

let health = $state<SystemHealth | null>(null);
let loading = $state(false);
let backendReachable = $state(true);
let pollTimer: ReturnType<typeof setInterval> | null = null;

async function fetchHealth(): Promise<void> {
	try {
		loading = true;
		health = await systemApi.health();
		backendReachable = true;
	} catch {
		// API not reachable — mark backend as offline
		backendReachable = false;
		health = null;
	} finally {
		loading = false;
	}
}

/** Start polling health status. Call once from layout. */
export function startHealthPolling(): void {
	if (pollTimer) return;
	fetchHealth();
	pollTimer = setInterval(fetchHealth, POLL_INTERVAL);
}

/** Stop polling (cleanup). */
export function stopHealthPolling(): void {
	if (pollTimer) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
}

/** Force a refresh now. */
export function refreshHealth(): void {
	fetchHealth();
}

// Reactive getters
export function getHealth(): SystemHealth | null {
	return health;
}

export function isHealthLoading(): boolean {
	return loading;
}

/** True when the backend API itself is unreachable (fetch failed). */
export function isBackendOffline(): boolean {
	return !backendReachable;
}

// Convenience checks
// MPD/Gyro: assume OK until proven otherwise (graceful degradation)
// RFID: assume unavailable until confirmed (gate UI access)
export function isMpdConnected(): boolean {
	if (!health) return true;
	return health.mpd.status === 'connected';
}

export function isRfidAvailable(): boolean {
	if (!health) return false;
	return health.rfid.status === 'connected';
}

export function isGyroAvailable(): boolean {
	if (!health) return true;
	return health.gyro.status === 'connected';
}

/** True when health data has been loaded at least once. */
export function isHealthLoaded(): boolean {
	return health !== null;
}

export function isStorageCritical(): boolean {
	if (!health) return false;
	return health.storage.status === 'critical';
}

export function isStorageLow(): boolean {
	if (!health) return false;
	return health.storage.status === 'low' || health.storage.status === 'critical';
}
