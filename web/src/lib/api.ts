/**
 * Typed API client for the Tonado backend.
 */

import { t } from '$lib/i18n';

const BASE = '/api';
const DEFAULT_TIMEOUT = 15_000; // 15s

/** Structured API error with status code and user-friendly message. */
export class ApiError extends Error {
	status: number;
	userMessage: string;

	constructor(message: string, status: number, userMessage?: string) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.userMessage = userMessage ?? message;
	}
}

/**
 * Map raw fetch errors and HTTP status codes to user-friendly messages.
 */
function toApiError(err: unknown, status?: number): ApiError {
	// Network error (backend unreachable)
	if (err instanceof TypeError && (err.message.includes('fetch') || err.message.includes('network') || err.message.includes('Failed'))) {
		return new ApiError(err.message, 0, t('error.network'));
	}
	// AbortError from timeout
	if (err instanceof DOMException && err.name === 'AbortError') {
		return new ApiError('Request timed out', 408, t('error.timeout'));
	}
	// Already an ApiError
	if (err instanceof ApiError) return err;
	// HTTP status-based
	if (status === 401) return new ApiError(String(err), 401, t('error.unauthorized'));
	if (status === 403) return new ApiError(String(err), 403, t('error.forbidden'));
	if (status === 404) return new ApiError(String(err), 404, t('error.not_found'));
	if (status !== undefined && status >= 500) return new ApiError(String(err), status, t('error.server'));
	// Generic
	return new ApiError(String(err), status ?? 0, t('error.generic'));
}

export type ContentType = 'folder' | 'stream' | 'podcast' | 'playlist' | 'command';

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

export interface HardwareAudioOutput {
	name: string;
	type: string;
	device: string;
	recommended: boolean;
}

export interface HardwareDetection {
	pi: {
		model: string;
		revision: string;
		ram_mb: number;
		has_wifi: boolean;
		has_bluetooth: boolean;
		supported: boolean;
	};
	rfid: {
		reader: string;
		device: string;
	};
	audio: HardwareAudioOutput[];
	gyro_detected: boolean;
	gpio_available: boolean;
	is_mock: boolean;
}

export interface HardwareStatus extends HardwareDetection {
	wifi: {
		connected: boolean;
		ssid: string;
		ip: string;
	};
}

