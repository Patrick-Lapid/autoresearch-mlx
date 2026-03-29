import type { Run, RunDetail } from './types';

export async function fetchRuns(): Promise<Run[]> {
	const res = await fetch('/api/runs');
	return res.json();
}

export async function fetchRun(runId: string): Promise<RunDetail> {
	const res = await fetch(`/api/runs/${runId}`);
	return res.json();
}

export async function fetchDiff(runId: string): Promise<string> {
	const res = await fetch(`/api/runs/${runId}/diff`);
	const data = await res.json();
	return data.diff || '';
}
