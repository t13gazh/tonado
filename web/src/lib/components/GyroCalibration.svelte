<script lang="ts">
	import { t } from '$lib/i18n';
	import { systemApi } from '$lib/api';
	import Spinner from '$lib/components/Spinner.svelte';

	interface Props {
		onDone: () => void;
		onCancel: () => void;
	}

	let { onDone, onCancel }: Props = $props();

	type Step = 'intro' | 'rest_ready' | 'rest_measuring' | 'tilt_ready' | 'tilt_measuring' | 'test' | 'saving';
	let step = $state<Step>('intro');
	let error = $state('');

	// Live test feedback
	let testGesture = $state('');
	let testPollTimer = $state<ReturnType<typeof setInterval> | null>(null);
	let flipped = $state(false);

	async function startCalibration() {
		error = '';
		try {
			await systemApi.gyroCalibrateStart();
			step = 'rest_ready';
		} catch {
			error = t('gyro.error');
		}
	}

	async function measureRest() {
		error = '';
		step = 'rest_measuring';
		try {
			await systemApi.gyroCalibrateRest();
			step = 'tilt_ready';
		} catch {
			error = t('gyro.error_rest');
			step = 'rest_ready';
		}
	}

	async function measureTilt() {
		error = '';
		step = 'tilt_measuring';
		try {
			await systemApi.gyroCalibrateTilt();
			step = 'saving';
			const saveResult = await systemApi.gyroCalibrateSave();
			if (saveResult.status === 'ok') {
				step = 'test';
				startTestPolling();
			}
		} catch {
			error = t('gyro.error_tilt');
			step = 'tilt_ready';
		}
	}

	const gestureLabels: Record<string, string> = {
		tilt_left: 'gyro.test_tilt_left',
		tilt_right: 'gyro.test_tilt_right',
		tilt_forward: 'gyro.test_tilt_forward',
		tilt_back: 'gyro.test_tilt_back',
		shake: 'gyro.test_shake',
	};

	function startTestPolling() {
		stopTestPolling();
		testPollTimer = setInterval(async () => {
			try {
				const data = await systemApi.gyroRaw();
				if (data.gesture && data.gesture in gestureLabels) {
					testGesture = t(gestureLabels[data.gesture]);
				} else {
					testGesture = '';
				}
			} catch {
				// Ignore poll errors
			}
		}, 200);
	}

	function stopTestPolling() {
		if (testPollTimer) {
			clearInterval(testPollTimer);
			testPollTimer = null;
		}
	}

	async function finish() {
		stopTestPolling();
		onDone();
	}

	async function toggleFlip() {
		try {
			await systemApi.gyroFlipForward();
			flipped = !flipped;
		} catch {
			error = t('gyro.error');
		}
	}

	async function retry() {
		stopTestPolling();
		testGesture = '';
		error = '';
		await startCalibration();
	}

	async function cancel() {
		stopTestPolling();
		await systemApi.gyroCalibrateCancel().catch(() => {});
		onCancel();
	}
</script>

