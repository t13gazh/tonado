<script lang="ts" module>
	export type ButtonStepType = 'idle' | 'select' | 'scanning' | 'testing' | 'done';
</script>

<script lang="ts">
	import { t } from '$lib/i18n';
	import Icon from '$lib/components/Icon.svelte';
	import InlineError from '$lib/components/InlineError.svelte';
	import { createButtonScan, type ButtonAssignment } from '$lib/button-scan.svelte';

	interface Props {
		freeGpios: number[];
		error: string;
		buttonStep: ButtonStepType;
		onError: (msg: string) => void;
		onClearError: () => void;
	}

	let { freeGpios, error, buttonStep = $bindable('idle'), onError, onClearError }: Props = $props();

	const scan = createButtonScan();
	let testFeedEl: HTMLDivElement;

	// Auto-scroll test feed to bottom
	$effect(() => {
		if (scan.testEvents.length > 0 && testFeedEl) {
			testFeedEl.scrollTop = testFeedEl.scrollHeight;
		}
	});

	// Sync scan errors to parent
	$effect(() => {
		if (scan.error) onError(scan.error);
	});

	// Sync phase to parent
	$effect(() => {
		buttonStep = scan.phase as ButtonStepType;
	});

	export async function loadExisting() {
		await scan.loadExisting();
	}

	export function isDirty(): boolean {
		return scan.dirty;
	}

	export function hasExistingConfig(): boolean {
		return scan.hasExistingConfig;
	}

	export function startSelect() {
		onClearError();
		scan.startSelect();
	}

	export async function startScan() {
		onClearError();
		await scan.startScan();
	}

	export function cancelScan() {
		scan.reset();
	}

	export function skipCurrent() {
		scan.skipCurrentButton();
	}

	export async function retryScan() {
		onClearError();
		await scan.retryScan();
	}

	export async function startTest() {
		onClearError();
		await scan.startTest();
	}

	export async function stopTest() {
		await scan.stopTest();
	}

	export async function save(): Promise<boolean> {
		onClearError();
		return await scan.save();
	}

	export function reset() {
		scan.reset();
	}

	export function getAssignedCount(): number {
		return scan.assignedCount;
	}

	export function getAssignedLabels(): string[] {
		return scan.buttons
			.filter((b) => b.gpio !== null)
			.map((b) => t(b.label));
	}

	export function canSkipCurrent(): boolean {
		return scan.currentButton !== null && !scan.currentButton.required;
	}

	function getLabelForAction(btn: ButtonAssignment): string {
		return t(btn.label);
	}
</script>

