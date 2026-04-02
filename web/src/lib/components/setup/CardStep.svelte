<script lang="ts" module>
	export type CardStepType = 'intro' | 'scan' | 'content' | 'done';
</script>

<script lang="ts">
	import { t } from '$lib/i18n';
	import { type ContentType } from '$lib/api';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import ContentPicker from '$lib/components/ContentPicker.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { createCardScan } from '$lib/card-scan.svelte';

	interface Props {
		hasRfid: boolean;
		expertMode: boolean;
		existingCardCount: number;
		error: string;
		cardStep: CardStepType;
		onError: (msg: string) => void;
		onClearError: () => void;
	}

	let { hasRfid, expertMode, existingCardCount = 0, error, cardStep = $bindable('intro'), onError, onClearError }: Props = $props();

	const scan = createCardScan();

	// Sync scan errors to parent
	$effect(() => {
		if (scan.error) onError(scan.error);
	});

	// Advance to content step when scan completes
	$effect(() => {
		if (scan.scanComplete && cardStep === 'scan') {
			cardStep = 'content';
		}
	});

	// Advance to done step when save completes
	$effect(() => {
		if (scan.saveComplete && cardStep === 'content') {
			cardStep = 'done';
		}
	});

	export async function startCardScan() {
		cardStep = 'scan';
		onClearError();
		await scan.startScan(false);
	}

	export function cancelScan() {
		scan.cancelAutoRetry();
		cardStep = 'intro';
	}

	export async function saveCard() {
		onClearError();
		await scan.saveCard();
	}

	export function canSave(): boolean {
		return scan.canSave();
	}

	export function resetForNewCard() {
		scan.reset();
		startCardScan();
	}
</script>

{#if cardStep === 'intro'}
	<div class="flex flex-col items-center gap-6 text-center">
		<div class="w-24 h-24 rounded-2xl bg-surface-light flex items-center justify-center">
			<svg class="w-12 h-12 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
				<rect x="2" y="4" width="14" height="16" rx="2"/>
				<path d="M18 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>
				<circle cx="9" cy="12" r="3" fill="currentColor" stroke="none"/>
			</svg>
		</div>
		<h2 class="text-lg font-semibold text-text">
			{existingCardCount > 0 ? t('setup.card_count', { count: existingCardCount }) : t('setup.first_card')}
		</h2>
		{#if !hasRfid}
			<div class="w-full max-w-sm">
				<HealthBanner type="warning" message={t('setup.card_no_reader')} />
			</div>
		{:else}
			<p class="text-sm text-text-muted max-w-xs">
				{existingCardCount > 0 ? t('setup.card_desc_existing') : t('setup.card_desc')}
			</p>
		{/if}
	</div>
{/if}

{#if cardStep === 'scan'}
	<div class="flex flex-col items-center gap-6 text-center">
		<div class="w-28 h-28 rounded-2xl bg-surface-light flex items-center justify-center animate-pulse">
			<svg class="w-14 h-14 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
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
			{#if scan.autoRetryCountdown > 0}
				<p class="text-xs text-text-muted">{t('wizard.auto_retry', { seconds: scan.autoRetryCountdown })}</p>
			{/if}
			<button onclick={() => { scan.cancelAutoRetry(); onClearError(); scan.startScan(false); }} class="text-sm text-primary font-medium">{t('general.retry')}</button>
		{:else}
			<p class="text-sm text-text-muted animate-pulse">{t('wizard.scanning')}</p>
		{/if}
	</div>
{/if}

{#if cardStep === 'content'}
	<div class="flex flex-col gap-4">
		<h2 class="text-lg font-semibold text-text text-center">{t('wizard.select_content')}</h2>
		{#if scan.scannedCardId}
			<p class="text-xs text-text-muted text-center">{t('wizard.card_id', { id: scan.scannedCardId.toUpperCase() })}</p>
		{/if}
		{#if scan.hasExisting}
			<div class="px-3 py-2 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent text-center">
				{t('wizard.already_assigned')}
			</div>
		{/if}

		<ContentPicker
			contentType={scan.contentType}
			contentPath={scan.contentPath}
			name={scan.cardName}
			{expertMode}
			onTypeChange={(type: ContentType) => scan.handleTypeChange(type)}
			onSelect={(path: string, autoName: string) => scan.handleSelect(path, autoName)}
		/>

		<label class="block">
			<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_name')}</span>
			<input type="text" bind:value={scan.cardName} placeholder={t('wizard.name_placeholder')}
				class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50" />
		</label>

		{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
	</div>
{/if}

{#if cardStep === 'done'}
	<div class="flex flex-col items-center gap-6 text-center">
		<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
			<Icon name="check" size={40} class="text-green-500" strokeWidth={2.5} />
		</div>
		<div>
			<h2 class="text-lg font-semibold mb-1">{t('wizard.step_done')}</h2>
			<p class="text-sm text-text-muted max-w-xs">{t('wizard.done_desc')}</p>
		</div>
	</div>
{/if}
