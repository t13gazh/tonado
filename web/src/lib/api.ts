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
	repeat_mode: 'off' | 'all' | 'single';
	current_uri: string;
	is_stream: boolean;
	loading: boolean;
	shuffle: boolean;
}

export interface CardMapping {
	card_id: string;
	name: string;
	content_type: 'folder' | 'stream' | 'podcast' | 'playlist' | 'command';
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
	const { headers: extraHeaders, ...rest } = options ?? {};
	const token = getAuthToken();
	const res = await fetch(`${BASE}${path}`, {
		headers: {
			'Content-Type': 'application/json',
			...(token ? { Authorization: `Bearer ${token}` } : {}),
			...(extraHeaders instanceof Headers
				? Object.fromEntries(extraHeaders.entries())
				: (extraHeaders as Record<string, string>) ?? {}),
		},
		...rest,
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
	toggleRandom: () => request<{ shuffle: boolean }>('/player/shuffle', { method: 'POST' }),
	repeat: () => request<{ repeat_mode: string }>('/player/repeat', { method: 'POST' }),
	outputs: () => request<{ id: number; name: string; enabled: boolean }[]>('/player/outputs'),
	toggleOutput: (id: number, enabled: boolean) =>
		request<void>(`/player/outputs/${id}`, { method: 'POST', body: JSON.stringify({ enabled }) }),
};

export interface ScanResult {
	scanned: boolean;
	card_id: string | null;
	has_mapping?: boolean;
	mapping?: CardMapping | null;
}

// Cards API
export const cards = {
	list: () => request<CardMapping[]>('/cards/'),
	get: (id: string) => request<CardMapping>(`/cards/${id}`),
	create: (data: CardCreate) =>
		request<CardMapping>('/cards/', { method: 'POST', body: JSON.stringify(data) }),
	update: (id: string, data: Partial<CardCreate>) =>
		request<CardMapping>(`/cards/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
	delete: (id: string) => request<void>(`/cards/${id}`, { method: 'DELETE' }),
	waitForScan: (timeout = 30) => request<ScanResult>(`/cards/scan/wait?timeout=${timeout}`),
};

// Library API
export interface MediaFolder {
	name: string;
	path: string;
	track_count: number;
	cover_path: string | null;
	duration_seconds: number;
}

export interface MediaTrack {
	filename: string;
	path: string;
	duration_seconds: number;
}

export const library = {
	folders: () => request<MediaFolder[]>('/library/folders'),
	folder: (name: string) => request<MediaFolder>(`/library/folders/${name}`),
	tracks: (name: string) => request<MediaTrack[]>(`/library/folders/${name}/tracks`),
	createFolder: (name: string) => {
		const form = new FormData();
		form.append('name', name);
		return fetch(`${BASE}/library/folders`, { method: 'POST', body: form }).then((r) => r.json());
	},
	deleteFolder: (name: string) => request<void>(`/library/folders/${name}`, { method: 'DELETE' }),
	upload: (folder: string, file: File, onProgress?: (pct: number) => void) => {
		return new Promise<void>((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			const form = new FormData();
			form.append('file', file);
			xhr.open('POST', `${BASE}/library/upload/${folder}`);
			if (onProgress) {
				xhr.upload.onprogress = (e) => {
					if (e.lengthComputable) onProgress((e.loaded / e.total) * 100);
				};
			}
			xhr.onload = () => (xhr.status < 400 ? resolve() : reject(new Error(xhr.statusText)));
			xhr.onerror = () => reject(new Error('Upload fehlgeschlagen'));
			xhr.send(form);
		});
	},
	stats: () => request<{ total_bytes: number; file_count: number; folder_count: number }>('/library/stats'),
};

// Streams API
export interface RadioStation {
	id: number;
	name: string;
	url: string;
	category: string;
	logo_url: string | null;
}

export interface PodcastInfo {
	id: number;
	name: string;
	feed_url: string;
	auto_download: boolean;
	episode_count: number;
	logo_url: string | null;
}

export const streams = {
	listRadio: (category?: string) =>
		request<RadioStation[]>(`/streams/radio${category ? `?category=${category}` : ''}`),
	addRadio: (name: string, url: string) =>
		request<RadioStation>('/streams/radio', { method: 'POST', body: JSON.stringify({ name, url }) }),
	deleteRadio: (id: number) => request<void>(`/streams/radio/${id}`, { method: 'DELETE' }),
	listPodcasts: () => request<PodcastInfo[]>('/streams/podcasts'),
	addPodcast: (name: string, feed_url: string) =>
		request<PodcastInfo>('/streams/podcasts', {
			method: 'POST',
			body: JSON.stringify({ name, feed_url }),
		}),
	deletePodcast: (id: number) => request<void>(`/streams/podcasts/${id}`, { method: 'DELETE' }),
	episodes: (id: number) => request<{ title: string; audio_url: string; published: string | null }[]>(
		`/streams/podcasts/${id}/episodes`
	),
	refreshPodcast: (id: number) => request<{ new_episodes: number }>(
		`/streams/podcasts/${id}/refresh`, { method: 'POST' }
	),
};

// Playlists API
export interface PlaylistSummary {
	id: number;
	name: string;
	item_count: number;
	duration_seconds: number;
}

export interface PlaylistDetail extends PlaylistSummary {
	items: { id: number; position: number; content_type: string; content_path: string; title: string | null; duration_seconds: number }[];
}

export const playlistsApi = {
	list: () => request<PlaylistSummary[]>('/playlists/'),
	get: (id: number) => request<PlaylistDetail>(`/playlists/${id}`),
	create: (name: string) =>
		request<PlaylistSummary>('/playlists/', { method: 'POST', body: JSON.stringify({ name }) }),
	delete: (id: number) => request<void>(`/playlists/${id}`, { method: 'DELETE' }),
	play: (id: number) => request<void>(`/playlists/${id}/play`, { method: 'POST' }),
	addItem: (id: number, content_type: string, content_path: string, title?: string) =>
		request<void>(`/playlists/${id}/items`, {
			method: 'POST',
			body: JSON.stringify({ content_type, content_path, title }),
		}),
	removeItem: (itemId: number) => request<void>(`/playlists/items/${itemId}`, { method: 'DELETE' }),
};

// Auth API
export interface AuthStatus {
	authenticated: boolean;
	tier: string;
	parent_pin_set: boolean;
	expert_pin_set: boolean;
}

let _authToken: string | null = null;

export function setAuthToken(token: string | null): void {
	_authToken = token;
	if (token) localStorage.setItem('tonado_token', token);
	else localStorage.removeItem('tonado_token');
}

export function getAuthToken(): string | null {
	if (!_authToken) _authToken = localStorage.getItem('tonado_token');
	return _authToken;
}

function authHeaders(): Record<string, string> {
	const token = getAuthToken();
	return token ? { Authorization: `Bearer ${token}` } : {};
}

export const authApi = {
	login: async (pin: string) => {
		const res = await request<{ token: string; tier: string }>('/auth/login', {
			method: 'POST',
			body: JSON.stringify({ pin }),
		});
		setAuthToken(res.token);
		return res;
	},
	logout: () => { setAuthToken(null); },
	status: () => request<AuthStatus>('/auth/status'),
	setPin: (tier: string, pin: string) =>
		request<void>('/auth/pin', {
			method: 'POST',
			body: JSON.stringify({ tier, pin }),
		}),
	removePin: (tier: string) =>
		request<void>('/auth/pin', {
			method: 'DELETE',
			body: JSON.stringify({ tier }),
		}),
	sleepTimer: () => request<{ active: boolean; remaining_seconds: number }>('/auth/sleep-timer'),
	startSleepTimer: (minutes: number) =>
		request<void>('/auth/sleep-timer', { method: 'POST', body: JSON.stringify({ minutes }) }),
	cancelSleepTimer: () => request<void>('/auth/sleep-timer', { method: 'DELETE' }),
};

// System API
export interface SystemInfoData {
	hostname: string;
	pi_model: string;
	tonado_version: string;
	uptime_seconds: number;
	cpu_temp: number;
	ram_total_mb: number;
	ram_used_mb: number;
	disk_total_gb: number;
	disk_used_gb: number;
	overlay_active: boolean;
	ip_address: string;
}

export const systemApi = {
	info: () => request<SystemInfoData>('/system/info'),
	restart: () => request<void>('/system/restart', { method: 'POST' }),
	shutdown: () => request<void>('/system/shutdown', { method: 'POST' }),
	reboot: () => request<void>('/system/reboot', { method: 'POST' }),
	checkUpdate: () => request<{ available: boolean; commits: number; changes?: string[] }>('/system/update/check'),
	applyUpdate: () => request<{ success: boolean; output?: string; error?: string }>('/system/update/apply', { method: 'POST' }),
	enableOverlay: () => request<void>('/system/overlay/enable', { method: 'POST' }),
	disableOverlay: () => request<void>('/system/overlay/disable', { method: 'POST' }),
	exportBackup: () => `${BASE}/system/backup`,
	importBackup: (file: File) => {
		const form = new FormData();
		form.append('file', file);
		return fetch(`${BASE}/system/restore`, { method: 'POST', body: form }).then((r) => r.json());
	},
};

// Config API
export const config = {
	getAll: () => request<Record<string, unknown>>('/config/'),
	get: (key: string) => request<{ key: string; value: unknown }>(`/config/${key}`),
	set: (key: string, value: unknown) =>
		request<void>('/config/', { method: 'PUT', body: JSON.stringify({ key, value }) }),
};
