<script lang="ts">
	/**
	 * CoverArt — displays an album/track cover with a deterministic gradient + initial fallback.
	 *
	 * Props:
	 *   src   — URL to the cover endpoint. If the request fails or `src` is empty,
	 *           the fallback (gradient + initial from `title`) is rendered.
	 *   title — used for the fallback initial and the img aria-label.
	 *   size  — 'sm' | 'md' | 'lg' (default 'md'). Only affects the letter size in the fallback.
	 */

	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		src?: string;
		title: string;
		size?: Size;
	}

	const { src, title, size = 'md' }: Props = $props();

	let failed = $state(false);

	// Reset `failed` when the src changes so a new cover gets a fresh attempt.
	let currentSrc = $state('');
	$effect(() => {
		if (src !== currentSrc) {
			currentSrc = src ?? '';
			failed = false;
		}
	});

	// Initial: first printable char of `title`, uppercased. UTF-8 safe for ä/ö/ü.
	const initial = $derived.by(() => {
		const trimmed = (title ?? '').trim();
		if (!trimmed) return '?';
		// Iterator handles surrogate pairs and combining marks safely.
		const first = [...trimmed][0];
		return (first ?? '?').toLocaleUpperCase('de-DE');
	});

	// Deterministic hash → HSL gradient.
	// Simple FNV-1a variant so the same title always yields the same colours.
	function hash(s: string): number {
		let h = 0x811c9dc5;
		for (let i = 0; i < s.length; i++) {
			h ^= s.charCodeAt(i);
			h = (h * 0x01000193) >>> 0;
		}
		return h;
	}

	const gradient = $derived.by(() => {
		const h = hash(title || 'tonado');
		const hue1 = h % 360;
		const hue2 = (hue1 + 40) % 360;
		// Warm, saturated-but-soft palette — readable in both dark and light contexts.
		return `linear-gradient(135deg, hsl(${hue1} 62% 55%), hsl(${hue2} 58% 42%))`;
	});

	const letterClass = $derived(
		size === 'sm' ? 'text-xl' : size === 'lg' ? 'text-7xl' : 'text-4xl'
	);

	function handleError() {
		failed = true;
	}

	const showImage = $derived(!failed && !!src);
</script>

<div
	class="relative w-full h-full rounded-2xl overflow-hidden flex items-center justify-center shadow-xl"
	style={showImage ? undefined : `background: ${gradient}`}
	aria-label={title}
	role="img"
>
	{#if showImage}
		<img
			src={src}
			alt={title}
			loading="lazy"
			onerror={handleError}
			class="w-full h-full object-cover"
		/>
	{:else}
		<span
			class="font-bold text-white drop-shadow-sm select-none {letterClass}"
			aria-hidden="true"
		>
			{initial}
		</span>
	{/if}
</div>
