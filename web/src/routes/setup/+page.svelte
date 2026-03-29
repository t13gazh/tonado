<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, systemApi, config, player, type HardwareDetection, type WifiStatus, type SystemInfoData, type ContentType } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import { isBackendOffline } from '$lib/stores/health.svelte';
	import HardwareStep from '$lib/components/setup/HardwareStep.svelte';
	import WifiStep from '$lib/components/setup/WifiStep.svelte';
	import AudioStep from '$lib/components/setup/AudioStep.svelte';
	import CardStep from '$lib/components/setup/CardStep.svelte';
	import CompleteStep from '$lib/components/setup/CompleteStep.svelte';
	import type { CardStepType } from '$lib/components/setup/CardStep.svelte';

	type WizardStep = 'hardware' | 'wifi' | 'audio' | 'card' | 'complete';

	const STEPS: WizardStep[] = ['hardware', 'wifi', 'audio', 'card', 'complete'];
	const STEP_LABELS: Record<WizardStep, () => string> = {
		hardware: () => t('setup.step_hardware'),
		wifi: () => t('setup.step_wifi'),
		audio: () => t('setup.step_audio'),
		card: () => t('setup.step_card'),
		complete: () => t('setup.step_done'),
	};

	let currentStep = $state<WizardStep>('hardware');
	let highestStep = $state(0);
	let loading = $state(false);
	let error = $state('');

	// Hardware
	let hardware = $state<HardwareDetection | null>(null);
	let detectingHardware = $state(false);
	let sysInfo = $state<SystemInfoData | null>(null);

	// WiFi
	let wifiStatus = $state<WifiStatus | null>(null);
	let wifiLoading = $state(false);

	// Audio
	let audioOutputs = $state<{ id: number; name: string; enabled: boolean }[]>([]);
	let selectedAudioId = $state<number | null>(null);

	// Card
	let cardStep = $state<CardStepType>('intro');
	let expertMode = $state(false);
	let cardStepRef: CardStep;

	const backendDown = $derived(isBackendOffline());
	const currentIdx = $derived(STEPS.indexOf(currentStep));
	const hasRfid = $derived(hardware ? hardware.rfid.reader !== 'none' : false);

	onMount(async () => {
		try {
			const [status, info] = await Promise.all([
				setupApi.status(),
				systemApi.info().catch(() => null),
			]);
			sysInfo = info;
			if (status.is_complete) { goto('/'); return; }
			if (status.hardware) hardware = status.hardware;
			const stepMap: Record<string, WizardStep> = {
				not_started: 'hardware',
				hardware_detection: 'wifi',
				wifi_setup: 'audio',
				audio_setup: 'card',
				first_card: 'complete',
				completed: 'complete',
			};
			const mapped = stepMap[status.current_step];
			if (mapped && status.current_step !== 'not_started') {
				currentStep = mapped;
				highestStep = STEPS.indexOf(mapped);
			}
			if (!hardware) {
				try { hardware = (await setupApi.detectHardware()); } catch {}
			}
			if (currentStep === 'wifi') await loadWifiStatus();
		} catch {
			currentStep = 'hardware';
		}
		try {
			const cfg = await config.getAll();
			expertMode = cfg['wizard.expert_mode'] === true;
		} catch {}
	});

	async function detectHardware() {
		detectingHardware = true; error = '';
		try {
			const [hw, info] = await Promise.all([
				setupApi.detectHardware(),
				systemApi.info().catch(() => null),
			]);
			hardware = hw;
			sysInfo = info;
		}
		catch (e) { if (!backendDown) error = e instanceof Error ? e.message : 'Hardware detection failed'; }
		finally { detectingHardware = false; }
	}

	async function goToStep(step: WizardStep) {
		error = '';
		currentStep = step;
		const idx = STEPS.indexOf(step);
		if (idx > highestStep) highestStep = idx;
		if (step === 'hardware' && !hardware) await detectHardware();
		else if (step === 'wifi') await loadWifiStatus();
		else if (step === 'audio') await loadAudioOutputs();
		else if (step === 'card') cardStep = 'intro';
	}

	async function nextStep() {
		if (backendDown) return;
		if (currentIdx < STEPS.length - 1) await goToStep(STEPS[currentIdx + 1]);
	}

	async function prevStep() {
		if (currentIdx > 0) await goToStep(STEPS[currentIdx - 1]);
	}

	function canClickStep(idx: number): boolean {
		return idx <= highestStep && !backendDown;
	}

	async function loadWifiStatus() {
		wifiLoading = true;
		try { wifiStatus = await setupApi.wifiStatus(); } catch { wifiStatus = null; }
		finally { wifiLoading = false; }
	}

	async function loadAudioOutputs() {
		try {
			audioOutputs = await player.outputs();
			const enabled = audioOutputs.find((o) => o.enabled);
			if (enabled) selectedAudioId = enabled.id;
			else if (audioOutputs.length > 0) selectedAudioId = audioOutputs[0].id;
		} catch { audioOutputs = []; }
	}

	function onError(msg: string) { error = msg; }
	function onClearError() { error = ''; }

	async function completeSetup() {
		loading = true;
		try { await setupApi.complete(); goto('/'); }
		catch (e) { error = e instanceof Error ? e.message : 'Setup completion failed'; loading = false; }
	}
</script>

