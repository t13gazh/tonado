/**
 * Reactive player state store using Svelte 5 runes.
 * Connects via WebSocket for real-time updates.
 */

import type { PlayerState } from '$lib/api';

// Reactive state using $state rune
let playerState = $state<PlayerState>({
	state: 'stopped',
	volume: 50,
	current_track: '',
	current_album: '',
	elapsed: 0,
	duration: 0,
	playlist_length: 0,
	playlist_position: -1,
	repeat_mode: 'off',
	current_uri: '',
	is_stream: false,
	loading: false,
	shuffle: false,
});

let connected = $state(false);
let lastCardEvent = $state<{ type: string; card_id: string; mapping?: unknown } | null>(null);
let lastGesture = $state<{ gesture: string; action: string } | null>(null);

export interface SleepTimerSnapshot {
	active: boolean;
	remaining_seconds: number;
	fading: boolean;
	duration_seconds: number | null;
	/** Monotonic timestamp (ms) of the last authoritative update; used for local countdown. */
	received_at: number;
}

let sleepTimer = $state<SleepTimerSnapshot>({
	active: false,
	remaining_seconds: 0,
	fading: false,
	duration_seconds: null,
	received_at: 0,
});

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 2000;
const RECONNECT_MAX = 30000;

function getWsUrl(): string {
	const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
	return `${proto}//${location.host}/ws`;
}

function handleMessage(event: MessageEvent): void {
	try {
		const msg = JSON.parse(event.data);
		switch (msg.type) {
			case 'player_state':
				playerState = msg.data;
				break;
			case 'card_scanned':
				lastCardEvent = { type: 'scanned', ...msg.data };
				break;
			case 'card_removed':
				lastCardEvent = { type: 'removed', ...msg.data };
				break;
			case 'card_unknown':
				lastCardEvent = { type: 'unknown', ...msg.data };
				break;
			case 'gesture':
				lastGesture = msg.data;
				break;
			case 'sleep_timer':
				sleepTimer = {
					active: !!msg.data.active,
					remaining_seconds: Math.max(0, Math.floor(msg.data.remaining_seconds ?? 0)),
					fading: !!msg.data.fading,
					duration_seconds: msg.data.duration_seconds ?? null,
					received_at: performance.now(),
				};
				break;
		}
	} catch {
		// Ignore malformed messages
	}
}

export function connectWebSocket(): void {
	if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
		return;
	}

	try {
		ws = new WebSocket(getWsUrl());

		ws.onopen = () => {
			connected = true;
			reconnectDelay = 2000;
			if (reconnectTimer) {
				clearTimeout(reconnectTimer);
				reconnectTimer = null;
			}
		};

		ws.onmessage = handleMessage;

		ws.onclose = () => {
			connected = false;
			ws = null;
			// Auto-reconnect with exponential backoff (2s, 4s, 8s, ... max 30s)
			reconnectTimer = setTimeout(connectWebSocket, reconnectDelay);
			reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX);
		};

		ws.onerror = () => {
			ws?.close();
		};
	} catch {
		// Will retry via onclose
	}
}

export function disconnectWebSocket(): void {
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
	ws?.close();
	ws = null;
	connected = false;
}

// Export reactive getters
export function getPlayerState(): PlayerState {
	return playerState;
}

export function isConnected(): boolean {
	return connected;
}

export function getLastCardEvent() {
	return lastCardEvent;
}

export function getLastGesture() {
	return lastGesture;
}

export function getSleepTimer(): SleepTimerSnapshot {
	return sleepTimer;
}

/**
 * Merge a client-known timer state (e.g. from REST polling or optimistic
 * cancel/extend) into the store. Used when no WebSocket event has
 * arrived yet or the user just tapped a pill button.
 */
export function setSleepTimer(next: Partial<SleepTimerSnapshot>): void {
	sleepTimer = {
		...sleepTimer,
		...next,
		received_at: performance.now(),
	};
}
