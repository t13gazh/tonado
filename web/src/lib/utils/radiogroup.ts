/**
 * Roving-tabindex arrow-key navigation for ARIA radiogroup controls.
 *
 * Implements the WAI-ARIA radiogroup pattern where selection follows focus:
 * ArrowRight/ArrowDown → next, ArrowLeft/ArrowUp → prev, wraps around.
 *
 * Shared across sort-toggle segmented controls (FolderTab, PlaylistTab,
 * RadioTab, PodcastTab). FolderTab keeps its local copy for now; new tabs
 * use this utility so the behaviour stays consistent.
 */

export interface RadioGroupOptions<T extends string> {
	/** Ordered list of valid option values. Order defines Arrow-key traversal. */
	options: readonly T[];
	/** Current selection; used as the starting point for delta navigation. */
	current: T;
	/** Called with the next value when an Arrow key is pressed. */
	onChange: (next: T) => void;
	/** Called after `onChange` so the caller can move focus to the new radio. */
	onFocus?: (next: T) => void;
}

/**
 * Handle a keydown event on a radio within a radiogroup.
 * Returns `true` if the event was handled (caller may skip further logic).
 */
export function handleRadioKeydown<T extends string>(
	event: KeyboardEvent,
	opts: RadioGroupOptions<T>,
): boolean {
	const navKeys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'];
	if (!navKeys.includes(event.key)) return false;
	event.preventDefault();

	const idx = opts.options.indexOf(opts.current);
	if (idx === -1) return false;

	const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown';
	const delta = forward ? 1 : -1;
	const nextIdx = (idx + delta + opts.options.length) % opts.options.length;
	const next = opts.options[nextIdx];

	opts.onChange(next);
	opts.onFocus?.(next);
	return true;
}
