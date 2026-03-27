/**
 * Lightweight i18n module.
 * German is default and embedded. English prepared as secondary.
 */

import de from './de.js';
import en from './en.js';

type Messages = Record<string, string>;
type Locale = 'de' | 'en';

const locales: Record<Locale, Messages> = { de, en };

let currentLocale: Locale = 'de';

export function setLocale(locale: Locale): void {
	if (locale in locales) {
		currentLocale = locale;
	}
}

export function getLocale(): Locale {
	return currentLocale;
}

/**
 * Translate a key. Returns the key itself if not found.
 * Supports simple placeholder replacement: t('hello', { name: 'World' }) → "Hallo World"
 */
export function t(key: string, params?: Record<string, string | number>): string {
	let text = locales[currentLocale]?.[key] ?? locales.de[key] ?? key;
	if (params) {
		for (const [k, v] of Object.entries(params)) {
			text = text.replaceAll(`{${k}}`, String(v));
		}
	}
	return text;
}
