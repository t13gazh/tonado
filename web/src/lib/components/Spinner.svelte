<script lang="ts">
	type SpinnerSize = 'sm' | 'md' | 'lg';
	let { size = 'md' }: { size?: SpinnerSize } = $props();
	const sizes: Record<SpinnerSize, string> = { sm: 'w-5 h-5', md: 'w-8 h-8', lg: 'w-12 h-12' };
</script>

<div class="{sizes[size]} border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
