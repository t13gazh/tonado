<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, player, type HardwareDetection, type WifiNetwork, type WifiStatus } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

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
	let loading = $state(false);
	let error = $state('');

	// Hardware state
	let hardware = $state<HardwareDetection | null>(null);
	let detectingHardware = $state(false);

	// WiFi state
	let wifiStatus = $state<WifiStatus | null>(null);
	let wifiNetworks = $state<WifiNetwork[]>([]);
	let wifiScanning = $state(false);
	let showWifiList = $state(false);
	let selectedSsid = $state('');
	let wifiPassword = $state('');
	let wifiConnecting = $state(false);

	// Audio state
	let audioOutputs = $state<{ id: number; name: string; enabled: boolean }[]>([]);
	let selectedAudioId = $state<number | null>(null);

	onMount(async () => {
		try {
			const status = await setupApi.status();
			if (status.is_complete) {
				goto('/');
				return;
			}
			// Restore state based on current_step
			if (status.hardware) {
				hardware = status.hardware;
			}
			// Map backend step to wizard step
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
			}
			// If on hardware step and no hardware detected yet, auto-detect
			if (currentStep === 'hardware' && !hardware) {
				await detectHardware();
			}
		} catch {
			// Setup API not available, start from beginning
			await detectHardware();
		}
	});

	async function detectHardware() {
		detectingHardware = true;
		error = '';
		try {
			hardware = await setupApi.detectHardware();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Hardware detection failed';
		} finally {
			detectingHardware = false;
		}
	}

	async function goToStep(step: WizardStep) {
		error = '';
		currentStep = step;
		if (step === 'wifi') {
			await loadWifiStatus();
		} else if (step === 'audio') {
			await loadAudioOutputs();
		}
	}

	async function nextStep() {
		const idx = STEPS.indexOf(currentStep);
		if (idx < STEPS.length - 1) {
			await goToStep(STEPS[idx + 1]);
		}
	}

	// WiFi methods
	async function loadWifiStatus() {
		try {
			wifiStatus = await setupApi.wifiStatus();
		} catch {
			wifiStatus = null;
		}
	}

	async function scanWifi() {
		wifiScanning = true;
		error = '';
		try {
			wifiNetworks = await setupApi.wifiScan();
			showWifiList = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'WiFi scan failed';
		} finally {
			wifiScanning = false;
		}
	}

	async function connectWifi() {
		if (!selectedSsid) return;
		wifiConnecting = true;
		error = '';
		try {
			const result = await setupApi.wifiConnect(selectedSsid, wifiPassword);
			if (result.success) {
				wifiStatus = result.status ?? null;
				showWifiList = false;
				selectedSsid = '';
				wifiPassword = '';
			} else {
				error = result.error ?? t('setup.wifi_error');
			}
		} catch (e) {
			error = e instanceof Error ? e.message : t('setup.wifi_error');
		} finally {
			wifiConnecting = false;
		}
	}

	// Audio methods
	async function loadAudioOutputs() {
		try {
			audioOutputs = await player.outputs();
			const enabled = audioOutputs.find((o) => o.enabled);
			if (enabled) selectedAudioId = enabled.id;
			else if (audioOutputs.length > 0) selectedAudioId = audioOutputs[0].id;
		} catch {
			audioOutputs = [];
		}
	}

	async function selectAudio(id: number) {
		selectedAudioId = id;
		try {
			// Enable selected, disable others
			for (const output of audioOutputs) {
				if (output.id === id && !output.enabled) {
					await player.toggleOutput(output.id, true);
				} else if (output.id !== id && output.enabled) {
					await player.toggleOutput(output.id, false);
				}
			}
			await setupApi.setupAudio(`hw:${id}`);
			audioOutputs = await player.outputs();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Audio setup failed';
		}
	}

	async function completeSetup() {
		loading = true;
		try {
			await setupApi.complete();
			goto('/');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Setup completion failed';
			loading = false;
		}
	}
</script>

