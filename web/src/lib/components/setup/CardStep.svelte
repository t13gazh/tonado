<script lang="ts">
	import { t } from '$lib/i18n';
	import { cards, type ContentType } from '$lib/api';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import ContentPicker from '$lib/components/ContentPicker.svelte';

	export type CardStepType = 'intro' | 'scan' | 'content' | 'done';

	interface Props {
		hasRfid: boolean;
		expertMode: boolean;
		error: string;
		cardStep: CardStepType;
		onError: (msg: string) => void;
		onClearError: () => void;
	}

	let { hasRfid, expertMode, error, cardStep = $bindable('intro'), onError, onClearError }: Props = $props();

	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let cardName = $state('');
	let contentType = $state<ContentType>('folder');
	let contentPath = $state('');
	let autoRetryCountdown = $state(0);
	let autoRetryTimer = $state<ReturnType<typeof setInterval> | null>(null);

	function cancelAutoRetry() {
		if (autoRetryTimer) { clearInterval(autoRetryTimer); autoRetryTimer = null; }
		autoRetryCountdown = 0;
	}

	function startAutoRetry() {
		cancelAutoRetry();
		autoRetryCountdown = 3;
		autoRetryTimer = setInterval(() => {
			autoRetryCountdown -= 1;
			if (autoRetryCountdown <= 0) { cancelAutoRetry(); onClearError(); startCardScan(); }
		}, 1000);
	}

	export async function startCardScan() {
		cardStep = 'scan'; scanning = true; onClearError();
		try {
			const result = await cards.waitForScan(30, false);
			if (result.scanned && result.card_id) {
				scannedCardId = result.card_id;
				hasExisting = result.has_mapping ?? false;
				cardName = result.mapping?.name ?? '';
				contentType = (result.mapping?.content_type as ContentType) ?? 'folder';
				contentPath = result.mapping?.content_path ?? '';
				cardStep = 'content';
			} else { startCardScan(); return; }
		} catch {
			onError(t('error.scan_timeout')); scanning = false; startAutoRetry();
		}
	}

	export function cancelScan() {
		cancelAutoRetry();
		cardStep = 'intro';
	}

	function handleCardTypeChange(type: ContentType) { contentType = type; contentPath = ''; cardName = ''; }
	function handleCardSelect(path: string, autoName: string) { contentPath = path; cardName = autoName; }

	export async function saveCard() {
		if (!cardName.trim() || !contentPath.trim()) return;
		onClearError();
		try {
			const data = { card_id: scannedCardId, name: cardName.trim(), content_type: contentType as string, content_path: contentPath.trim() };
			if (hasExisting) await cards.update(scannedCardId, data);
			else await cards.create(data);
			cardStep = 'done';
		} catch { onError(t('error.save_failed')); }
	}

	export function canSave(): boolean {
		return !!(cardName.trim() && contentPath.trim());
	}

	export function resetForNewCard() {
		scannedCardId = ''; cardName = ''; contentPath = ''; contentType = 'folder'; hasExisting = false;
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
		<h2 class="text-lg font-semibold text-text">{t('setup.first_card')}</h2>
		{#if !hasRfid}
			<div class="w-full max-w-sm">
				<HealthBanner type="warning" message={t('setup.card_no_reader')} />
			</div>
		{:else}
			<p class="text-sm text-text-muted max-w-xs">{t('setup.card_desc')}</p>
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
			{#if autoRetryCountdown > 0}
				<p class="text-xs text-text-muted">{t('wizard.auto_retry', { seconds: autoRetryCountdown })}</p>
			{/if}
			<button onclick={() => { cancelAutoRetry(); onClearError(); startCardScan(); }} class="text-sm text-primary font-medium">{t('general.retry')}</button>
		{:else}
			<p class="text-sm text-text-muted animate-pulse">{t('wizard.scanning')}</p>
		{/if}
	</div>
{/if}

{#if cardStep === 'content'}
	<div class="flex flex-col gap-4">
		<h2 class="text-lg font-semibold text-text text-center">{t('wizard.select_content')}</h2>
		{#if scannedCardId}
			<p class="text-xs text-text-muted text-center">{t('wizard.card_id', { id: scannedCardId.toUpperCase() })}</p>
		{/if}
		{#if hasExisting}
			<div class="px-3 py-2 bg-accent/10 border border-accent/20 rounded-lg text-sm text-accent text-center">
				{t('wizard.already_assigned')}
			</div>
		{/if}

		<ContentPicker
			{contentType}
			{contentPath}
			name={cardName}
			{expertMode}
			onTypeChange={handleCardTypeChange}
			onSelect={handleCardSelect}
		/>

		<label class="block">
			<span class="text-xs text-text-muted mb-1 block">{t('wizard.content_name')}</span>
			<input type="text" bind:value={cardName} placeholder="Die drei ???, Folge 1"
				class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50" />
		</label>

		{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
	</div>
{/if}

{#if cardStep === 'done'}
	<div class="flex flex-col items-center gap-6 text-center">
		<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
			<svg class="w-10 h-10 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
				<path d="M20 6L9 17l-5-5"/>
			</svg>
		</div>
		<div>
			<h2 class="text-lg font-semibold mb-1">{t('wizard.step_done')}</h2>
			<p class="text-sm text-text-muted max-w-xs">{t('wizard.done_desc')}</p>
		</div>
	</div>
{/if}
