<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n';
	import { setupApi, ApiError } from '$lib/api';
	import InlineError from '$lib/components/InlineError.svelte';
	import Icon from '$lib/components/Icon.svelte';

	interface Props {
		saved: boolean;
		error: string;
		onError: (msg: string) => void;
		/** Called once the credentials are accepted + persisted by the backend. */
		onSaved: () => void;
	}

	let { saved = $bindable(), error, onError, onSaved }: Props = $props();

	// Same bounds the backend enforces (MIN_PASSWORD_LENGTH / WPA2 max).
	const MIN_PASSWORD_LENGTH = 10;
	const MAX_PASSWORD_LENGTH = 63;
	const MAX_SSID_LENGTH = 32;

	let ssid = $state('');
	let password = $state('');
	let showPassword = $state(false);
	let loadingSuggestion = $state(true);
	let saving = $state(false);
	let localError = $state<string | null>(null);

	const passwordTooShort = $derived(password.length > 0 && password.length < MIN_PASSWORD_LENGTH);
	const ssidEmpty = $derived(ssid.trim().length === 0);

	async function loadSuggestion(): Promise<boolean> {
		loadingSuggestion = true;
		localError = null;
		try {
			const creds = await setupApi.recoveryWifiSuggestion();
			ssid = creds.ssid;
			password = creds.password;
			return true;
		} catch {
			// Fall back to a sensible default name; the parent can still type a
			// password. The backend will reject an empty / short one on submit.
			if (!ssid) ssid = 'Tonado';
			return false;
		} finally {
			loadingSuggestion = false;
		}
	}

	function validate(): string | null {
		const name = ssid.trim();
		if (!name) return t('setup.recovery_ssid_required');
		if (name.length > MAX_SSID_LENGTH) return t('setup.recovery_ssid_too_long');
		if (password.length < MIN_PASSWORD_LENGTH) return t('setup.recovery_password_too_short');
		return null;
	}

	async function save() {
		if (saving) return; // guard against a double-submit (page-level nav button)
		localError = null;
		const err = validate();
		if (err) {
			localError = err;
			onError(err);
			return;
		}
		saving = true;
		try {
			await setupApi.saveRecoveryWifi(ssid.trim(), password);
			saved = true;
			onSaved();
		} catch (e) {
			let msg: string;
			if (e instanceof ApiError) {
				// Backend returns curated German messages for validation (400).
				msg = e.status === 400 ? e.userMessage : t('setup.recovery_save_failed');
				if (e.status === 400 && e.message) msg = e.message;
			} else {
				msg = t('setup.recovery_save_failed');
			}
			localError = msg;
			onError(msg);
		} finally {
			saving = false;
		}
	}

	export function isValid(): boolean {
		return validate() === null;
	}

	export async function submit() {
		await save();
	}

	async function regenerate() {
		// Re-pull a fresh suggestion (new generated password) without losing the
		// SSID the parent may have already typed. Surface a failure instead of
		// silently doing nothing — the parent explicitly asked for a new one.
		const keptSsid = ssid;
		const ok = await loadSuggestion();
		if (keptSsid.trim()) ssid = keptSsid;
		if (!ok) {
			const msg = t('setup.recovery_suggest_failed');
			localError = msg;
			onError(msg);
		}
	}

	const visibleError = $derived(localError ?? (error ? error : null));

	onMount(loadSuggestion);
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.recovery_title')}</h2>
	<p class="text-sm text-text-muted text-center">{t('setup.recovery_desc')}</p>

	<!-- "Warum?" — explains the fridge-note use case in parent language. -->
	<div class="bg-surface-light rounded-xl p-3 flex items-start gap-2">
		<Icon name="help-circle" size={16} class="text-primary mt-0.5 shrink-0" strokeWidth={2} />
		<p class="text-xs text-text-muted">{t('setup.recovery_why')}</p>
	</div>

	{#if loadingSuggestion}
		<p class="text-sm text-text-muted py-4 text-center">{t('setup.recovery_loading')}</p>
	{:else}
		<fieldset class="flex flex-col gap-1.5 border-0 p-0 m-0" disabled={saving || saved}>
			<label for="recovery-ssid" class="text-sm text-text">{t('setup.recovery_name_label')}</label>
			<input
				id="recovery-ssid"
				type="text"
				bind:value={ssid}
				maxlength={MAX_SSID_LENGTH}
				autocomplete="off"
				aria-describedby={visibleError ? 'recovery-error' : undefined}
				aria-invalid={ssidEmpty ? 'true' : undefined}
				class="w-full px-3 py-2.5 bg-surface border-2 border-surface-lighter rounded-xl text-text focus:border-primary focus:ring-2 focus:ring-primary/40 focus:outline-none transition-colors"
			/>
		</fieldset>

		<fieldset class="flex flex-col gap-1.5 border-0 p-0 m-0" disabled={saving || saved}>
			<label for="recovery-password" class="text-sm text-text">{t('setup.recovery_password_label')}</label>
			<div class="relative">
				<input
					id="recovery-password"
					type={showPassword ? 'text' : 'password'}
					bind:value={password}
					maxlength={MAX_PASSWORD_LENGTH}
					autocomplete="off"
					aria-describedby={visibleError ? 'recovery-error' : undefined}
					aria-invalid={passwordTooShort ? 'true' : undefined}
					class="w-full px-3 py-2.5 pr-12 bg-surface border-2 border-surface-lighter rounded-xl text-text focus:border-primary focus:ring-2 focus:ring-primary/40 focus:outline-none transition-colors"
				/>
				<button
					type="button"
					onclick={() => (showPassword = !showPassword)}
					aria-label={showPassword ? t('setup.recovery_hide_password') : t('setup.recovery_show_password')}
					class="absolute right-2 top-1/2 -translate-y-1/2 p-2 min-h-11 min-w-11 inline-flex items-center justify-center text-text-muted hover:text-text rounded-lg transition-colors"
				>
					<Icon name={showPassword ? 'eye-off' : 'eye'} size={18} />
				</button>
			</div>
			{#if passwordTooShort}
				<p class="text-xs text-amber-400">{t('setup.recovery_password_too_short')}</p>
			{/if}
		</fieldset>

		<button
			type="button"
			onclick={regenerate}
			disabled={saving || saved}
			class="self-start inline-flex items-center gap-1.5 text-xs text-primary hover:text-primary-light transition-colors disabled:opacity-50"
		>
			<Icon name="refresh" size={14} />
			{t('setup.recovery_regenerate')}
		</button>
	{/if}

	{#if saved}
		<p class="text-sm text-green-400 text-center">{t('setup.recovery_saved')}</p>
	{/if}

	<InlineError message={visibleError} id="recovery-error" />
</div>
