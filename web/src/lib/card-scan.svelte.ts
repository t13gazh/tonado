/**
 * Shared card scan logic used by both the card wizard and setup wizard.
 * Encapsulates scanning state, auto-retry, and save functionality.
 */
import { cards, type ContentType } from '$lib/api';
import { t } from '$lib/i18n';

export function createCardScan() {
	let scanning = $state(false);
	let scannedCardId = $state('');
	let hasExisting = $state(false);
	let cardName = $state('');
	let contentType = $state<ContentType>('folder');
	let contentPath = $state('');
	let error = $state('');
	let autoRetryCountdown = $state(0);
	let autoRetryTimer = $state<ReturnType<typeof setInterval> | null>(null);
	let abortController = $state<AbortController | null>(null);
	let scanComplete = $state(false);
	let saveComplete = $state(false);

	function cancelAutoRetry() {
		if (autoRetryTimer) { clearInterval(autoRetryTimer); autoRetryTimer = null; }
		autoRetryCountdown = 0;
	}

	function startAutoRetry(onRetry: () => void) {
		cancelAutoRetry();
		autoRetryCountdown = 3;
		autoRetryTimer = setInterval(() => {
			autoRetryCountdown -= 1;
			if (autoRetryCountdown <= 0) {
				cancelAutoRetry();
				error = '';
				onRetry();
			}
		}, 1000);
	}

	async function startScan(newOnly = false) {
		if (abortController) abortController.abort();
		abortController = new AbortController();
		scanning = true;
		scanComplete = false;
		error = '';
		try {
			const result = await cards.waitForScan(30, newOnly);
			if (abortController?.signal.aborted) return;
			if (result.scanned && result.card_id) {
				scannedCardId = result.card_id;
				hasExisting = result.has_mapping ?? false;
				if (result.mapping) {
					cardName = result.mapping.name;
					contentType = result.mapping.content_type as ContentType;
					contentPath = result.mapping.content_path;
				} else {
					cardName = '';
					contentPath = '';
					contentType = 'folder';
				}
				scanComplete = true;
			} else {
				// No card detected, retry (unless aborted)
				if (!abortController?.signal.aborted) startScan(newOnly);
				return;
			}
		} catch {
			if (abortController?.signal.aborted) return;
			error = t('error.scan_timeout');
			scanning = false;
			startAutoRetry(() => startScan(newOnly));
		}
	}

	function handleTypeChange(type: ContentType) {
		contentType = type;
		contentPath = '';
		cardName = '';
	}

	function handleSelect(path: string, autoName: string) {
		contentPath = path;
		cardName = autoName;
	}

	async function saveCard() {
		if (!cardName.trim() || !contentPath.trim()) return;
		error = '';
		try {
			const data = {
				card_id: scannedCardId,
				name: cardName.trim(),
				content_type: contentType as string,
				content_path: contentPath.trim(),
			};
			if (hasExisting) {
				await cards.update(scannedCardId, data);
			} else {
				await cards.create(data);
			}
			saveComplete = true;
		} catch {
			error = t('error.save_failed');
		}
	}

	function canSave(): boolean {
		return !!(cardName.trim() && contentPath.trim());
	}

	function reset() {
		if (abortController) { abortController.abort(); abortController = null; }
		cancelAutoRetry();
		scanning = false;
		scannedCardId = '';
		cardName = '';
		contentPath = '';
		contentType = 'folder';
		hasExisting = false;
		scanComplete = false;
		saveComplete = false;
		error = '';
	}

	function clearError() {
		error = '';
	}

	return {
		get scanning() { return scanning; },
		get scannedCardId() { return scannedCardId; },
		get hasExisting() { return hasExisting; },
		get cardName() { return cardName; },
		set cardName(v: string) { cardName = v; },
		get contentType() { return contentType; },
		set contentType(v: ContentType) { contentType = v; },
		get contentPath() { return contentPath; },
		set contentPath(v: string) { contentPath = v; },
		get error() { return error; },
		set error(v: string) { error = v; },
		get autoRetryCountdown() { return autoRetryCountdown; },
		get scanComplete() { return scanComplete; },
		get saveComplete() { return saveComplete; },
		startScan,
		cancelAutoRetry,
		handleTypeChange,
		handleSelect,
		saveCard,
		canSave,
		reset,
		clearError,
	};
}
