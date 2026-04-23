<script lang="ts" module>
	/**
	 * Exported so the parent wizard can branch on CompleteStep's internal state.
	 * `intro`    → informed-consent screen, waits for primary button click
	 * `testing`  → verifying WiFi credentials against Lane B
	 * `failed`   → test failed, user may retry or go back to WiFi step
	 * `switching`→ WiFi OK, waiting for the phone to reach the box on the new net
	 * `timeout`  → 5 min of polling without the phone finding the box
	 * `done`     → box was reached (before the auto-redirect fires)
	 */
	export type CompleteStepStatus = 'intro' | 'testing' | 'failed' | 'switching' | 'timeout' | 'done';
</script>

<script lang="ts">
	import { t } from '$lib/i18n';
	import { setupApi, type HardwareDetection, type SystemInfoData, type WifiStatus } from '$lib/api';
	import Icon from '$lib/components/Icon.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import InlineError from '$lib/components/InlineError.svelte';
	import QRCode from '$lib/components/setup/QRCode.svelte';

	/** Shape of the test-wifi result Lane B produces. Re-declared here so the
	 *  parent can stash it in +page.svelte without pulling the whole setupApi
	 *  namespace. Mirror of `setupApi.testWifi`'s return type. */
	export interface WifiProbeResult {
		ok: boolean;
		error: string | null;
		ip: string | null;
		/** One-shot token that the backend expects back on /setup/confirm-complete.
		 *  May be absent in older backends — we tolerate that. */
		token?: string | null;
	}

	interface Props {
		hardware: HardwareDetection | null;
		sysInfo: SystemInfoData | null;
		wifiStatus: WifiStatus | null;
		buttonCount: number;
		buttonLabels: string[];
		error: string;
		/** Credentials captured by WifiStep — needed for the final test-wifi call.
		 *  If unavailable, CompleteStep tests with password='' (Lane B may still
		 *  validate against cached credentials). */
		wifiSsid?: string;
		wifiPassword?: string;
		/** If WifiStep already probed the home WiFi via the same internal helper
		 *  Lane B uses for /setup/test-wifi, the parent can pass the result here
		 *  so CompleteStep skips re-testing and jumps straight to switching. */
		wifiProbeResult?: WifiProbeResult | null;
		/** Called when the user wants to go back to the WiFi step after a
		 *  failed test or a polling timeout. */
		onBackToWifi?: () => void;
	}

	let {
		hardware,
		sysInfo,
		wifiStatus,
		buttonCount = 0,
		buttonLabels = [],
		error,
		wifiSsid = '',
		wifiPassword = '',
		wifiProbeResult = null,
		onBackToWifi,
	}: Props = $props();

	// ─── State machine ─────────────────────────────────────────────────────
	// Intro is the default: the user must click "Jetzt einrichten" before we
	// start the WiFi test. This prevents the "auto-nav + spinner" surprise.
	let status = $state<CompleteStepStatus>('intro');
	let testError = $state<string>('');
	let testedIp = $state<string>('');
	/** Token handed over by Lane B from /setup/test-wifi; forwarded to
	 *  /setup/confirm-complete. Falsy = no token available. */
	let confirmToken = $state<string | null>(null);

	/** Progress-message bucket while polling: 0=<30s, 30=30–60s, 60=60–90s, 90=>=90s. */
	let progressStage = $state<0 | 30 | 60 | 90>(0);

	/** iOS detection for the Safari/mDNS hint. One-shot on first paint. */
	const isIos = typeof navigator !== 'undefined'
		&& /iPad|iPhone|iPod/.test(navigator.userAgent)
		&& !(window as { MSStream?: unknown }).MSStream;

	/** Shown briefly before `window.location.href` fires so the user sees a
	 *  success blip instead of a hard redirect. */
	let showSuccessToast = $state(false);

	// ─── Derived addresses ─────────────────────────────────────────────────
	// Hostname resolution: prefer sysInfo.hostname, fall back to 'tonado'.
	// `.local` suffix is appended here — sysInfo returns the bare hostname.
	const hostnameBase = $derived(
		(sysInfo?.hostname && sysInfo.hostname.trim() && sysInfo.hostname !== 'unknown')
			? sysInfo.hostname.trim()
			: 'tonado'
	);
	const hostnameFull = $derived(`${hostnameBase}.local`);
	const hostnameUrl = $derived(`http://${hostnameFull}/`);

	// IP comes either from the test result or from the pre-existing WiFi status.
	const ipAddress = $derived(testedIp || wifiStatus?.ip_address || '');
	const ipUrl = $derived(ipAddress ? `http://${ipAddress}/` : '');

	// QR primary payload: mDNS URL (iOS native, Android 12+). IP is fallback text.
	const qrValue = $derived(hostnameUrl);

	const wifiName = $derived(wifiSsid || wifiStatus?.ssid || '');

	// ─── Error mapping (Backend → User text) ───────────────────────────────
	/**
	 * Map Lane B's deutsche Error-Strings auf SSID-aware Texte.
	 * Lane B liefert bereits Klartext; wir verfeinern nur, wenn wir die SSID
	 * einblenden können. Bei Unbekanntem wird der Originalfehler 1:1 gezeigt.
	 */
	function mapBackendError(raw: string | null | undefined, ssid: string): string {
		if (!raw) return '';
		const lower = raw.toLowerCase();
		if (ssid) {
			if (lower.includes('passwort') || lower.includes('password') || lower.includes('auth')) {
				return t('setup.wrong_password_with_ssid', { ssid });
			}
			if (lower.includes('nicht gefunden') || lower.includes('not found') || lower.includes('ssid')) {
				return t('setup.ssid_not_found_with_ssid', { ssid });
			}
		}
		if (lower.includes('timeout') || lower.includes('zeit')) {
			return t('setup.complete_test_timeout_error');
		}
		return raw;
	}

	// ─── Intro → testing (informed-consent flow) ──────────────────────────
	async function startTest() {
		// If WifiStep already produced a probe result, skip the round-trip and
		// jump straight to switching. This avoids double-testing and — more
		// importantly — avoids tearing down the AP twice.
		if (wifiProbeResult) {
			if (wifiProbeResult.ok) {
				if (wifiProbeResult.ip) testedIp = wifiProbeResult.ip;
				if (wifiProbeResult.token) confirmToken = wifiProbeResult.token;
				status = 'switching';
				startPolling();
				return;
			}
			// Cached probe failed → surface the error but still allow retry.
			testError = mapBackendError(wifiProbeResult.error, wifiSsid || wifiStatus?.ssid || '');
			status = 'failed';
			return;
		}
		await runWifiTest();
	}

	async function runWifiTest() {
		testError = '';
		status = 'testing';

		const ssid = wifiSsid || wifiStatus?.ssid || '';
		if (!ssid) {
			// No credentials at all → skip to switching; Lane B's confirm-complete
			// will still happen when the client reaches the box on new IP.
			status = 'switching';
			startPolling();
			return;
		}

		// Client-side hard timeout 25s (matches backend 20s + 5s buffer).
		const TEST_TIMEOUT_MS = 25_000;
		const timeoutPromise = new Promise<WifiProbeResult>((_, reject) =>
			setTimeout(() => reject(new Error('__client_timeout__')), TEST_TIMEOUT_MS)
		);

		try {
			const result = await Promise.race([
				setupApi.testWifi(ssid, wifiPassword, TEST_TIMEOUT_MS) as Promise<WifiProbeResult>,
				timeoutPromise,
			]);
			if (result.ok) {
				if (result.ip) testedIp = result.ip;
				if (result.token) confirmToken = result.token;
				status = 'switching';
				startPolling();
			} else {
				testError = mapBackendError(result.error, ssid) || t('setup.wifi_error');
				status = 'failed';
			}
		} catch (e) {
			if (e instanceof Error && e.message === '__client_timeout__') {
				testError = t('setup.complete_test_timeout_error');
			} else {
				testError = e instanceof Error ? e.message : t('setup.wifi_error');
			}
			status = 'failed';
		}
	}

	// ─── Polling: wait for the box on the new network ──────────────────────
	const POLL_INTERVAL_MS = 2_000;
	const PROGRESS_30_MS = 30_000;
	const PROGRESS_60_MS = 60_000;
	const PROGRESS_90_MS = 90_000;
	const POLL_TIMEOUT_MS = 300_000; // 5 min — hard stop
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let progressTimers: ReturnType<typeof setTimeout>[] = [];
	let hardTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
	let redirecting = false;

	function startPolling() {
		if (pollTimer) return;
		progressStage = 0;
		// Staggered progress hints.
		progressTimers = [
			setTimeout(() => { progressStage = 30; }, PROGRESS_30_MS),
			setTimeout(() => { progressStage = 60; }, PROGRESS_60_MS),
			setTimeout(() => { progressStage = 90; }, PROGRESS_90_MS),
		];
		// Hard stop after POLL_TIMEOUT_MS → timeout state (QR-first fallback UI).
		hardTimeoutTimer = setTimeout(() => {
			if (status === 'switching') {
				stopPolling();
				status = 'timeout';
			}
		}, POLL_TIMEOUT_MS);

		pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
		// Fire first poll immediately so the happy path is instantaneous on
		// same-network testing (dev).
		void pollOnce();
	}

	function stopPolling() {
		if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
		progressTimers.forEach((tm) => clearTimeout(tm));
		progressTimers = [];
		if (hardTimeoutTimer) { clearTimeout(hardTimeoutTimer); hardTimeoutTimer = null; }
	}

	function retryPolling() {
		// Reset state and poll again. User-initiated from timeout screen.
		status = 'switching';
		startPolling();
	}

	/**
	 * Probe both addresses in parallel with short per-request timeouts.
	 * First successful response wins; we then ask the box to finalise setup
	 * and redirect the browser to the canonical hostname URL.
	 *
	 * NB: Cross-origin fetches to `http://tonado.local/api/health` will be
	 * blocked by the browser when the page itself is served from a different
	 * origin (e.g. captive portal IP). We use `mode: 'no-cors'` so an
	 * *opaque* success still counts — we don't need the body, only "reached".
	 */
	async function pollOnce() {
		if (redirecting) return;
		const candidates: string[] = [];
		if (hostnameUrl) candidates.push(`${hostnameUrl}api/health`);
		if (ipUrl) candidates.push(`${ipUrl}api/health`);
		if (candidates.length === 0) return;

		const attempts = candidates.map((url) => probe(url).then((ok) => (ok ? url : null)));
		const reached = (await Promise.all(attempts)).find((u) => u);
		if (reached) {
			await handleReached(reached);
		}
	}

	async function probe(url: string): Promise<boolean> {
		try {
			const ctrl = new AbortController();
			const to = setTimeout(() => ctrl.abort(), 1_500);
			const res = await fetch(url, {
				method: 'GET',
				mode: 'no-cors',
				cache: 'no-store',
				signal: ctrl.signal,
			});
			clearTimeout(to);
			// `no-cors` → opaque response, `res.ok` is false but `res.type === 'opaque'`
			// counts as "reachable". Same-origin responses come back with `ok=true`.
			return res.ok || res.type === 'opaque';
		} catch {
			return false;
		}
	}

	async function handleReached(reachedBaseHealthUrl: string) {
		if (redirecting) return;
		redirecting = true;
		stopPolling();
		status = 'done';

		// Determine base (strip /api/health).
		const base = reachedBaseHealthUrl.replace(/api\/health$/, '');

		// Fire-and-forget the confirm-complete. We can't read the response body
		// under `no-cors`, but that's fine — Lane B writes .setup-complete either
		// way. 409 is treated as success (already complete).
		//
		// Lane B's token (if any) is appended as query param AND body field so
		// either transport works until the contract is fully locked in.
		// TODO: drop whichever variant Lane B does not honour once finalised.
		try {
			const qs = confirmToken ? `?token=${encodeURIComponent(confirmToken)}` : '';
			await fetch(`${base}api/setup/confirm-complete${qs}`, {
				method: 'POST',
				mode: 'no-cors',
				cache: 'no-store',
				headers: confirmToken ? { 'Content-Type': 'application/json' } : undefined,
				body: confirmToken ? JSON.stringify({ token: confirmToken }) : undefined,
			});
		} catch {
			/* ignore — redirect will still work */
		}

		// Small success toast before the hard redirect. 1.5s is enough to register
		// but short enough not to drag. A screen-reader-friendly role="status" is
		// attached to the toast in the template.
		showSuccessToast = true;

		// Prefer the mDNS URL for the final redirect so the user lands on a
		// stable, shareable address (the DHCP IP may change).
		const target = hostnameUrl && reachedBaseHealthUrl.includes(hostnameBase) ? hostnameUrl : base;

		setTimeout(() => {
			window.location.href = target;
		}, 1_500);
	}

	// Cleanup on unmount.
	$effect(() => {
		return () => { stopPolling(); };
	});

	// Combine an external error from the page with our internal testError.
	const displayError = $derived(testError || error);

	// Derived UI helpers
	const progressHint = $derived.by(() => {
		if (status !== 'switching') return '';
		if (progressStage === 30) return t('setup.complete_progress_30');
		if (progressStage === 60) return t('setup.complete_progress_60');
		if (progressStage === 90) return t('setup.complete_progress_90', { ssid: wifiName || '' });
		return '';
	});
