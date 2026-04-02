/**
 * Shared button scan logic for the setup wizard.
 * Encapsulates scanning state machine, sequential button detection,
 * and test mode functionality.
 */
import { buttonsApi, type ButtonAction, type ButtonConfigItem, type ButtonTestEvent } from '$lib/api';
import { t } from '$lib/i18n';

export interface ButtonAssignment {
	action: ButtonAction;
	label: string;
	gpio: number | null;
	required: boolean;
	selected: boolean;
	skipped: boolean;
}

export type ButtonScanPhase = 'idle' | 'select' | 'scanning' | 'testing' | 'done';

const DEFAULT_BUTTONS: ButtonAssignment[] = [
	{ action: 'volume_up', label: 'buttons.volume_up', gpio: null, required: false, selected: true, skipped: false },
	{ action: 'volume_down', label: 'buttons.volume_down', gpio: null, required: false, selected: true, skipped: false },
	{ action: 'play_pause', label: 'buttons.play_pause', gpio: null, required: false, selected: false, skipped: false },
	{ action: 'next_track', label: 'buttons.next_track', gpio: null, required: false, selected: false, skipped: false },
	{ action: 'previous_track', label: 'buttons.previous_track', gpio: null, required: false, selected: false, skipped: false },
];

export function createButtonScan() {
	let phase = $state<ButtonScanPhase>('idle');
	let buttons = $state<ButtonAssignment[]>(structuredClone(DEFAULT_BUTTONS));
	let currentIndex = $state(0);
	let error = $state('');
	let saving = $state(false);
	let testEvents = $state<ButtonTestEvent[]>([]);
	let testPollTimer = $state<ReturnType<typeof setInterval> | null>(null);
	let abortController = $state<AbortController | null>(null);
	let existingConfig = $state<ButtonConfigItem[]>([]);
	let dirty = $state(false);

	const selectedButtons = $derived(buttons.filter((b) => b.selected));
	const assignedButtons = $derived(buttons.filter((b) => b.gpio !== null));
	const currentButton = $derived(
		phase === 'scanning' && currentIndex < selectedButtons.length
			? selectedButtons[currentIndex]
			: null,
	);
	const scanProgress = $derived({ current: currentIndex, total: selectedButtons.length });
	const assignedCount = $derived(assignedButtons.length);
	const hasExistingConfig = $derived(existingConfig.length > 0);

	async function loadExisting(): Promise<void> {
		try {
			existingConfig = await buttonsApi.getConfig();
		} catch {
			existingConfig = [];
		}
		dirty = false;
	}

	function toggleButton(action: ButtonAction) {
		const btn = buttons.find((b) => b.action === action);
		if (btn && !btn.required) {
			btn.selected = !btn.selected;
		}
	}

	function startSelect() {
		phase = 'select';
		error = '';
	}

	async function startScan() {
		if (selectedButtons.length === 0) return;
		phase = 'scanning';
		currentIndex = 0;
		error = '';
		dirty = true;
		// Reset all assignments
		for (const btn of buttons) {
			btn.gpio = null;
			btn.skipped = false;
		}
		await scanNextButton();
	}

	async function scanNextButton() {
		if (currentIndex >= selectedButtons.length) {
			phase = 'done';
			return;
		}

		if (abortController) abortController.abort();
		abortController = new AbortController();
		error = '';

		try {
			await buttonsApi.scanStart();
			const timeout = selectedButtons[currentIndex].required ? 30 : 15;
			const result = await buttonsApi.scanResult(timeout);

			if (abortController?.signal.aborted) return;

			if (result.detected && result.gpio !== null) {
				// Find the actual button in the main array and assign
				const action = selectedButtons[currentIndex].action;
				const btn = buttons.find((b) => b.action === action);
				if (btn) btn.gpio = result.gpio;
				currentIndex++;
				await scanNextButton();
			} else {
				// Timeout — skip optional, error for required
				const btn = selectedButtons[currentIndex];
				if (!btn.required) {
					const mainBtn = buttons.find((b) => b.action === btn.action);
					if (mainBtn) mainBtn.skipped = true;
					currentIndex++;
					await scanNextButton();
				} else {
					error = t('buttons.scan_timeout');
				}
			}
		} catch {
			if (abortController?.signal.aborted) return;
			error = t('buttons.scan_error');
		}
	}

	function skipCurrentButton() {
		if (!currentButton || currentButton.required) return;
		const mainBtn = buttons.find((b) => b.action === currentButton.action);
		if (mainBtn) mainBtn.skipped = true;
		if (abortController) abortController.abort();
		currentIndex++;
		scanNextButton();
	}

	async function retryScan() {
		error = '';
		await scanNextButton();
	}

	async function startTest() {
		phase = 'testing';
		testEvents = [];
		error = '';
		try {
			// Send assigned buttons so backend can start a temporary listener
			const assigned = buttons
				.filter((b) => b.gpio !== null)
				.map((b) => ({ action: b.action, gpio: b.gpio! }));
			await buttonsApi.testStart(assigned.length > 0 ? assigned : undefined);
			// Poll for test events every 500ms
			testPollTimer = setInterval(async () => {
				try {
					const events = await buttonsApi.testEvents();
					if (events.length > 0) {
						testEvents = [...testEvents, ...events].slice(-20); // Keep last 20
					}
				} catch { /* ignore poll errors */ }
			}, 500);
		} catch {
			error = t('buttons.test_error');
			phase = 'done';
		}
	}

	async function stopTest() {
		if (testPollTimer) {
			clearInterval(testPollTimer);
			testPollTimer = null;
		}
		try { await buttonsApi.testStop(); } catch { /* ignore */ }
		phase = 'done';
	}

	async function save(): Promise<boolean> {
		saving = true;
		error = '';
		try {
			const config: ButtonConfigItem[] = assignedButtons.map((b) => ({
				action: b.action,
				gpio: b.gpio!,
			}));
			await buttonsApi.saveConfig(config);
			saving = false;
			return true;
		} catch {
			error = t('error.save_failed');
			saving = false;
			return false;
		}
	}

	function reset() {
		if (abortController) { abortController.abort(); abortController = null; }
		if (testPollTimer) { clearInterval(testPollTimer); testPollTimer = null; }
		try { buttonsApi.scanStop(); } catch { /* ignore */ }
		phase = 'idle';
		buttons = structuredClone(DEFAULT_BUTTONS);
		currentIndex = 0;
		error = '';
		saving = false;
		testEvents = [];
	}

	return {
		get phase() { return phase; },
		get buttons() { return buttons; },
		get selectedButtons() { return selectedButtons; },
		get currentButton() { return currentButton; },
		get scanProgress() { return scanProgress; },
		get assignedCount() { return assignedCount; },
		get assignedButtons() { return assignedButtons; },
		get error() { return error; },
		set error(v: string) { error = v; },
		get saving() { return saving; },
		get testEvents() { return testEvents; },
		get hasExistingConfig() { return hasExistingConfig; },
		get existingConfig() { return existingConfig; },
		get dirty() { return dirty; },
		loadExisting,
		toggleButton,
		startSelect,
		startScan,
		skipCurrentButton,
		retryScan,
		startTest,
		stopTest,
		save,
		reset,
	};
}
