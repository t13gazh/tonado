<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, type WifiNetwork, type WifiStatus } from '$lib/api';
	import Spinner from '$lib/components/Spinner.svelte';
	import Icon from '$lib/components/Icon.svelte';

	interface Props {
		wifiStatus: WifiStatus | null;
		wifiLoading: boolean;
		error: string;
		onError: (msg: string) => void;
		onWifiStatusChange: (status: WifiStatus | null) => void;
	}

	let { wifiStatus, wifiLoading, error, onError, onWifiStatusChange }: Props = $props();

	let wifiNetworks = $state<WifiNetwork[]>([]);
	let wifiScanning = $state(false);
	let showWifiList = $state(false);
	let selectedSsid = $state('');
	let wifiPassword = $state('');
	let wifiConnecting = $state(false);
	let showPassword = $state(false);

	async function scanWifi() {
		wifiScanning = true;
		try { wifiNetworks = await setupApi.wifiScan(); showWifiList = true; }
		catch (e) { onError(e instanceof Error ? e.message : t('setup.wifi_scan_failed')); }
		finally { wifiScanning = false; }
	}

	async function connectWifi() {
		if (!selectedSsid) return;
		wifiConnecting = true;
		try {
			const result = await setupApi.wifiConnect(selectedSsid, wifiPassword);
			if (result.success) {
				onWifiStatusChange(result.status ?? null);
				showWifiList = false; selectedSsid = ''; wifiPassword = '';
			} else { onError(result.error ?? t('setup.wifi_error')); }
		} catch (e) { onError(e instanceof Error ? e.message : t('setup.wifi_error')); }
		finally { wifiConnecting = false; }
	}
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.wifi')}</h2>
	{#if wifiLoading}
		<div class="flex justify-center py-8"><Spinner /></div>
	{:else if wifiStatus?.connected && !showWifiList}
		<div class="bg-surface-light rounded-xl p-4 space-y-2">
			<div class="flex items-center gap-2">
				<Icon name="check" size={20} class="text-green-500" strokeWidth={2.5} />
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

				<button onclick={() => { showWifiList = false; selectedSsid = ''; }}
					class="w-full py-2 text-sm text-text-muted hover:text-text transition-colors">
					{t('general.cancel')}
				</button>
			</div>
		{/if}
	{/if}

	{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
</div>
