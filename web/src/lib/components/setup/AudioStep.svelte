<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, player, type HardwareAudioOutput } from '$lib/api';

	interface Props {
		hardwareAudio: HardwareAudioOutput[];
		selectedDevice: string | null;
		error: string;
		onError: (msg: string) => void;
		onAudioChange: (device: string) => void;
	}

	let { hardwareAudio, selectedDevice, error, onError, onAudioChange }: Props = $props();

	let testing = $state(false);
	let testResult = $state<'success' | 'error' | null>(null);

	async function testAudio() {
		if (!selectedDevice) return;
		testing = true;
		testResult = null;
		try {
			await setupApi.testAudio();
			testResult = 'success';
		} catch {
			testResult = 'error';
		} finally {
			testing = false;
			// Clear result after 3 seconds
			setTimeout(() => { testResult = null; }, 3000);
		}
	}

	const TYPE_LABELS: Record<string, string> = {
		i2s: 'I2S DAC',
		hdmi: 'HDMI',
		usb: 'USB',
		analog: 'Analog',
		bluetooth: 'Bluetooth',
	};

	async function selectAudio(output: HardwareAudioOutput) {
		try {
			await setupApi.setupAudio(output.device);

			// Enable the matching MPD output if possible, disable others (except "Browser")
			try {
				const mpdOutputs = await player.outputs();
				for (const mpd of mpdOutputs) {
					if (mpd.name === 'Browser') continue;
					// Enable the first non-Browser output when a hardware device is selected
					// MPD typically has one main output matching the hardware
					const shouldEnable = mpd.name !== 'Browser';
					if (shouldEnable && !mpd.enabled) await player.toggleOutput(mpd.id, true);
				}
			} catch {
				// MPD output toggle is best-effort during setup
			}

			onAudioChange(output.device);
		} catch (e) {
			onError(e instanceof Error ? e.message : t('setup.audio_setup_failed'));
		}
	}
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.audio_select')}</h2>
	<p class="text-sm text-text-muted text-center">{t('setup.audio_desc')}</p>

	{#if hardwareAudio.length === 0}
		<p class="text-sm text-text-muted py-4 text-center">{t('setup.audio_no_outputs')}</p>
	{:else}
		<div class="space-y-2">
			{#each hardwareAudio as output}
				{@const isSelected = selectedDevice === output.device}
				<button onclick={() => selectAudio(output)}
					class="w-full bg-surface-light rounded-xl p-4 flex items-center gap-3 text-left transition-colors {isSelected ? 'ring-2 ring-primary' : 'hover:bg-surface-lighter'}">
					<div class="w-5 h-5 rounded-full border-2 flex items-center justify-center {isSelected ? 'border-primary' : 'border-surface-lighter'}">
						{#if isSelected}<div class="w-2.5 h-2.5 rounded-full bg-primary"></div>{/if}
					</div>
					<div class="flex-1">
						<span class="text-sm text-text">{output.name}</span>
						<div class="flex gap-1.5 mt-1">
							<span class="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded-full">{TYPE_LABELS[output.type] ?? output.type}</span>
							{#if output.recommended}
								<span class="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">{t('setup.audio_recommended')}</span>
							{/if}
						</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}

	{#if selectedDevice}
		<div class="flex flex-col items-center gap-2">
			<button
				onclick={testAudio}
				disabled={testing}
				aria-label={t('setup.audio_test')}
				class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-surface-light text-text hover:bg-surface-lighter disabled:opacity-50"
			>
				{#if testing}
					<svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
					</svg>
				{:else}
					<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
						<path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
					</svg>
				{/if}
				{t('setup.audio_test')}
			</button>
			{#if testResult === 'success'}
				<span class="text-sm text-green-400">{t('setup.audio_test_ok')}</span>
			{:else if testResult === 'error'}
				<span class="text-sm text-red-400">{t('setup.audio_test_fail')}</span>
			{/if}
		</div>
	{/if}

	{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
</div>
