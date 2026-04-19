/**
 * Troubleshooting help entries for the setup wizard.
 *
 * Content is bundled statically so it is available even when the box has
 * no network connection (e.g. during the WiFi step). Body-strings live in
 * the i18n files under the `help.*` namespace.
 *
 * Mini-markdown supported in body strings:
 *   - `**bold**`      — bold span
 *   - `\n\n`          — paragraph break (body is split into paragraphs)
 *   - `[text](url)`   — a single inline link per paragraph
 */

export interface HelpEntry {
	/** Stable key (used by callers to look up the entry) */
	key: string;
	/** i18n key for the dialog title */
	titleKey: string;
	/** List of i18n keys — each resolves to one body paragraph */
	bodyKeys: string[];
}

export const helpEntries: Record<string, HelpEntry> = {
	wifi_not_found: {
		key: 'wifi_not_found',
		titleKey: 'help.wifi_not_found.title',
		bodyKeys: [
			'help.wifi_not_found.body_1',
			'help.wifi_not_found.body_2',
			'help.wifi_not_found.body_3',
		],
	},
	figure_not_recognized: {
		key: 'figure_not_recognized',
		titleKey: 'help.figure_not_recognized.title',
		bodyKeys: [
			'help.figure_not_recognized.body_1',
			'help.figure_not_recognized.body_2',
			'help.figure_not_recognized.body_3',
		],
	},
	no_sound: {
		key: 'no_sound',
		titleKey: 'help.no_sound.title',
		bodyKeys: [
			'help.no_sound.body_1',
			'help.no_sound.body_2',
			'help.no_sound.body_3',
		],
	},
	app_not_finding_box: {
		key: 'app_not_finding_box',
		titleKey: 'help.app_not_finding_box.title',
		bodyKeys: [
			'help.app_not_finding_box.body_1',
			'help.app_not_finding_box.body_2',
			'help.app_not_finding_box.body_3',
		],
	},
	hardware_incomplete: {
		key: 'hardware_incomplete',
		titleKey: 'help.hardware_incomplete.title',
		bodyKeys: [
			'help.hardware_incomplete.body_1',
			'help.hardware_incomplete.body_2',
			'help.hardware_incomplete.body_3',
		],
	},
};

export function getHelpEntry(key: string): HelpEntry | null {
	return helpEntries[key] ?? null;
}
