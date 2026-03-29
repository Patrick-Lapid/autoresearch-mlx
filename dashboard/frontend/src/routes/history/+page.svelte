<script lang="ts">
	import { onMount } from 'svelte';
	import type { Run, AgentNote, ParamChange } from '$lib/types';
	import { HYPERPARAM_KEYS } from '$lib/types';
	import type { SSEEvent } from '$lib/types';
	import { fetchRuns, fetchNotes, fetchDiff } from '$lib/api';
	import RunGraph from '$lib/components/RunGraph.svelte';
	import InsightSidebar from '$lib/components/InsightSidebar.svelte';
	import DiffViewer from '$lib/components/DiffViewer.svelte';

	let runs: Run[] = $state([]);
	let notes: AgentNote[] = $state([]);
	let selectedRun: Run | null = $state(null);
	let selectedDiff: string = $state('');
	let loadingDiff = $state(false);
	let showInsights = $state(true);

	onMount(async () => {
		runs = await fetchRuns();
		try { notes = await fetchNotes(); } catch { notes = []; }

		// SSE for real-time updates
		const es = new EventSource('/stream');
		es.onmessage = (e) => {
			const event: SSEEvent = JSON.parse(e.data);
			if (event.type === 'run_start') {
				const newRun: Run = {
					run_id: event.run_id,
					iteration: event.iteration,
					started_at: Date.now() / 1000,
					ended_at: null,
					status: 'running',
					accepted: null,
					val_bpb: null,
					parent_run_id: event.parent_run_id,
					depth: null, total_batch_size: null, device_batch_size: null,
					embedding_lr: null, unembedding_lr: null, matrix_lr: null,
					scalar_lr: null, weight_decay: null, warmup_ratio: null,
					warmdown_ratio: null, final_lr_frac: null, adam_betas: null,
					window_pattern: null, aspect_ratio: null, head_dim: null,
					time_budget: null, num_params_m: null, total_tokens_m: null,
					num_steps: null, training_seconds: null, peak_vram_mb: null,
					mfu_percent: null, diff_patch: null,
				};
				// Merge config into run fields
				if (event.config) {
					for (const [k, v] of Object.entries(event.config)) {
						if (k in newRun) (newRun as any)[k] = v;
					}
				}
				runs = [...runs, newRun];
			} else if (event.type === 'run_end') {
				runs = runs.map(r => r.run_id === event.run_id
					? { ...r, ...event.summary, val_bpb: event.val_bpb, status: 'completed' as const, ended_at: Date.now() / 1000 }
					: r
				);
				// Update selected if viewing this run
				if (selectedRun?.run_id === event.run_id) {
					selectedRun = runs.find(r => r.run_id === event.run_id) ?? selectedRun;
				}
			} else if (event.type === 'accept_decision') {
				runs = runs.map(r => r.run_id === event.run_id
					? { ...r, accepted: event.accepted ? 1 : 0 }
					: r
				);
				if (selectedRun?.run_id === event.run_id) {
					selectedRun = runs.find(r => r.run_id === event.run_id) ?? selectedRun;
				}
			} else if (event.type === 'agent_note') {
				notes = [...notes, {
					id: Date.now(),
					run_id: event.run_id,
					ts: Date.now() / 1000,
					intent: event.intent,
					hypothesis: event.hypothesis,
					raw: null,
				}];
			}
		};

		return () => es.close();
	});

	// Build plateaus for insight sidebar
	let plateaus = $derived.by(() => {
		const accepted = runs.filter(r => r.accepted === 1).sort((a, b) => a.iteration - b.iteration);
		const notesByParent = new Map<string, AgentNote[]>();
		for (const n of notes) {
			const arr = notesByParent.get(n.run_id) || [];
			arr.push(n);
			notesByParent.set(n.run_id, arr);
		}
		return accepted.map(parent => {
			const children = runs
				.filter(r => r.parent_run_id === parent.run_id && r.run_id !== parent.run_id)
				.sort((a, b) => a.iteration - b.iteration);
			const parentNotes = (notesByParent.get(parent.run_id) || []).sort((a, b) => a.ts - b.ts);
			const usedNotes = new Set<number>();
			const paired = children.map(child => {
				let matchedNote: AgentNote | null = null;
				for (const n of parentNotes) {
					if (!usedNotes.has(n.id) && n.ts <= child.started_at + 5) {
						matchedNote = n;
						usedNotes.add(n.id);
						break;
					}
				}
				const paramChanges: ParamChange[] = [];
				for (const key of HYPERPARAM_KEYS) {
					const cv = child[key]; const pv = parent[key];
					if (cv != null && pv != null && String(cv) !== String(pv))
						paramChanges.push({ key, from: pv as string | number, to: cv as string | number });
				}
				return { run: child, note: matchedNote, paramChanges };
			});
			return { parent, children: paired, noteForParent: null as AgentNote | null };
		});
	});

	async function onSelectRun(run: Run | null) {
		selectedRun = run;
		selectedDiff = '';
		if (run) {
			loadingDiff = true;
			selectedDiff = await fetchDiff(run.run_id);
			loadingDiff = false;
		}
	}

	function statusLabel(r: Run): string {
		if (r.accepted === 1) return 'accepted';
		if (r.accepted === 0) return 'rejected';
		return r.status;
	}

	function statusClass(r: Run): string {
		if (r.accepted === 1) return 'acc';
		if (r.accepted === 0) return 'rej';
		if (r.status === 'running') return 'run';
		return '';
	}

	// Find note for selected run
	let selectedNote = $derived.by(() => {
		if (!selectedRun?.parent_run_id) return null;
		const parentNotes = notes.filter(n => n.run_id === selectedRun!.parent_run_id).sort((a, b) => a.ts - b.ts);
		let best: AgentNote | null = null;
		for (const n of parentNotes) {
			if (n.ts <= selectedRun!.started_at + 5) best = n;
		}
		return best;
	});

	// Param changes for selected run
	let selectedParams = $derived.by((): ParamChange[] => {
		if (!selectedRun?.parent_run_id) return [];
		const parent = runs.find(r => r.run_id === selectedRun!.parent_run_id);
		if (!parent) return [];
		const changes: ParamChange[] = [];
		for (const key of HYPERPARAM_KEYS) {
			const cv = selectedRun![key]; const pv = parent[key];
			if (cv != null && pv != null && String(cv) !== String(pv))
				changes.push({ key, from: pv as string | number, to: cv as string | number });
		}
		return changes;
	});

	// Delta for selected run
	let selectedDelta = $derived.by(() => {
		if (!selectedRun?.val_bpb || !selectedRun?.parent_run_id) return null;
		const parent = runs.find(r => r.run_id === selectedRun!.parent_run_id);
		if (!parent?.val_bpb) return null;
		const d = selectedRun!.val_bpb! - parent.val_bpb;
		const pct = ((d / parent.val_bpb) * 100).toFixed(1);
		return {
			text: (d >= 0 ? '+' : '') + d.toFixed(6),
			pct: (d >= 0 ? '+' : '') + pct + '%',
			cls: d < 0 ? 'good' : 'bad',
		};
	});

	function fmtParam(key: string, val: string | number): string {
		if (typeof val === 'number') {
			if (key.endsWith('_lr')) return val.toPrecision(3);
			if (key.endsWith('_ratio') || key === 'final_lr_frac') return val.toFixed(2);
			return String(val);
		}
		return String(val);
	}