async function request<T>(path: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
	const { headers: extraHeaders, signal: existingSignal, timeoutMs, ...rest } = options ?? {};
	const token = getAuthToken();

	// Timeout via AbortController (respects existing signal)
	const controller = new AbortController();
	const timeoutId = setTimeout(() => controller.abort(), timeoutMs ?? DEFAULT_TIMEOUT);
	if (existingSignal) {
		existingSignal.addEventListener('abort', () => controller.abort());
	}

	let res: Response;
	try {
		res = await fetch(`${BASE}${path}`, {
			headers: {
				'Content-Type': 'application/json',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
				...(extraHeaders instanceof Headers
					? Object.fromEntries(extraHeaders.entries())
					: (extraHeaders as Record<string, string>) ?? {}),
			},
			signal: controller.signal,
			...rest,
		});
	} catch (err) {
		clearTimeout(timeoutId);
		throw toApiError(err);
	}
	clearTimeout(timeoutId);

	if (!res.ok) {
		let detail = res.statusText;
		try {
			const body = await res.json();
			if (body.detail) detail = body.detail;
		} catch { /* no JSON body */ }
		throw toApiError(new Error(detail), res.status);
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
	playFolder: (path: string, startIndex?: number) =>
		request<void>('/player/play-folder', { method: 'POST', body: JSON.stringify({ path, start_index: startIndex }) }),
	playUrl: (url: string) =>
		request<void>('/player/play-url', { method: 'POST', body: JSON.stringify({ url }) }),
	playUrls: (urls: string[], startIndex?: number) =>
		request<void>('/player/play-urls', { method: 'POST', body: JSON.stringify({ urls, start_index: startIndex }) }),
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
	waitForScan: (timeout = 30, newOnly = false) =>
		request<ScanResult>(`/cards/scan/wait?timeout=${timeout}${newOnly ? '&new_only=true' : ''}`, { timeoutMs: (timeout + 5) * 1000 }),
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
		const token = getAuthToken();
		return fetch(`${BASE}/library/folders`, {
			method: 'POST',
			body: form,
			...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
		}).then((r) => r.json());
	},
	deleteFolder: (name: string) => request<void>(`/library/folders/${name}`, { method: 'DELETE' }),
	upload: (folder: string, file: File, onProgress?: (pct: number) => void) => {
		return new Promise<void>((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			const form = new FormData();
			form.append('file', file);
			xhr.open('POST', `${BASE}/library/upload/${folder}`);
			const token = getAuthToken();
			if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
			if (onProgress) {
				xhr.upload.onprogress = (e) => {
					if (e.lengthComputable) onProgress((e.loaded / e.total) * 100);
				};
			}
			xhr.onload = () => (xhr.status < 400 ? resolve() : reject(new ApiError(xhr.statusText, xhr.status)));
			xhr.onerror = () => reject(new ApiError('Upload failed', 0));
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
	episodes: (id: number) => request<{ title: string; audio_url: string; published: string | null; duration: string | null }[]>(
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

export interface ComponentHealth {
	status: string;
	detail: string;
	free_mb?: number;
}

export interface SystemHealth {
	mpd: ComponentHealth;
	rfid: ComponentHealth;
	gyro: ComponentHealth;
	audio: ComponentHealth;
	storage: ComponentHealth;
	network: ComponentHealth;
}

export const systemApi = {
	health: () => request<SystemHealth>('/system/health'),
	info: () => request<SystemInfoData>('/system/info'),
	hardware: () => request<HardwareStatus>('/system/hardware'),
	restart: () => request<void>('/system/restart', { method: 'POST' }),
	shutdown: () => request<void>('/system/shutdown', { method: 'POST' }),
	reboot: () => request<void>('/system/reboot', { method: 'POST' }),
	checkUpdate: () => request<{ available: boolean; commits: number; changelog?: string; current_version?: string; remote_version?: string }>('/system/update/check'),
	applyUpdate: () => request<{ success: boolean; output?: string; error?: string; old_version?: string; new_version?: string; files_changed?: number }>('/system/update/apply', { method: 'POST' }),
	// Gyro calibration
	gyroRaw: () => request<{ raw: { x: number; y: number; z: number }; mapped: { x: number; y: number; z: number }; calibrated: boolean; axis_map: Record<string, unknown> }>('/system/gyro/raw'),
	gyroCalibrateStart: () => request<{ status: string }>('/system/gyro/calibrate/start', { method: 'POST' }),
	gyroCalibrateRest: () => request<{ status: string; samples: number; avg: { x: number; y: number; z: number } }>('/system/gyro/calibrate/rest', { method: 'POST' }),
	gyroCalibrateTilt: () => request<{ status: string; samples: number; avg: { x: number; y: number; z: number } }>('/system/gyro/calibrate/tilt', { method: 'POST' }),
	gyroCalibrateSave: () => request<{ status: string; axis_map: Record<string, unknown>; bias: Record<string, number> }>('/system/gyro/calibrate/save', { method: 'POST' }),
	gyroCalibrateCancel: () => request<{ status: string }>('/system/gyro/calibrate/cancel', { method: 'POST' }),
	gyroFlipForward: () => request<{ status: string; axis_map: Record<string, unknown> }>('/system/gyro/flip-forward', { method: 'POST' }),
	enableOverlay: () => request<void>('/system/overlay/enable', { method: 'POST' }),
	disableOverlay: () => request<void>('/system/overlay/disable', { method: 'POST' }),
	exportBackup: () => `${BASE}/system/backup`,
	importBackup: (file: File) => {
		const form = new FormData();
		form.append('file', file);
		const token = getAuthToken();
		return fetch(`${BASE}/system/restore`, {
			method: 'POST',
			body: form,
			...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
		}).then((r) => r.json());
	},
};

// Config API
export const config = {
	getAll: () => request<Record<string, unknown>>('/config/'),
	get: (key: string) => request<{ key: string; value: unknown }>(`/config/${key}`),
	set: (key: string, value: unknown) =>
		request<void>('/config/', { method: 'PUT', body: JSON.stringify({ key, value }) }),
};

// Button types
export type ButtonAction = 'volume_up' | 'volume_down' | 'play_pause' | 'next_track' | 'previous_track';
export interface ButtonConfigItem { action: ButtonAction; gpio: number; }
export interface ButtonScanResult { gpio: number | null; detected: boolean; }
export interface ButtonTestEvent { action: ButtonAction; gpio: number | null; }

// Buttons API
export const buttonsApi = {
	freeGpios: () => request<{ gpios: number[] }>('/buttons/free-gpios').then(r => r.gpios),
	getConfig: () => request<ButtonConfigItem[]>('/buttons/config'),
	saveConfig: (buttons: ButtonConfigItem[]) =>
		request<void>('/buttons/config', { method: 'POST', body: JSON.stringify({ buttons }) }),
	clearConfig: () => request<void>('/buttons/config', { method: 'DELETE' }),
	scanStart: () => request<void>('/buttons/scan/start', { method: 'POST' }),
	scanResult: (timeout = 15) => request<ButtonScanResult>(`/buttons/scan/result?timeout=${timeout}`, { timeoutMs: (timeout + 5) * 1000 }),
	scanStop: () => request<void>('/buttons/scan/stop', { method: 'POST' }),
	testStart: (buttons?: ButtonConfigItem[]) =>
		request<void>('/buttons/test/start', {
			method: 'POST',
			body: buttons ? JSON.stringify({ buttons }) : undefined,
		}),
	testEvents: () => request<ButtonTestEvent[]>('/buttons/test/events'),
	testStop: () => request<void>('/buttons/test/stop', { method: 'POST' }),
};

// Setup Wizard API
export interface SetupStatus {
	current_step: string;
	progress: number;
	is_complete: boolean;
	hardware: HardwareDetection | null;
	hardware_changed: boolean;
}

export interface WifiNetwork {
	ssid: string;
	signal: number;
	security: string;
	connected: boolean;
}

export interface WifiStatus {
	connected: boolean;
	ssid: string;
	ip_address: string;
	signal_strength: number;
}

export const setupApi = {
	status: () => request<SetupStatus>('/setup/status'),
	detectHardware: () => request<HardwareDetection>('/setup/detect-hardware', { method: 'POST' }),
	wifiConnect: (ssid: string, password: string = '') =>
		request<{ success: boolean; status?: WifiStatus; error?: string }>('/setup/wifi/connect', {
			method: 'POST',
			body: JSON.stringify({ ssid, password }),
		}),
	wifiScan: () => request<WifiNetwork[]>('/setup/wifi/scan'),
	wifiStatus: () => request<WifiStatus>('/setup/wifi/status'),
	setupAudio: (device: string) =>
		request<{ success: boolean; device: string }>('/setup/audio', {
			method: 'POST',
			body: JSON.stringify({ device }),
		}),
	testAudio: () => request<{ success: boolean }>('/setup/test-audio', { method: 'POST' }),
	firstCardDone: () => request<{ success: boolean }>('/setup/first-card-done', { method: 'POST' }),
	complete: () => request<{ success: boolean }>('/setup/complete', { method: 'POST' }),
	reset: () => request<{ status: string }>('/setup/reset', { method: 'POST' }),
};