<div class="flex flex-col h-dvh">
	<!-- Fixed header -->
	<div class="shrink-0 px-4 pt-4 pb-2">
		<h1 class="text-xl font-bold text-text text-center">{t('setup.title')}</h1>
	</div>

	<!-- Step indicator (clickable) -->
	<div class="shrink-0 flex items-center gap-1.5 px-4 pb-3">
		{#each STEPS as step, i}
			{@const isActive = step === currentStep}
			{@const isCompleted = currentIdx > i}
			{@const clickable = canClickStep(i) && step !== currentStep}
			<button
				class="flex-1 flex flex-col items-center gap-1 {clickable ? 'cursor-pointer' : 'cursor-default'}"
				onclick={() => { if (clickable) goToStep(step); }}
				disabled={!clickable}
			>
				<div class="w-full h-1.5 rounded-full transition-colors {isActive ? 'bg-primary' : isCompleted ? 'bg-primary/60' : 'bg-surface-lighter'}"></div>
				<span class="text-[10px] transition-colors {isActive ? 'text-primary font-medium' : clickable ? 'text-text-muted hover:text-text' : 'text-text-muted'}">{STEP_LABELS[step]()}</span>
			</button>
		{/each}
	</div>

	<!-- Backend offline warning -->
	{#if backendDown}
		<div class="shrink-0 px-4 pb-2">
			<HealthBanner type="error" message={t('health.backend_offline')} />
		</div>
	{/if}

	<!-- Scrollable content area (centered) -->
	<div class="flex-1 overflow-y-auto px-4">
		<div class="flex flex-col min-h-full justify-center py-4">

		{#if currentStep === 'hardware'}
			<HardwareStep
				{hardware} {sysInfo} {detectingHardware} {error} {backendDown}
				onHardwareDetected={(hw, info) => { hardware = hw; sysInfo = info; }}
				{onError}
			/>
		{:else if currentStep === 'wifi'}
			<WifiStep
				{wifiStatus} {wifiLoading} {error}
				{onError}
				onWifiStatusChange={(status) => { wifiStatus = status; }}
			/>
		{:else if currentStep === 'audio'}
			<AudioStep
				{audioOutputs} {selectedAudioId} {error}
				{onError}
				onAudioChange={(outputs, id) => { audioOutputs = outputs; selectedAudioId = id; }}
			/>
		{:else if currentStep === 'card'}
			<CardStep
				bind:this={cardStepRef}
				bind:cardStep
				{hasRfid} {expertMode} {error}
				{onError} {onClearError}
			/>
		{:else if currentStep === 'complete'}
			<CompleteStep {hardware} {sysInfo} {wifiStatus} {error} />
		{/if}

		</div>
	</div>

	<!-- Fixed bottom navigation -->
	<div class="shrink-0 px-4 py-3 border-t border-surface-lighter bg-surface">
		{#if currentStep === 'hardware'}
			{#if !detectingHardware}
				<button onclick={nextStep} disabled={backendDown}
					class="w-full py-3 bg-primary hover:bg-primary-light disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors">
					{t('setup.next')}
				</button>
			{/if}

		{:else if currentStep === 'wifi'}
			<div class="flex gap-3">
				<button onclick={prevStep}
					class="py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
					{t('general.back')}
				</button>
				<button onclick={nextStep} disabled={backendDown}
					class="flex-1 py-3 bg-primary hover:bg-primary-light disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors">
					{t('setup.next')}
				</button>
			</div>

		{:else if currentStep === 'audio'}
			<div class="flex gap-3">
				<button onclick={prevStep}
					class="py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
					{t('general.back')}
				</button>
				<button onclick={nextStep} disabled={backendDown}
					class="flex-1 py-3 bg-primary hover:bg-primary-light disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors">
					{t('setup.next')}
				</button>
			</div>

		{:else if currentStep === 'card'}
			{#if cardStep === 'intro'}
				<div class="flex flex-col gap-2">
					{#if hasRfid}
						<button onclick={() => cardStepRef.startCardScan()} disabled={backendDown}
							class="w-full py-3 bg-primary hover:bg-primary-light disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors">
							{t('setup.card_setup')}
						</button>
					{/if}
					<div class="flex gap-3">
						<button onclick={prevStep}
							class="py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
							{t('general.back')}
						</button>
						<button onclick={async () => { try { await setupApi.firstCardDone(); } catch {} await goToStep('complete'); }}
							class="flex-1 py-3 {hasRfid ? 'bg-surface-light hover:bg-surface-lighter text-text-muted' : 'bg-primary hover:bg-primary-light text-white'} rounded-lg font-medium transition-colors">
							{hasRfid ? t('setup.card_skip') : t('setup.next')}
						</button>
					</div>
				</div>
			{:else if cardStep === 'scan'}
				<button onclick={() => cardStepRef.cancelScan()}
					class="w-full py-3 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
					{t('general.cancel')}
				</button>
			{:else if cardStep === 'content'}
				<div class="flex gap-3">
					<button onclick={() => { cardStep = 'intro'; }}
						class="py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
						{t('general.back')}
					</button>
					<button onclick={() => cardStepRef.saveCard()} disabled={!cardStepRef?.canSave()}
						class="flex-1 py-3 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-lg font-medium transition-colors">
						{t('wizard.next')}
					</button>
				</div>
			{:else if cardStep === 'done'}
				<div class="flex flex-col gap-2">
					<button onclick={async () => { try { await setupApi.firstCardDone(); } catch {} await goToStep('complete'); }}
						class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors">
						{t('setup.next')}
					</button>
					<button onclick={() => cardStepRef.resetForNewCard()}
						class="w-full py-2.5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
						{t('card.add')}
					</button>
				</div>
			{/if}

		{:else if currentStep === 'complete'}
			<div class="flex gap-3">
				<button onclick={prevStep}
					class="py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
					{t('general.back')}
				</button>
				<button onclick={completeSetup} disabled={loading || backendDown}
					class="flex-1 py-3 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-lg font-medium transition-colors">
					{#if loading}<span class="animate-pulse">{t('general.loading')}</span>
					{:else}{t('setup.complete_button')}{/if}
				</button>
			</div>
		{/if}
	</div>
</div>
