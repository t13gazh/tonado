/**
 * Lightweight i18n module with language switching support.
 * German is default and always complete. Other languages fall back to German.
 * Community can add translations — see docs/TRANSLATIONS.md.
 */

import de from './de.js';
import en from './en.js';

type Messages = Record<string, string>;

export interface Language {
	code: string;
	name: string;
	native: string;
	complete: boolean;
}

// Built-in languages
const builtinLanguages: Record<string, Messages> = { de, en };

// Runtime-registered languages (community translations)
const customLanguages: Record<string, Messages> = {};

// All available language metadata
const languageRegistry: Language[] = [
	{ code: 'de', name: 'German', native: 'Deutsch', complete: true },
	{ code: 'en', name: 'English', native: 'English', complete: false },
];

// TODO: Make reactive with $state when migrating to .svelte.ts
// Currently language changes require a page reload to take effect.
let currentLang = (typeof localStorage !== 'undefined'
	? localStorage.getItem('tonado-lang')
	: null) || 'de';

function getMessages(code: string): Messages | undefined {
	return builtinLanguages[code] ?? customLanguages[code];
}

/**
 * Set the active language. Persists to localStorage.
 */
export function setLanguage(code: string): void {
	if (getMessages(code)) {
		currentLang = code;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('tonado-lang', code);
		}
	}
}

/**
 * Get the current language code.
 */
export function getLanguage(): string {
	return currentLang;
}

/**
 * Get all available languages with metadata.
 */
export function getLanguages(): Language[] {
	return [...languageRegistry];
}

/**
 * Register a community translation at runtime.
 * This allows dynamic language loading without rebuilding.
 */
export function registerLanguage(code: string, name: string, native: string, messages: Messages): void {
	customLanguages[code] = messages;
	const existing = languageRegistry.find(l => l.code === code);
	if (existing) {
		existing.native = native;
		existing.complete = getCompleteness(code) >= 95;
	} else {
		languageRegistry.push({
			code,
			name,
			native,
			complete: getCompleteness(code) >= 95,
		});
	}
}

/**
 * Get translation completeness for a language (0-100).
 * Compared against German (the reference).
 */
export function getCompleteness(code: string): number {
	if (code === 'de') return 100;
	const messages = getMessages(code);
	if (!messages) return 0;
	const deKeys = Object.keys(de);
	if (deKeys.length === 0) return 100;
	const translated = deKeys.filter(k => k in messages).length;
	return Math.round((translated / deKeys.length) * 100);
}

/**
 * Translate a key. Falls back: current language → German → key itself.
 * Supports placeholder replacement: t('hello', { name: 'World' }) → "Hallo World"
 */
export function t(key: string, params?: Record<string, string | number>): string {
	const messages = getMessages(currentLang);
	let text = messages?.[key] ?? de[key] ?? key;
	if (params) {
		for (const [k, v] of Object.entries(params)) {
			text = text.replaceAll(`{${k}}`, String(v));
		}
	}
	return text;
}

// Backward compatibility
export const setLocale = setLanguage;
export const getLocale = getLanguage;
