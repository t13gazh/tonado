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

let nextId = 0;
let toasts = $state<Toast[]>([]);

/** Add a toast notification. Auto-dismisses after type-specific duration. */
export function addToast(message: string, type: ToastType = 'success'): void {
	const id = nextId++;
	toasts = [...toasts, { id, message, type }];
	setTimeout(() => {
		toasts = toasts.filter((t) => t.id !== id);
	}, DURATION_MS[type]);
}

/** Remove a toast by id. */
export function removeToast(id: number): void {
	toasts = toasts.filter((t) => t.id !== id);
}

/** Get current toasts (reactive). */
export function getToasts(): Toast[] {
	return toasts;
}
