<script lang="ts">
	import { t } from '$lib/i18n';
	import { systemApi, type SystemInfoData, type HardwareStatus, type SystemHealth } from '$lib/api';
	import { onMount } from 'svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';

	let info = $state<SystemInfoData | null>(null);
	let hardware = $state<HardwareStatus | null>(null);
	let healthData = $state<SystemHealth | null>(null);
	let updateStatus = $state<{ available: boolean; commits: number; changes?: string[]; current_version?: string; remote_version?: string; error?: string } | null>(null);
	let updating = $state(false);
	let checking = $state(false);
	let loading = $state(true);
	let message = $state('');
	let confirmShutdown = $state(false);
	let powerAction = $state<'restart' | 'reboot' | 'shutdown' | null>(null);

	async function waitForServer(timeout = 90_000): Promise<boolean> {
		const start = Date.now();
		while (Date.now() - start < timeout) {
			try {
				const res = await fetch('/api/system/info', { signal: AbortSignal.timeout(3000) });
				if (res.ok) return true;
			} catch {
				// Server not yet ready
			}
			await new Promise((r) => setTimeout(r, 2000));
		}
		return false;
	}

	async function doPowerAction(action: 'restart' | 'reboot' | 'shutdown') {
		powerAction = action;
		try {
			if (action === 'restart') {
				await systemApi.restart();
				message = t('system.restart_ok');
			} else if (action === 'reboot') {
				await systemApi.reboot();
				message = t('system.reboot_ok');
			} else {
				await systemApi.shutdown();
				message = t('system.shutdown_ok');
				return; // No reconnect on shutdown
			}
		} catch {
			// Request may fail if server dies before response — that's expected
			message = action === 'restart' ? t('system.restart_ok') : t('system.reboot_ok');
		}
		// Wait for server to come back, then reload
		const ok = await waitForServer();
		if (ok) {
			window.location.reload();
		} else {
			message = t('system.connection_lost');
			powerAction = null;
		}
	}

	onMount(async () => {
		try {
			const [infoData, hwData, hData] = await Promise.all([
				systemApi.info(),
				systemApi.hardware().catch(() => null),
				systemApi.health().catch(() => null),
			]);
			info = infoData;
			hardware = hwData;
			healthData = hData;
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
		checking = true;
		try {
			updateStatus = await systemApi.checkUpdate();
		} catch {
			updateStatus = { available: false, commits: 0, error: t('system.connection_lost') };
		}
		checking = false;
	}

	async function applyUpdate() {
		updating = true;
		message = t('system.update_installing');
		try {
			const result = await systemApi.applyUpdate();
			if (result.success) {
				message = t('system.update_success', {
					old: result.old_version ?? '?',
					new: result.new_version ?? '?',
					files: result.files_changed ?? 0,
				});
				updateStatus = null;
			} else {
				message = t('system.update_error', { error: result.error ?? '' });
			}
		} catch {
			message = t('system.update_error', { error: t('system.connection_lost') });
		}
		updating = false;
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
			<Spinner />
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

			<!-- Health warnings -->
			{#if healthData}
				{@const warnings = [
					...(healthData.mpd.status !== 'connected' ? [{ type: 'error' as const, msg: t('health.mpd_disconnected') }] : []),
					...(healthData.audio.status === 'no_output' ? [{ type: 'warning' as const, msg: t('health.audio_no_output') }] : []),
					...(healthData.rfid.status !== 'connected' ? [{ type: 'info' as const, msg: t('health.rfid_unavailable') }] : []),
					...(healthData.gyro.status !== 'connected' ? [{ type: 'info' as const, msg: t('health.gyro_unavailable') }] : []),
					...(healthData.storage.status === 'critical' ? [{ type: 'error' as const, msg: t('health.storage_critical') }] : []),
					...(healthData.storage.status === 'low' ? [{ type: 'warning' as const, msg: t('health.storage_low', { free_mb: healthData.storage.free_mb ?? 0 }) }] : []),
				]}
				{#if warnings.length > 0}
					<div class="flex flex-col gap-2">
						{#each warnings as w}
							<HealthBanner type={w.type} message={w.msg} />
						{/each}
					</div>
				{/if}
			{/if}

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
							<div class="text-xs text-text-muted/60 mt-1">{t('system.mock_hardware')}</div>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Update -->
			<div class="bg-surface-light rounded-xl p-4">
				<h2 class="text-sm font-semibold mb-3">{t('system.update')}</h2>
				{#if updateStatus}
					{#if updateStatus.error}
						<p class="text-sm text-text-muted">{updateStatus.error}</p>
						<button onclick={() => { updateStatus = null; }} class="mt-2 w-full px-4 py-2.5 bg-surface-light hover:bg-surface-lighter rounded-lg text-text-muted text-sm font-medium transition-colors">
							{t('system.update_check')}
						</button>
					{:else if updateStatus.available}
						<div class="space-y-3">
							<p class="text-sm text-accent">{t('system.update_available', { count: updateStatus.commits })}</p>
							{#if updateStatus.current_version && updateStatus.remote_version}
								<p class="text-xs text-text-muted">
									{updateStatus.current_version} → {updateStatus.remote_version}
								</p>
							{/if}
							{#if updateStatus.changes && updateStatus.changes.length > 0}
								<div class="text-xs text-text-muted bg-surface rounded-lg p-3 max-h-32 overflow-y-auto space-y-1 font-mono">
									{#each updateStatus.changes as change}
										<div class="truncate">{change}</div>
									{/each}
								</div>
							{/if}
							<button
								onclick={applyUpdate}
								disabled={updating}
								class="w-full px-4 py-2.5 bg-accent text-white rounded-lg text-sm disabled:opacity-50"
							>
								{#if updating}
									<span class="animate-pulse">{t('system.update_installing')}</span>
								{:else}
									{t('system.update_apply')}
								{/if}
							</button>
						</div>
					{:else}
						<p class="text-sm text-text-muted">{t('system.update_none')}</p>
					{/if}
				{:else}
					<button onclick={checkUpdate} disabled={checking} class="w-full px-4 py-2.5 bg-primary/15 text-primary border border-primary/30 rounded-lg text-sm font-medium hover:bg-primary/25 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
						{#if checking}
							<Spinner size="sm" />
							{t('system.update_checking')}
						{:else}
							{t('system.update_check')}
						{/if}
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
						class="flex-1 px-4 py-2 bg-primary/15 text-primary border border-primary/30 rounded-lg text-sm text-center font-medium hover:bg-primary/25 transition-colors"
					>
						{t('system.backup_export')}
					</a>
					<label class="flex-1 px-4 py-2 bg-primary/15 text-primary border border-primary/30 rounded-lg text-sm text-center font-medium hover:bg-primary/25 transition-colors cursor-pointer">
						{t('system.backup_import')}
						<input type="file" accept=".json" class="hidden" onchange={handleBackupImport} />
					</label>
				</div>
			</div>

			<!-- Power -->
			<div class="bg-surface-light rounded-xl p-4">
				<div class="flex flex-col gap-2">
					<button onclick={() => doPowerAction('restart')} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-surface-light hover:bg-surface-lighter rounded-lg text-text-muted text-sm font-medium transition-colors disabled:opacity-50">
						{#if powerAction === 'restart'}
							<span class="flex items-center gap-2"><Spinner size="sm" /> {t('system.restart_ok')}</span>
						{:else}
							{t('system.restart')}
						{/if}
					</button>
					<button onclick={() => doPowerAction('reboot')} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-surface-light hover:bg-surface-lighter rounded-lg text-text-muted text-sm font-medium transition-colors disabled:opacity-50">
						{#if powerAction === 'reboot'}
							<span class="flex items-center gap-2"><Spinner size="sm" /> {t('system.reboot_ok')}</span>
						{:else}
							{t('system.reboot')}
						{/if}
					</button>
					{#if confirmShutdown}
						<button onclick={() => { doPowerAction('shutdown'); confirmShutdown = false; }} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-red-600 hover:bg-red-500 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-50">
							{#if powerAction === 'shutdown'}
								<span class="flex items-center gap-2"><Spinner size="sm" /> {t('system.shutdown_ok')}</span>
							{:else}
								{t('system.confirm_shutdown')}
							{/if}
						</button>
					{:else}
						<button onclick={() => (confirmShutdown = true)} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-red-500/10 border border-red-600/30 rounded-lg text-red-400 text-sm font-medium hover:bg-red-500/20 transition-colors disabled:opacity-50">
							{t('system.shutdown')}
						</button>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
