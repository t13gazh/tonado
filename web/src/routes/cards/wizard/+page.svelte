<script lang="ts">
	import { t } from '$lib/i18n';
	import { config, type ContentType } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ContentPicker from '$lib/components/ContentPicker.svelte';
	import { createCardScan } from '$lib/card-scan.svelte';
	import Icon from '$lib/components/Icon.svelte';

	type Step = 'scan' | 'content' | 'done';

	let step = $state<Step>('scan');
	let expertMode = $state(false);
	let waitForNewCard = $state(false);

	const scan = createCardScan();

	// Auto-dismiss errors
	$effect(() => {
		if (scan.error) {
			const timer = setTimeout(() => (scan.error = ''), 5000);
			return () => clearTimeout(timer);
		}
	});

	// Advance to content step when scan completes
	$effect(() => {
		if (scan.scanComplete && step === 'scan') {
			step = 'content';
		}
	});

	// Advance to done step when save completes
	$effect(() => {
		if (scan.saveComplete && step === 'content') {
			step = 'done';
		}
	});

	onMount(async () => {
		try {
			const cfg = await config.getAll();
			expertMode = cfg['wizard.expert_mode'] === true;
		} catch {}
		scan.startScan(false);
	});

	function handleTypeChange(type: ContentType) {
		scan.handleTypeChange(type);
	}

	function handleSelect(path: string, autoName: string) {
		scan.handleSelect(path, autoName);
	}

	function resetAndScanNext() {
		waitForNewCard = true;
		step = 'scan';
		scan.reset();
		scan.startScan(true);
	}
</script>

<div class="flex flex-col h-full p-4">
	<!-- Header -->
	<div class="flex items-center gap-3 mb-6">
		<a href="/cards" class="p-2 text-text-muted hover:text-text" aria-label={t('general.back')}>
			<Icon name="arrow-left" size={20} />
		</a>
		<h1 class="text-lg font-bold">{t('wizard.title')}</h1>
	</div>

	<!-- Step indicators -->
	<div class="flex items-center gap-2 mb-6 px-4">
		{#each ['scan', 'content', 'done'] as s, i}
			{@const completed = ['scan', 'content', 'done'].indexOf(step) > i}
			{@const active = s === step}
			<div class="flex-1 h-1 rounded-full {active || completed ? 'bg-primary' : 'bg-surface-lighter'}"></div>
		{/each}
	</div>

	<!-- Step: Scan -->
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
			{#if scan.error}
				<p class="text-sm text-red-400">{scan.error}</p>
				{#if scan.autoRetryCountdown > 0}
					<p class="text-xs text-text-muted">{t('wizard.auto_retry', { seconds: scan.autoRetryCountdown })}</p>
				{/if}
				<button onclick={() => { scan.cancelAutoRetry(); scan.clearError(); scan.startScan(waitForNewCard); }} class="text-sm text-primary font-medium">{t('general.retry')}</button>
			{:else}
				<p class="text-sm text-text-muted animate-pulse">{t('wizard.scanning')}</p>
			{/if}
		</div>
	{/if}

	<!-- Step: Content selection -->
	{#if step === 'content'}
		<div class="flex-1 flex flex-col gap-4 overflow-hidden">
			{#if scan.scannedCardId}
				<p class="text-xs text-text-muted">{t('wizard.card_id', { id: scan.scannedCardId.toUpperCase() })}</p>
			{/if}
			{#if scan.hasExisting}
				<div class="px-3 py-2 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent">
					{t('wizard.already_assigned')}
				</div>
			{/if}

			<ContentPicker
				contentType={scan.contentType}
				contentPath={scan.contentPath}
				name={scan.cardName}
				{expertMode}
				onTypeChange={handleTypeChange}
				onSelect={handleSelect}
			/>

			<!-- Name -->
			<label class="block">
				<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_name')}</span>
				<input
					type="text"
					bind:value={scan.cardName}
					placeholder="Die drei ???, Folge 1"
					class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
				/>
			</label>

			{#if scan.error}
				<p class="text-sm text-red-400">{scan.error}</p>
			{/if}

			<div class="flex gap-3 pt-2">
				<button
					onclick={() => { waitForNewCard = true; step = 'scan'; scan.reset(); scan.startScan(true); }}
					class="flex-1 px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text-muted text-sm font-medium"
				>
					{t('general.back')}
				</button>
				<button
					onclick={() => scan.saveCard()}
					disabled={!scan.canSave()}
					class="flex-1 px-4 py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-colors"
				>
					{scan.hasExisting ? t('wizard.reassign') : t('wizard.next')}
				</button>
			</div>
		</div>
	{/if}

	<!-- Step: Done -->
	{#if step === 'done'}
		<div class="flex-1 flex flex-col items-center justify-center text-center gap-6">
			<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
				<Icon name="check" size={40} class="text-green-500" strokeWidth={2.5} />
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
					onclick={resetAndScanNext}
					class="px-8 py-2.5 bg-surface-light hover:bg-surface-lighter rounded-xl text-text text-sm font-medium transition-colors"
				>
					{t('card.add')}
				</button>
			</div>
		</div>
	{/if}
</div>
