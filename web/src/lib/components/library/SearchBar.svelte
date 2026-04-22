<script lang="ts">
	import { t } from '$lib/i18n';
	import { untrack } from 'svelte';

	interface Props {
		/** Controlled value — parent owns state. */
		value: string;
		/** Fired on every (debounced) input change with the new value. */
		oninput: (value: string) => void;
		/** Optional override for the placeholder. Defaults to library.search_placeholder. */
		placeholder?: string;
	}

	let { value, oninput, placeholder }: Props = $props();

	// Local draft so typing stays instant even while we debounce the parent update.
	let draft = $state(value);
	let inputEl = $state<HTMLInputElement | null>(null);
	let timer: ReturnType<typeof setTimeout> | null = null;
	let idleHandle: number | null = null;
	// `pending` is truthy from the first keystroke until the debounced `oninput`
	// has actually been dispatched. Drives the subtle spinner in the search icon
	// slot so the user sees that filtering is still catching up.
	let pending = $state(false);

	// Sync draft to parent value ONLY when the parent reset it externally
	// (e.g. navigation clearing `librarySearch`). Without `untrack` around the
	// comparison, `draft` itself becomes a dependency of the effect, which means
	// every keystroke (draft = 'h' → re-run → value is still '' from the 300 ms
	// debounce → draft reset to '') erases the typed character until the
	// debounce finally fires. The user sees characters disappear and reappear,
	// which is exactly the "typing is blocked" symptom.
	$effect(() => {
		const next = value;
		if (untrack(() => draft) !== next) draft = next;
	});

	// Cancel any pending debounce when the component unmounts — otherwise a
	// setTimeout scheduled right before navigation would fire against an
	// unmounted component and call the parent's `oninput` into the void.
	$effect(() => {
		return () => {
			if (timer) {
				clearTimeout(timer);
				timer = null;
			}
			if (idleHandle !== null && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
				(window as unknown as { cancelIdleCallback: (h: number) => void }).cancelIdleCallback(idleHandle);
				idleHandle = null;
			}
			pending = false;
		};
	});

	function scheduleEmit(next: string) {
		draft = next;
		pending = true;
		if (timer) clearTimeout(timer);
		// 300 ms debounce keeps the IME-friendly feel while cutting the per-keystroke
		// filter cost (loadAllTracks fan-out on the Folder tab is expensive). The
		// `requestIdleCallback` wrap defers the actual filter work to a non-critical
		// frame so typing stays smooth even on a Pi Zero W Chromium with 100+ folders.
		timer = setTimeout(() => {
			timer = null;
			const emit = () => {
				idleHandle = null;
				oninput(next);
				pending = false;
			};
			if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
				idleHandle = (window as unknown as {
					requestIdleCallback: (cb: () => void, opts?: { timeout?: number }) => number;
				}).requestIdleCallback(emit, { timeout: 100 });
			} else {
				emit();
			}
		}, 300);
	}

	function emitNow(next: string) {
		draft = next;
		if (timer) {
			clearTimeout(timer);
			timer = null;
		}
		if (idleHandle !== null && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
			(window as unknown as { cancelIdleCallback: (h: number) => void }).cancelIdleCallback(idleHandle);
			idleHandle = null;
		}
		pending = false;
		oninput(next);
	}

	function onKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape' && draft) {
			event.preventDefault();
			emitNow('');
		}
	}

	function clear() {
		emitNow('');
		inputEl?.focus();
	}
</script>

<!--
	Freeform search input. Debounced 300 ms + requestIdleCallback so onInput stays
	cheap even with 200+ folders on a Pi Zero W. Escape clears; clear button
	appears only when there's content. Min height 44px for tap-target.

	The native browser search affordances (webkit cancel button, IE/Edge clear
	cross) are hidden via arbitrary variants — we render our own X so the control
	looks identical across Chromium, WebKit, and the Pi kiosk browser. Using
	`type="search"` instead of `type="text"` is kept deliberately: VoiceOver /
	TalkBack announce it as a search field and hardware keyboards offer proper
	shortcuts.
-->
<div role="search" class="relative mb-3">
	<span class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-text-muted">
		{#if pending}
			<!--
				Subtle non-blinking progress indicator. Border-based spinner (like the
				shared `Spinner` component) has a 1-frame pop; this SVG-based variant
				fades in smoothly via the rotate animation and stays small enough to
				sit inside the 16×16 icon slot without nudging the layout.
			-->
			<svg class="w-4 h-4 animate-spin text-text-muted/60" viewBox="0 0 24 24" fill="none" aria-hidden="true">
				<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" opacity="0.25" />
				<path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
			</svg>
		{:else}
			<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<circle cx="11" cy="11" r="7" />
				<path d="m20 20-3.5-3.5" />
			</svg>
		{/if}
	</span>
	<input
		bind:this={inputEl}
		type="search"
		value={draft}
		oninput={(e) => scheduleEmit((e.currentTarget as HTMLInputElement).value)}
		onkeydown={onKeyDown}
		placeholder={placeholder ?? t('library.search_placeholder')}
		aria-label={placeholder ?? t('library.search_placeholder')}
		aria-busy={pending}
		autocomplete="off"
		autocorrect="off"
		autocapitalize="off"
		spellcheck="false"
		class="w-full min-h-11 pl-9 pr-10 py-2 bg-surface-light border border-surface-lighter rounded-lg text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary [&::-webkit-search-cancel-button]:hidden [&::-webkit-search-decoration]:hidden [&::-ms-clear]:hidden"
	/>
	{#if draft}
		<button
			type="button"
			onclick={clear}
			aria-label={t('library.search_clear')}
			class="absolute inset-y-0 right-1 my-auto h-11 w-11 flex items-center justify-center text-text-muted hover:text-text"
		>
			<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M18 6 6 18" />
				<path d="m6 6 12 12" />
			</svg>
		</button>
	{/if}
</div>
