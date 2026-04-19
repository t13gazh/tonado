// Shared search state for the library page.
//
// A single Runes-based store owns the freeform query so that the sticky
// SearchBar on the library page and every tab (FolderTab, RadioTab,
// PodcastTab, PlaylistTab) see the exact same value. All tabs derive their
// filtered list from `librarySearch.query`; the page derives tab-badge hit
// counts from the same source. There is no persistence — the query resets
// when the user navigates away and back to the library.
//
// Why Runes instead of a writable store: Svelte 5's `$state` in module scope
// produces a reactive singleton that participates in `$derived` / `$effect`
// chains without the ceremony of subscribe/unsubscribe. Consumers read
// `librarySearch.query` and write via `setQuery(...)` / `clear()`.

// State object is exported as a single reactive holder so consumers can do
// `$derived(librarySearch.query.toLowerCase())` without importing the setter.
class LibrarySearchStore {
	/** Current freeform query. Empty string means "no active search". */
	query = $state('');

	/** Replace the query with the given value. Trimming happens in consumers. */
	setQuery(next: string): void {
		this.query = next;
	}

	/** Reset to empty. Used by ESC handler and the clear button. */
	clear(): void {
		this.query = '';
	}
}

export const librarySearch = new LibrarySearchStore();

/**
 * Accent- and case-insensitive normalization helper. Used by every tab's
 * `$derived` filter so the matching rules stay identical across tabs.
 *
 * - Lowercase.
 * - Strip combining diacritics (ü → u, é → e).
 * - ß → ss (not a combining mark, handled explicitly).
 */
export function normalizeForSearch(s: string): string {
	return s
		.toLowerCase()
		.normalize('NFD')
		.replace(/\p{Diacritic}/gu, '')
		.replace(/ß/g, 'ss');
}
