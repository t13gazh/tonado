<script lang="ts">
	import { t } from '$lib/i18n';
	import { systemApi, type SystemInfoData, type HardwareStatus } from '$lib/api';
	import { onMount } from 'svelte';

	let info = $state<SystemInfoData | null>(null);
	let hardware = $state<HardwareStatus | null>(null);
	let updateStatus = $state<{ available: boolean; commits: number } | null>(null);
	let loading = $state(true);
	let message = $state('');
	let confirmShutdown = $state(false);

	onMount(async () => {
		try {
			const [infoData, hwData] = await Promise.all([
				systemApi.info(),
				systemApi.hardware().catch(() => null),
			]);
			info = infoData;
			hardware = hwData;
		} catch {}
		loading = false;
	});

	function rfidLabel(reader: string): string {
		const labels: Record<string, string> = {
			rc522: 'RC522 (SPI)',
			pn532: 'PN532 (I2C)',
			usb: 'USB HID',
		};
		return labels[reader] ?? reader;
	}

	function formatUptime(seconds: number): string {
		const h = Math.floor(seconds / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		return h > 0 ? t('system.uptime_hours', { h, m }) : t('system.uptime_minutes', { m });
	}

	async function checkUpdate() {
		updateStatus = await systemApi.checkUpdate();
	}

	async function applyUpdate() {
		message = 'Update wird installiert...';
		const result = await systemApi.applyUpdate();
		message = result.success ? t('system.update_done') : t('system.update_error', { error: result.error ?? '' });
	}

	async function handleBackupImport(e: Event) {
		const input = e.target as HTMLInputElement;
		if (!input.files?.[0]) return;
		const result = await systemApi.importBackup(input.files[0]);
		if (result.imported) {
			message = t('system.backup_done', {
				cards: result.imported.cards,
				config: result.imported.config,
			});
		}
	}
</script>

<div class="p-4">
	<div class="flex items-center gap-3 mb-4">
		<a href="/settings" class="p-2 text-text-muted hover:text-text">
			<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M19 12H5M12 19l-7-7 7-7"/>
			</svg>
		</a>
		<h1 class="text-xl font-bold">{t('system.title')}</h1>
	</div>

	{#if message}
		<div class="mb-3 px-3 py-2 bg-primary/10 border border-primary/20 rounded-lg text-primary text-sm">{message}</div>
	{/if}

	{#if loading}
		<div class="flex justify-center py-12">
			<div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
		</div>
	{:else if info}
		<div class="flex flex-col gap-4">
			<!-- System info -->
			<div class="bg-surface-light rounded-xl p-4">
				<h2 class="text-sm font-semibold mb-3">{t('system.info')}</h2>
				<div class="grid grid-cols-2 gap-y-2 text-sm">
					<span class="text-text-muted">{t('system.version')}</span>
					<span>{info.tonado_version}</span>
					<span class="text-text-muted">{t('system.hostname')}</span>
					<span>{info.hostname || '—'}</span>
					<span class="text-text-muted">{t('system.model')}</span>
					<span>{info.pi_model || '—'}</span>
					<span class="text-text-muted">{t('system.ip')}</span>
					<span>{info.ip_address || '—'}</span>
					<span class="text-text-muted">{t('system.uptime')}</span>
					<span>{info.uptime_seconds ? formatUptime(info.uptime_seconds) : '—'}</span>
					<span class="text-text-muted">{t('system.cpu_temp')}</span>
					<span>{info.cpu_temp ? `${info.cpu_temp.toFixed(1)} °C` : '—'}</span>
					<span class="text-text-muted">{t('system.ram')}</span>
					<span>{info.ram_total_mb ? `${info.ram_used_mb} / ${info.ram_total_mb} MB` : '—'}</span>
					<span class="text-text-muted">{t('system.disk')}</span>
					<span>{info.disk_total_gb ? `${info.disk_used_gb} / ${info.disk_total_gb} GB` : '—'}</span>
				</div>
			</div>

			<!-- Hardware -->
			{#if hardware}
				<div class="bg-surface-light rounded-xl p-4">
					<h2 class="text-sm font-semibold mb-3">{t('system.hardware')}</h2>
					<div class="flex flex-col gap-2.5 text-sm">
						{#if hardware.pi.model !== 'unknown'}
							<div class="flex items-center justify-between">
								<span class="text-text-muted">{t('system.model')}</span>
								<span>{hardware.pi.model}{hardware.pi.ram_mb ? ` (${hardware.pi.ram_mb} MB)` : ''}</span>
							</div>
						{/if}

						<div class="flex items-center justify-between">
							<span class="text-text-muted">{t('system.hardware_rfid')}</span>
							<span class="flex items-center gap-1.5">
								<span class="w-2 h-2 rounded-full {hardware.rfid.reader !== 'none' ? 'bg-green-500' : 'bg-red-500'}"></span>
								{#if hardware.rfid.reader !== 'none'}
									{rfidLabel(hardware.rfid.reader)}
								{:else}
									{t('system.hardware_not_detected')}
								{/if}
							</span>
						</div>

						<div class="flex items-center justify-between">
							<span class="text-text-muted">{t('system.hardware_gyro')}</span>
							<span class="flex items-center gap-1.5">
								<span class="w-2 h-2 rounded-full {hardware.gyro_detected ? 'bg-green-500' : 'bg-red-500'}"></span>
								{hardware.gyro_detected ? t('system.hardware_detected') : t('system.hardware_not_detected')}
							</span>
						</div>

						<div class="flex items-start justify-between">
							<span class="text-text-muted">{t('system.hardware_audio')}</span>
							<div class="flex flex-col items-end gap-1">
								{#if hardware.audio.length > 0}
									{#each hardware.audio as output}
										<span class="flex items-center gap-1.5">
											{#if output.recommended}
												<span class="w-2 h-2 rounded-full bg-green-500"></span>
											{/if}
											{output.name}
										</span>
									{/each}
								{:else}
									<span class="flex items-center gap-1.5">
										<span class="w-2 h-2 rounded-full bg-red-500"></span>
										{t('system.hardware_not_detected')}
									</span>
								{/if}
							</div>
						</div>

						<div class="flex items-center justify-between">
							<span class="text-text-muted">{t('system.hardware_wifi')}</span>
							<span class="flex items-center gap-1.5">
								<span class="w-2 h-2 rounded-full {hardware.wifi.connected ? 'bg-green-500' : 'bg-red-500'}"></span>
								{#if hardware.wifi.connected}
									{hardware.wifi.ssid}{hardware.wifi.ip ? ` (${hardware.wifi.ip})` : ''}
								{:else}
									{t('system.hardware_not_connected')}
								{/if}
							</span>
						</div>

						{#if hardware.is_mock}
							<div class="text-xs text-text-muted/60 mt-1">Simulierte Hardware (kein Raspberry Pi)</div>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Update -->
			<div class="bg-surface-light rounded-xl p-4">
				<h2 class="text-sm font-semibold mb-3">{t('system.update')}</h2>
				{#if updateStatus}
					{#if updateStatus.available}
						<p class="text-sm text-accent mb-2">{t('system.update_available', { count: updateStatus.commits })}</p>
						<button onclick={applyUpdate} class="px-4 py-2 bg-accent text-white rounded-lg text-sm">{t('system.update_apply')}</button>
					{:else}
						<p class="text-sm text-text-muted">{t('system.update_none')}</p>
					{/if}
				{:else}
					<button onclick={checkUpdate} class="px-4 py-2 bg-surface text-text-muted border border-surface-lighter rounded-lg text-sm hover:text-text">
						{t('system.update_check')}
					</button>
				{/if}
			</div>

			<!-- Backup -->
			<div class="bg-surface-light rounded-xl p-4">
				<h2 class="text-sm font-semibold mb-3">{t('system.backup')}</h2>
				<div class="flex gap-2">
					<a
						href={systemApi.exportBackup()}
						download="tonado-backup.json"
						class="flex-1 px-4 py-2 bg-surface border border-surface-lighter rounded-lg text-sm text-center text-text-muted hover:text-text"
					>
						{t('system.backup_export')}
					</a>
					<label class="flex-1 px-4 py-2 bg-surface border border-surface-lighter rounded-lg text-sm text-center text-text-muted hover:text-text cursor-pointer">
						{t('system.backup_import')}
						<input type="file" accept=".json" class="hidden" onchange={handleBackupImport} />
					</label>
				</div>
			</div>

			<!-- Power -->
			<div class="bg-surface-light rounded-xl p-4">
				<div class="flex flex-col gap-2">
					<button onclick={() => systemApi.restart()} class="w-full px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-sm text-text-muted hover:text-text text-left">
						{t('system.restart')}
					</button>
					<button onclick={() => systemApi.reboot()} class="w-full px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-sm text-text-muted hover:text-text text-left">
						{t('system.reboot')}
					</button>
					{#if confirmShutdown}
						<button onclick={() => { systemApi.shutdown(); confirmShutdown = false; }} class="w-full px-4 py-2.5 bg-red-600 rounded-lg text-sm text-white text-left">
							{t('system.confirm_shutdown')}
						</button>
					{:else}
						<button onclick={() => (confirmShutdown = true)} class="w-full px-4 py-2.5 bg-surface border border-red-600/30 rounded-lg text-sm text-red-400 hover:text-red-300 text-left">
							{t('system.shutdown')}
						</button>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
