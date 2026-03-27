/** Format seconds as mm:ss (for player progress) */
export function formatTime(seconds: number): string {
	if (!seconds || seconds < 0) return '0:00';
	const mins = Math.floor(seconds / 60);
	const secs = Math.floor(seconds % 60);
	return `${mins}:${secs.toString().padStart(2, '0')}`;
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