<div class="flex flex-col h-full">
	<!-- Header -->
	<div class="px-4 pt-4 pb-2">
		<h1 class="text-xl font-bold text-text">{t('setup.title')}</h1>
	</div>

	<!-- Step indicator -->
	<div class="flex items-center gap-1.5 px-4 pb-4">
		{#each STEPS as step, i}
			{@const isActive = step === currentStep}
			{@const isCompleted = STEPS.indexOf(currentStep) > i}
			<div class="flex-1 flex flex-col items-center gap-1">
				<div class="w-full h-1 rounded-full {isActive ? 'bg-primary' : isCompleted ? 'bg-primary/60' : 'bg-surface-lighter'}"></div>
				<span class="text-[10px] {isActive ? 'text-primary font-medium' : 'text-text-muted'}">{STEP_LABELS[step]()}</span>
			</div>
		{/each}
	</div>

	<!-- Content -->
	<div class="flex-1 overflow-y-auto px-4 pb-4">
		<!-- Step 1: Hardware Detection -->
		{#if currentStep === 'hardware'}
			<div class="flex flex-col gap-4">
				{#if detectingHardware}
					<div class="flex flex-col items-center justify-center gap-4 py-12">
						<div class="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center animate-pulse">
							<svg class="w-8 h-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<rect x="4" y="4" width="16" height="16" rx="2"/>
								<path d="M9 9h6v6H9z"/>
								<path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>
							</svg>
						</div>
						<p class="text-text-muted animate-pulse">{t('setup.detecting_hardware')}</p>
					</div>
				{:else if hardware}
					<div class="bg-surface-light rounded-xl p-4 space-y-3">
						<h2 class="text-sm font-semibold text-text">{t('setup.detection_complete')}</h2>

						{#if hardware.is_mock}
							<p class="text-xs text-text-muted">{t('setup.detection_mock')}</p>
						{/if}

						<!-- Pi Model -->
						<div class="flex items-center justify-between py-2 border-b border-surface-lighter">
							<span class="text-sm text-text-muted">{t('setup.pi_model')}</span>
							<span class="text-sm text-text">
								{#if hardware.pi.model !== 'unknown'}
									<span class="inline-flex items-center gap-1">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{hardware.pi.model}
										{#if hardware.pi.ram_mb > 0}
											<span class="text-text-muted">({hardware.pi.ram_mb} MB)</span>
										{/if}
									</span>
								{:else}
									<span class="text-text-muted">--</span>
								{/if}
							</span>
						</div>

						<!-- RFID Reader -->
						<div class="flex items-center justify-between py-2 border-b border-surface-lighter">
							<span class="text-sm text-text-muted">{t('setup.rfid_reader')}</span>
							<span class="text-sm">
								{#if hardware.rfid.reader !== 'none'}
									<span class="inline-flex items-center gap-1 text-text">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{hardware.rfid.reader.toUpperCase()}
									</span>
								{:else}
									<span class="inline-flex items-center gap-1 text-text-muted">
										<span class="w-4 text-center">--</span>
										{t('setup.not_found')}
									</span>
								{/if}
							</span>
						</div>

						<!-- Gyro -->
						<div class="flex items-center justify-between py-2 border-b border-surface-lighter">
							<span class="text-sm text-text-muted">{t('setup.gyro_sensor')}</span>
							<span class="text-sm">
								{#if hardware.gyro_detected}
									<span class="inline-flex items-center gap-1 text-text">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{t('setup.detected')}
									</span>
								{:else}
									<span class="inline-flex items-center gap-1 text-text-muted">
										<span class="w-4 text-center">--</span>
										{t('setup.not_found')}
									</span>
								{/if}
							</span>
						</div>

						<!-- Audio outputs -->
						<div class="flex items-center justify-between py-2">
							<span class="text-sm text-text-muted">{t('setup.audio_outputs')}</span>
							<span class="text-sm text-text">
								{#if hardware.audio.length > 0}
									<span class="inline-flex items-center gap-1">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{hardware.audio.length}
									</span>
								{:else}
									<span class="text-text-muted">--</span>
								{/if}
							</span>
						</div>
					</div>
				{/if}

				{#if error}
					<p class="text-sm text-red-400">{error}</p>
				{/if}

				{#if !detectingHardware}
					<button
						onclick={nextStep}
						class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors"
					>
						{t('setup.next')}
					</button>
				{/if}
			</div>
		{/if}

		<!-- Step 2: WiFi Setup -->
		{#if currentStep === 'wifi'}
			<div class="flex flex-col gap-4">
				{#if wifiStatus?.connected && !showWifiList}
					<!-- Already connected -->
					<div class="bg-surface-light rounded-xl p-4 space-y-2">
						<div class="flex items-center gap-2">
							<svg class="w-5 h-5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
							<span class="text-sm font-medium text-text">{t('setup.wifi_connected', { ssid: wifiStatus.ssid })}</span>
						</div>
						{#if wifiStatus.ip_address}
							<p class="text-xs text-text-muted pl-7">{t('setup.wifi_connected_ip', { ip: wifiStatus.ip_address })}</p>
						{/if}
					</div>
					<button
						onclick={scanWifi}
						class="w-full py-2.5 bg-surface-light hover:bg-surface-lighter text-text rounded-lg text-sm font-medium transition-colors"
					>
						{t('setup.wifi_other')}
					</button>
				{:else}
					<!-- WiFi scan / select -->
					{#if !showWifiList}
						<button
							onclick={scanWifi}
							disabled={wifiScanning}
							class="w-full py-3 bg-surface-light hover:bg-surface-lighter text-text rounded-lg font-medium transition-colors disabled:opacity-50"
						>
							{#if wifiScanning}
								<span class="animate-pulse">{t('setup.wifi_scanning')}</span>
							{:else}
								{t('setup.wifi_select')}
							{/if}
						</button>
					{:else}
						<div class="space-y-2">
							<h3 class="text-sm font-medium text-text">{t('setup.wifi_select')}</h3>
							<div class="bg-surface-light rounded-xl overflow-hidden divide-y divide-surface-lighter max-h-48 overflow-y-auto">
								{#each wifiNetworks as network}
									<button
										onclick={() => { selectedSsid = network.ssid; wifiPassword = ''; }}
										class="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-surface-lighter transition-colors {selectedSsid === network.ssid ? 'bg-primary/10' : ''}"
									>
										<span class="text-sm text-text">{network.ssid}</span>
										<div class="flex items-center gap-2">
											{#if network.security !== 'open'}
												<svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
												</svg>
											{/if}
											<!-- Signal bars -->
											<div class="flex items-end gap-0.5 h-3">
												<div class="w-1 h-1 rounded-sm {network.signal > 0 ? 'bg-text-muted' : 'bg-surface-lighter'}"></div>
												<div class="w-1 h-1.5 rounded-sm {network.signal > 30 ? 'bg-text-muted' : 'bg-surface-lighter'}"></div>
												<div class="w-1 h-2 rounded-sm {network.signal > 60 ? 'bg-text-muted' : 'bg-surface-lighter'}"></div>
												<div class="w-1 h-3 rounded-sm {network.signal > 80 ? 'bg-text-muted' : 'bg-surface-lighter'}"></div>
											</div>
										</div>
									</button>
								{/each}
							</div>

							{#if selectedSsid}
								<div class="space-y-3 pt-2">
									<label class="block">
										<span class="text-xs text-text-muted mb-1 block">{t('setup.wifi_password')}</span>
										<input
											type="password"
											bind:value={wifiPassword}
											placeholder="..."
											class="w-full px-3 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
										/>
									</label>
									<button
										onclick={connectWifi}
										disabled={wifiConnecting}
										class="w-full py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
									>
										{#if wifiConnecting}
											<span class="animate-pulse">{t('setup.connect')}...</span>
										{:else}
											{t('setup.connect')}
										{/if}
									</button>
								</div>
							{/if}

							<button
								onclick={() => { showWifiList = false; selectedSsid = ''; }}
								class="w-full py-2 text-sm text-text-muted hover:text-text transition-colors"
							>
								{t('general.cancel')}
							</button>
						</div>
					{/if}
				{/if}

				{#if error}
					<p class="text-sm text-red-400">{error}</p>
				{/if}

				<div class="flex gap-3 pt-2">
					<button
						onclick={() => nextStep()}
						class="flex-1 py-3 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors"
					>
						{t('setup.skip')}
					</button>
					<button
						onclick={nextStep}
						class="flex-1 py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors"
					>
						{t('setup.next')}
					</button>
				</div>
			</div>
		{/if}

		<!-- Step 3: Audio Setup -->
		{#if currentStep === 'audio'}
			<div class="flex flex-col gap-4">
				<h2 class="text-sm font-semibold text-text">{t('setup.audio_select')}</h2>

				{#if audioOutputs.length === 0}
					<p class="text-sm text-text-muted py-4 text-center">{t('setup.audio_no_outputs')}</p>
				{:else}
					<div class="space-y-2">
						{#each audioOutputs as output}
							<button
								onclick={() => selectAudio(output.id)}
								class="w-full bg-surface-light rounded-xl p-4 flex items-center gap-3 text-left transition-colors {selectedAudioId === output.id ? 'ring-2 ring-primary' : 'hover:bg-surface-lighter'}"
							>
								<!-- Radio circle -->
								<div class="w-5 h-5 rounded-full border-2 flex items-center justify-center {selectedAudioId === output.id ? 'border-primary' : 'border-surface-lighter'}">
									{#if selectedAudioId === output.id}
										<div class="w-2.5 h-2.5 rounded-full bg-primary"></div>
									{/if}
								</div>
								<div class="flex-1">
									<span class="text-sm text-text">{output.name}</span>
									{#if output.enabled}
										<span class="ml-2 text-xs text-green-500">{t('setup.audio_recommended')}</span>
									{/if}
								</div>
							</button>
						{/each}
					</div>
				{/if}

				{#if error}
					<p class="text-sm text-red-400">{error}</p>
				{/if}

				<button
					onclick={nextStep}
					class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors"
				>
					{t('setup.next')}
				</button>
			</div>
		{/if}

		<!-- Step 4: First Card -->
		{#if currentStep === 'card'}
			<div class="flex flex-col items-center justify-center gap-6 py-8">
				<div class="w-24 h-24 rounded-2xl bg-surface-light flex items-center justify-center">
					<svg class="w-12 h-12 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
						<rect x="2" y="4" width="14" height="16" rx="2"/>
						<path d="M18 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>
						<circle cx="9" cy="12" r="3" fill="currentColor" stroke="none"/>
					</svg>
				</div>
				<div class="text-center">
					<h2 class="text-lg font-semibold text-text mb-1">{t('setup.first_card')}</h2>
					<p class="text-sm text-text-muted max-w-xs">{t('setup.card_desc')}</p>
				</div>

				<div class="flex flex-col gap-2 w-full max-w-xs">
					<button
						onclick={async () => {
							await setupApi.firstCardDone();
							goto('/cards/wizard');
						}}
						class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors"
					>
						{t('setup.card_setup')}
					</button>
					<button
						onclick={async () => {
							await setupApi.firstCardDone();
							await goToStep('complete');
						}}
						class="w-full py-2.5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors"
					>
						{t('setup.card_skip')}
					</button>
				</div>
			</div>
		{/if}

		<!-- Step 5: Complete -->
		{#if currentStep === 'complete'}
			<div class="flex flex-col items-center justify-center gap-6 py-8">
				<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
					<svg class="w-10 h-10 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
						<path d="M20 6L9 17l-5-5"/>
					</svg>
				</div>
				<div class="text-center">
					<h2 class="text-xl font-bold text-text mb-2">{t('setup.complete_title')}</h2>
					<p class="text-sm text-text-muted max-w-xs">{t('setup.complete_desc')}</p>
				</div>

				<!-- Summary -->
				{#if hardware}
					<div class="w-full max-w-sm bg-surface-light rounded-xl p-4 space-y-2 text-sm">
						{#if hardware.pi.model !== 'unknown'}
							<div class="flex justify-between">
								<span class="text-text-muted">{t('setup.pi_model')}</span>
								<span class="text-text">{hardware.pi.model}</span>
							</div>
						{/if}
						{#if hardware.rfid.reader !== 'none'}
							<div class="flex justify-between">
								<span class="text-text-muted">{t('setup.rfid_reader')}</span>
								<span class="text-text">{hardware.rfid.reader.toUpperCase()}</span>
							</div>
						{/if}
						{#if hardware.gyro_detected}
							<div class="flex justify-between">
								<span class="text-text-muted">{t('setup.gyro_sensor')}</span>
								<span class="text-green-500">{t('setup.detected')}</span>
							</div>
						{/if}
					</div>
				{/if}

				{#if error}
					<p class="text-sm text-red-400">{error}</p>
				{/if}

				<button
					onclick={completeSetup}
					disabled={loading}
					class="w-full max-w-xs py-3 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-xl font-medium transition-colors"
				>
					{#if loading}
						<span class="animate-pulse">{t('general.loading')}</span>
					{:else}
						{t('setup.complete_button')}
					{/if}
				</button>
			</div>
		{/if}
	</div>
</div>
