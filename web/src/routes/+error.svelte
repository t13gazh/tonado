<script lang="ts">
	import { t } from '$lib/i18n';
	import { page } from '$app/state';
</script>

<div class="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
	<div class="w-16 h-16 mb-6 rounded-full bg-surface-light flex items-center justify-center">
		<svg class="w-8 h-8 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<circle cx="12" cy="12" r="10"/>
			<line x1="12" y1="8" x2="12" y2="12"/>
			<line x1="12" y1="16" x2="12.01" y2="16"/>
		</svg>
	</div>

	<h1 class="text-xl font-bold text-text mb-2">{t('error.title')}</h1>
	<p class="text-sm text-text-muted mb-1">{t('error.description')}</p>
	{#if page.status}
		<p class="text-xs text-text-muted mb-6">({page.status})</p>
	{/if}

	<div class="flex gap-3">
		<button onclick={() => history.back()} class="px-4 py-2 bg-surface-light text-text rounded-lg text-sm hover:bg-surface-lighter transition-colors">
			{t('error.back')}
		</button>
		<button onclick={() => location.reload()} class="px-4 py-2 bg-primary text-white rounded-lg text-sm hover:bg-primary/90 transition-colors">
			{t('error.reload')}
		</button>
	</div>
</div>