<div class="flex flex-col gap-4">
	{#if error}
		<div class="px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">{error}</div>
	{/if}

	{#if step === 'intro'}
		<div class="text-center space-y-3">
			<div class="w-16 h-16 mx-auto rounded-full bg-primary/20 flex items-center justify-center">
				<svg class="w-8 h-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
				</svg>
			</div>
			<h3 class="text-lg font-semibold">{t('gyro.calibrate')}</h3>
			<p class="text-sm text-text-muted">{t('gyro.calibrate_desc')}</p>
		</div>
		<button onclick={startCalibration} class="w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
			{t('gyro.start_button')}
		</button>
		<button onclick={cancel} class="w-full px-4 py-2.5 text-text-muted text-sm">
			{t('gyro.cancel')}
		</button>

	{:else if step === 'rest_ready'}
		<!-- Step 1: Place box flat — user confirms -->
		<div class="text-center space-y-3">
			<div class="w-16 h-16 mx-auto rounded-full bg-amber-500/20 flex items-center justify-center">
				<svg class="w-10 h-10 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="3" y="10" width="18" height="8" rx="1"/>
					<line x1="2" y1="18" x2="22" y2="18" stroke-width="2"/>
				</svg>
			</div>
			<h3 class="text-lg font-semibold">{t('gyro.step_rest')}</h3>
			<p class="text-xs text-text-muted">{t('gyro.step_rest_hint')}</p>
		</div>
		<button onclick={measureRest} class="w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
			{t('gyro.step_rest_confirm')}
		</button>
		<button onclick={cancel} class="w-full px-4 py-2.5 text-text-muted text-sm">
			{t('gyro.cancel')}
		</button>

	{:else if step === 'rest_measuring'}
		<div class="text-center space-y-3">
			<div class="w-16 h-16 mx-auto rounded-full bg-amber-500/20 flex items-center justify-center animate-pulse">
				<svg class="w-10 h-10 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="3" y="10" width="18" height="8" rx="1"/>
					<line x1="2" y1="18" x2="22" y2="18" stroke-width="2"/>
				</svg>
			</div>
			<h3 class="text-lg font-semibold">{t('gyro.step_rest')}</h3>
			<div class="flex items-center justify-center gap-2 text-sm text-text-muted">
				<Spinner size="sm" />
				{t('gyro.step_rest_waiting')}
			</div>
		</div>

	{:else if step === 'tilt_ready'}
		<!-- Step 2: Tilt right — user confirms -->
		<div class="text-center space-y-3">
			<div class="text-xs text-green-500 font-medium">{t('gyro.step_rest_done')}</div>
			<div class="w-16 h-16 mx-auto rounded-full bg-primary/20 flex items-center justify-center">
				<svg class="w-10 h-10 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="3" y="10" width="18" height="8" rx="1" transform="rotate(25 12 14)"/>
					<path d="M17 8l3 3-3 3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
				</svg>
			</div>
			<h3 class="text-lg font-semibold">{t('gyro.step_tilt')}</h3>
			<p class="text-xs text-text-muted">{t('gyro.step_tilt_hint')}</p>
		</div>
		<button onclick={measureTilt} class="w-full px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
			{t('gyro.step_tilt_confirm')}
		</button>
		<button onclick={cancel} class="w-full px-4 py-2.5 text-text-muted text-sm">
			{t('gyro.cancel')}
		</button>

	{:else if step === 'tilt_measuring'}
		<div class="text-center space-y-3">
			<div class="w-16 h-16 mx-auto rounded-full bg-primary/20 flex items-center justify-center animate-pulse">
				<svg class="w-10 h-10 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="3" y="10" width="18" height="8" rx="1" transform="rotate(25 12 14)"/>
					<path d="M17 8l3 3-3 3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
				</svg>
			</div>
			<h3 class="text-lg font-semibold">{t('gyro.step_tilt')}</h3>
			<div class="flex items-center justify-center gap-2 text-sm text-text-muted">
				<Spinner size="sm" />
				{t('gyro.step_tilt_waiting')}
			</div>
		</div>

	{:else if step === 'saving'}
		<div class="flex flex-col items-center gap-3 py-8">
			<Spinner />
			<p class="text-sm text-text-muted">{t('gyro.saving')}</p>
		</div>

	{:else if step === 'test'}
		<div class="text-center space-y-3">
			<div class="text-xs text-green-500 font-medium">{t('gyro.step_tilt_done')}</div>
			<h3 class="text-lg font-semibold">{t('gyro.step_test')}</h3>

			<!-- Live gesture indicator -->
			<div class="h-12 flex items-center justify-center">
				{#if testGesture}
					<div class="px-4 py-2 bg-primary/20 text-primary rounded-full text-sm font-medium animate-pulse">
						{testGesture}
					</div>
				{:else}
					<div class="text-text-muted/40 text-sm">—</div>
				{/if}
			</div>

			<!-- Gesture legend -->
			<div class="text-xs text-text-muted space-y-1 text-left bg-surface-light rounded-lg p-3">
				<div>{t('gyro.test_tilt_left')}</div>
				<div>{t('gyro.test_tilt_right')}</div>
				<div>{t('gyro.test_tilt_forward')}</div>
				<div>{t('gyro.test_tilt_back')}</div>
				<div>{t('gyro.test_shake')}</div>
			</div>
		</div>

		<button onclick={finish} class="w-full px-4 py-2.5 bg-accent hover:bg-accent/80 text-white rounded-lg text-sm font-medium transition-colors">
			{t('gyro.save_ok')}
		</button>
		<button
			onclick={toggleFlip}
			class="w-full flex items-center justify-between px-4 py-2.5 bg-surface hover:bg-surface-lighter rounded-lg text-sm transition-colors"
		>
			<span class="text-text-muted">{t('gyro.flip_forward')}</span>
			<div class="w-10 h-6 rounded-full transition-colors {flipped ? 'bg-primary' : 'bg-surface-lighter'} relative">
				<div class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform {flipped ? 'translate-x-4' : 'translate-x-0.5'}"></div>
			</div>
		</button>
		<button onclick={retry} class="w-full px-4 py-2.5 text-text-muted text-sm">
			{t('gyro.retry')}
		</button>
	{/if}
</div>