</script>

<div class="decisions-view">
	<!-- Graph (fills viewport) -->
	<div class="graph-area">
		<RunGraph {runs} {notes} onSelect={onSelectRun} />
	</div>

	<!-- Floating Insight Sidebar (top-right) -->
	<div class="insight-float" class:collapsed={!showInsights}>
		<button class="insight-toggle" onclick={() => (showInsights = !showInsights)}>
			{showInsights ? '\u2715' : '\u2139'}
		</button>
		{#if showInsights}
			<div class="insight-body">
				<InsightSidebar {runs} {notes} {plateaus} />
			</div>
		{/if}
	</div>

	<!-- Selected Run Detail Card (floating, bottom-left) -->
	{#if selectedRun}
		<div class="detail-card">
			<div class="dc-header">
				<div class="dc-title">
					<span class="dc-iter">#{selectedRun.iteration}</span>
					<span class="dc-id">{selectedRun.run_id}</span>
					<span class="dc-badge {statusClass(selectedRun)}">{statusLabel(selectedRun)}</span>
				</div>
				<button class="dc-close" onclick={() => onSelectRun(null)}>&times;</button>
			</div>

			{#if selectedRun.val_bpb != null}
				<div class="dc-bpb">
					<span class="dc-bpb-val">{selectedRun.val_bpb.toFixed(6)}</span>
					<span class="dc-bpb-label">bpb</span>
					{#if selectedDelta}
						<span class="dc-delta {selectedDelta.cls}">{selectedDelta.text} ({selectedDelta.pct})</span>
					{/if}
				</div>
			{/if}

			{#if selectedNote}
				<div class="dc-section">
					<div class="dc-intent">{selectedNote.intent}</div>
					{#if selectedNote.hypothesis}
						<div class="dc-hypothesis">{selectedNote.hypothesis}</div>
					{/if}
				</div>
			{/if}

			{#if selectedParams.length > 0}
				<div class="dc-pills">
					{#each selectedParams as ch}
						<span class="dc-pill">
							<span class="pill-k">{ch.key}</span>
							<span class="pill-from">{fmtParam(ch.key, ch.from)}</span>
							<span class="pill-arr">&rarr;</span>
							<span class="pill-to">{fmtParam(ch.key, ch.to)}</span>
						</span>
					{/each}
				</div>
			{/if}

			<!-- Metrics row -->
			<div class="dc-metrics">
				{#if selectedRun.num_params_m}<span>{selectedRun.num_params_m.toFixed(1)}M params</span>{/if}
				{#if selectedRun.num_steps}<span>{selectedRun.num_steps} steps</span>{/if}
				{#if selectedRun.training_seconds}<span>{selectedRun.training_seconds.toFixed(0)}s</span>{/if}
				{#if selectedRun.peak_vram_mb}<span>{selectedRun.peak_vram_mb.toFixed(0)}MB</span>{/if}
			</div>

			<!-- Diff -->
			{#if selectedDiff}
				<details class="dc-diff-details">
					<summary>View diff</summary>
					<div class="dc-diff">
						<DiffViewer diff={selectedDiff} />
					</div>
				</details>
			{:else if loadingDiff}
				<div class="dc-loading">Loading diff...</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.decisions-view {
		position: relative;
		height: calc(100vh - 56px - 3rem);
		min-height: 500px;
	}

	.graph-area {
		width: 100%;
		height: 100%;
	}

	/* Floating Insight Panel */
	.insight-float {
		position: absolute;
		top: 12px;
		right: 12px;
		z-index: 20;
	}
	.insight-float.collapsed {
		background: transparent;
	}
	.insight-float:not(.collapsed) {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		box-shadow: var(--shadow-lg);
		width: 260px;
	}

	.insight-toggle {
		position: absolute;
		top: 0;
		right: 0;
		width: 32px;
		height: 32px;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		color: var(--text-dim);
		font-size: 0.85rem;
		z-index: 1;
		box-shadow: var(--shadow-sm);
		transition: all 0.15s ease;
	}
	.insight-float:not(.collapsed) .insight-toggle {
		top: 8px;
		right: 8px;
		border: none;
		box-shadow: none;
		background: none;
	}
	.insight-toggle:hover {
		color: var(--text);
	}

	.insight-body {
		padding: 1rem 1.1rem;
		max-height: calc(100vh - 56px - 6rem);
		overflow-y: auto;
	}

	/* Selected Run Detail Card */
	.detail-card {
		position: absolute;
		bottom: 12px;
		left: 12px;
		z-index: 20;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		box-shadow: var(--shadow-lg);
		padding: 1rem 1.25rem;
		width: 380px;
		max-height: calc(100vh - 56px - 6rem);
		overflow-y: auto;
	}

	.dc-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}
	.dc-title {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.dc-iter {
		font-family: var(--font-mono);
		font-weight: 700;
		font-size: 1.1rem;
		color: var(--text);
	}
	.dc-id {
		font-family: var(--font-mono);
		font-size: 0.72rem;
		color: var(--text-dim);
	}
	.dc-badge {
		font-size: 0.6rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		padding: 0.12rem 0.4rem;
		border-radius: 4px;
	}
	.dc-badge.acc { background: var(--green-bg); color: var(--green); }
	.dc-badge.rej { background: var(--red-bg); color: var(--red); }
	.dc-badge.run { background: var(--amber-bg); color: var(--amber); }

	.dc-close {
		background: none;
		border: 1px solid var(--border);
		color: var(--text-dim);
		font-size: 1.1rem;
		cursor: pointer;
		width: 26px;
		height: 26px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-sm);
		line-height: 1;
		transition: all 0.15s ease;
	}
	.dc-close:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.dc-bpb {
		display: flex;
		align-items: baseline;
		gap: 0.35rem;
		margin-bottom: 0.5rem;
	}
	.dc-bpb-val {
		font-family: var(--font-mono);
		font-size: 1.3rem;
		font-weight: 700;
		color: var(--text);
	}
	.dc-bpb-label {
		font-size: 0.72rem;
		color: var(--text-dim);
		text-transform: uppercase;
	}
	.dc-delta {
		font-family: var(--font-mono);
		font-size: 0.78rem;
		font-weight: 600;
		margin-left: 0.25rem;
	}
	.dc-delta.good { color: var(--green); }
	.dc-delta.bad { color: var(--red); opacity: 0.7; }

	.dc-section {
		margin-bottom: 0.5rem;
		padding-bottom: 0.5rem;
		border-bottom: 1px solid var(--border);
	}
	.dc-intent {
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--text);
		line-height: 1.4;
	}
	.dc-hypothesis {
		font-size: 0.75rem;
		color: var(--text-secondary);
		font-style: italic;
		line-height: 1.4;
		margin-top: 0.15rem;
	}

	.dc-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-bottom: 0.5rem;
	}
	.dc-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		padding: 0.15rem 0.5rem;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 999px;
		font-size: 0.68rem;
		font-family: var(--font-mono);
	}
	.pill-k { color: var(--text-dim); font-weight: 500; }
	.pill-from { color: var(--red); opacity: 0.7; }
	.pill-arr { color: var(--text-dim); font-size: 0.6rem; }
	.pill-to { color: var(--accent); font-weight: 600; }

	.dc-metrics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		font-size: 0.72rem;
		color: var(--text-dim);
		font-family: var(--font-mono);
		margin-bottom: 0.5rem;
	}

	.dc-diff-details {
		border-top: 1px solid var(--border);
		padding-top: 0.4rem;
	}
	.dc-diff-details summary {
		font-size: 0.72rem;
		font-weight: 600;
		color: var(--text-secondary);
		cursor: pointer;
		padding: 0.25rem 0;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.dc-diff-details summary:hover {
		color: var(--text);
	}
	.dc-diff {
		margin-top: 0.4rem;
		max-height: 300px;
		overflow-y: auto;
	}

	.dc-loading {
		font-size: 0.72rem;
		color: var(--text-dim);
		padding: 0.25rem 0;
	}
</style>
