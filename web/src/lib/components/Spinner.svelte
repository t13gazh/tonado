<script lang="ts">
	type SpinnerSize = 'sm' | 'md' | 'lg';
	type SpinnerVariant = 'default' | 'light';
	let { size = 'md', variant = 'default' }: { size?: SpinnerSize; variant?: SpinnerVariant } = $props();
	const sizes: Record<SpinnerSize, string> = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' };
	const variants: Record<SpinnerVariant, string> = {
		default: 'border-primary border-t-transparent',
		light: 'border-white/80 border-t-transparent',
	};
</script>

<div class="{sizes[size]} border-2 {variants[variant]} rounded-full animate-spin"></div>
