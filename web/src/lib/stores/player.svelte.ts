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
});

let connected = $state(false);
let lastCardEvent = $state<{ type: string; card_id: string; mapping?: unknown } | null>(null);
let lastGesture = $state<{ gesture: string; action: string } | null>(null);

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

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
			if (reconnectTimer) {
				clearTimeout(reconnectTimer);
				reconnectTimer = null;
			}
		};

		ws.onmessage = handleMessage;

		ws.onclose = () => {
			connected = false;
			ws = null;
			// Auto-reconnect after 2 seconds
			reconnectTimer = setTimeout(connectWebSocket, 2000);
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
