<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, type WifiNetwork, type WifiScanSource, type WifiStatus } from '$lib/api';
	import { onMount } from 'svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import InlineError from '$lib/components/InlineError.svelte';

	interface Props {
		wifiStatus: WifiStatus | null;
		error: string;
		onError: (msg: string) => void;
		onWifiStatusChange: (status: WifiStatus | null) => void;
		/** Lifted to the page so CompleteStep can re-verify the credentials
		 *  against Lane B's /setup/test-wifi before switching the phone. */
		onCredentialsCaptured?: (ssid: string, password: string) => void;
		/** Lane B's fix #5: /setup/wifi/connect now uses probe_home_wifi
		 *  internally (AP stays up). We stash the successful connect result so
		 *  CompleteStep can skip the redundant /setup/test-wifi round-trip.
		 *  TODO: align with Lane B if the response grows a `token` field here. */
		onWifiProbeCaptured?: (probe: { ok: boolean; error: string | null; ip: string | null; token?: string | null }) => void;
	}

	let {
		wifiStatus,
		error,
		onError,
		onWifiStatusChange,
		onCredentialsCaptured,
		onWifiProbeCaptured,
	}: Props = $props();

	// ─── Scan state ─────────────────────────────────────────────────────────
	// The fork in +page.svelte already chose the online path, so we scan as soon
	// as the step mounts. The list is served from the backend's boot-time cache
	// (source === 'cache'); a friendly empty state — not an error — covers the
	// "nothing nearby yet" case. The manual SSID input is always available as a
	// co-equal path regardless of scan outcome.
	let wifiNetworks = $state<WifiNetwork[]>([]);
	let scanSource = $state<WifiScanSource | null>(null);
	let scannedAt = $state<number | null>(null);
	let wifiScanning = $state(false);
	let scanFailed = $state(false);

	// ─── Selection / connect state ──────────────────────────────────────────
	let selectedSsid = $state('');
	let manualSsid = $state('');
	let wifiPassword = $state('');
	let wifiConnecting = $state(false);
	let showPassword = $state(false);

	// The SSID we actually connect with: a picked network wins, otherwise the
	// manually typed name. Manual typing clears any list selection (see below).
	const activeSsid = $derived(selectedSsid || manualSsid.trim());

	const showEmptyState = $derived(
		!wifiScanning && !scanFailed && wifiNetworks.length === 0
	);

	// Cache-age label, only meaningful when the backend served the boot cache.
	const cacheAgeLabel = $derived.by(() => {
		if (scanSource !== 'cache') return '';
		if (scannedAt == null) return t('setup.wifi_list_from_boot');
		const ageSec = Math.max(0, Date.now() / 1000 - scannedAt);
		let age: string;
		if (ageSec < 90) age = t('setup.wifi_age_just_now');
		else if (ageSec < 3600) age = t('setup.wifi_age_minutes', { n: Math.round(ageSec / 60) });
		else age = t('setup.wifi_age_hours', { n: Math.round(ageSec / 3600) });
		return t('setup.wifi_list_age', { age });
	});

	async function scanWifi() {
		wifiScanning = true;
		scanFailed = false;
		onError('');
		try {
			const result = await setupApi.wifiScan();
			wifiNetworks = result.networks ?? [];
			scanSource = result.source ?? null;
			scannedAt = result.scanned_at ?? null;
		} catch (e) {
			// A scan failure is NOT fatal — the manual SSID path still works.
			scanFailed = true;
			onError(e instanceof Error ? e.message : t('setup.wifi_scan_failed'));
		} finally {
			wifiScanning = false;
		}
	}

	function selectNetwork(network: WifiNetwork) {
		selectedSsid = network.ssid;
		manualSsid = '';
		wifiPassword = '';
		onError('');
	}

	function onManualInput() {
		// Typing a manual name takes over from a list selection.
		if (manualSsid.trim()) selectedSsid = '';
	}

	async function connectWifi() {
		const ssid = activeSsid;
		if (!ssid) return;
		wifiConnecting = true;
		onError('');
		try {
			const result = await setupApi.wifiConnect(ssid, wifiPassword);
			if (result.ok) {
				// Lane B now uses probe_home_wifi — AP stays up, so we keep the
				// existing wifiStatus snapshot and capture credentials/token for
				// the final confirm-complete handshake after the phone switches
				// networks.
				onCredentialsCaptured?.(ssid, wifiPassword);
				onWifiProbeCaptured?.({
					ok: true,
					error: null,
					ip: result.ip,
					token: result.token ?? null,
				});
				selectedSsid = '';
				manualSsid = '';
				wifiPassword = '';
			} else {
				onError(result.error ?? t('setup.wifi_error'));
				onWifiProbeCaptured?.({
					ok: false,
					error: result.error,
					ip: null,
				});
			}
		} catch (e) {
			onError(e instanceof Error ? e.message : t('setup.wifi_error'));
		} finally {
			wifiConnecting = false;
		}
	}

	onMount(() => {
		// Auto-scan on entry — the fork already committed us to the online path.
		void scanWifi();
	});
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.wifi')}</h2>
	<p class="text-sm text-text-muted text-center">{t('setup.wifi_intro')}</p>

	{#if wifiStatus?.connected}
		<div class="bg-surface-light rounded-xl p-4 space-y-2">
			<div class="flex items-center gap-2">
				<Icon name="check" size={20} class="text-green-500" strokeWidth={2.5} />
				<span class="text-sm font-medium text-text">{t('setup.wifi_connected', { ssid: wifiStatus.ssid })}</span>
			</div>
			{#if wifiStatus.ip_address}
				<p class="text-xs text-text-muted pl-7">{t('setup.wifi_connected_ip', { ip: wifiStatus.ip_address })}</p>
			{/if}
		</div>
	{/if}

	<!-- ─── Network list (from the backend's boot cache) ─────────────────── -->
	<div class="space-y-2">
		<div class="flex items-center justify-between">
			<h3 class="text-sm font-medium text-text">{t('setup.wifi_select')}</h3>
			<button
				onclick={scanWifi}
				disabled={wifiScanning}
				class="inline-flex items-center gap-1.5 text-xs text-primary hover:text-primary-light transition-colors disabled:opacity-50"
			>
				<Icon name="refresh" size={14} />
				{wifiScanning ? t('setup.wifi_scanning') : t('setup.wifi_rescan')}
			</button>
		</div>

		{#if wifiScanning && wifiNetworks.length === 0}
			<div class="flex justify-center py-6"><Spinner /></div>
		{:else if showEmptyState}
			<div class="bg-surface-light rounded-xl p-4 flex items-start gap-2">
				<Icon name="help-circle" size={16} class="text-primary mt-0.5 shrink-0" strokeWidth={2} />
				<p class="text-xs text-text-muted">{t('setup.wifi_list_empty')}</p>
			</div>
		{:else if wifiNetworks.length > 0}
			{#if cacheAgeLabel}
				<p class="text-xs text-text-muted">{cacheAgeLabel}</p>
			{/if}
			<div class="bg-surface-light rounded-xl overflow-hidden divide-y divide-surface-lighter max-h-48 overflow-y-auto">
				{#each wifiNetworks as network}
					<button onclick={() => selectNetwork(network)}
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
		{/if}
	</div>

	<!-- ─── Manual SSID entry — always visible, co-equal path ─────────────── -->
	<div class="space-y-2 pt-1">
		<label for="wifi-manual-ssid" class="text-sm font-medium text-text block">{t('setup.wifi_manual_title')}</label>
		<input
			id="wifi-manual-ssid"
			type="text"
			bind:value={manualSsid}
			oninput={onManualInput}
			placeholder={t('setup.wifi_manual_ssid_placeholder')}
			autocomplete="off"
			aria-label={t('setup.wifi_manual_ssid_label')}
			class="w-full px-3 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
		/>
	</div>

	<!-- ─── Password + connect (shared by list + manual paths) ───────────── -->
	{#if activeSsid}
		<div class="space-y-3 pt-1">
			<p class="text-xs text-text-muted">&bdquo;{activeSsid}&ldquo;</p>
			<label class="block">
				<span class="text-xs text-text-muted mb-1 block">{t('setup.wifi_password')}</span>
				<div class="relative">
					<input type={showPassword ? 'text' : 'password'} bind:value={wifiPassword} placeholder="..."
						class="w-full px-3 py-2.5 pr-10 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50" />
					<button type="button"
						onclick={() => showPassword = !showPassword}
						aria-label={showPassword ? t('setup.wifi_password_hide') : t('setup.wifi_password_show')}
						class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2 rounded transition-colors">
						<Icon name={showPassword ? 'eye-off' : 'eye'} size={18} />
					</button>
				</div>
			</label>
			<button onclick={connectWifi} disabled={wifiConnecting}
				class="w-full py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
				{#if wifiConnecting}<span class="animate-pulse">{t('setup.connect')}...</span>
				{:else}{t('setup.connect')}{/if}
			</button>
		</div>
	{/if}

	{#if error}<InlineError message={error} />{/if}
</div>
