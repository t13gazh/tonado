<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n';
	import { authApi, setupApi, ApiError } from '$lib/api';
	import InlineError from '$lib/components/InlineError.svelte';

	interface Props {
		saved: boolean;
		error: string;
		onError: (msg: string) => void;
		onSaved: () => void;
	}

	let { saved = $bindable(), error, onError, onSaved }: Props = $props();

	// Four-digit OTP-style inputs for each PIN.
	const PIN_LENGTH = 4;
	const emptyPin = () => Array.from({ length: PIN_LENGTH }, () => '');

	let parentDigits = $state<string[]>(emptyPin());
	let parentRepeatDigits = $state<string[]>(emptyPin());
	let expertDigits = $state<string[]>(emptyPin());
	let expertRepeatDigits = $state<string[]>(emptyPin());

	// Element refs for auto-focus-advance / backspace-back.
	let parentInputs: HTMLInputElement[] = [];
	let parentRepeatInputs: HTMLInputElement[] = [];
	let expertInputs: HTMLInputElement[] = [];
	let expertRepeatInputs: HTMLInputElement[] = [];

	let saving = $state(false);
	let localError = $state<string | null>(null);

	// Joined strings for validation / submit.
	const parentPin = $derived(parentDigits.join(''));
	const parentPinRepeat = $derived(parentRepeatDigits.join(''));
	const expertPin = $derived(expertDigits.join(''));
	const expertPinRepeat = $derived(expertRepeatDigits.join(''));
	const expertPairComplete = $derived(expertPin.length > 0 || expertPinRepeat.length > 0);

	// Row identifiers — used to remember which row already auto-advanced once.
	type RowId = 'parent' | 'parentRepeat' | 'expert' | 'expertRepeat';
	// Tracks rows that already triggered the one-shot jump to the next row,
	// so editing a digit inside a fully-filled row does NOT pull focus away.
	const advancedRows = new Set<RowId>();

	/** Brief focus-pulse to confirm the cursor jumped to a new row. */
	function pulseFocus(el: HTMLInputElement | undefined): void {
		if (!el) return;
		el.classList.remove('pin-focus-pulse');
		// Force reflow so the animation restarts if it was already applied.
		void el.offsetWidth;
		el.classList.add('pin-focus-pulse');
		window.setTimeout(() => el.classList.remove('pin-focus-pulse'), 260);
	}

	/** Accept digit-only, single char; auto-advance on input. */
	function handleDigitInput(
		digits: string[],
		inputs: HTMLInputElement[],
		index: number,
		e: Event,
		nextRow?: { id: RowId; inputs: HTMLInputElement[]; digits: string[] },
	): void {
		const el = e.target as HTMLInputElement;
		const sanitized = el.value.replace(/\D/g, '').slice(-1);
		digits[index] = sanitized;
		// Write back the sanitized value (protects against paste / non-digits).
		el.value = sanitized;
		if (!sanitized) return;
		if (index < PIN_LENGTH - 1) {
			inputs[index + 1]?.focus();
			inputs[index + 1]?.select();
			return;
		}
		// Last digit of the row just got filled — try to jump into the next row.
		if (nextRow && !advancedRows.has(nextRow.id)) {
			const nextEmpty = nextRow.digits.every((d) => !d);
			if (nextEmpty) {
				advancedRows.add(nextRow.id);
				const target = nextRow.inputs[0];
				target?.focus();
				target?.select();
				pulseFocus(target);
			}
		}
	}

	/** Backspace on empty cell jumps back; Arrow-Left/Right navigate. */
	function handleDigitKeydown(
		digits: string[],
		inputs: HTMLInputElement[],
		index: number,
		e: KeyboardEvent,
	): void {
		if (e.key === 'Backspace' && !digits[index] && index > 0) {
			e.preventDefault();
			inputs[index - 1]?.focus();
			inputs[index - 1]?.select();
			return;
		}
		if (e.key === 'ArrowLeft' && index > 0) {
			e.preventDefault();
			inputs[index - 1]?.focus();
			inputs[index - 1]?.select();
			return;
		}
		if (e.key === 'ArrowRight' && index < PIN_LENGTH - 1) {
			e.preventDefault();
			inputs[index + 1]?.focus();
			inputs[index + 1]?.select();
		}
	}

	/** Paste a 4-digit PIN at once: fill all cells, move focus to last. */
	function handleDigitPaste(
		digits: string[],
		inputs: HTMLInputElement[],
		e: ClipboardEvent,
	): void {
		const pasted = e.clipboardData?.getData('text')?.replace(/\D/g, '') ?? '';
		if (!pasted) return;
		e.preventDefault();
		for (let i = 0; i < PIN_LENGTH; i++) {
			digits[i] = pasted[i] ?? '';
		}
		const lastFilled = Math.min(pasted.length, PIN_LENGTH) - 1;
		if (lastFilled >= 0) {
			inputs[lastFilled]?.focus();
			inputs[lastFilled]?.select();
		}
	}

	function validate(): string | null {
		if (parentPin.length < PIN_LENGTH) return t('setup.pin_too_short');
		if (parentPin !== parentPinRepeat) return t('setup.pin_mismatch');
		if (expertPairComplete) {
			if (expertPin.length < PIN_LENGTH) return t('setup.pin_too_short');
			if (expertPin !== expertPinRepeat) return t('setup.pin_mismatch');
		}
		return null;
	}

	async function save() {
		localError = null;
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
			// Translate status-based errors — never leak raw backend strings.
			let msg: string;
			if (e instanceof ApiError) {
				if (e.status === 403) msg = t('setup.pin_access_denied');
				else if (e.status === 401) msg = t('setup.pin_unauthorized');
				else msg = t('setup.pin_save_failed');
			} else {
				msg = t('setup.pin_save_failed');
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

	// Prefer the local (structured) error over the page-level fallback.
	const visibleError = $derived(localError ?? (error ? error : null));

	onMount(() => {
		if (!saved) parentInputs[0]?.focus();
	});
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.pin_title')}</h2>
	<p class="text-sm text-text-muted text-center">{t('setup.pin_desc')}</p>

	<!-- Parent PIN (required, fixed 4 digits) -->
	<fieldset class="flex flex-col border-0 p-0 m-0" disabled={saving || saved}>
		<legend class="text-sm text-text text-center w-full mb-3">{t('setup.pin_parent_label')}</legend>
		<div
			class="flex gap-2 justify-center"
			role="group"
			aria-label={t('setup.pin_parent_label')}
			aria-describedby={visibleError ? 'pin-error' : undefined}
		>
			{#each parentDigits as digit, i (i)}
				<input
					bind:this={parentInputs[i]}
					type="password"
					inputmode="numeric"
					autocomplete="new-password"
					maxlength="1"
					value={digit}
					oninput={(e) =>
						handleDigitInput(parentDigits, parentInputs, i, e, {
							id: 'parentRepeat',
							inputs: parentRepeatInputs,
							digits: parentRepeatDigits,
						})}
					onkeydown={(e) => handleDigitKeydown(parentDigits, parentInputs, i, e)}
					onpaste={(e) => handleDigitPaste(parentDigits, parentInputs, e)}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					aria-label={t('setup.pin_parent_digit', { n: i + 1 })}
					aria-invalid={visibleError ? 'true' : undefined}
					class="w-14 h-16 text-center text-2xl font-semibold tabular-nums bg-surface border-2 border-surface-lighter rounded-xl text-text focus:border-primary focus:ring-2 focus:ring-primary/40 focus:outline-none transition-colors"
				/>
			{/each}
		</div>
	</fieldset>

	<!-- Parent PIN repeat -->
	<fieldset class="flex flex-col border-0 p-0 m-0" disabled={saving || saved}>
		<legend class="text-sm text-text text-center w-full mb-3">{t('setup.pin_confirm_label')}</legend>
		<div
			class="flex gap-2 justify-center"
			role="group"
			aria-label={t('setup.pin_confirm_label')}
			aria-describedby={visibleError ? 'pin-error' : undefined}
		>
			{#each parentRepeatDigits as digit, i (i)}
				<input
					bind:this={parentRepeatInputs[i]}
					type="password"
					inputmode="numeric"
					autocomplete="new-password"
					maxlength="1"
					value={digit}
					oninput={(e) =>
						handleDigitInput(parentRepeatDigits, parentRepeatInputs, i, e, {
							id: 'expert',
							inputs: expertInputs,
							digits: expertDigits,
						})}
					onkeydown={(e) => handleDigitKeydown(parentRepeatDigits, parentRepeatInputs, i, e)}
					onpaste={(e) => handleDigitPaste(parentRepeatDigits, parentRepeatInputs, e)}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					aria-label={t('setup.pin_parent_repeat_digit', { n: i + 1 })}
					class="w-14 h-16 text-center text-2xl font-semibold tabular-nums bg-surface border-2 border-surface-lighter rounded-xl text-text focus:border-primary focus:ring-2 focus:ring-primary/40 focus:outline-none transition-colors"
				/>
			{/each}
		</div>
	</fieldset>

	<!-- Expert PIN (optional, also 4 digits) -->
	<fieldset class="flex flex-col border-0 p-0 m-0" disabled={saving || saved}>
		<legend class="text-sm text-text text-center w-full">{t('setup.pin_expert_label')}</legend>
		<p class="text-xs text-text-muted text-center mb-3">{t('setup.pin_expert_hint')}</p>
		<div
			class="flex gap-2 justify-center"
			role="group"
			aria-label={t('setup.pin_expert_label')}
			aria-describedby={visibleError ? 'pin-error' : undefined}
		>
			{#each expertDigits as digit, i (i)}
				<input
					bind:this={expertInputs[i]}
					type="password"
					inputmode="numeric"
					autocomplete="new-password"
					maxlength="1"
					value={digit}
					oninput={(e) =>
						handleDigitInput(expertDigits, expertInputs, i, e, {
							id: 'expertRepeat',
							inputs: expertRepeatInputs,
							digits: expertRepeatDigits,
						})}
					onkeydown={(e) => handleDigitKeydown(expertDigits, expertInputs, i, e)}
					onpaste={(e) => handleDigitPaste(expertDigits, expertInputs, e)}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					aria-label={t('setup.pin_expert_digit', { n: i + 1 })}
					class="w-14 h-16 text-center text-2xl font-semibold tabular-nums bg-surface border-2 border-surface-lighter rounded-xl text-text focus:border-primary focus:ring-2 focus:ring-primary/40 focus:outline-none transition-colors"
				/>
			{/each}
		</div>
	</fieldset>

	<!-- Expert PIN repeat -->
	<fieldset class="flex flex-col border-0 p-0 m-0" disabled={saving || saved}>
		<legend class="text-sm text-text text-center w-full mb-3">{t('setup.pin_confirm_label')}</legend>
		<div
			class="flex gap-2 justify-center"
			role="group"
			aria-label={t('setup.pin_confirm_label')}
			aria-describedby={visibleError ? 'pin-error' : undefined}
		>
			{#each expertRepeatDigits as digit, i (i)}
				<input
					bind:this={expertRepeatInputs[i]}
					type="password"
					inputmode="numeric"
					autocomplete="new-password"
					maxlength="1"
					value={digit}
					oninput={(e) => handleDigitInput(expertRepeatDigits, expertRepeatInputs, i, e)}
					onkeydown={(e) => handleDigitKeydown(expertRepeatDigits, expertRepeatInputs, i, e)}
					onpaste={(e) => handleDigitPaste(expertRepeatDigits, expertRepeatInputs, e)}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					aria-label={t('setup.pin_expert_repeat_digit', { n: i + 1 })}
					class="w-14 h-16 text-center text-2xl font-semibold tabular-nums bg-surface border-2 border-surface-lighter rounded-xl text-text focus:border-primary focus:ring-2 focus:ring-primary/40 focus:outline-none transition-colors"
				/>
			{/each}
		</div>
	</fieldset>

	{#if saved}
		<p class="text-sm text-green-400 text-center">{t('setup.pin_saved')}</p>
	{/if}

	<InlineError message={visibleError} id="pin-error" />
</div>

<style>
	/* Brief ring-pulse confirming an auto-advance into the next PIN row.
	   Kept subtle: ~240ms, ease-out, no layout shift — only ring + tiny scale. */
	:global(.pin-focus-pulse) {
		animation: pin-focus-pulse 240ms cubic-bezier(0.22, 1, 0.36, 1);
	}
	@keyframes pin-focus-pulse {
		0% {
			box-shadow: 0 0 0 0 rgb(var(--color-primary, 99 102 241) / 0.55);
			transform: scale(1);
		}
		60% {
			box-shadow: 0 0 0 6px rgb(var(--color-primary, 99 102 241) / 0);
			transform: scale(1.04);
		}
		100% {
			box-shadow: 0 0 0 0 rgb(var(--color-primary, 99 102 241) / 0);
			transform: scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		:global(.pin-focus-pulse) {
			animation: none;
		}
	}
</style>
