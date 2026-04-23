<script lang="ts">
	/**
	 * QR code renderer using the `qrcode` npm package (already a dependency).
	 * Renders to an inline `<canvas>` that scales via Tailwind.
	 *
	 * Lazy-loads the qrcode lib on mount to keep the initial bundle small —
	 * setup wizard only reaches this component on the last screen.
	 *
	 * If rendering fails (lib load error, canvas missing) the component now
	 * falls back to a prominently visible, tappable link pill so the user can
	 * still reach the encoded URL manually. Previously the fallback was only
	 * `sr-only` which left a blank white square on screen.
	 */
	interface Props {
		/** Data to encode. Typically a URL like `http://tonado.local/`. */
		value: string;
		/** Pixel size for the rendered canvas (square). Default: 200 (Lane C:
		 *  raised from 176/192 to improve scan tolerance on phones held at arm's
		 *  length). */
		size?: number;
		/** Error correction level. `Q` is Lane C's new default — better scan
		 *  tolerance in imperfect lighting / angles than the previous `M`. */
		level?: 'L' | 'M' | 'Q' | 'H';
		/** Accessible label for screen readers. */
		ariaLabel?: string;
		/** Optional short hostname for the fallback link pill, e.g. `tonado.local`.
		 *  When omitted the raw `value` URL is shown instead. */
		fallbackLabel?: string;
	}

	let { value, size = 200, level = 'Q', ariaLabel = '', fallbackLabel = '' }: Props = $props();

	let canvas = $state<HTMLCanvasElement | null>(null);
	let rendered = $state(false);
	let renderError = $state(false);

	// Re-render whenever `value` or `size` change.
	$effect(() => {
		if (!canvas || !value) return;
		// Touch reactive deps so Svelte re-runs when they change.
		const _v = value;
		const _s = size;

		renderError = false;
		rendered = false;

		(async () => {
			try {
				const qr = await import('qrcode');
				await qr.toCanvas(canvas, _v, {
					width: _s,
					margin: 1,
					errorCorrectionLevel: level,
					color: {
						// Dark foreground, light background — readable by phone cameras
						// regardless of Tonado's dark theme.
						dark: '#0f172a',
						light: '#ffffff',
					},
				});
				rendered = true;
			} catch (err) {
				console.error('QR render failed', err);
				rendered = false;
				renderError = true;
			}
		})();
	});

	const linkLabel = $derived(fallbackLabel || value);
</script>

{#if renderError}
	<!-- Fallback: lib load failed. Offer a large tappable link pill instead of
	     a blank white square. The href uses the same URL as the QR payload. -->
	<a
		href={value}
		class="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-4 text-base font-semibold text-slate-900 shadow-sm hover:bg-slate-100 transition-colors min-h-11"
		aria-label={ariaLabel || linkLabel}
	>
		{linkLabel}
	</a>
{:else}
	<div
		class="inline-block rounded-xl bg-white p-3 shadow-sm"
		role="img"
		aria-label={ariaLabel || value}
	>
		<canvas
			bind:this={canvas}
			width={size}
			height={size}
			class="block"
			style="width: {size}px; height: {size}px;"
		></canvas>
		{#if !rendered}
			<!-- Visible fallback while QR renders. Keeps the user informed that
			     something is happening even if rendering is slow. -->
			<a
				href={value}
				class="mt-2 block text-center text-xs font-medium text-slate-900 underline underline-offset-2 hover:text-slate-700"
			>
				{linkLabel}
			</a>
		{/if}
	</div>
{/if}
