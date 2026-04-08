<script lang="ts">
	import { t } from '$lib/i18n';
	import { authApi, ApiError } from '$lib/api';
	import { refreshAuth } from '$lib/stores/auth.svelte';

	interface Props {
		open: boolean;
		onSuccess: () => void;
		onClose: () => void;
	}

	let { open, onSuccess, onClose }: Props = $props();

	let pin = $state('');
	let error = $state('');
	let loading = $state(false);
	let shake = $state(false);
	let pinInput = $state<HTMLInputElement | null>(null);

	$effect(() => {
		if (open) {
			pin = '';
			error = '';
			loading = false;
			shake = false;
			// Auto-focus after DOM update
			requestAnimationFrame(() => pinInput?.focus());
		}
	});

	async function submit() {
		if (!pin.trim() || loading) return;
		loading = true;
		error = '';
		try {
			await authApi.login(pin);
			refreshAuth();
			onSuccess();
		} catch (err) {
			if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
				error = t('auth.wrong_pin');
			} else {
				error = t('general.error');
			}
			shake = true;
			setTimeout(() => { shake = false; }, 500);
			pinInput?.focus();
		} finally {
			loading = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) onClose();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50"
		role="dialog"
		aria-modal="true"
		onclick={handleBackdrop}
		onkeydown={handleKeydown}
	>
		<div class="bg-surface-light w-full sm:w-[24rem] rounded-t-2xl sm:rounded-2xl p-5 flex flex-col animate-slide-up">
			<h2 class="text-lg font-bold mb-1">{t('auth.enter_parent_pin')}</h2>

			<form onsubmit={(e) => { e.preventDefault(); submit(); }} class="flex flex-col gap-4 mt-3">
				<div>
					<input
						bind:this={pinInput}
						bind:value={pin}
						type="password"
						inputmode="numeric"
						maxlength="10"
						autocomplete="off"
						placeholder="PIN"
						class="w-full px-4 py-3 bg-surface border rounded-lg text-text text-center text-lg tracking-widest focus:outline-none focus:border-primary {error ? 'border-red-400' : 'border-surface-lighter'} {shake ? 'animate-shake' : ''}"
					/>
					{#if error}
						<p class="text-sm text-red-400 mt-2 text-center">{error}</p>
					{/if}
				</div>

				<button
					type="submit"
					disabled={!pin.trim() || loading}
					class="w-full py-3 bg-primary hover:bg-primary-light disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
				>
					{loading ? t('general.loading') : t('auth.login_button')}
				</button>
			</form>

			<button
				onclick={onClose}
				class="mt-3 w-full py-2 text-sm text-text-muted hover:text-text text-center transition-colors"
			>
				{t('auth.cancel')}
			</button>
		</div>
	</div>
{/if}

<style>
	@keyframes slide-up {
		from { transform: translateY(100%); opacity: 0; }
		to { transform: translateY(0); opacity: 1; }
	}
	@keyframes shake {
		0%, 100% { transform: translateX(0); }
		20%, 60% { transform: translateX(-6px); }
		40%, 80% { transform: translateX(6px); }
	}
	:global(.animate-slide-up) {
		animation: slide-up 0.3s ease-out;
	}
	:global(.animate-shake) {
		animation: shake 0.4s ease-in-out;
	}
</style>
