<script lang="ts">
	import { t } from '$lib/i18n';
	import { authApi, setupApi } from '$lib/api';

	interface Props {
		saved: boolean;
		error: string;
		onError: (msg: string) => void;
		onSaved: () => void;
	}

	let { saved = $bindable(), error, onError, onSaved }: Props = $props();

	let parentPin = $state('');
	let parentPinRepeat = $state('');
	let expertPin = $state('');
	let expertPinRepeat = $state('');
	let saving = $state(false);
	let localError = $state('');

	const expertPairComplete = $derived(expertPin.length > 0 || expertPinRepeat.length > 0);

	function validate(): string | null {
		if (parentPin.length < 4) return t('setup.pin_too_short');
		if (parentPin !== parentPinRepeat) return t('setup.pin_mismatch');
		if (expertPairComplete) {
			if (expertPin.length < 4) return t('setup.pin_too_short');
			if (expertPin !== expertPinRepeat) return t('setup.pin_mismatch');
		}
		return null;
	}

	async function save() {
		localError = '';
		const err = validate();
		if (err) {
			localError = err;
			onError(err);
			return;
		}
		saving = true;
		try {
			await authApi.setPin('parent', parentPin);
			if (expertPairComplete) {
				await authApi.setPin('expert', expertPin);
			}
			await setupApi.pinDone();
			saved = true;
			onSaved();
		} catch (e) {
			const msg = e instanceof Error ? e.message : t('setup.pin_save_failed');
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
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.pin_title')}</h2>
	<p class="text-sm text-text-muted text-center">{t('setup.pin_desc')}</p>

	<div class="flex flex-col gap-2">
		<label class="text-sm text-text" for="pin-parent">{t('setup.pin_parent_label')}</label>
		<input
			id="pin-parent"
			type="password"
			inputmode="numeric"
			autocomplete="new-password"
			maxlength="32"
			bind:value={parentPin}
			placeholder={t('setup.pin_parent_placeholder')}
			disabled={saving || saved}
			class="bg-surface-light rounded-lg px-4 py-3 text-text placeholder:text-text-muted focus:ring-2 focus:ring-primary outline-none"
		/>
		<input
			type="password"
			inputmode="numeric"
			autocomplete="new-password"
			maxlength="32"
			bind:value={parentPinRepeat}
			placeholder={t('setup.pin_confirm_label')}
			disabled={saving || saved}
			class="bg-surface-light rounded-lg px-4 py-3 text-text placeholder:text-text-muted focus:ring-2 focus:ring-primary outline-none"
		/>
	</div>

	<div class="flex flex-col gap-2">
		<label class="text-sm text-text" for="pin-expert">{t('setup.pin_expert_label')}</label>
		<p class="text-xs text-text-muted">{t('setup.pin_expert_hint')}</p>
		<input
			id="pin-expert"
			type="password"
			inputmode="numeric"
			autocomplete="new-password"
			maxlength="32"
			bind:value={expertPin}
			placeholder={t('setup.pin_parent_placeholder')}
			disabled={saving || saved}
			class="bg-surface-light rounded-lg px-4 py-3 text-text placeholder:text-text-muted focus:ring-2 focus:ring-primary outline-none"
		/>
		<input
			type="password"
			inputmode="numeric"
			autocomplete="new-password"
			maxlength="32"
			bind:value={expertPinRepeat}
			placeholder={t('setup.pin_confirm_label')}
			disabled={saving || saved}
			class="bg-surface-light rounded-lg px-4 py-3 text-text placeholder:text-text-muted focus:ring-2 focus:ring-primary outline-none"
		/>
	</div>

	{#if saved}
		<p class="text-sm text-green-400 text-center">{t('setup.pin_saved')}</p>
	{/if}
	{#if localError}
		<p class="text-sm text-red-400 text-center">{localError}</p>
	{:else if error}
		<p class="text-sm text-red-400 text-center">{error}</p>
	{/if}
</div>