{#if buttonStep === 'idle'}
	<div class="flex flex-col items-center gap-6 text-center">
		{#if scan.hasExistingConfig}
			<!-- Existing config detected -->
			<div class="w-24 h-24 rounded-2xl bg-green-500/20 flex items-center justify-center">
				<Icon name="check" size={48} class="text-green-500" strokeWidth={1.5} />
			</div>
			<h2 class="text-lg font-semibold text-text">{t('buttons.already_configured_title')}</h2>
			<p class="text-sm text-text-muted max-w-xs">
				{t('buttons.already_configured_desc', { count: String(scan.existingConfig.length), labels: scan.existingConfig.map((b) => t(`buttons.${b.action}`)).join(', ') })}
			</p>
		{:else}
			<div class="w-24 h-24 rounded-2xl bg-surface-light flex items-center justify-center">
				<!-- Button/GPIO icon -->
				<svg class="w-12 h-12 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<circle cx="12" cy="12" r="9"/>
					<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>
					<path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>
				</svg>
			</div>
			<h2 class="text-lg font-semibold text-text">{t('buttons.title')}</h2>
			<p class="text-sm text-text-muted max-w-xs">{t('buttons.intro')}</p>
			{#if freeGpios.length === 0}
				<p class="text-sm text-text-muted">{t('buttons.no_gpios')}</p>
			{:else}
				<p class="text-xs text-text-muted">{t('buttons.free_gpios', { count: String(freeGpios.length) })}</p>
			{/if}
		{/if}
	</div>
{/if}

{#if buttonStep === 'select'}
	<div class="flex flex-col gap-4">
		<h2 class="text-lg font-semibold text-text text-center">{t('buttons.select_title')}</h2>
		<p class="text-sm text-text-muted text-center">{t('buttons.select_desc')}</p>

		<div class="bg-surface-light rounded-xl p-3 space-y-1">
			{#each scan.buttons as btn}
				<label class="flex items-center gap-3 py-2.5 px-2 rounded-lg {btn.required ? 'opacity-80' : 'hover:bg-surface-lighter cursor-pointer'}">
					<input
						type="checkbox"
						checked={btn.selected}
						disabled={btn.required}
						onchange={() => scan.toggleButton(btn.action)}
						class="w-4 h-4 rounded accent-primary"
					/>
					<span class="text-sm text-text flex-1">{getLabelForAction(btn)}</span>
					{#if btn.required}
						<span class="text-xs text-primary">{t('buttons.required')}</span>
					{/if}
				</label>
			{/each}
		</div>
	</div>
{/if}

{#if buttonStep === 'scanning'}
	<div class="flex flex-col items-center gap-6 text-center">
		<!-- Current button prompt -->
		{#if scan.currentButton}
			<div class="w-28 h-28 rounded-2xl bg-surface-light flex items-center justify-center animate-pulse">
				<svg class="w-14 h-14 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<circle cx="12" cy="12" r="9"/>
					<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" class="animate-ping"/>
					<path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>
				</svg>
			</div>
			<div>
				<h2 class="text-lg font-semibold mb-1">{t('buttons.press_now')}</h2>
				<p class="text-base text-primary font-medium">{getLabelForAction(scan.currentButton)}</p>
				<p class="text-xs text-text-muted mt-1">
					{t('buttons.progress', { current: String(scan.scanProgress.current + 1), total: String(scan.scanProgress.total) })}
				</p>
			</div>
		{/if}

		{#if error}
			<InlineError message={error} />
			<button onclick={() => retryScan()} class="text-sm text-primary font-medium">{t('general.retry')}</button>
		{:else if scan.currentButton}
			<p class="text-sm text-text-muted animate-pulse">{t('buttons.waiting')}</p>
		{/if}

		<!-- Progress list showing already assigned buttons -->
		{#if scan.selectedButtons.length > 1}
			<div class="w-full max-w-sm bg-surface-light rounded-xl p-3 space-y-1 text-left">
				{#each scan.selectedButtons as btn, i}
					<div class="flex items-center gap-2 py-1.5 px-2 text-sm {i === scan.scanProgress.current ? 'text-primary font-medium' : ''}">
						{#if btn.gpio !== null}
							<Icon name="check" size={16} class="text-green-500" strokeWidth={2.5} />
							<span class="flex-1 text-text">{getLabelForAction(btn)}</span>
							<Icon name="check" size={14} class="text-green-500" strokeWidth={2} />
						{:else if btn.skipped}
							<span class="w-4 text-center text-text-muted">--</span>
							<span class="flex-1 text-text-muted">{getLabelForAction(btn)}</span>
							<span class="text-xs text-text-muted">{t('buttons.skipped')}</span>
						{:else if i === scan.scanProgress.current}
							<span class="w-4 h-4 rounded-full border-2 border-primary animate-pulse"></span>
							<span class="flex-1">{getLabelForAction(btn)}</span>
						{:else}
							<span class="w-4 h-4 rounded-full border border-surface-lighter"></span>
							<span class="flex-1 text-text-muted">{getLabelForAction(btn)}</span>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}

{#if buttonStep === 'done'}
	<div class="flex flex-col items-center gap-6 text-center">
		<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
			<Icon name="check" size={40} class="text-green-500" strokeWidth={2.5} />
		</div>
		<div>
			<h2 class="text-lg font-semibold mb-1">{t('buttons.done_title')}</h2>
			<p class="text-sm text-text-muted max-w-xs">{t('buttons.done_desc', { count: String(scan.assignedCount) })}</p>
		</div>

		<!-- Assignment summary -->
		<div class="w-full max-w-sm bg-surface-light rounded-xl p-3 space-y-1 text-left">
			{#each scan.selectedButtons as btn}
				<div class="flex items-center gap-2 py-1.5 px-2 text-sm">
					{#if btn.gpio !== null}
						<Icon name="check" size={16} class="text-green-500" strokeWidth={2.5} />
						<span class="flex-1 text-text">{getLabelForAction(btn)}</span>
					{:else}
						<span class="w-4 text-center text-text-muted">--</span>
						<span class="flex-1 text-text-muted">{getLabelForAction(btn)}</span>
						<span class="text-xs text-text-muted">{t('buttons.skipped')}</span>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Prominent test button -->
		<button onclick={() => startTest()}
			class="w-full max-w-sm py-3 bg-primary hover:bg-primary-light text-white rounded-xl font-medium transition-colors">
			{t('buttons.test_start')}
		</button>

		{#if error}<InlineError message={error} />{/if}
	</div>
{/if}

{#if buttonStep === 'testing'}
	<div class="flex flex-col items-center gap-6 text-center">
		<div class="w-20 h-20 rounded-2xl bg-primary/20 flex items-center justify-center">
			<svg class="w-10 h-10 text-primary animate-pulse" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
				<circle cx="12" cy="12" r="9"/>
				<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>
				<path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>
			</svg>
		</div>
		<div>
			<h2 class="text-lg font-semibold mb-1">{t('buttons.test_title')}</h2>
			<p class="text-sm text-text-muted">{t('buttons.test_desc')}</p>
		</div>

		<!-- Live event feed -->
		<div class="w-full max-w-sm bg-surface-light rounded-xl p-3 min-h-[120px] text-left">
			{#if scan.testEvents.length === 0}
				<p class="text-sm text-text-muted text-center py-4 animate-pulse">{t('buttons.test_waiting')}</p>
			{:else}
				<div bind:this={testFeedEl} class="space-y-1 max-h-48 overflow-y-auto">
					{#each scan.testEvents as event, i}
						<div class="flex items-center gap-2 py-1 px-2 text-sm {i === scan.testEvents.length - 1 ? 'text-primary font-medium' : 'text-text-muted'}">
							<span class="w-2 h-2 rounded-full {i === scan.testEvents.length - 1 ? 'bg-primary' : 'bg-surface-lighter'}"></span>
							<span>{t(`buttons.${event.action}`)}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>

		{#if error}<InlineError message={error} />{/if}
	</div>
{/if}
