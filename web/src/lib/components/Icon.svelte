<script lang="ts">
	import { icons } from '$lib/icons';

	interface Props {
		name: string;
		size?: number;
		class?: string;
		fill?: string;
		strokeWidth?: number;
	}

	let {
		name,
		size = 24,
		class: className = '',
		fill = 'none',
		strokeWidth = 2,
	}: Props = $props();

	const path = $derived(icons[name] ?? '');
</script>

<svg
	class={className}
	width={size}
	height={size}
	viewBox="0 0 24 24"
	{fill}
	stroke="currentColor"
	stroke-width={strokeWidth}
	stroke-linecap="round"
	stroke-linejoin="round"
>
	{@html path}
</svg>
