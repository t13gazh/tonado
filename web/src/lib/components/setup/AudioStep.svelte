<script lang="ts">
	import { t } from '$lib/i18n';
	import { player, setupApi } from '$lib/api';

	interface Props {
		audioOutputs: { id: number; name: string; enabled: boolean }[];
		selectedAudioId: number | null;
		error: string;
		onError: (msg: string) => void;
		onAudioChange: (outputs: { id: number; name: string; enabled: boolean }[], selectedId: number) => void;
	}

	let { audioOutputs, selectedAudioId, error, onError, onAudioChange }: Props = $props();

	async function selectAudio(id: number) {
		try {
			for (const output of audioOutputs) {
				if (output.id === id && !output.enabled) await player.toggleOutput(output.id, true);
				else if (output.id !== id && output.enabled) await player.toggleOutput(output.id, false);
			}
			await setupApi.setupAudio(`hw:${id}`);
			const updated = await player.outputs();
			onAudioChange(updated, id);
		} catch (e) { onError(e instanceof Error ? e.message : 'Audio setup failed'); }
	}
</script>

<div class="flex flex-col gap-4">
	<h2 class="text-lg font-semibold text-text text-center">{t('setup.audio_select')}</h2>
	<p class="text-sm text-text-muted text-center">{t('setup.audio_desc')}</p>

	{#if audioOutputs.length === 0}
		<p class="text-sm text-text-muted py-4 text-center">{t('setup.audio_no_outputs')}</p>
	{:else}
		<div class="space-y-2">
			{#each audioOutputs as output}
				<button onclick={() => selectAudio(output.id)}
					class="w-full bg-surface-light rounded-xl p-4 flex items-center gap-3 text-left transition-colors {selectedAudioId === output.id ? 'ring-2 ring-primary' : 'hover:bg-surface-lighter'}">
					<div class="w-5 h-5 rounded-full border-2 flex items-center justify-center {selectedAudioId === output.id ? 'border-primary' : 'border-surface-lighter'}">
						{#if selectedAudioId === output.id}<div class="w-2.5 h-2.5 rounded-full bg-primary"></div>{/if}
					</div>
					<div class="flex-1">
						<span class="text-sm text-text">{output.name}</span>
						{#if output.enabled}<span class="ml-2 text-xs text-green-500">{t('setup.audio_recommended')}</span>{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}

	{#if error}<p class="text-sm text-red-400">{error}</p>{/if}
</div>
