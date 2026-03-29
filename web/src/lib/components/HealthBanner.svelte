<!--
  Inline warning banner for degraded hardware states.
  Shows an amber/red banner with icon and message.

  Usage: <HealthBanner type="warning" message="..." />
-->
<script lang="ts">
	type BannerType = 'warning' | 'error' | 'info';

	let { type = 'warning', message }: { type?: BannerType; message: string } = $props();

	const colors: Record<BannerType, string> = {
		warning: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
		error: 'bg-red-500/10 border-red-500/30 text-red-400',
		info: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
	};

	const icons: Record<BannerType, string> = {
		warning: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z',
		error: 'M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z',
		info: 'M11.25 11.25l.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z',
	};
</script>

<div class="flex items-start gap-2.5 px-3 py-2.5 rounded-xl border text-sm {colors[type]}">
	<svg class="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
		<path stroke-linecap="round" stroke-linejoin="round" d={icons[type]} />
	</svg>
	<span>{message}</span>
</div>
