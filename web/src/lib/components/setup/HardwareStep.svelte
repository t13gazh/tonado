<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, systemApi, type HardwareDetection, type SystemInfoData } from '$lib/api';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import Icon from '$lib/components/Icon.svelte';

	interface Props {
		hardware: HardwareDetection | null;
		sysInfo: SystemInfoData | null;
		detectingHardware: boolean;
		error: string;
		backendDown: boolean;
		onHardwareDetected: (hw: HardwareDetection, info: SystemInfoData | null) => void;
		onError: (msg: string) => void;
	}

	let { hardware, sysInfo, detectingHardware, error, backendDown, onHardwareDetected, onError }: Props = $props();
</script>

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
							<Icon name="check" size={16} class="text-green-500" strokeWidth={2.5} />
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
							<Icon name="check" size={16} class="text-green-500" strokeWidth={2.5} />
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
							<Icon name="check" size={16} class="text-green-500" strokeWidth={2.5} />
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
							<Icon name="check" size={16} class="text-green-500" strokeWidth={2.5} />
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
