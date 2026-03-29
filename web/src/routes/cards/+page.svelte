<script lang="ts">
	import { t } from '$lib/i18n';
	import { cards, config, type CardMapping, type ContentType } from '$lib/api';
	import { onMount } from 'svelte';
	import ContentPicker from '$lib/components/ContentPicker.svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import { isBackendOffline, isRfidAvailable } from '$lib/stores/health.svelte';

	let allCards = $state<CardMapping[]>([]);
	let loading = $state(true);
	let error = $state('');
	let expertMode = $state(false);

	$effect(() => {
		if (error) {
			const timer = setTimeout(() => (error = ''), 5000);
			return () => clearTimeout(timer);
		}
	});

	// Edit state
	let editingCard = $state<CardMapping | null>(null);
	let editName = $state('');
	let editContentType = $state<ContentType>('folder');
	let editContentPath = $state('');

	// Delete state
	let deletingCard = $state<CardMapping | null>(null);

	const typeLabels: Record<string, () => string> = {
		folder: () => t('wizard.type_folder'),
		stream: () => t('wizard.type_radio'),
		podcast: () => t('wizard.type_podcast'),
		playlist: () => t('wizard.type_playlist'),
		command: () => t('wizard.type_command'),
	};

	onMount(async () => {
		await loadCards();
		try {
			const cfg = await config.getAll();
			expertMode = cfg['wizard.expert_mode'] === true;
		} catch {}
	});

	async function loadCards() {
		loading = true;
		error = '';
		try {
			allCards = await cards.list();
		} catch (e) {
			if (!isBackendOffline()) error = e instanceof Error ? e.message : t('general.error');
		} finally {
			loading = false;
		}
	}

	function startEdit(card: CardMapping) {
		editingCard = card;
		editName = card.name;
		editContentType = card.content_type as ContentType;
		editContentPath = card.content_path;
	}

	function handleEditTypeChange(type: ContentType) {
		editContentType = type;
		editContentPath = '';
		editName = '';
	}

	function handleEditSelect(path: string, autoName: string) {
		editContentPath = path;
		editName = autoName;
	}

	async function saveEdit() {
		if (!editingCard || !editName.trim() || !editContentPath.trim()) return;
		try {
			await cards.update(editingCard.card_id, {
				name: editName.trim(),
				content_type: editContentType,
				content_path: editContentPath.trim(),
			});
			editingCard = null;
			await loadCards();
		} catch {
			error = t('error.save_failed');
		}
	}

	async function confirmDelete() {
		if (!deletingCard) return;
		try {
			await cards.delete(deletingCard.card_id);
			deletingCard = null;
			await loadCards();
		} catch {
			error = t('error.delete_failed');
		}
	}
</script>

