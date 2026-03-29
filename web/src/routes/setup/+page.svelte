<script lang="ts">
	import { t } from '$lib/i18n';
	import Spinner from '$lib/components/Spinner.svelte';
	import { setupApi, systemApi, cards, config, player, type HardwareDetection, type WifiNetwork, type WifiStatus, type SystemInfoData, type ContentType } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import ContentPicker from '$lib/components/ContentPicker.svelte';
	import { isBackendOffline } from '$lib/stores/health.svelte';

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
	let wifiNetworks = $state<WifiNetwork[]>([]);
	let wifiScanning = $state(false);
	let showWifiList = $state(false);
	let selectedSsid = $state('');
	let wifiPassword = $state('');
	let wifiConnecting = $state(false);

	// Audio
	let audioOutputs = $state<{ id: number; name: string; enabled: boolean }[]>([]);
	let selectedAudioId = $state<number | null>(null);

	// Card (inline wizard)
	type CardStep = 'intro' | 'scan' | 'content' | 'done';
	let cardStep = $state<CardStep>('intro');
	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let cardName = $state('');
	let contentType = $state<ContentType>('folder');
	let contentPath = $state('');
	let expertMode = $state(false);
	let autoRetryCountdown = $state(0);
	let autoRetryTimer = $state<ReturnType<typeof setInterval> | null>(null);

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
			// Always fetch hardware if not in status (e.g. navigating back)
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

	// WiFi
	async function loadWifiStatus() {
		wifiLoading = true;
		try { wifiStatus = await setupApi.wifiStatus(); } catch { wifiStatus = null; }
		finally { wifiLoading = false; }
	}

	async function scanWifi() {
		wifiScanning = true; error = '';
		try { wifiNetworks = await setupApi.wifiScan(); showWifiList = true; }
		catch (e) { error = e instanceof Error ? e.message : 'WiFi scan failed'; }
		finally { wifiScanning = false; }
	}

	async function connectWifi() {
		if (!selectedSsid) return;
		wifiConnecting = true; error = '';
		try {
			const result = await setupApi.wifiConnect(selectedSsid, wifiPassword);
			if (result.success) { wifiStatus = result.status ?? null; showWifiList = false; selectedSsid = ''; wifiPassword = ''; }
			else { error = result.error ?? t('setup.wifi_error'); }
		} catch (e) { error = e instanceof Error ? e.message : t('setup.wifi_error'); }
		finally { wifiConnecting = false; }
	}

	// Audio
	async function loadAudioOutputs() {
		try {
			audioOutputs = await player.outputs();
			const enabled = audioOutputs.find((o) => o.enabled);
			if (enabled) selectedAudioId = enabled.id;
			else if (audioOutputs.length > 0) selectedAudioId = audioOutputs[0].id;
		} catch { audioOutputs = []; }
	}

	async function selectAudio(id: number) {
		selectedAudioId = id;
		try {
			for (const output of audioOutputs) {
				if (output.id === id && !output.enabled) await player.toggleOutput(output.id, true);
				else if (output.id !== id && output.enabled) await player.toggleOutput(output.id, false);
			}
			await setupApi.setupAudio(`hw:${id}`);
			audioOutputs = await player.outputs();
		} catch (e) { error = e instanceof Error ? e.message : 'Audio setup failed'; }
	}

	// Inline card wizard
	function cancelAutoRetry() {
		if (autoRetryTimer) { clearInterval(autoRetryTimer); autoRetryTimer = null; }
		autoRetryCountdown = 0;
	}

	function startAutoRetry() {
		cancelAutoRetry();
		autoRetryCountdown = 3;
		autoRetryTimer = setInterval(() => {
			autoRetryCountdown -= 1;
			if (autoRetryCountdown <= 0) { cancelAutoRetry(); error = ''; startCardScan(); }
		}, 1000);
	}

	async function startCardScan() {
		cardStep = 'scan'; scanning = true; error = '';
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
			error = t('error.scan_timeout'); scanning = false; startAutoRetry();
		}
	}

	function handleCardTypeChange(type: ContentType) { contentType = type; contentPath = ''; cardName = ''; }
	function handleCardSelect(path: string, autoName: string) { contentPath = path; cardName = autoName; }

	async function saveCard() {
		if (!cardName.trim() || !contentPath.trim()) return;
		error = '';
		try {
			const data = { card_id: scannedCardId, name: cardName.trim(), content_type: contentType as string, content_path: contentPath.trim() };
			if (hasExisting) await cards.update(scannedCardId, data);
			else await cards.create(data);
			cardStep = 'done';
		} catch { error = t('error.save_failed'); }
	}

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

		<!-- ═══ Step 1: Hardware ═══ -->
		{#if currentStep === 'hardware'}
			<div class="flex flex-col gap-4 text-center">
				<h2 class="text-lg font-semibold text-text">{detectingHardware ? t('setup.detecting_hardware') : t('setup.detection_complete')}</h2>
				{#if detectingHardware}
					<div class="flex flex-col items-center gap-4 py-8">
						<div class="w-16 h-16 rounded-full bg-primary/20 flex items-center justify-center animate-pulse">
							<svg class="w-8 h-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/>
								<path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>
							</svg>
						</div>
						<p class="text-text-muted animate-pulse">{t('setup.detecting_hardware')}</p>
					</div>
				{:else if hardware}
					{#if hardware.is_mock}
						<HealthBanner type="info" message={t('setup.detection_mock')} />
					{:else}
						<p class="text-sm text-text-muted">{t('setup.hardware_intro')}</p>
					{/if}

					<div class="bg-surface-light rounded-xl p-4 space-y-3 text-left">

						<!-- Pi Model -->
						<div class="flex items-center justify-between py-1.5 border-b border-surface-lighter">
							<span class="text-sm text-text-muted">{t('setup.pi_model')}</span>
							<span class="text-sm text-text">
								{#if hardware.pi.model !== 'unknown'}
									<span class="inline-flex items-center gap-1">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{hardware.pi.model}
										{#if hardware.pi.ram_mb > 0}<span class="text-text-muted">({hardware.pi.ram_mb} MB)</span>{/if}
									</span>
								{:else}<span class="text-text-muted">--</span>{/if}
							</span>
						</div>

						<!-- Audio -->
						<div class="flex items-center justify-between py-1.5 border-b border-surface-lighter">
							<span class="text-sm text-text-muted">{t('setup.audio_outputs')}</span>
							<span class="text-sm text-text">
								{#if hardware.audio.length > 0}
									<span class="inline-flex items-center gap-1">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{hardware.audio.map(a => a.name).join(', ')}
									</span>
								{:else}<span class="text-text-muted">--</span>{/if}
							</span>
						</div>

						<!-- RFID Reader -->
						<div class="flex items-center justify-between py-1.5 border-b border-surface-lighter">
							<span class="text-sm text-text-muted">{t('setup.rfid_reader')}</span>
							<span class="text-sm">
								{#if hardware.rfid.reader !== 'none'}
									<span class="inline-flex items-center gap-1 text-text">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{hardware.rfid.reader.toUpperCase()}
									</span>
								{:else}
									<span class="inline-flex items-center gap-1 text-text-muted"><span class="w-4 text-center">--</span>{t('setup.not_found')}</span>
								{/if}
							</span>
						</div>

						<!-- Gyro -->
						<div class="flex items-center justify-between py-1.5 {sysInfo ? 'border-b border-surface-lighter' : ''}">
							<span class="text-sm text-text-muted">{t('setup.gyro_sensor')}</span>
							<span class="text-sm">
								{#if hardware.gyro_detected}
									<span class="inline-flex items-center gap-1 text-text">
										<svg class="w-4 h-4 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
										{t('setup.detected')}
									</span>
								{:else}
									<span class="inline-flex items-center gap-1 text-text-muted"><span class="w-4 text-center">--</span>{t('setup.not_found')}</span>
								{/if}
							</span>
						</div>

						<!-- Storage -->
						{#if sysInfo}
							<div class="flex items-center justify-between py-1.5">
								<span class="text-sm text-text-muted">{t('system.disk')}</span>
								<span class="text-sm text-text">
									{sysInfo.disk_used_gb.toFixed(1)} / {sysInfo.disk_total_gb.toFixed(1)} GB
									<span class="text-text-muted">({(sysInfo.disk_total_gb - sysInfo.disk_used_gb).toFixed(1)} GB {t('setup.free')})</span>
								</span>
							</div>
						{/if}
					</div>
				{/if}

				{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
			</div>
		{/if}

		<!-- ═══ Step 2: WiFi ═══ -->
		{#if currentStep === 'wifi'}
			<div class="flex flex-col gap-4">
				<h2 class="text-lg font-semibold text-text text-center">{t('setup.wifi')}</h2>
				{#if wifiLoading}
					<div class="flex justify-center py-8">
						<Spinner />
					</div>
				{:else if wifiStatus?.connected && !showWifiList}
					<div class="bg-surface-light rounded-xl p-4 space-y-2">
						<div class="flex items-center gap-2">
							<svg class="w-5 h-5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
							<span class="text-sm font-medium text-text">{t('setup.wifi_connected', { ssid: wifiStatus.ssid })}</span>
						</div>
						{#if wifiStatus.ip_address}
							<p class="text-xs text-text-muted pl-7">{t('setup.wifi_connected_ip', { ip: wifiStatus.ip_address })}</p>
						{/if}
					</div>
					<button onclick={scanWifi}
						class="w-full py-2.5 bg-surface-light hover:bg-surface-lighter text-text rounded-lg text-sm font-medium transition-colors">
						{t('setup.wifi_other')}
					</button>
				{:else}
					{#if !showWifiList}
						<p class="text-sm text-text-muted text-center">{t('setup.wifi_intro')}</p>
						<button onclick={scanWifi} disabled={wifiScanning}
							class="w-full py-3 bg-surface-light hover:bg-surface-lighter text-text rounded-lg font-medium transition-colors disabled:opacity-50">
							{#if wifiScanning}<span class="animate-pulse">{t('setup.wifi_scanning')}</span>
							{:else}{t('setup.wifi_select')}{/if}
						</button>
					{:else}
						<div class="space-y-2">
							<h3 class="text-sm font-medium text-text">{t('setup.wifi_select')}</h3>
							<div class="bg-surface-light rounded-xl overflow-hidden divide-y divide-surface-lighter max-h-48 overflow-y-auto">
								{#each wifiNetworks as network}
									<button onclick={() => { selectedSsid = network.ssid; wifiPassword = ''; }}
										class="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-surface-lighter transition-colors {selectedSsid === network.ssid ? 'bg-primary/10' : ''}">
										<span class="text-sm text-text">{network.ssid}</span>
										<div class="flex items-center gap-2">
											{#if network.security !== 'open'}
												<svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
													<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
												</svg>
											{/if}
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
										<input type="password" bind:value={wifiPassword} placeholder="..."
											class="w-full px-3 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50" />
									</label>
									<button onclick={connectWifi} disabled={wifiConnecting}
										class="w-full py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
										{#if wifiConnecting}<span class="animate-pulse">{t('setup.connect')}...</span>
										{:else}{t('setup.connect')}{/if}
									</button>
								</div>
							{/if}

							<button onclick={() => { showWifiList = false; selectedSsid = ''; }}
								class="w-full py-2 text-sm text-text-muted hover:text-text transition-colors">
								{t('general.cancel')}
							</button>
						</div>
					{/if}
				{/if}

				{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
			</div>
		{/if}

		<!-- ═══ Step 3: Audio ═══ -->
		{#if currentStep === 'audio'}
			<div class="flex flex-col gap-4">
				<h2 class="text-lg font-semibold text-text text-center">{t('setup.audio_select')}</h2>
				<p class="text-sm text-text-muted text-center">{t('setup.audio_desc')}</p>

				{#if audioOutputs.length === 0}
					<p class="text-sm text-text-muted py-4 text-center">{t('setup.audio_no_outputs')}</p>
				{:else}
					<div class="space-y-2">
						{#each audioOutputs as output}
							<button onclick={() => selectAudio(output.id)}
								class="w-full bg-surface-light rounded-xl p-4 flex items-center gap-3 text-left transition-colors {selectedAudioId === output.id ? 'ring-2 ring-primary' : 'hover:bg-surface-lighter'}">
								<div class="w-5 h-5 rounded-full border-2 flex items-center justify-center {selectedAudioId === output.id ? 'border-primary' : 'border-surface-lighter'}">
									{#if selectedAudioId === output.id}<div class="w-2.5 h-2.5 rounded-full bg-primary"></div>{/if}
								</div>
								<div class="flex-1">
									<span class="text-sm text-text">{output.name}</span>
									{#if output.enabled}<span class="ml-2 text-xs text-green-500">{t('setup.audio_recommended')}</span>{/if}
								</div>
							</button>
						{/each}
					</div>
				{/if}

				{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
			</div>
		{/if}

		<!-- ═══ Step 4: Card (inline) ═══ -->
		{#if currentStep === 'card'}

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
						<button onclick={() => { cancelAutoRetry(); error = ''; startCardScan(); }} class="text-sm text-primary font-medium">{t('general.retry')}</button>
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
		{/if}

		<!-- ═══ Step 5: Complete ═══ -->
		{#if currentStep === 'complete'}
			<div class="flex flex-col items-center gap-6 text-center">
				<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
					<svg class="w-10 h-10 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
						<path d="M20 6L9 17l-5-5"/>
					</svg>
				</div>
				<div>
					<h2 class="text-xl font-bold text-text mb-2">{t('setup.complete_title')}</h2>
					{#if sysInfo}
						<p class="text-sm text-text-muted max-w-xs">{t('setup.complete_reach', { url: `${sysInfo.hostname}.local` })}</p>
					{:else}
						<p class="text-sm text-text-muted max-w-xs">{t('setup.complete_desc')}</p>
					{/if}
				</div>

				<!-- Summary card -->
				<div class="w-full max-w-sm bg-surface-light rounded-xl p-4 space-y-2 text-sm text-left">
					{#if hardware}
						{#if hardware.pi.model !== 'unknown'}
							<div class="flex justify-between"><span class="text-text-muted">{t('setup.pi_model')}</span><span class="text-text">{hardware.pi.model}</span></div>
						{/if}
						{#if hardware.audio.length > 0}
							<div class="flex justify-between"><span class="text-text-muted">{t('setup.audio_outputs')}</span><span class="text-text">{hardware.audio.map(a => a.name).join(', ')}</span></div>
						{/if}
						{#if hardware.rfid.reader !== 'none'}
							<div class="flex justify-between"><span class="text-text-muted">{t('setup.rfid_reader')}</span><span class="text-text">{hardware.rfid.reader.toUpperCase()}</span></div>
						{/if}
					{/if}
					{#if wifiStatus?.connected}
						<div class="flex justify-between"><span class="text-text-muted">{t('setup.step_wifi')}</span><span class="text-text">„{wifiStatus.ssid}"</span></div>
					{/if}
					{#if sysInfo}
						<div class="flex justify-between"><span class="text-text-muted">{t('setup.complete_address')}</span><span class="text-primary">{sysInfo.hostname}.local</span></div>
					{/if}
					{#if wifiStatus?.ip_address}
						<div class="flex justify-between"><span class="text-text-muted">{t('setup.complete_ip_fallback')}</span><span class="text-text">{wifiStatus.ip_address}</span></div>
					{/if}
				</div>

				<p class="text-xs text-text-muted max-w-xs">{t('setup.homescreen_hint')}</p>

				{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
			</div>
		{/if}

		</div>
	</div>

	<!-- ═══ Fixed bottom navigation ═══ -->
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
						<button onclick={startCardScan} disabled={backendDown}
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
				<button onclick={() => { cancelAutoRetry(); cardStep = 'intro'; }}
					class="w-full py-3 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
					{t('general.cancel')}
				</button>
			{:else if cardStep === 'content'}
				<div class="flex gap-3">
					<button onclick={() => { cardStep = 'intro'; }}
						class="py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors">
						{t('general.back')}
					</button>
					<button onclick={saveCard} disabled={!cardName.trim() || !contentPath.trim()}
						class="flex-1 py-3 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-lg font-medium transition-colors">
						{hasExisting ? t('wizard.reassign') : t('wizard.next')}
					</button>
				</div>
			{:else if cardStep === 'done'}
				<div class="flex flex-col gap-2">
					<button onclick={async () => { try { await setupApi.firstCardDone(); } catch {} await goToStep('complete'); }}
						class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors">
						{t('setup.next')}
					</button>
					<button onclick={() => { scannedCardId = ''; cardName = ''; contentPath = ''; contentType = 'folder'; hasExisting = false; startCardScan(); }}
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
