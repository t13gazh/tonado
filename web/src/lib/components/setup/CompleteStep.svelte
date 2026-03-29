<script lang="ts">
	import { t } from '$lib/i18n';
	import type { HardwareDetection, SystemInfoData, WifiStatus } from '$lib/api';
	import Icon from '$lib/components/Icon.svelte';

	interface Props {
		hardware: HardwareDetection | null;
		sysInfo: SystemInfoData | null;
		wifiStatus: WifiStatus | null;
		error: string;
	}

	let { hardware, sysInfo, wifiStatus, error }: Props = $props();
</script>

<div class="flex flex-col items-center gap-6 text-center">
	<div class="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center">
		<Icon name="check" size={40} class="text-green-500" strokeWidth={2.5} />
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
			<div class="flex justify-between"><span class="text-text-muted">{t('setup.step_wifi')}</span><span class="text-text">&bdquo;{wifiStatus.ssid}&ldquo;</span></div>
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
