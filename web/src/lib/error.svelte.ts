/**
 * Reactive auto-dismissing error state for Svelte 5 components.
 * Usage:
 *   const error = createAutoError();
 *   error.value = 'Something went wrong';  // auto-clears after timeout
 */
export function createAutoError(timeout = 5000) {
	let message = $state('');

	$effect(() => {
		if (message) {
			const timer = setTimeout(() => (message = ''), timeout);
			return () => clearTimeout(timer);
		}
	});

	return {
		get value() {
			return message;
		},
		set value(v: string) {
			message = v;
		},
	};
}
