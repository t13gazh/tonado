/**
 * Typed API client for the Tonado backend.
 */

const BASE = '/api';

export interface PlayerState {
	state: 'playing' | 'paused' | 'stopped';
	volume: number;
	current_track: string;
	current_album: string;
	elapsed: number;
	duration: number;
	playlist_length: number;
	playlist_position: number;
}

export interface CardMapping {
	card_id: string;
	name: string;
	content_type: 'folder' | 'stream' | 'podcast' | 'command';
	content_path: string;
	cover_path: string | null;
	resume_position: number;
}

export interface CardCreate {
	card_id: string;
	name: string;
	content_type: string;
	content_path: string;
	cover_path?: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json' },
		...options,
	});
	if (!res.ok) {
		throw new Error(`API error: ${res.status} ${res.statusText}`);
	}
	return res.json();
}

// Player API
export const player = {
	state: () => request<PlayerState>('/player/state'),
	play: () => request<void>('/player/play', { method: 'POST' }),
	pause: () => request<void>('/player/pause', { method: 'POST' }),
	toggle: () => request<void>('/player/toggle', { method: 'POST' }),
	stop: () => request<void>('/player/stop', { method: 'POST' }),
	next: () => request<void>('/player/next', { method: 'POST' }),
	previous: () => request<void>('/player/previous', { method: 'POST' }),
	volume: (volume: number) =>
		request<void>('/player/volume', { method: 'POST', body: JSON.stringify({ volume }) }),
	seek: (position: number) =>
		request<void>('/player/seek', { method: 'POST', body: JSON.stringify({ position }) }),
	shuffle: () => request<void>('/player/shuffle', { method: 'POST' }),
};

// Cards API
export const cards = {
	list: () => request<CardMapping[]>('/cards/'),
	get: (id: string) => request<CardMapping>(`/cards/${id}`),
	create: (data: CardCreate) =>
		request<CardMapping>('/cards/', { method: 'POST', body: JSON.stringify(data) }),
	update: (id: string, data: Partial<CardCreate>) =>
		request<CardMapping>(`/cards/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	delete: (id: string) => request<void>(`/cards/${id}`, { method: 'DELETE' }),
};

// Config API
export const config = {
	getAll: () => request<Record<string, unknown>>('/config/'),
	get: (key: string) => request<{ key: string; value: unknown }>(`/config/${key}`),
	set: (key: string, value: unknown) =>
		request<void>('/config/', { method: 'PUT', body: JSON.stringify({ key, value }) }),
};
