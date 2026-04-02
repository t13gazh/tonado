<script lang="ts">
	import { t } from '$lib/i18n';
	import { page } from '$app/state';

	const status = $derived(page.status);
	const is404 = $derived(status === 404);
	const isOffline = $derived(typeof navigator !== 'undefined' && !navigator.onLine);

	const title = $derived(
		isOffline ? t('error.offline_title') :
		is404 ? t('error.not_found_title') :
		t('error.title')
	);

	const description = $derived(
		isOffline ? t('error.offline_description') :
		is404 ? t('error.not_found_description') :
		t('error.description')
	);

	// SVG path data for each error type
	const iconPath = $derived(
		isOffline
			// WiFi-off icon
			? 'M1 1l22 22M16.72 11.06A10.94 10.94 0 0 1 19 12.55M5 12.55a10.94 10.94 0 0 1 5.17-2.39M10.71 5.05A16 16 0 0 1 22.56 9M1.42 9a15.91 15.91 0 0 1 4.7-2.88M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01'
			: is404
			// Search icon
			? 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM21 21l-4.35-4.35'
			// Exclamation circle
			: 'M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z'
	);

	const iconColor = $derived(
		isOffline ? 'text-amber-400' :
		is404 ? 'text-text-muted' :
		'text-red-400'
	);
</script>

<div class="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
	<div class="w-16 h-16 mb-6 rounded-full bg-surface-light flex items-center justify-center">
		<svg class="w-8 h-8 {iconColor}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<path d={iconPath} />
		</svg>
	</div>

	<h1 class="text-xl font-bold text-text mb-2">{title}</h1>
	<p class="text-sm text-text-muted mb-1">{description}</p>
	{#if status && !is404 && !isOffline}
		<p class="text-xs text-text-muted mb-6">({status})</p>
	{/if}

	<div class="flex gap-3 mt-4">
		<button onclick={() => history.back()} class="px-4 py-2.5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
			{t('error.back')}
		</button>
		{#if isOffline}
			<button onclick={() => location.reload()} class="px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
				{t('error.reload')}
			</button>
		{:else}
			<a href="/" class="px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
				{t('error.home')}
			</a>
		{/if}
	</div>
</div>