<div class="p-4">
	<!-- Header -->
	<div class="flex items-center justify-between mb-4">
		<h1 class="text-xl font-bold text-text">{t('card.title')}</h1>
		{#if isRfidAvailable()}
			<a
				href="/cards/wizard"
				class="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors"
			>
				<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
					<path d="M12 5v14M5 12h14"/>
				</svg>
				{t('card.add')}
			</a>
		{:else}
			<span
				class="flex items-center gap-2 px-4 py-2 bg-surface-lighter text-text-muted rounded-lg text-sm font-medium opacity-50 cursor-not-allowed"
			>
				<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
					<path d="M12 5v14M5 12h14"/>
				</svg>
				{t('card.add')}
			</span>
		{/if}
	</div>

	{#if isRfidAvailable() === false}
		<div class="mb-4">
			<HealthBanner type="warning" message={t('health.rfid_unavailable')} />
		</div>
	{/if}

	{#if loading}
		<div class="flex items-center justify-center py-20">
			<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
		</div>
	{:else if error}
		<div class="text-center py-20">
			<p class="text-red-400 mb-2">{error}</p>
			<button onclick={loadCards} class="text-primary text-sm">{t('general.retry')}</button>
		</div>
	{:else if allCards.length === 0}
		<div class="text-center py-20 text-text-muted">
			<svg class="w-16 h-16 mx-auto mb-4 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
				<rect x="2" y="4" width="14" height="16" rx="2"/>
				<path d="M18 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>
			</svg>
			<p class="text-sm font-medium">{t('card.empty')}</p>
			<p class="text-xs mt-1">{t('card.empty_hint')}</p>
		</div>
	{:else}
		<!-- Card Wall Grid -->
		<div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
			{#each allCards as card (card.card_id)}
				<div class="bg-surface-light rounded-xl overflow-hidden group relative">
					<!-- Cover -->
					<div class="aspect-square bg-surface-lighter flex items-center justify-center">
						{#if card.cover_path}
							<img src={card.cover_path} alt={card.name} class="w-full h-full object-cover" />
						{:else}
							<div class="flex flex-col items-center text-text-muted opacity-30">
								<svg class="w-10 h-10" viewBox="0 0 24 24" fill="currentColor">
									<path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
								</svg>
							</div>
						{/if}
					</div>

					<!-- Info -->
					<div class="p-2.5">
						<p class="text-sm font-medium text-text truncate">{card.name}</p>
						<p class="text-xs text-text-muted mt-0.5">{typeLabels[card.content_type]?.() ?? card.content_type}</p>
					</div>

					<!-- Actions -->
					<div class="absolute top-2 right-2 flex gap-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
						<button
							onclick={() => startEdit(card)}
							class="p-1.5 bg-surface/80 rounded-lg backdrop-blur-sm text-text-muted hover:text-text"
							aria-label={t('card.edit')}
						>
							<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
								<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
							</svg>
						</button>
						<button
							onclick={() => (deletingCard = card)}
							class="p-1.5 bg-surface/80 rounded-lg backdrop-blur-sm text-text-muted hover:text-red-400"
							aria-label={t('general.delete')}
						>
							<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14z"/>
							</svg>
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Edit Modal (full-screen on mobile) -->
{#if editingCard}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50" onclick={() => (editingCard = null)}>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="bg-surface-light w-full sm:w-[28rem] max-h-[85vh] rounded-t-2xl sm:rounded-2xl p-5 flex flex-col overflow-hidden"
			onclick={(e) => e.stopPropagation()}
		>
			<h2 class="text-lg font-bold mb-4">{t('card.edit')}</h2>

			<div class="flex-1 overflow-y-auto flex flex-col gap-4 min-h-0">
				<!-- Name -->
				<label class="block">
					<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_name')}</span>
					<input
						type="text"
						bind:value={editName}
						class="w-full px-3 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
					/>
				</label>

				<!-- Content Picker (same as wizard) -->
				<ContentPicker
					contentType={editContentType}
					contentPath={editContentPath}
					name={editName}
					{expertMode}
					onTypeChange={handleEditTypeChange}
					onSelect={handleEditSelect}
				/>
			</div>

			<div class="flex gap-3 pt-4">
				<button
					onclick={() => (editingCard = null)}
					class="flex-1 px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text-muted text-sm font-medium"
				>
					{t('general.cancel')}
				</button>
				<button
					onclick={saveEdit}
					disabled={!editName.trim() || !editContentPath.trim()}
					class="flex-1 px-4 py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-colors"
				>
					{t('general.save')}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Delete Confirmation -->
{#if deletingCard}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50" onclick={() => (deletingCard = null)}>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="bg-surface-light w-full sm:w-96 rounded-t-2xl sm:rounded-2xl p-6" onclick={(e) => e.stopPropagation()}>
			<h2 class="text-lg font-bold mb-2">{t('general.delete')}</h2>
			<p class="text-sm text-text-muted mb-4">{t('card.delete_confirm', { name: deletingCard.name })}</p>

			<div class="flex gap-3">
				<button
					onclick={() => (deletingCard = null)}
					class="flex-1 px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text-muted text-sm font-medium"
				>
					{t('general.cancel')}
				</button>
				<button
					onclick={confirmDelete}
					class="flex-1 px-4 py-2.5 bg-red-600 hover:bg-red-500 rounded-lg text-white text-sm font-medium transition-colors"
				>
					{t('general.delete')}
				</button>
			</div>
		</div>
	</div>
{/if}
