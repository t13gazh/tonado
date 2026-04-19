<script lang="ts">
	import { t } from '$lib/i18n';

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

	// Reset draft when parent resets the value (e.g. navigation).
	$effect(() => {
		if (value !== draft) draft = value;
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
		};
	});

	function scheduleEmit(next: string) {
		draft = next;
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => {
			oninput(next);
			timer = null;
		}, 200);
	}

	function emitNow(next: string) {
		draft = next;
		if (timer) {
			clearTimeout(timer);
			timer = null;
		}
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
	Freeform search input. Debounced 200 ms so onInput stays cheap; Escape clears;
	clear button appears only when there's content. Min height 44px for tap-target.
-->
<div role="search" class="relative mb-3">
	<span class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-text-muted">
		<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<circle cx="11" cy="11" r="7" />
			<path d="m20 20-3.5-3.5" />
		</svg>
	</span>
	<input
		bind:this={inputEl}
		type="search"
		value={draft}
		oninput={(e) => scheduleEmit((e.currentTarget as HTMLInputElement).value)}
		onkeydown={onKeyDown}
		placeholder={placeholder ?? t('library.search_placeholder')}
		aria-label={placeholder ?? t('library.search_placeholder')}
		autocomplete="off"
		autocorrect="off"
		autocapitalize="off"
		spellcheck="false"
		class="w-full min-h-11 pl-9 pr-10 py-2 bg-surface-light border border-surface-lighter rounded-lg text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
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