</script>

<!-- Polite live region for state transitions — screen readers will read the
     title automatically; the focus is never moved programmatically so sighted
     users are not disoriented either. -->
<div class="flex flex-col items-center gap-6 text-center" role="status" aria-live="polite">
	{#if status === 'intro'}
		<!-- State 0: informed-consent intro — no auto-start, no spinner. -->
		<div class="w-20 h-20 rounded-full bg-primary/15 flex items-center justify-center">
			<Icon name="check" size={40} class="text-primary" strokeWidth={2.5} />
		</div>
		<div>
			<h2 class="text-xl font-bold text-text mb-2">{t('setup.complete_intro_title')}</h2>
			<p class="text-sm text-text-muted max-w-xs mx-auto">{t('setup.complete_intro_body')}</p>
		</div>
		<button
			type="button"
			onclick={startTest}
			class="w-full max-w-xs py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors min-h-11 focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
		>
			{t('setup.complete_intro_start')}
		</button>

	{:else if status === 'testing'}
		<!-- State 1: testing WiFi credentials -->
		<div class="w-20 h-20 rounded-full bg-primary/15 flex items-center justify-center">
			<Spinner size="lg" />
		</div>
		<h2 class="text-xl font-bold text-text">{t('setup.complete_testing')}</h2>
		{#if wifiName}
			<p class="text-sm text-text-muted">&bdquo;{wifiName}&ldquo;</p>
		{/if}

	{:else if status === 'failed'}
		<!-- State 2: test failed — retry or back to WiFi step -->
		<div class="w-20 h-20 rounded-full bg-red-500/15 flex items-center justify-center">
			<Icon name="alert-triangle" size={40} class="text-red-400" strokeWidth={2} />
		</div>
		<div>
			<h2 class="text-xl font-bold text-text mb-2">{t('setup.complete_test_failed_title')}</h2>
			<!-- If mapBackendError produced SSID-aware text, testError already
			     contains it. Fall back to the generic body only if no error at all. -->
			<p class="text-sm text-text-muted max-w-xs mx-auto">
				{testError ? testError : t('setup.complete_test_failed_body')}
			</p>
		</div>
		<div class="w-full max-w-xs flex flex-col gap-2">
			<button
				type="button"
				onclick={runWifiTest}
				class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors min-h-11 focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
			>
				{t('setup.complete_retry')}
			</button>
			{#if onBackToWifi}
				<button
					type="button"
					onclick={onBackToWifi}
					class="w-full py-3 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors min-h-11 focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
				>
					{t('setup.complete_back_to_wifi')}
				</button>
			{/if}
		</div>

	{:else if status === 'timeout'}
		<!-- State 4: polling exhausted — QR-first fallback. -->
		<div class="w-16 h-16 rounded-full bg-amber-500/15 flex items-center justify-center">
			<Icon name="alert-triangle" size={32} class="text-amber-400" strokeWidth={2} />
		</div>
		<div>
			<h2 class="text-xl font-bold text-text mb-2">{t('setup.complete_timeout_title')}</h2>
			<p class="text-sm text-text-muted max-w-xs mx-auto">{t('setup.complete_timeout_body')}</p>
		</div>

		<!-- Prominent QR — the recovery path. -->
		<QRCode
			value={qrValue}
			size={220}
			level="Q"
			ariaLabel={t('setup.complete_qr_label')}
			fallbackLabel={hostnameFull}
		/>
		<div class="text-xs text-text-muted">
			<span>{t('setup.complete_address')}:</span>
			<span class="text-primary font-medium">{hostnameFull}</span>
		</div>

		<div class="w-full max-w-xs flex flex-col gap-2">
			<button
				type="button"
				onclick={retryPolling}
				class="w-full py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors min-h-11 focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
			>
				{t('setup.complete_timeout_retry')}
			</button>
			{#if onBackToWifi}
				<button
					type="button"
					onclick={onBackToWifi}
					class="w-full py-3 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors min-h-11 focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
				>
					{t('setup.complete_back_to_wifi')}
				</button>
			{/if}
		</div>

	{:else}
		<!-- State 3 + 5: switching / done — ready screen with big box name. -->
		<div class="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center">
			<Icon name="check" size={32} class="text-green-500" strokeWidth={2.5} />
		</div>

		<!-- Emotional headline: "Fertig!" big, box name even bigger & accent-coloured. -->
		<div class="flex flex-col items-center gap-1">
			<h2 class="text-2xl font-bold text-text">{t('setup.complete_done_heading')}</h2>
			<p class="text-sm text-text-muted">{t('setup.complete_box_name_label')}</p>
			<p class="text-3xl font-extrabold text-primary tracking-tight">{hostnameBase}</p>
		</div>

		<!-- .local explainer — demystifies the address for non-technical parents. -->
		<p class="text-xs text-text-muted max-w-sm">
			{t('setup.complete_local_explainer', { hostname: hostnameBase })}
		</p>

		<!-- Numbered WLAN-switch instructions. -->
		{#if wifiName}
			<ol class="w-full max-w-sm bg-surface-light rounded-xl p-4 text-left space-y-2 text-sm text-text">
				<li class="flex gap-3">
					<span class="shrink-0 w-6 h-6 rounded-full bg-primary/20 text-primary font-semibold text-xs flex items-center justify-center">1</span>
					<span>{t('setup.complete_switch_step1')}</span>
				</li>
				<li class="flex gap-3">
					<span class="shrink-0 w-6 h-6 rounded-full bg-primary/20 text-primary font-semibold text-xs flex items-center justify-center">2</span>
					<span>{t('setup.complete_switch_step2', { ssid: wifiName })}</span>
				</li>
				<li class="flex gap-3">
					<span class="shrink-0 w-6 h-6 rounded-full bg-primary/20 text-primary font-semibold text-xs flex items-center justify-center">3</span>
					<span>{t('setup.complete_switch_step3')}</span>
				</li>
			</ol>

			<!-- iOS-only deep link to WiFi settings. Harmless on Android (ignored). -->
			<a
				href="App-prefs:root=WIFI"
				class="inline-flex items-center justify-center gap-2 py-2.5 px-4 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors min-h-11"
			>
				<Icon name="wifi" size={16} />
				{t('setup.complete_wifi_settings_button')}
			</a>
		{:else}
			<p class="text-sm text-text-muted max-w-xs">{t('setup.complete_switch_generic')}</p>
		{/if}

		<!-- QR code (enlarged, higher error correction). -->
		<div class="flex flex-col items-center gap-3">
			<QRCode
				value={qrValue}
				size={200}
				level="Q"
				ariaLabel={t('setup.complete_qr_label')}
				fallbackLabel={hostnameFull}
			/>
			<div class="text-xs text-text-muted space-y-0.5">
				<div>
					<span class="text-text-muted">{t('setup.complete_address')}:</span>
					<span class="text-primary font-medium">{hostnameFull}</span>
				</div>
				{#if ipAddress}
					<div>
						<span class="text-text-muted">{t('setup.complete_ip_fallback')}:</span>
						<span class="text-text">{ipAddress}</span>
					</div>
				{/if}
			</div>
			<p class="text-xs text-text-muted max-w-xs">{t('setup.complete_qr_hint')}</p>
		</div>

		<!-- iOS-specific Safari hint — shown early, not only after 2 min. -->
		{#if isIos}
			<div class="w-full max-w-sm bg-surface-light rounded-xl p-3 text-left">
				<div class="flex items-start gap-2">
					<Icon name="help-circle" size={16} class="text-primary mt-0.5 shrink-0" strokeWidth={2} />
					<p class="text-xs text-text-muted">{t('setup.complete_ios_safari_hint')}</p>
				</div>
			</div>
		{/if}

		<!-- Live polling indicator with staged progress hints. -->
		{#if status === 'switching'}
			<div class="flex flex-col items-center gap-2 text-xs text-text-muted max-w-xs">
				<div class="flex items-center gap-2">
					<Spinner size="sm" />
					<span>{t('setup.complete_searching')}</span>
				</div>
				{#if progressHint}
					<p class="text-xs text-text-muted italic">{progressHint}</p>
				{/if}
			</div>
		{/if}

		<!-- Success toast before redirect — pure aesthetic polish. -->
		{#if showSuccessToast}
			<div
				class="fixed inset-x-0 bottom-6 z-50 flex justify-center px-4 pointer-events-none"
				aria-live="polite"
			>
				<div class="flex items-center gap-2 bg-green-500 text-white px-4 py-2.5 rounded-full shadow-lg pointer-events-auto">
					<Icon name="check" size={18} strokeWidth={3} />
					<span class="text-sm font-medium">{t('setup.complete_success_toast')}</span>
				</div>
			</div>
		{/if}

		<!-- Hardware summary — collapsed by default to keep the finale emotional. -->
		<details class="w-full max-w-sm bg-surface-light rounded-xl">
			<summary class="cursor-pointer px-4 py-3 text-sm text-text-muted select-none list-none flex items-center justify-between">
				<span>{t('setup.complete_hardware_summary_toggle')}</span>
				<Icon name="chevron-down" size={16} />
			</summary>
			<div class="px-4 pb-3 space-y-2 text-sm text-left border-t border-surface-lighter pt-3">
				{#if hardware}
					{#if hardware.pi.model !== 'unknown'}
						<div class="flex justify-between">
							<span class="text-text-muted">{t('setup.pi_model')}</span>
							<span class="text-text">{hardware.pi.model}</span>
						</div>
					{/if}
					{#if hardware.audio.length > 0}
						<div class="flex justify-between">
							<span class="text-text-muted">{t('setup.audio_outputs')}</span>
							<span class="text-text">{hardware.audio.map(a => a.name).join(', ')}</span>
						</div>
					{/if}
					{#if hardware.rfid.reader !== 'none'}
						<div class="flex justify-between">
							<span class="text-text-muted">{t('setup.rfid_reader')}</span>
							<span class="text-text">{hardware.rfid.reader.toUpperCase()}</span>
						</div>
					{/if}
					{#if hardware.gyro_detected}
						<div class="flex justify-between">
							<span class="text-text-muted">{t('setup.gyro_sensor')}</span>
							<span class="text-text">{t('setup.detected')}</span>
						</div>
					{/if}
				{/if}
				{#if buttonCount > 0}
					<div class="flex justify-between">
						<span class="text-text-muted">{t('setup.step_buttons')}</span>
						<span class="text-text">{buttonLabels.join(', ')}</span>
					</div>
				{/if}
				{#if wifiStatus?.connected}
					<div class="flex justify-between">
						<span class="text-text-muted">{t('setup.step_wifi')}</span>
						<span class="text-text">&bdquo;{wifiStatus.ssid}&ldquo;</span>
					</div>
				{/if}
			</div>
		</details>
	{/if}

	{#if displayError && status !== 'failed' && status !== 'timeout'}
		<InlineError message={displayError} />
	{/if}
</div>
