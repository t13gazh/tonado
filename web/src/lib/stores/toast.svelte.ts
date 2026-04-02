/**
 * Global toast notification store for Svelte 5.
 * Supports success, error, and info toasts with auto-dismiss.
 *
 * Usage:
 *   import { addToast, getToasts } from '$lib/stores/toast.svelte';
 *   addToast('Gespeichert', 'success');
 */

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
	id: number;
	message: string;
	type: ToastType;
}

const DURATION_MS: Record<ToastType, number> = {
	success: 2500,
	error: 5000,
	info: 3500,
};

const MAX_TOASTS = 3;

let nextId = 0;
let toasts = $state<Toast[]>([]);
const timers = new Map<number, ReturnType<typeof setTimeout>>();

/** Add a toast notification. Auto-dismisses after type-specific duration. Deduplicates identical messages. */
export function addToast(message: string, type: ToastType = 'success'): void {
	// Deduplicate: skip if same message already shown
	if (toasts.some((t) => t.message === message && t.type === type)) return;

	const id = nextId++;
	toasts = [...toasts, { id, message, type }];

	// Enforce max limit — remove oldest
	if (toasts.length > MAX_TOASTS) {
		const oldest = toasts[0];
		removeToast(oldest.id);
	}

	const timer = setTimeout(() => {
		timers.delete(id);
		toasts = toasts.filter((t) => t.id !== id);
	}, DURATION_MS[type]);
	timers.set(id, timer);
}

/** Remove a toast by id. */
export function removeToast(id: number): void {
	const timer = timers.get(id);
	if (timer) {
		clearTimeout(timer);
		timers.delete(id);
	}
	toasts = toasts.filter((t) => t.id !== id);
}

/** Get current toasts (reactive). */
export function getToasts(): Toast[] {
	return toasts;
}
