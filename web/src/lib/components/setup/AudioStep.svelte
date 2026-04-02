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
			onError(e instanceof Error ? e.message : 'Audio setup failed');
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

	{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
</div>
