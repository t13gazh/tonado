<script lang="ts">
	import { t } from '$lib/i18n';
	import { cards, type CardMapping } from '$lib/api';
	import { onMount } from 'svelte';

	let allCards = $state<CardMapping[]>([]);
	let loading = $state(true);
	let error = $state('');
	let search = $state('');
	let filter = $state<'all' | 'folder' | 'stream' | 'podcast'>('all');
	let gridView = $state(true);

	const filtered = $derived(() => {
		let result = allCards;
		if (filter !== 'all') {
			result = result.filter((c) => c.content_type === filter);
		}
		if (search.trim()) {
			const q = search.toLowerCase();
			result = result.filter(
				(c) => c.name.toLowerCase().includes(q) || c.content_path.toLowerCase().includes(q)
			);
		}
		return result;
	});

	const filterOptions = [
		{ value: 'all' as const, label: () => t('library.filter.all') },
		{ value: 'folder' as const, label: () => t('library.filter.folder') },
		{ value: 'stream' as const, label: () => t('library.filter.stream') },
		{ value: 'podcast' as const, label: () => t('library.filter.podcast') },
	];

	onMount(async () => {
		try {
			allCards = await cards.list();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unbekannter Fehler';
		} finally {
			loading = false;
		}
	});
</script>

<div class="p-4 pb-2">
	<!-- Header -->
	<div class="flex items-center justify-between mb-4">
		<h1 class="text-xl font-bold text-text">{t('library.title')}</h1>
		<button
			onclick={() => (gridView = !gridView)}
			class="p-2 text-text-muted hover:text-text transition-colors"
			aria-label={gridView ? t('library.list_view') : t('library.grid_view')}
		>
			{#if gridView}
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
					<path d="M3 4h18v2H3V4zm0 7h18v2H3v-2zm0 7h18v2H3v-2z"/>
				</svg>
			{:else}
				<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
					<rect x="3" y="3" width="7" height="7" rx="1"/>
					<rect x="14" y="3" width="7" height="7" rx="1"/>
					<rect x="3" y="14" width="7" height="7" rx="1"/>
					<rect x="14" y="14" width="7" height="7" rx="1"/>
				</svg>
			{/if}
		</button>
	</div>

	<!-- Search -->
	<div class="relative mb-3">
		<svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<circle cx="11" cy="11" r="8"/>
			<path d="M21 21l-4.35-4.35"/>
		</svg>
		<input
			type="text"
			bind:value={search}
			placeholder={t('library.search')}
			class="w-full pl-10 pr-4 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text placeholder:text-text-muted text-sm focus:outline-none focus:border-primary"
		/>
	</div>

	<!-- Filter tabs -->
	<div class="flex gap-2 mb-4 overflow-x-auto">
		{#each filterOptions as opt}
			<button
				onclick={() => (filter = opt.value)}
				class="px-3 py-1.5 text-xs font-medium rounded-full whitespace-nowrap transition-colors
					{filter === opt.value
						? 'bg-primary text-white'
						: 'bg-surface-light text-text-muted hover:text-text'}"
			>
				{opt.label()}
			</button>
		{/each}
	</div>
</div>

<!-- Content -->
<div class="px-4 pb-4">
	{#if loading}
		<div class="flex items-center justify-center py-20">
			<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
		</div>
	{:else if error}
		<div class="text-center py-20">
			<p class="text-red-400 mb-2">{error}</p>
			<button onclick={() => location.reload()} class="text-primary text-sm">{t('general.retry')}</button>
		</div>
	{:else if filtered().length === 0}
		<div class="text-center py-20 text-text-muted">
			<svg class="w-16 h-16 mx-auto mb-4 opacity-30" viewBox="0 0 24 24" fill="currentColor">
				<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
			</svg>
			<p class="text-sm font-medium">{t('library.empty')}</p>
			<p class="text-xs mt-1">{t('library.empty_hint')}</p>
		</div>
	{:else if gridView}
		<!-- Grid view -->
		<div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
			{#each filtered() as card (card.card_id)}
				<button
					class="bg-surface-light rounded-xl overflow-hidden text-left hover:bg-surface-lighter transition-colors active:scale-[0.98]"
				>
					<div class="aspect-square bg-surface-lighter flex items-center justify-center">
						{#if card.cover_path}
							<img src={card.cover_path} alt={card.name} class="w-full h-full object-cover" />
						{:else}
							<svg class="w-12 h-12 text-text-muted opacity-30" viewBox="0 0 24 24" fill="currentColor">
								<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
							</svg>
						{/if}
					</div>
					<div class="p-2.5">
						<p class="text-sm font-medium text-text truncate">{card.name}</p>
						<p class="text-xs text-text-muted mt-0.5 capitalize">{card.content_type}</p>
					</div>
				</button>
			{/each}
		</div>
	{:else}
		<!-- List view -->
		<div class="flex flex-col gap-2">
			{#each filtered() as card (card.card_id)}
				<button
					class="flex items-center gap-3 p-3 bg-surface-light rounded-xl hover:bg-surface-lighter transition-colors active:scale-[0.99] text-left"
				>
					<div class="w-12 h-12 rounded-lg bg-surface-lighter flex-shrink-0 flex items-center justify-center overflow-hidden">
						{#if card.cover_path}
							<img src={card.cover_path} alt={card.name} class="w-full h-full object-cover" />
						{:else}
							<svg class="w-6 h-6 text-text-muted opacity-30" viewBox="0 0 24 24" fill="currentColor">
								<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
							</svg>
						{/if}
					</div>
					<div class="flex-1 min-w-0">
						<p class="text-sm font-medium text-text truncate">{card.name}</p>
						<p class="text-xs text-text-muted capitalize">{card.content_type}</p>
					</div>
					<svg class="w-5 h-5 text-text-muted shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M9 18l6-6-6-6"/>
					</svg>
				</button>
			{/each}
		</div>
	{/if}
</div>
