<script lang="ts">
	import { t } from '$lib/i18n';
	import { systemApi, setupApi, config, ApiError, type SystemInfoData, type HardwareStatus, type SystemHealth } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import Spinner from '$lib/components/Spinner.svelte';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import GyroCalibration from '$lib/components/GyroCalibration.svelte';
	import { getAuthTier } from '$lib/stores/auth.svelte';

	const isExpert = $derived(getAuthTier() === 'expert');

	let info = $state<SystemInfoData | null>(null);
	let hardware = $state<HardwareStatus | null>(null);
	let healthData = $state<SystemHealth | null>(null);
	let updateStatus = $state<{ available: boolean; commits: number; changelog?: string; current_version?: string; remote_version?: string; error?: string } | null>(null);
	type UpdatePhase =
		| 'idle'
		| 'applying'
		| 'restarting'
		| 'verifying'
		| 'success'
		| 'no_changes'
		| 'error';
	let updatePhase = $state<UpdatePhase>('idle');
	let updatePhaseError = $state<string>('');
	let updatedToVersion = $state<string>('');
	let updating = $state(false);
	let checking = $state(false);
	let loading = $state(true);
	let message = $state('');
	let confirmShutdown = $state(false);
	let powerAction = $state<'restart' | 'reboot' | 'shutdown' | null>(null);
	let showGyroCalibration = $state(false);
	let gyroCalibrated = $state(false);

	// Guard against state updates after the component has unmounted. The update
	// flow polls asynchronously for several minutes — navigating away should
	// cancel both the poll loop and the success-dismiss setTimeout so we don't
	// mutate detached state.
	let componentAlive = true;
	let successDismissTimer: ReturnType<typeof setTimeout> | null = null;
	let noChangesDismissTimer: ReturnType<typeof setTimeout> | null = null;
	onDestroy(() => {
		componentAlive = false;
		if (successDismissTimer) clearTimeout(successDismissTimer);
		if (noChangesDismissTimer) clearTimeout(noChangesDismissTimer);
	});

	function stripMarkdown(s: string): string {
		// Release notes come through as a plain-text render, but older release
		// sections may still contain Markdown emphasis and link syntax. Strip
		// the common tokens so parents see clean prose, not stray asterisks.
		return s
			.replace(/\*\*([^*]+)\*\*/g, '$1')
			.replace(/\*([^*]+)\*/g, '$1')
			.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
			.replace(/`([^`]+)`/g, '$1');
	}

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
			try {
				const allConfig = await config.getAll();
				gyroCalibrated = (allConfig['gyro.calibrated'] as boolean) ?? false;
			} catch {}
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
		// Skip while an apply-flow is active — otherwise a background poll could
		// race with the check and stomp on updateStatus mid-flight.
		if (updatePhase !== 'idle') return;
		checking = true;
		try {
			updateStatus = await systemApi.checkUpdate();
		} catch {
			updateStatus = { available: false, commits: 0, error: t('system.connection_lost') };
		}
		checking = false;
	}

	async function pollForRestart(expectedVersion: string, timeoutMs = 120_000): Promise<void> {
		// After the apply response we expect the service to restart. While it is
		// away the info endpoint will time out or return 5xx — treat that as the
		// "restarting" phase. Once we get a clean response we check the version
		// string and transition to verifying → success.
		const start = Date.now();
		let sawOutage = false;
		while (componentAlive && Date.now() - start < timeoutMs) {
			try {
				const res = await fetch('/api/system/info', {
					signal: AbortSignal.timeout(3000),
				});
				if (!componentAlive) return;
				if (res.ok) {
					if (sawOutage) {
						updatePhase = 'verifying';
					}
					const data = (await res.json()) as SystemInfoData;
					// Version match = success. If the backend did not restart at all
					// (edge case) we still wait for a potential delayed restart
					// until we see at least one outage.
					if (data.tonado_version === expectedVersion && sawOutage) {
						info = data;
						updatedToVersion = expectedVersion;
						updatePhase = 'success';
						// Auto-hide success banner after 3 seconds, back to idle.
						// Track the timer so onDestroy can cancel it cleanly.
						successDismissTimer = setTimeout(() => {
							successDismissTimer = null;
							if (!componentAlive) return;
							if (updatePhase === 'success') {
								updatePhase = 'idle';
								updateStatus = null;
								updatedToVersion = '';
							}
						}, 3000);
						return;
					}
					// Same version as before — keep polling, maybe restart pending.
					updatePhase = 'restarting';
				} else {
					sawOutage = true;
					updatePhase = 'restarting';
				}
			} catch {
				if (!componentAlive) return;
				sawOutage = true;
				updatePhase = 'restarting';
			}
			await new Promise((r) => setTimeout(r, 2000));
		}
		if (!componentAlive) return;
		// Timeout — inform the user but don't claim failure, the update itself
		// may have succeeded, just the verification timed out.
		updatePhase = 'error';
		updatePhaseError = t('system.update_timeout_hint');
	}

	async function applyUpdate() {
		updating = true;
		updatePhase = 'applying';
		updatePhaseError = '';
		message = '';
		const expectedVersion = updateStatus?.remote_version ?? '';
		try {
			const result = await systemApi.applyUpdate();
			if (!result.success) {
				updatePhase = 'error';
				updatePhaseError = result.error ?? t('system.connection_lost');
				updating = false;
				return;
			}
			if (result.no_changes) {
				updatedToVersion = result.new_version ?? expectedVersion;
				updatePhase = 'no_changes';
				noChangesDismissTimer = setTimeout(() => {
					noChangesDismissTimer = null;
					if (!componentAlive) return;
					if (updatePhase === 'no_changes') {
						updatePhase = 'idle';
						updateStatus = null;
						updatedToVersion = '';
					}
				}, 3000);
				updating = false;
				return;
			}
			// Real update went through — backend is about to restart. Poll until
			// the service is back with the expected version.
			updatePhase = 'restarting';
			const targetVersion = result.new_version ?? expectedVersion;
			updating = false;
			await pollForRestart(targetVersion);
		} catch {
			updatePhase = 'error';
			updatePhaseError = t('system.connection_lost');
			updating = false;
		}
	}

	async function retryUpdate() {
		updatePhaseError = '';
		// If the previous apply actually succeeded and only the poll timed out,
		// checkUpdate will now report no pending commits. Treat that as success
		// instead of kicking off a fresh pip install on a half-applied state.
		const check = await systemApi.checkUpdate().catch(() => null);
		if (!componentAlive) return;
		if (check && check.available === false) {
			updatedToVersion = check.current_version ?? updatedToVersion;
			updatePhase = 'success';
			successDismissTimer = setTimeout(() => {
				successDismissTimer = null;
				if (!componentAlive) return;
				if (updatePhase === 'success') {
					updatePhase = 'idle';
					updateStatus = null;
					updatedToVersion = '';
				}
			}, 3000);
			return;
		}
		updatePhase = 'idle';
		await applyUpdate();
	}

	function reloadPage() {
		window.location.reload();
	}

	async function restartWizard() {
		try {
			await setupApi.reset();
			goto('/setup');
		} catch (e) {
			// 403 = kein Experten-Tier — User braucht eine explizite Anleitung,
			// nicht die generische Fehlermeldung.
			if (e instanceof ApiError && e.status === 403) {
				message = t('system.setup_wizard_needs_expert');
			} else {
				message = t('system.setup_wizard_error');
			}
		}
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
				{#if updatePhase !== 'idle'}
					<!-- Single ARIA-live wrapper for every phase view so screen-reader
					     parents hear each transition (applying → restarting → verifying
					     → success / no_changes / error). Without this the minutes-long
					     install would be silent and feel broken. -->
					<div role="status" aria-live="polite" aria-atomic="true">
						{#if updatePhase === 'applying' || updatePhase === 'restarting' || updatePhase === 'verifying'}
							<!-- Active progress view, reserves a fixed min-height so the panel doesn't jump -->
							<div class="min-h-[7rem] flex flex-col items-center justify-center gap-3 py-3">
								<Spinner size="md" />
								<p class="text-sm text-text animate-pulse">
									{#if updatePhase === 'applying'}
										{t('system.update_phase_applying')}
									{:else if updatePhase === 'restarting'}
										{t('system.update_phase_restarting')}
									{:else}
										{t('system.update_phase_verifying')}
									{/if}
								</p>
								{#if updateStatus?.current_version && updateStatus?.remote_version}
									<p class="text-xs text-text-muted">{updateStatus.current_version} → {updateStatus.remote_version}</p>
								{/if}
							</div>
						{:else if updatePhase === 'success'}
							<div class="min-h-[7rem] flex flex-col items-center justify-center gap-2 py-3">
								<svg class="w-10 h-10 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round"/>
								</svg>
								<p class="text-sm text-green-500 font-medium">{t('system.update_success_short', { version: updatedToVersion })}</p>
							</div>
						{:else if updatePhase === 'no_changes'}
							<div class="min-h-[7rem] flex flex-col items-center justify-center gap-2 py-3">
								<svg class="w-10 h-10 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M9 12l2 2 4-4" stroke-linecap="round" stroke-linejoin="round"/>
									<circle cx="12" cy="12" r="10"/>
								</svg>
								<p class="text-sm text-text-muted">{t('system.update_no_changes', { version: updatedToVersion || (info?.tonado_version ?? '?') })}</p>
							</div>
						{:else if updatePhase === 'error'}
							<div class="space-y-3">
								<p class="text-sm text-red-400">{t('system.update_error', { error: updatePhaseError })}</p>
								<!-- Two buttons: reload always gets the user back to a known state
								     (covers the poll-timeout-despite-successful-apply case), while
								     retry kicks off a fresh apply for real failures. -->
								<button
									onclick={reloadPage}
									class="w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors"
								>
									{t('system.update_reload_page')}
								</button>
								<button
									onclick={retryUpdate}
									class="w-full px-4 py-2.5 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium transition-colors"
								>
									{t('system.update_retry')}
								</button>
							</div>
						{/if}
					</div>
				{:else if updateStatus}
					{#if updateStatus.error}
						<p class="text-sm text-text-muted">{updateStatus.error}</p>
						<button onclick={() => { updateStatus = null; }} class="mt-2 w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
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
							{#if updateStatus.changelog}
								<div class="text-xs text-text bg-surface rounded-lg p-3 max-h-64 overflow-y-auto space-y-1">
									{#each updateStatus.changelog.split('\n') as line}
										{#if line.startsWith('### ')}
											<div class="font-semibold text-text mt-2 first:mt-0">{stripMarkdown(line.slice(4))}</div>
										{:else if line.startsWith('## ')}
											<div class="font-semibold text-text mt-2 first:mt-0">{stripMarkdown(line.slice(3))}</div>
										{:else if line.startsWith('- ')}
											<div class="text-text-muted pl-3 flex gap-2"><span aria-hidden="true">•</span><span>{stripMarkdown(line.slice(2))}</span></div>
										{:else if line.trim()}
											<div class="text-text-muted">{stripMarkdown(line)}</div>
										{/if}
									{/each}
								</div>
							{/if}
							<button
								onclick={applyUpdate}
								disabled={updating}
								class="w-full px-4 py-2.5 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
							>
								{t('system.update_apply')}
							</button>
						</div>
					{:else}
						<p class="text-sm text-text-muted">{t('system.update_none')}</p>
					{/if}
				{:else}
					<button onclick={checkUpdate} disabled={checking} class="w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2">
						{#if checking}
							<Spinner size="sm" variant="light" />
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
					<button
						onclick={() => systemApi.exportBackup()}
						class="flex-1 px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm text-center font-medium transition-colors"
					>
						{t('system.backup_export')}
					</button>
					<label class="flex-1 px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm text-center font-medium transition-colors cursor-pointer">
						{t('system.backup_import')}
						<input type="file" accept=".json" class="hidden" onchange={handleBackupImport} />
					</label>
				</div>
			</div>

			<!-- Setup Wizard -->
			<div class="bg-surface-light rounded-xl p-4">
				<h2 class="text-sm font-semibold mb-3">{t('system.setup_wizard')}</h2>
				<p class="text-xs text-text-muted mb-3">{t('system.setup_wizard_desc')}</p>
				{#if isExpert}
					<button onclick={restartWizard} class="w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
						{t('system.setup_wizard_restart')}
					</button>
				{:else}
					<div class="text-xs text-amber-500 mb-2">{t('system.setup_wizard_needs_expert')}</div>
					<a href="/settings" class="block w-full px-4 py-2.5 bg-surface hover:bg-surface-lighter text-text text-sm font-medium rounded-lg text-center transition-colors">
						{t('system.setup_wizard_login_hint')}
					</a>
				{/if}
			</div>


			<!-- Gyro Calibration -->
			{#if healthData?.gyro?.status === 'connected'}
				<div class="bg-surface-light rounded-xl p-4">
					{#if showGyroCalibration}
						<GyroCalibration
							onDone={() => { showGyroCalibration = false; gyroCalibrated = true; message = t('gyro.calibrated'); }}
							onCancel={() => { showGyroCalibration = false; }}
						/>
					{:else}
						<div class="flex items-center justify-between">
							<div>
								<h2 class="text-sm font-semibold">{t('gyro.calibrate')}</h2>
								<p class="text-xs text-text-muted mt-0.5">{t('gyro.calibrate_desc')}</p>
							</div>
							<span class="text-xs {gyroCalibrated ? 'text-green-500' : 'text-amber-500'}">
								{gyroCalibrated ? t('gyro.calibrated') : t('gyro.not_calibrated')}
							</span>
						</div>
						<button
							onclick={() => { showGyroCalibration = true; }}
							class="mt-3 w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors"
						>
							{t('gyro.start_button')}
						</button>
					{/if}
				</div>
			{/if}

			<!-- Power -->
			<div class="bg-surface-light rounded-xl p-4">
				<h2 class="text-sm font-semibold mb-3">{t('system.power')}</h2>
				<div class="flex flex-col gap-2">
					<button onclick={() => doPowerAction('restart')} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-surface hover:bg-surface-lighter rounded-lg text-text-muted text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
						{#if powerAction === 'restart'}
							<span class="flex items-center justify-center gap-2"><Spinner size="sm" /> {t('system.restart_ok')}</span>
						{:else}
							{t('system.restart')}
						{/if}
					</button>
					<button onclick={() => doPowerAction('reboot')} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-surface hover:bg-surface-lighter rounded-lg text-text-muted text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
						{#if powerAction === 'reboot'}
							<span class="flex items-center justify-center gap-2"><Spinner size="sm" /> {t('system.reboot_ok')}</span>
						{:else}
							{t('system.reboot')}
						{/if}
					</button>
				</div>
				<div class="mt-4 pt-4 border-t border-surface-lighter">
					{#if confirmShutdown}
						<button onclick={() => { doPowerAction('shutdown'); confirmShutdown = false; }} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-red-600 hover:bg-red-500 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
							{#if powerAction === 'shutdown'}
								<span class="flex items-center justify-center gap-2"><Spinner size="sm" variant="light" /> {t('system.shutdown_ok')}</span>
							{:else}
								{t('system.confirm_shutdown')}
							{/if}
						</button>
					{:else}
						<button onclick={() => (confirmShutdown = true)} disabled={!!powerAction} class="w-full px-4 py-2.5 bg-red-500/20 rounded-lg text-red-400 text-sm font-medium hover:bg-red-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
							{t('system.shutdown')}
						</button>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
