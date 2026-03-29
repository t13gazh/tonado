<script lang="ts">
	import { t } from '$lib/i18n';
	import { config, authApi, type AuthStatus } from '$lib/api';
	import { onMount } from 'svelte';

	let authStatus = $state<AuthStatus | null>(null);
	let allConfig = $state<Record<string, unknown>>({});
	let error = $state('');
	let errorTimer: ReturnType<typeof setTimeout> | null = null;
	let showToast = $state(false);

	// PIN forms
	let parentPinValue = $state('');
	let expertPinValue = $state('');
	let loginPin = $state('');
	let loginError = $state('');

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

			const timer = await authApi.sleepTimer();
			sleepActive = timer.active;
			sleepRemaining = timer.remaining_seconds;
		} catch (e) {
			error = String(e);
		}
	}

	async function login() {
		loginError = '';
		try {
			await authApi.login(loginPin);
			loginPin = '';
			await loadAll();
		} catch {
			loginError = t('settings.login_error');
		}
	}

	function logout() {
		authApi.logout();
		authStatus = null;
		loadAll();
	}

	async function saveSetting(key: string, value: unknown) {
		await config.set(key, value);
		flashToast();
	}

	function flashToast() {
		showToast = true;
		setTimeout(() => (showToast = false), 2000);
	}

	// Determine current tier level: 0=open, 1=parent, 2=expert
	const currentTier = $derived(() => {
		if (!authStatus) return 0;
		if (!authStatus.parent_pin_set && !authStatus.expert_pin_set) return 2; // No PINs = full access
		if (!authStatus.authenticated) return 0;
		if (authStatus.tier === 'expert') return 2;
		if (authStatus.tier === 'parent') return 1;
		return 0;
	});
	const isParent = $derived(currentTier() >= 1);
	const isExpert = $derived(currentTier() >= 2);

	// PIN can only be changed when: no PIN set yet (first time), or user is authenticated
	const canChangePin = $derived(
		authStatus !== null && (!authStatus.parent_pin_set || authStatus.authenticated)
	);

	async function setParentPin() {
		if (parentPinValue.length < 4) return;
		try {
			await authApi.setPin('parent', parentPinValue);
			parentPinValue = '';
			await loadAll();
			flashToast();
		} catch (e) {
			error = 'Bitte erst anmelden, um die PIN zu ändern.';
		}
	}

	async function setExpertPin() {
		if (expertPinValue.length < 4) return;
		try {
			await authApi.setPin('expert', expertPinValue);
			expertPinValue = '';
			await loadAll();
			flashToast();
		} catch {
			error = 'Bitte erst anmelden, um die PIN zu ändern.';
		}
	}

	async function startSleep() {
		await authApi.startSleepTimer(sleepMinutes);
		sleepActive = true;
		sleepRemaining = sleepMinutes * 60;
	}

	async function cancelSleep() {
		await authApi.cancelSleepTimer();
		sleepActive = false;
		sleepRemaining = 0;
	}
</script>

<!-- Fixed toast (does not affect layout) -->
<div
	class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-green-500/90 text-white text-sm rounded-xl shadow-lg transition-all duration-300 pointer-events-none
		{showToast ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2'}"
>
	{t('settings.saved')}
</div>

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
				<button onclick={login} class="px-4 py-2 bg-primary text-white rounded-lg text-sm">{t('settings.login')}</button>
			</div>
			{#if loginError}
				<p class="text-xs text-red-400 mt-2">{loginError}</p>
			{/if}
		</div>
	{/if}

	{#if authStatus?.authenticated}
		<div class="flex items-center justify-between mb-4 px-1">
			<span class="text-xs text-text-muted">Angemeldet als: <span class="text-primary">{authStatus.tier === 'expert' ? 'Experte' : authStatus.tier === 'parent' ? 'Eltern' : 'Offen'}</span></span>
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

		<!-- PIN management -->
		<div class="bg-surface-light rounded-xl p-4">
			{#if !canChangePin}
				<p class="text-xs text-text-muted">Bitte erst anmelden, um PINs zu verwalten.</p>
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
						disabled={parentPinValue.length < 4}
						class="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-30 disabled:cursor-not-allowed"
					>
						{t('settings.pin_set')}
					</button>
				</div>

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
					disabled={expertPinValue.length < 4}
					class="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-30 disabled:cursor-not-allowed"
				>
					{t('settings.pin_set')}
				</button>
			</div>
			{/if}
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
					{allConfig['wizard.expert_mode'] ? 'An' : 'Aus'}
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
				<p class="text-xs text-text-muted mt-0.5">Updates, Backup, Neustart</p>
			</div>
			<svg class="w-5 h-5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M9 18l6-6-6-6"/>
			</svg>
		</a>
		{/if}
	</div>
</div>
