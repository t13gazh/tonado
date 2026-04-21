<script lang="ts">
	/**
	 * Inline error notice with accessible role="alert" and a gentle fade-in.
	 * Renders nothing if `message` is empty/null/undefined.
	 *
	 * Usage:
	 *   <InlineError message={error} id="pin-error" />
	 *   <input aria-invalid={!!error} aria-describedby="pin-error" />
	 */
	interface Props {
		message?: string | null;
		id?: string;
	}

	let { message, id }: Props = $props();
</script>

{#if message}
	<p
		{id}
		role="alert"
		class="inline-error flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm"
	>
		<svg
			class="w-4 h-4 shrink-0 mt-0.5"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			aria-hidden="true"
		>
			<circle cx="12" cy="12" r="10" />
			<line x1="12" y1="8" x2="12" y2="12" />
			<line x1="12" y1="16" x2="12.01" y2="16" />
		</svg>
		<span>{message}</span>
	</p>
{/if}

<style>
	.inline-error {
		opacity: 1;
		transition: opacity 150ms ease-out;
	}
	@starting-style {
		.inline-error {
			opacity: 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.inline-error {
			transition: none;
		}
	}
</style>
