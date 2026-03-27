<script lang="ts">
	import '../app.css';
	import { t } from '$lib/i18n';
	import { connectWebSocket, disconnectWebSocket, isConnected } from '$lib/stores/player.svelte';
	import { onMount } from 'svelte';
	import { page } from '$app/state';

	let { children } = $props();

	onMount(() => {
		connectWebSocket();
		return () => disconnectWebSocket();
	});

	const navItems = [
		{ href: '/', label: () => t('nav.player'), icon: 'player' },
		{ href: '/library', label: () => t('nav.library'), icon: 'library' },
		{ href: '/cards', label: () => t('nav.cards'), icon: 'cards' },
	];
</script>

<svelte:head>
	<title>Tonado</title>
</svelte:head>

<div class="relative flex flex-col h-dvh bg-surface">
	<!-- Main content -->
	<main class="flex-1 overflow-y-auto">
		{@render children()}
	</main>

	<!-- Bottom navigation -->
	<nav class="flex items-center justify-around bg-surface-light border-t border-surface-lighter px-4 py-2 pb-[max(0.5rem,var(--spacing-safe-bottom))]">
		{#each navItems as item}
			{@const active = page.url.pathname === item.href}
			<a
				href={item.href}
				class="flex flex-col items-center gap-1 px-6 py-1 rounded-lg transition-colors {active ? 'text-primary' : 'text-text-muted hover:text-text'}"
			>
				{#if item.icon === 'player'}
					<svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<circle cx="12" cy="12" r="10"/>
						<polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none"/>
					</svg>
				{:else if item.icon === 'library'}
					<svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<rect x="3" y="3" width="7" height="7" rx="1"/>
						<rect x="14" y="3" width="7" height="7" rx="1"/>
						<rect x="3" y="14" width="7" height="7" rx="1"/>
						<rect x="14" y="14" width="7" height="7" rx="1"/>
					</svg>
				{:else if item.icon === 'cards'}
					<svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<rect x="2" y="4" width="14" height="16" rx="2"/>
						<path d="M18 8h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>
					</svg>
				{/if}
				<span class="text-xs font-medium">{item.label()}</span>
			</a>
		{/each}

		<!-- Connection indicator -->
		<div class="absolute top-2 right-3">
			<div class="w-2 h-2 rounded-full {isConnected() ? 'bg-green-500' : 'bg-red-500'}"></div>
		</div>
	</nav>
</div>
