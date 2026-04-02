<!--
  Global toast container. Renders all active toasts as floating notifications.
  Add to root layout once. Does not affect page layout.

  Usage: <ToastContainer />
-->
<script lang="ts">
	import { getToasts, removeToast, type ToastType } from '$lib/stores/toast.svelte';

	const colorMap: Record<ToastType, string> = {
		success: 'bg-green-500/90 text-white',
		error: 'bg-red-500/90 text-white',
		info: 'bg-blue-500/90 text-white',
	};
</script>

<div class="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-2 pointer-events-none" aria-live="polite">
	{#each getToasts() as toast (toast.id)}
		<div
			role="status"
			class="px-4 py-2 text-sm rounded-xl shadow-lg transition-all duration-300 animate-toast-in pointer-events-auto cursor-pointer {colorMap[toast.type]}"
			onclick={() => removeToast(toast.id)}
		>
			{toast.message}
		</div>
	{/each}
</div>

<style>
	@keyframes toast-in {
		from {
			opacity: 0;
			transform: translateY(-8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	.animate-toast-in {
		animation: toast-in 0.2s ease-out;
	}
</style>
