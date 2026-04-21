<script lang="ts">
	import { t } from '$lib/i18n';
	import { config, authApi, setupApi, type AuthStatus, ApiError } from '$lib/api';
	import { onMount } from 'svelte';
	import QRCode from 'qrcode';
	import HealthBanner from '$lib/components/HealthBanner.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { isBackendOffline, isGyroAvailable } from '$lib/stores/health.svelte';
	import { addToast } from '$lib/stores/toast.svelte';

	let authStatus = $state<AuthStatus | null>(null);
	let allConfig = $state<Record<string, unknown>>({});
	let error = $state('');
	let errorTimer: ReturnType<typeof setTimeout> | null = null;

	// PIN forms
	let parentPinValue = $state('');
	let expertPinValue = $state('');
	let loginPin = $state('');
	let loginError = $state('');
	let loginLoading = $state(false);
	let parentPinLoading = $state(false);
	let expertPinLoading = $state(false);

	// Settings values
	let maxVolume = $state(80);
	let startupVolume = $state(50);
	let sleepMinutes = $state(30);
	let sleepActive = $state(false);
	let sleepRemaining = $state(0);
	let idleMinutes = $state(0);
	let cardRemovePauses = $state(false);
	let gyroEnabled = $state(true);
	let gyroSensitivity = $state('normal');

	// WiFi rescue (auto-fallback AP)
	let wlanRescueEnabled = $state(true);
	let wlanRescueTimeoutSeconds = $state(300);
	let apCredentials = $state<{ ssid: string; password: string } | null>(null);
	let apQrDataUrl = $state('');
	let apPasswordCopied = $state(false);

	// Discrete interval presets (in seconds) — segmented control in UI
	const RESCUE_PRESETS = [
		{ seconds: 120, key: 'settings.wlan_rescue_interval_short' },
		{ seconds: 300, key: 'settings.wlan_rescue_interval_medium' },
		{ seconds: 600, key: 'settings.wlan_rescue_interval_long' },
		{ seconds: 1200, key: 'settings.wlan_rescue_interval_verylong' },
	] as const;

	onMount(async () => {
		await loadAll();
	});

	$effect(() => {
		if (error) {
			if (errorTimer) clearTimeout(errorTimer);
			errorTimer = setTimeout(() => { error = ''; }, 5000);
		}
	});

	async function loadAll() {
		try {
			[authStatus, allConfig] = await Promise.all([
				authApi.status(),
				config.getAll(),
			]);
			maxVolume = (allConfig['player.max_volume'] as number) ?? 80;
			startupVolume = (allConfig['player.startup_volume'] as number) ?? 50;
			idleMinutes = (allConfig['system.idle_shutdown_minutes'] as number) ?? 0;
			cardRemovePauses = (allConfig['card.remove_pauses'] as boolean) ?? false;
			gyroEnabled = (allConfig['gyro.enabled'] as boolean) ?? true;
			gyroSensitivity = (allConfig['gyro.sensitivity'] as string) ?? 'normal';
			wlanRescueEnabled = (allConfig['wifi.auto_fallback_enabled'] as boolean) ?? true;
			wlanRescueTimeoutSeconds = (allConfig['wifi.fallback_timeout_seconds'] as number) ?? 300;

			// Credentials + QR are only reachable with a PARENT token
			if (authStatus?.authenticated) {
				try {
					apCredentials = await setupApi.portalCredentials();
					await regenerateQr();
				} catch {
					apCredentials = null;
					apQrDataUrl = '';
				}
			}

			const timer = await authApi.sleepTimer();
			sleepActive = timer.active;
			sleepRemaining = timer.remaining_seconds;
		} catch (e) {
			if (!isBackendOffline()) error = String(e);
		}
	}

	async function login() {
		loginError = '';
		loginLoading = true;
		try {
			await authApi.login(loginPin);
			loginPin = '';
			await loadAll();
		} catch {
			loginError = t('settings.login_error');
		} finally {
			loginLoading = false;
		}
	}

	function logout() {
		authApi.logout();
		authStatus = null;
		loadAll();
	}

	async function saveSetting(key: string, value: unknown) {
		try {
			await config.set(key, value);
			addToast(t('settings.saved'), 'success');
		} catch (e) {
			addToast(e instanceof ApiError ? e.userMessage : t('error.save_failed'), 'error');
		}
	}

	async function regenerateQr() {
		if (!apCredentials) {
			apQrDataUrl = '';
			return;
		}
		// WIFI: URI scheme — modern phones scan this and offer to join directly.
		const escaped = (s: string) => s.replace(/([\\;,":])/g, '\\$1');
		const payload = `WIFI:T:WPA;S:${escaped(apCredentials.ssid)};P:${escaped(apCredentials.password)};;`;
		try {
			apQrDataUrl = await QRCode.toDataURL(payload, { margin: 1, width: 240 });
		} catch {
			apQrDataUrl = '';
		}
	}

	async function toggleWlanRescue(value: boolean) {
		const prev = wlanRescueEnabled;
		wlanRescueEnabled = value;
		try {
			await config.set('wifi.auto_fallback_enabled', value);
			if (value) {
				addToast(t('settings.saved'), 'success');
			} else {
				addToast(t('settings.wlan_rescue_off_warning'), 'info');
			}
		} catch (e) {
			wlanRescueEnabled = prev;
			addToast(e instanceof ApiError ? e.userMessage : t('error.save_failed'), 'error');
		}
	}

	async function setWlanRescueInterval(seconds: number) {
		const prev = wlanRescueTimeoutSeconds;
		wlanRescueTimeoutSeconds = seconds;
		try {
			await config.set('wifi.fallback_timeout_seconds', seconds);
			addToast(t('settings.saved'), 'success');
		} catch (e) {
			wlanRescueTimeoutSeconds = prev;
			addToast(e instanceof ApiError ? e.userMessage : t('error.save_failed'), 'error');
		}
	}

	async function copyApPassword() {
		if (!apCredentials) return;
		try {
			await navigator.clipboard.writeText(apCredentials.password);
			apPasswordCopied = true;
			addToast(t('settings.wlan_rescue_ap_copied'), 'success');
			setTimeout(() => { apPasswordCopied = false; }, 2000);
		} catch {
			addToast(t('error.save_failed'), 'error');
		}
	}

	function escapeHtml(s: string): string {
		return s
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	function printApQr() {
		if (!apCredentials || !apQrDataUrl) return;
		// Open a minimal print-only window so the user can stick the QR on the fridge.
		// SSID is user-controlled (set in the setup wizard) and rendered into inline
		// HTML here — must be escaped to avoid stored XSS via a hostile SSID.
		const w = window.open('', '_blank', 'width=400,height=600');
		if (!w) return;
		const ssid = escapeHtml(apCredentials.ssid);
		const password = escapeHtml(apCredentials.password);
		const printTitle = escapeHtml(t('settings.wlan_rescue_print_title'));
		const printIntro = escapeHtml(t('settings.wlan_rescue_print_intro'));
		const networkLabel = escapeHtml(t('settings.wlan_rescue_ap_network'));
		const passwordLabel = escapeHtml(t('settings.wlan_rescue_ap_password'));
		w.document.write(`<!doctype html><html><head><title>${printTitle}</title>
			<style>
				body { font-family: system-ui, sans-serif; text-align: center; padding: 24px; color: #111; }
				h1 { font-size: 18px; margin-bottom: 8px; }
				p { font-size: 14px; color: #444; margin: 4px 0; }
				img { max-width: 100%; margin-top: 16px; }
				.creds { margin-top: 16px; font-family: monospace; font-size: 13px; }
			</style>
			</head><body>
			<h1>${printTitle}</h1>
			<p>${printIntro}</p>
			<div class="creds">
				<div>${networkLabel}: <strong>${ssid}</strong></div>
				<div>${passwordLabel}: <strong>${password}</strong></div>
			</div>
			<img src="${apQrDataUrl}" alt="QR" />
			<script>window.onload = () => { window.print(); };<\/script>
			</body></html>`);
		w.document.close();
	}

	// Determine current tier level: 0=open, 1=parent, 2=expert
	const currentTier = $derived.by(() => {
		if (!authStatus) return 0;
		if (!authStatus.parent_pin_set && !authStatus.expert_pin_set) return 2; // No PINs = full access
		if (!authStatus.authenticated) return 0;
		if (authStatus.tier === 'expert') return 2;
		// Parent gets full access when no expert PIN exists (otherwise can never set one)
		if (authStatus.tier === 'parent' && !authStatus.expert_pin_set) return 2;
		if (authStatus.tier === 'parent') return 1;
		return 0;
	});
	const isParent = $derived(currentTier >= 1);
	const isExpert = $derived(currentTier >= 2);

	// PIN can only be changed when: no PIN set yet (first time), or user is authenticated
	const canChangePin = $derived(
		authStatus !== null && (!authStatus.parent_pin_set || authStatus.authenticated)
	);

	async function setParentPin() {
		if (parentPinValue.length < 4) return;
		parentPinLoading = true;
		try {
			await authApi.setPin('parent', parentPinValue);
			// Auto-login so the user isn't locked out after setting their first PIN
			try { await authApi.login(parentPinValue); } catch {}
			parentPinValue = '';
			await loadAll();
			addToast(t('settings.saved'), 'success');
		} catch (e) {
			error = t('settings.login_required_change');
		} finally {
			parentPinLoading = false;
		}
	}

	async function setExpertPin() {
		if (expertPinValue.length < 4) return;
		expertPinLoading = true;
		try {
			await authApi.setPin('expert', expertPinValue);
			// Auto-login with the new expert PIN to stay at expert tier
			try { await authApi.login(expertPinValue); } catch {}
			expertPinValue = '';
			await loadAll();
			addToast(t('settings.saved'), 'success');
		} catch {
			error = t('settings.login_required_change');
		} finally {
			expertPinLoading = false;
		}
	}

	async function removeParentPin() {
		try {
			await authApi.removePin('parent');
			await loadAll();
			addToast(t('settings.saved'), 'success');
		} catch {
			error = t('settings.login_required_change');
		}
	}

	async function removeExpertPin() {
		try {
			await authApi.removePin('expert');
			await loadAll();
			addToast(t('settings.saved'), 'success');
		} catch {
			error = t('settings.login_required_change');
		}
	}

	async function startSleep() {
		try {
			await authApi.startSleepTimer(sleepMinutes);
			sleepActive = true;
			sleepRemaining = sleepMinutes * 60;
		} catch {
			error = t('general.error');
		}
	}

	async function cancelSleep() {
		try {
			await authApi.cancelSleepTimer();
			sleepActive = false;
			sleepRemaining = 0;
		} catch {
			error = t('general.error');
		}
	}
</script>

<div class="p-4">
	<h1 class="text-xl font-bold mb-4">{t('settings.title')}</h1>

	{#if error}
		<div class="mb-3 text-sm text-red-400">{error}</div>
	{/if}

	<!-- Login section -->
	{#if authStatus && (authStatus.parent_pin_set || authStatus.expert_pin_set) && !authStatus.authenticated}
		<div class="bg-surface-light rounded-xl p-4 mb-4">
			<h2 class="text-sm font-semibold mb-3">{t('settings.login')}</h2>
			<div class="flex gap-2">
				<input
					type="password"
					bind:value={loginPin}
					placeholder={t('settings.login_pin')}
					class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
					onkeydown={(e) => e.key === 'Enter' && login()}
				/>
				<button onclick={login} disabled={loginLoading} class="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-60 flex items-center gap-2">
						{#if loginLoading}<Spinner size="sm" variant="light" />{/if}
						{t('settings.login')}
					</button>
			</div>
			{#if loginError}
				<p class="text-xs text-red-400 mt-2">{loginError}</p>
			{/if}
		</div>
	{/if}

	{#if authStatus?.authenticated}
		<div class="flex items-center justify-between mb-4 px-1">
			<span class="text-xs text-text-muted">{t('settings.logged_in_as')} <span class="text-primary">{authStatus.tier === 'expert' ? t('settings.tier_expert') : authStatus.tier === 'parent' ? t('settings.tier_parent') : t('settings.tier_open')}</span></span>
			<button onclick={logout} class="text-xs text-text-muted hover:text-text">{t('settings.logout')}</button>
		</div>
	{/if}

	<div class="flex flex-col gap-4">
		<!-- Sleep timer (visible to everyone) -->
		<div class="bg-surface-light rounded-xl p-4">
			<h2 class="text-sm font-semibold mb-3">{t('settings.sleep_timer')}</h2>
			{#if sleepActive}
				<div class="flex items-center justify-between">
					<span class="text-sm text-accent">{t('settings.sleep_active', { minutes: Math.ceil(sleepRemaining / 60) })}</span>
					<button onclick={cancelSleep} class="text-sm text-red-400">{t('settings.sleep_cancel')}</button>
				</div>
			{:else}
				<div class="flex items-center gap-3">
					<input type="number" min="1" max="120" bind:value={sleepMinutes}
						class="w-20 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm text-center focus:outline-none focus:border-primary" />
					<span class="text-sm text-text-muted">{t('settings.sleep_minutes')}</span>
					<button onclick={startSleep} class="ml-auto px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('settings.sleep_start')}</button>
				</div>
			{/if}
		</div>

		{#if isParent}
		<!-- Volume (parent+) -->
		<div class="bg-surface-light rounded-xl p-4">
			<h2 class="text-sm font-semibold mb-3">{t('settings.max_volume')}</h2>
			<div class="flex items-center gap-3">
				<input
					type="range" min="10" max="100" bind:value={maxVolume}
					onchange={() => saveSetting('player.max_volume', maxVolume)}
					class="flex-1 h-2 bg-surface-lighter rounded-full appearance-none cursor-pointer
						[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
						[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
				/>
				<span class="text-sm text-text-muted w-8 text-right tabular-nums">{maxVolume}</span>
			</div>

			<h2 class="text-sm font-semibold mt-4 mb-3">{t('settings.startup_volume')}</h2>
			<div class="flex items-center gap-3">
				<input
					type="range" min="0" max="100" bind:value={startupVolume}
					onchange={() => saveSetting('player.startup_volume', startupVolume)}
					class="flex-1 h-2 bg-surface-lighter rounded-full appearance-none cursor-pointer
						[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
						[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
				/>
				<span class="text-sm text-text-muted w-8 text-right tabular-nums">{startupVolume}</span>
			</div>
		</div>

		<!-- Card remove behavior (parent+) -->
		<div class="bg-surface-light rounded-xl p-4">
			<h2 class="text-sm font-semibold mb-3">{t('settings.card_remove')}</h2>
			<div class="flex gap-2">
				<button
					onclick={() => { cardRemovePauses = true; saveSetting('card.remove_pauses', true); }}
					class="flex-1 px-3 py-2 rounded-lg text-sm transition-colors {cardRemovePauses ? 'bg-primary text-white' : 'bg-surface text-text-muted'}"
				>
					{t('settings.card_remove_pause')}
				</button>
				<button
					onclick={() => { cardRemovePauses = false; saveSetting('card.remove_pauses', false); }}
					class="flex-1 px-3 py-2 rounded-lg text-sm transition-colors {!cardRemovePauses ? 'bg-primary text-white' : 'bg-surface text-text-muted'}"
				>
					{t('settings.card_remove_continue')}
				</button>
			</div>
		</div>

		<!-- Gyro settings -->
		<div class="bg-surface-light rounded-xl p-4">
			{#if isGyroAvailable() === false}
				<HealthBanner type="info" message={t('health.gyro_unavailable')} />
			{:else}
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-sm font-semibold">{t('settings.gyro')}</h2>
					<button
						onclick={() => { gyroEnabled = !gyroEnabled; saveSetting('gyro.enabled', gyroEnabled); }}
						class="px-3 py-1 rounded-full text-xs font-medium transition-colors {gyroEnabled ? 'bg-primary text-white' : 'bg-surface text-text-muted'}"
					>
						{gyroEnabled ? t('settings.gyro_enabled') : t('settings.gyro_disabled')}
					</button>
				</div>
				{#if gyroEnabled}
					<div class="flex gap-2">
						{#each ['gentle', 'normal', 'wild'] as level}
							{@const label = level === 'gentle' ? t('settings.gyro_gentle') : level === 'normal' ? t('settings.gyro_normal') : t('settings.gyro_wild')}
							<button
								onclick={() => { gyroSensitivity = level; saveSetting('gyro.sensitivity', level); }}
								class="flex-1 px-3 py-2 rounded-lg text-sm transition-colors {gyroSensitivity === level ? 'bg-primary text-white' : 'bg-surface text-text-muted'}"
							>
								{label}
							</button>
						{/each}
					</div>
				{/if}
			{/if}
		</div>

		<!-- WiFi rescue (parent+) — auto-fallback AP mode -->
		<div class="bg-surface-light rounded-xl p-4">
			<div class="flex items-center justify-between mb-2">
				<h2 class="text-sm font-semibold">{t('settings.wlan_rescue_title')}</h2>
				<label class="relative inline-flex items-center cursor-pointer">
					<input
						type="checkbox"
						class="sr-only peer"
						checked={wlanRescueEnabled}
						onchange={(e) => toggleWlanRescue((e.target as HTMLInputElement).checked)}
					/>
					<div class="w-11 h-6 bg-surface peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
				</label>
			</div>
			<p class="text-xs text-text-muted mb-3">{t('settings.wlan_rescue_desc')}</p>

			{#if wlanRescueEnabled && apCredentials}
				<div class="bg-surface rounded-lg p-3 sm:p-4 mb-3">
					<div class="text-xs text-text-muted mb-3">{t('settings.wlan_rescue_ap_info')}</div>
					<div class="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-center">
						<!-- Credentials left (mobile: top) -->
						<div class="flex flex-col gap-2 text-xs">
							<div class="flex flex-col gap-0.5">
								<span class="text-text-muted">{t('settings.wlan_rescue_ap_network')}</span>
								<span class="font-mono break-all">{apCredentials.ssid}</span>
							</div>
							<div class="flex flex-col gap-0.5">
								<span class="text-text-muted">{t('settings.wlan_rescue_ap_password')}</span>
								<div class="flex items-center gap-2">
									<span class="font-mono break-all flex-1">{apCredentials.password}</span>
									<button
										onclick={copyApPassword}
										class="px-3 py-1.5 bg-primary hover:bg-primary-light text-white rounded-lg text-xs font-medium transition-colors shrink-0"
									>
										{apPasswordCopied ? t('settings.wlan_rescue_ap_copied') : t('settings.wlan_rescue_ap_copy')}
									</button>
								</div>
							</div>
						</div>

						<!-- QR right (mobile: bottom) -->
						{#if apQrDataUrl}
							<div class="flex flex-col items-center gap-2 sm:items-end">
								<div class="p-2 bg-white rounded-xl shadow-sm">
									<img
										src={apQrDataUrl}
										alt={t('settings.wlan_rescue_qr_aria')}
										class="w-40 h-40 sm:w-44 sm:h-44 block"
									/>
								</div>
								<button
									onclick={printApQr}
									disabled={!apQrDataUrl}
									class="w-full sm:w-auto px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-1.5"
								>
									<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
										<polyline points="6 9 6 2 18 2 18 9"/>
										<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
										<rect x="6" y="14" width="12" height="8"/>
									</svg>
									{t('settings.wlan_rescue_ap_qr_print')}
								</button>
							</div>
						{/if}
					</div>
				</div>
			{/if}

			{#if wlanRescueEnabled}
				<div class="flex items-center gap-2 mb-1">
					<span class="text-xs text-text-muted">{t('settings.wlan_rescue_interval')}</span>
				</div>
				<div class="flex gap-1" role="radiogroup" aria-label={t('settings.wlan_rescue_interval')}>
					{#each RESCUE_PRESETS as preset}
						{@const isActive = wlanRescueTimeoutSeconds === preset.seconds}
						<button
							onclick={() => setWlanRescueInterval(preset.seconds)}
							role="radio"
							aria-checked={isActive}
							class="flex-1 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors {isActive ? 'bg-primary text-white ring-2 ring-primary ring-offset-2 ring-offset-surface-light' : 'bg-surface text-text-muted hover:text-text'}"
						>
							{t(preset.key)}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- PIN management: parent sees own PIN, expert sees both -->
		<div class="bg-surface-light rounded-xl p-4">
			{#if !canChangePin}
				<p class="text-xs text-text-muted">{t('settings.login_required_pin')}</p>
			{:else}
				<h2 class="text-sm font-semibold mb-3">{t('settings.pin_parent')}</h2>
				<p class="text-xs text-text-muted mb-2">
					{authStatus?.parent_pin_set ? t('settings.pin_active') : t('settings.pin_not_set')}
				</p>
				<div class="flex gap-2">
					<input
						type="password"
						bind:value={parentPinValue}
						placeholder={t('settings.pin_placeholder')}
						class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
						onkeydown={(e) => e.key === 'Enter' && setParentPin()}
					/>
					<button
						onclick={setParentPin}
						disabled={parentPinValue.length < 4 || parentPinLoading}
						class="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-2"
					>
						{#if parentPinLoading}<Spinner size="sm" variant="light" />{/if}
						{t('settings.pin_set')}
					</button>
					{#if authStatus?.parent_pin_set}
						<button
							onclick={removeParentPin}
							class="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm hover:bg-red-500/30"
						>
							{t('settings.pin_remove')}
						</button>
					{/if}
				</div>

			{#if isExpert}
			<h2 class="text-sm font-semibold mt-4 mb-3">{t('settings.pin_expert')}</h2>
			<p class="text-xs text-text-muted mb-2">
				{authStatus?.expert_pin_set ? t('settings.pin_active') : t('settings.pin_not_set')}
			</p>
			<div class="flex gap-2">
				<input
					type="password"
					bind:value={expertPinValue}
					placeholder={t('settings.pin_placeholder')}
					class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
					onkeydown={(e) => e.key === 'Enter' && setExpertPin()}
				/>
				<button
					onclick={setExpertPin}
					disabled={expertPinValue.length < 4 || expertPinLoading}
					class="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-2"
				>
					{#if expertPinLoading}<Spinner size="sm" variant="light" />{/if}
					{t('settings.pin_set')}
				</button>
				{#if authStatus?.expert_pin_set}
					<button
						onclick={removeExpertPin}
						class="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm hover:bg-red-500/30"
					>
						{t('settings.pin_remove')}
					</button>
				{/if}
			</div>
			{/if}
			{/if}
		</div>

		{/if}

		{#if isExpert}
		<!-- Idle shutdown (expert) -->
		<div class="bg-surface-light rounded-xl p-4">
			<h2 class="text-sm font-semibold mb-3">{t('settings.idle_shutdown')}</h2>
			<select
				bind:value={idleMinutes}
				onchange={() => saveSetting('system.idle_shutdown_minutes', idleMinutes)}
				class="w-full px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
			>
				<option value={0}>{t('settings.idle_off')}</option>
				<option value={15}>{t('settings.idle_minutes', { minutes: 15 })}</option>
				<option value={30}>{t('settings.idle_minutes', { minutes: 30 })}</option>
				<option value={60}>{t('settings.idle_minutes', { minutes: 60 })}</option>
			</select>
		</div>
		<!-- Expert mode toggle -->
		<div class="bg-surface-light rounded-xl p-4">
			<div class="flex items-center justify-between">
				<div>
					<h2 class="text-sm font-semibold">{t('settings.expert_mode')}</h2>
					<p class="text-xs text-text-muted mt-0.5">{t('settings.expert_mode_desc')}</p>
				</div>
				<button
					onclick={() => { const v = !(allConfig['wizard.expert_mode'] ?? false); allConfig['wizard.expert_mode'] = v; saveSetting('wizard.expert_mode', v); }}
					class="px-3 py-1 rounded-full text-xs font-medium transition-colors {allConfig['wizard.expert_mode'] ? 'bg-primary text-white' : 'bg-surface text-text-muted'}"
				>
					{allConfig['wizard.expert_mode'] ? t('settings.on') : t('settings.off')}
				</button>
			</div>
		</div>

		<!-- System link -->
		<a
			href="/settings/system"
			class="flex items-center justify-between bg-surface-light rounded-xl p-4 hover:bg-surface-lighter transition-colors"
		>
			<div>
				<h2 class="text-sm font-semibold">{t('system.title')}</h2>
				<p class="text-xs text-text-muted mt-0.5">{t('settings.system_desc')}</p>
			</div>
			<svg class="w-5 h-5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M9 18l6-6-6-6"/>
			</svg>
		</a>
		{/if}
	</div>
</div>
