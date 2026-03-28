/** Format seconds as mm:ss (for player progress) */
export function formatTime(seconds: number): string {
	if (!seconds || seconds < 0) return '0:00';
	const mins = Math.floor(seconds / 60);
	const secs = Math.floor(seconds % 60);
	return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/** Parse a file path into folder and display title.
 *  Only cleans up names that look like filenames (contain / or .).
 *  Meta titles from tags are returned as-is. */
export function parseTrackName(raw: string): { folder: string; title: string } {
	const slashIdx = raw.lastIndexOf('/');
	const folder = slashIdx >= 0 ? raw.substring(0, slashIdx) : '';
	let name = slashIdx >= 0 ? raw.substring(slashIdx + 1) : raw;
	// Only strip extension and clean up if it looks like a filename
	const dotIdx = name.lastIndexOf('.');
	const looksLikeFile = dotIdx > 0 && name.length - dotIdx <= 5;
	if (looksLikeFile) {
		name = name.substring(0, dotIdx);
		name = name.replace(/[-_]/g, ' ');
	}
	return { folder, title: name };
}

/** Format seconds as human-readable duration: "3:24" or "1 Std. 12 Min." */
export function formatDuration(seconds: number): string {
	if (!seconds || seconds <= 0) return '';
	const hours = Math.floor(seconds / 3600);
	const mins = Math.floor((seconds % 3600) / 60);
	const secs = Math.floor(seconds % 60);
	if (hours > 0) return `${hours} Std. ${mins} Min.`;
	if (mins > 0) return `${mins}:${secs.toString().padStart(2, '0')}`;
	return `0:${secs.toString().padStart(2, '0')}`;
}
