<script lang="ts">
	import { t } from '$lib/i18n';
	import { cards } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	type Step = 'scan' | 'content' | 'done';

	let step = $state<Step>('scan');
	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let error = $state('');

	// Content form
	let name = $state('');
	let contentType = $state<'folder' | 'stream' | 'podcast' | 'command'>('folder');
	let contentPath = $state('');

	const contentTypes = [
		{ value: 'folder' as const, label: () => t('wizard.type_folder') },
		{ value: 'stream' as const, label: () => t('wizard.type_stream') },
		{ value: 'podcast' as const, label: () => t('wizard.type_podcast') },
		{ value: 'command' as const, label: () => t('wizard.type_command') },
	];

	// Auto-start scanning on mount
	onMount(() => {
		startScan();
	});

	async function startScan() {
		scanning = true;
		error = '';
		try {
			const result = await cards.waitForScan(30);
			if (result.scanned && result.card_id) {
				scannedCardId = result.card_id;
				hasExisting = result.has_mapping ?? false;
				if (result.mapping) {
					name = result.mapping.name;
					contentType = result.mapping.content_type;
					contentPath = result.mapping.content_path;
				}
				step = 'content';
			} else {
				// Timeout — not an error, just retry
				scanning = false;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
			scanning = false;
		}
	}

	async function saveCard() {
		if (!name.trim() || !contentPath.trim()) return;
		error = '';
		try {
			if (hasExisting) {
				await cards.update(scannedCardId, {
					name: name.trim(),
					content_type: contentType,
					content_path: contentPath.trim(),
				});
			} else {
				await cards.create({
					card_id: scannedCardId,
					name: name.trim(),
					content_type: contentType,
					content_path: contentPath.trim(),
				});
			}
			step = 'done';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Fehler';
		}
	}
</script>

<div class="flex flex-col h-full p-4">
	<!-- Header -->
	<div class="flex items-center gap-3 mb-6">
		<a href="/cards" class="p-2 text-text-muted hover:text-text">
			<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M19 12H5M12 19l-7-7 7-7"/>
			</svg>
		</a>
		<h1 class="text-lg font-bold">{t('wizard.title')}</h1>
	</div>

	<!-- Step indicators -->
	<div class="flex items-center gap-2 mb-8 px-4">
		{#each ['scan', 'content', 'done'] as s, i}
			{@const completed = ['scan', 'content', 'done'].indexOf(step) > i}
			{@const active = s === step}
			<div class="flex-1 h-1 rounded-full {active || completed ? 'bg-primary' : 'bg-surface-lighter'}"></div>
		{/each}
	</div>

	<!-- Step: Scan (auto-started) -->
	{#if step === 'scan'}
		<div class="flex-1 flex flex-col items-center justify-center text-center gap-6">
			<div class="w-32 h-32 rounded-2xl bg-surface-light flex items-center justify-center animate-pulse">
				<svg class="w-16 h-16 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="2" y="4" width="14" height="16" rx="2"/>
					<path d="M18 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>
					<circle cx="9" cy="12" r="3" fill="currentColor" stroke="none" class="animate-ping"/>
				</svg>
			</div>

			<div>
				<h2 class="text-lg font-semibold mb-1">{t('wizard.step_scan')}</h2>
				<p class="text-sm text-text-muted">{t('wizard.step_scan_desc')}</p>
			</div>

			{#if error}
				<p class="text-sm text-red-400">{error}</p>
			{/if}

			{#if !scanning}
				<button
					onclick={startScan}
					class="px-6 py-2.5 bg-primary hover:bg-primary-light text-white rounded-xl text-sm font-medium transition-colors"
				>
					{t('general.retry')}
				</button>
			{:else}
				<p class="text-sm text-text-muted animate-pulse">{t('wizard.scanning')}</p>
			{/if}
		</div>
	{/if}

	<!-- Step: Content selection -->
	{#if step === 'content'}
		<div class="flex-1 flex flex-col gap-4">
			{#if hasExisting}
				<div class="px-3 py-2 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent">
					{t('wizard.already_assigned')}
				</div>
			{/if}

			<!-- Content type selector -->
			<div>
				<span class="text-xs text-text-muted mb-2 block">{t('wizard.content_type')}</span>
				<div class="grid grid-cols-2 gap-2">
					{#each contentTypes as ct}
						<button
							onclick={() => (contentType = ct.value)}
							class="px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left
								{contentType === ct.value
									? 'bg-primary text-white'
									: 'bg-surface-light text-text-muted hover:text-text'}"
						>
							{ct.label()}
						</button>
					{/each}
				</div>
			</div>

			<!-- Name -->
			<label class="block">
				<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_name')}</span>
				<input
					type="text"
					bind:value={name}
					placeholder="Die drei ???, Folge 1"
					class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
				/>
			</label>

			<!-- Path/URL -->
			<label class="block">
				<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_path')}</span>
				<input
					type="text"
					bind:value={contentPath}
					placeholder={contentType === 'stream' ? 'https://...' : 'Die drei Fragezeichen/Folge 1'}
					class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
				/>
			</label>

			{#if error}
				<p class="text-sm text-red-400">{error}</p>
			{/if}

			<div class="mt-auto flex gap-3 pt-4">
				<button
					onclick={() => { step = 'scan'; startScan(); }}
					class="flex-1 px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text-muted text-sm font-medium"
				>
					{t('general.back')}
				</button>
				<button
					onclick={saveCard}
					disabled={!name.trim() || !contentPath.trim()}
					class="flex-1 px-4 py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-colors"
				>
					{hasExisting ? t('wizard.reassign') : t('wizard.next')}
				</button>
			</div>
		</div>
	{/if}

	<!-- Step: Done -->
	{#if step === 'done'}
		<div class="flex-1 flex flex-col items-center justify-center text-center gap-6">
			<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
				<svg class="w-10 h-10 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
					<path d="M20 6L9 17l-5-5"/>
				</svg>
			</div>

			<div>
				<h2 class="text-lg font-semibold mb-1">{t('wizard.step_done')}</h2>
				<p class="text-sm text-text-muted max-w-xs">{t('wizard.done_desc')}</p>
			</div>

			<div class="flex flex-col gap-2 w-full max-w-xs">
				<button
					onclick={() => goto('/cards')}
					class="px-8 py-3 bg-primary hover:bg-primary-light text-white rounded-xl text-sm font-medium transition-colors"
				>
					{t('wizard.finish')}
				</button>
				<button
					onclick={() => { step = 'scan'; scannedCardId = ''; name = ''; contentPath = ''; hasExisting = false; startScan(); }}
					class="px-8 py-2.5 text-text-muted text-sm"
				>
					{t('card.add')}
				</button>
			</div>
		</div>
	{/if}
</div>
