<script lang="ts">
	import { t } from '$lib/i18n';
	import Icon from '$lib/components/Icon.svelte';
	import type { HelpEntry } from '$lib/help/entries';

	interface Props {
		open: boolean;
		entry: HelpEntry | null;
		onClose: () => void;
	}

	let { open = $bindable(false), entry, onClose }: Props = $props();

	let sheetEl = $state<HTMLDivElement | null>(null);
	let closeBtnEl = $state<HTMLButtonElement | null>(null);
	let previousFocus: HTMLElement | null = null;

	// Move focus into the sheet when it opens, restore on close.
	$effect(() => {
		if (open) {
			previousFocus = document.activeElement as HTMLElement | null;
			requestAnimationFrame(() => closeBtnEl?.focus());
		} else if (previousFocus) {
			previousFocus.focus();
			previousFocus = null;
		}
	});

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			close();
			return;
		}
		if (e.key === 'Tab' && sheetEl) {
			// Minimal focus trap: keep Tab / Shift+Tab inside the sheet.
			const focusables = sheetEl.querySelectorAll<HTMLElement>(
				'button, [href], input, [tabindex]:not([tabindex="-1"])'
			);
			if (focusables.length === 0) return;
			const first = focusables[0];
			const last = focusables[focusables.length - 1];
			const active = document.activeElement;
			if (e.shiftKey && active === first) {
				e.preventDefault();
				last.focus();
			} else if (!e.shiftKey && active === last) {
				e.preventDefault();
				first.focus();
			}
		}
	}

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) close();
	}

	function close() {
		open = false;
		onClose?.();
	}

	/**
	 * Minimal markdown renderer — supports only what the help content needs:
	 *   - `**bold**`     — wraps in <strong>
	 *   - `[text](url)`  — single inline link with safe attributes
	 * All other input is escaped. Returns a string of sanitised HTML.
	 */
	function escapeHtml(text: string): string {
		return text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	function renderInline(raw: string): string {
		let html = escapeHtml(raw);
		// Bold: **text** — applied before link detection is fine because the
		// escaped text does not contain raw asterisks in URLs.
		html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
		// Link: [text](https://...) — accept http/https only to avoid javascript:
		html = html.replace(
			/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
			(_m, label, url) =>
				`<a href="${url}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">${label}</a>`
		);
		return html;
	}

	const paragraphs = $derived.by(() => {
		if (!entry) return [] as string[];
		// Each body key resolves to one paragraph. We additionally allow "\n\n"
		// inside a single key to generate multiple paragraphs.
		const out: string[] = [];
		for (const key of entry.bodyKeys) {
			const text = t(key);
			if (!text || text === key) continue;
			for (const chunk of text.split(/\n\n+/)) {
				const trimmed = chunk.trim();
				if (trimmed) out.push(trimmed);
			}
		}
		return out;
	});
</script>

{#if open && entry}
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50 help-backdrop"
		role="dialog"
		aria-modal="true"
		aria-labelledby="help-sheet-title"
		onclick={handleBackdrop}
		onkeydown={handleKeydown}
	>
		<div
			bind:this={sheetEl}
			class="help-sheet bg-surface-light w-full sm:w-[28rem] max-h-[85vh] rounded-t-2xl sm:rounded-2xl flex flex-col overflow-hidden"
		>
			<!-- Header: drag handle + close -->
			<div class="shrink-0 flex items-center justify-between px-5 pt-4 pb-2">
				<div class="flex-1 flex justify-center sm:hidden">
					<div class="w-10 h-1 rounded-full bg-surface-lighter"></div>
				</div>
				<button
					bind:this={closeBtnEl}
					type="button"
					onclick={close}
					aria-label={t('help.close_aria')}
					class="p-1.5 text-text-muted hover:text-text rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
				>
					<Icon name="x" size={20} />
				</button>
			</div>

			<!-- Title + scrollable body -->
			<div class="flex-1 overflow-y-auto px-5 pb-5">
				<h2 id="help-sheet-title" class="text-lg font-bold text-text mb-3">
					{t(entry.titleKey)}
				</h2>
				<div class="flex flex-col gap-3 text-sm text-text-muted leading-relaxed">
					{#each paragraphs as paragraph}
						<!-- eslint-disable-next-line svelte/no-at-html-tags -->
						<p>{@html renderInline(paragraph)}</p>
					{/each}
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Smooth entry: slide up on mobile, fade/scale on desktop.
	   Respects prefers-reduced-motion. */
	.help-sheet {
		animation: help-slide-up 250ms ease-out;
	}
	.help-backdrop {
		animation: help-fade-in 200ms ease-out;
	}

	@keyframes help-slide-up {
		from {
			transform: translateY(100%);
			opacity: 0;
		}
		to {
			transform: translateY(0);
			opacity: 1;
		}
	}
	@keyframes help-fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@media (min-width: 640px) {
		.help-sheet {
			animation: help-scale-in 200ms ease-out;
		}
		@keyframes help-scale-in {
			from {
				transform: scale(0.96);
				opacity: 0;
			}
			to {
				transform: scale(1);
				opacity: 1;
			}
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.help-sheet,
		.help-backdrop {
			animation: none;
		}
	}
</style>
