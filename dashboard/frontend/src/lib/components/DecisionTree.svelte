<script lang="ts">
	import type { Run, AgentNote, Plateau, PlateauChild, ParamChange } from '$lib/types';
	import { HYPERPARAM_KEYS } from '$lib/types';
	import { fetchDiff } from '$lib/api';
	import DiffViewer from './DiffViewer.svelte';

	let { runs = [], notes = [] }: { runs: Run[]; notes: AgentNote[] } = $props();

	let expandedId: string | null = $state(null);
	let diffCache: Record<string, string> = $state({});
	let loadingDiff: string | null = $state(null);

	function getParamChanges(child: Run, parent: Run): ParamChange[] {
		const changes: ParamChange[] = [];
		for (const key of HYPERPARAM_KEYS) {
			const cv = child[key];
			const pv = parent[key];
			if (cv != null && pv != null && String(cv) !== String(pv)) {
				changes.push({ key, from: pv as string | number, to: cv as string | number });
			}
		}
		return changes;
	}

	// Find the note that was written for the run that *became* this accepted parent
	// i.e. the note written from the grandparent plateau that led to trying this run
	function findNoteForAccepted(run: Run, allNotes: AgentNote[], allRuns: Run[]): AgentNote | null {
		if (!run.parent_run_id) return null;
		// Notes logged against the grandparent, find the one closest before this run started
		const parentNotes = allNotes
			.filter(n => n.run_id === run.parent_run_id)
			.sort((a, b) => a.ts - b.ts);
		// Match by timestamp: the note written just before this run started
		let best: AgentNote | null = null;
		for (const n of parentNotes) {
			if (n.ts <= run.started_at) best = n;
		}
		return best;
	}

	let plateaus = $derived.by(() => {
		const accepted = runs.filter(r => r.accepted === 1).sort((a, b) => a.iteration - b.iteration);

		// Also include the root run if it's not accepted but has children
		const rootRuns = runs.filter(r => !r.parent_run_id).sort((a, b) => a.iteration - b.iteration);
		const firstAccepted = accepted[0];
		// If the first run is accepted, it's already in the list
		// If not, we still want to show it as the root

		const notesByParent = new Map<string, AgentNote[]>();
		for (const note of notes) {
			const arr = notesByParent.get(note.run_id) || [];
			arr.push(note);
			notesByParent.set(note.run_id, arr);
		}

		const result: Plateau[] = [];

		for (const parent of accepted) {
			const children = runs
				.filter(r => r.parent_run_id === parent.run_id && r.run_id !== parent.run_id)
				.sort((a, b) => a.iteration - b.iteration);

			const parentNotes = (notesByParent.get(parent.run_id) || []).sort((a, b) => a.ts - b.ts);

			// Match notes to children by timestamp order
			const usedNotes = new Set<number>();
			const paired: PlateauChild[] = children.map(child => {
				let matchedNote: AgentNote | null = null;
				for (const n of parentNotes) {
					if (!usedNotes.has(n.id) && n.ts <= child.started_at + 5) {
						matchedNote = n;
						usedNotes.add(n.id);
						break;
					}
				}
				return {
					run: child,
					note: matchedNote,
					paramChanges: getParamChanges(child, parent),
				};
			});

			result.push({
				parent,
				children: paired,
				noteForParent: findNoteForAccepted(parent, notes, runs),
			});
		}

		return result;
	});

	function toggleExpand(runId: string) {
		expandedId = expandedId === runId ? null : runId;
	}

	async function loadDiff(runId: string) {
		if (diffCache[runId] !== undefined) return;
		loadingDiff = runId;
		diffCache[runId] = await fetchDiff(runId);
		loadingDiff = null;
	}

	function bpbDelta(child: Run, parent: Run): { text: string; cls: string; pct: string } {
		if (child.val_bpb == null || parent.val_bpb == null) return { text: '-', cls: '', pct: '' };
		const d = child.val_bpb - parent.val_bpb;
		const pct = ((d / parent.val_bpb) * 100).toFixed(1);
		return {
			text: (d >= 0 ? '+' : '') + d.toFixed(4),
			cls: d < 0 ? 'delta-good' : 'delta-bad',
			pct: (d >= 0 ? '+' : '') + pct + '%',
		};
	}

	function formatParam(key: string, val: string | number): string {
		if (typeof val === 'number') {
			if (key.endsWith('_lr')) return val.toPrecision(3);
			if (key.endsWith('_ratio') || key === 'final_lr_frac') return val.toFixed(2);
			return String(val);
		}
		return String(val);
	}
</script>

<div class="tree">
	{#each plateaus as plateau, pi (plateau.parent.run_id)}
		{@const isExpanded = expandedId === plateau.parent.run_id}
		{@const hasChildren = plateau.children.length > 0}
		{@const isLast = pi === plateaus.length - 1}

		<!-- Trunk node (accepted run) -->
		<div class="trunk-segment" class:last={isLast}>
			<button class="trunk-node" onclick={() => toggleExpand(plateau.parent.run_id)} class:expanded={isExpanded}>
				<div class="trunk-dot"></div>
				<div class="trunk-content">
					<div class="trunk-header">
						<span class="trunk-iter">#{plateau.parent.iteration}</span>
						<span class="trunk-bpb">{plateau.parent.val_bpb?.toFixed(4) ?? '-'}</span>
						<span class="trunk-bpb-label">bpb</span>
						{#if hasChildren}
							<span class="trunk-stats">
								{plateau.children.filter(c => c.run.accepted === 1).length}/{plateau.children.length} accepted
							</span>
						{/if}
						<span class="expand-icon">{isExpanded ? '\u25BC' : '\u25B6'}</span>
					</div>
					{#if plateau.noteForParent}
						<div class="trunk-intent">{plateau.noteForParent.intent}</div>
					{:else if pi === 0}
						<div class="trunk-intent">Baseline</div>
					{/if}
				</div>
			</button>

			<!-- Rejected branches (always visible, compact) -->
			{#if !isExpanded && hasChildren}
				<div class="branches-compact">
					{#each plateau.children.filter(c => c.run.accepted !== 1) as child (child.run.run_id)}
						{@const delta = bpbDelta(child.run, plateau.parent)}
						<div class="branch-pip" title="{child.note?.intent ?? 'run #' + child.run.iteration}: {child.run.val_bpb?.toFixed(4)} ({delta.text})">
							<span class="pip {delta.cls}"></span>
						</div>
					{/each}
				</div>
			{/if}

			<!-- Expanded plateau detail -->
			{#if isExpanded}
				<div class="plateau-detail">
					<div class="plateau-summary">
						<span class="plateau-count">{plateau.children.length} attempt{plateau.children.length !== 1 ? 's' : ''}</span>
						{#if plateau.children.some(c => c.run.accepted === 1)}
							<span class="plateau-breakthrough">
								breakthrough on attempt #{plateau.children.findIndex(c => c.run.accepted === 1) + 1}
							</span>
						{:else if plateau.children.length > 0}
							<span class="plateau-stuck">no breakthrough yet</span>
						{/if}
					</div>

					{#each plateau.children as child (child.run.run_id)}
						{@const delta = bpbDelta(child.run, plateau.parent)}
						{@const isAccepted = child.run.accepted === 1}
						<div class="attempt" class:accepted={isAccepted} class:rejected={child.run.accepted === 0}>
							<div class="attempt-header">
								<span class="attempt-status">{isAccepted ? '\u2713' : '\u2717'}</span>
								<span class="attempt-iter">#{child.run.iteration}</span>
								{#if child.run.val_bpb != null}
									<span class="attempt-bpb">{child.run.val_bpb.toFixed(4)}</span>
									<span class="attempt-delta {delta.cls}">{delta.text}</span>
									<span class="attempt-pct {delta.cls}">{delta.pct}</span>
								{/if}
							</div>

							{#if child.note}
								<div class="attempt-reasoning">
									<div class="attempt-intent">{child.note.intent}</div>
									{#if child.note.hypothesis}
										<div class="attempt-hypothesis">{child.note.hypothesis}</div>
									{/if}
								</div>
							{/if}

							{#if child.paramChanges.length > 0}
								<div class="param-pills">
									{#each child.paramChanges as change}
										<span class="param-pill">
											<span class="pill-key">{change.key}</span>
											<span class="pill-from">{formatParam(change.key, change.from)}</span>
											<span class="pill-arrow">\u2192</span>
											<span class="pill-to">{formatParam(change.key, change.to)}</span>
										</span>
									{/each}
								</div>
							{/if}

							{#if isAccepted && child.run.diff_patch}
								<button class="diff-toggle" onclick={() => loadDiff(child.run.run_id)}>
									{diffCache[child.run.run_id] !== undefined ? 'Hide diff' : 'View diff'}
								</button>
								{#if diffCache[child.run.run_id]}
									<div class="attempt-diff">
										<DiffViewer diff={diffCache[child.run.run_id]} />
									</div>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/each}

	{#if plateaus.length === 0}
		<div class="empty">No completed runs yet</div>
	{/if}
</div>

<style>
	.tree {
		position: relative;
	}

	/* Trunk segment: one accepted node + its branches */
	.trunk-segment {
		position: relative;
		padding-left: 28px;
		padding-bottom: 0.25rem;
	}
	/* Vertical trunk line */
	.trunk-segment::before {
		content: '';
		position: absolute;
		left: 9px;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--border-strong);
	}
	.trunk-segment.last::before {
		bottom: calc(100% - 18px);
	}

	/* Trunk node button */
	.trunk-node {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0.5rem 0.75rem 0.5rem 0;
		width: 100%;
		text-align: left;
		border-radius: var(--radius-sm);
		transition: background 0.15s ease;
	}
	.trunk-node:hover {
		background: var(--bg-hover);
	}

	.trunk-dot {
		width: 16px;
		height: 16px;
		min-width: 16px;
		border-radius: 50%;
		background: var(--green);
		border: 3px solid var(--bg-card);
		box-shadow: 0 0 0 2px var(--green);
		margin-top: 2px;
		position: relative;
		z-index: 2;
		margin-left: -22px;
	}

	.trunk-content {
		flex: 1;
		min-width: 0;
	}

	.trunk-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.trunk-iter {
		font-family: var(--font-mono);
		font-weight: 700;
		font-size: 0.9rem;
		color: var(--text);
	}

	.trunk-bpb {
		font-family: var(--font-mono);
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--green);
	}

	.trunk-bpb-label {
		font-size: 0.7rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.trunk-stats {
		font-size: 0.72rem;
		color: var(--text-dim);
		margin-left: auto;
	}

	.expand-icon {
		font-size: 0.6rem;
		color: var(--text-dim);
		transition: transform 0.15s ease;
	}

	.trunk-intent {
		font-size: 0.8rem;
		color: var(--text-secondary);
		margin-top: 0.15rem;
		line-height: 1.4;
	}

	/* Compact branch pips (collapsed view) */
	.branches-compact {
		display: flex;
		gap: 0.35rem;
		padding: 0.25rem 0 0.5rem 0;
		flex-wrap: wrap;
	}

	.branch-pip {
		cursor: default;
	}

	.pip {
		display: block;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--border-strong);
	}
	.pip.delta-bad {
		background: rgba(220, 38, 38, 0.4);
	}
	.pip.delta-good {
		background: var(--green);
	}

	/* Expanded plateau detail */
	.plateau-detail {
		margin: 0.35rem 0 0.75rem 0;
	}

	.plateau-summary {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.75rem;
		color: var(--text-dim);
		padding: 0.35rem 0;
		margin-bottom: 0.35rem;
		border-bottom: 1px solid var(--border);
	}

	.plateau-count {
		font-weight: 600;
	}

	.plateau-breakthrough {
		color: var(--green);
		font-weight: 500;
	}

	.plateau-stuck {
		color: var(--amber);
		font-weight: 500;
	}

	/* Individual attempt card */
	.attempt {
		position: relative;
		margin: 0.4rem 0;
		padding: 0.65rem 0.85rem;
		background: var(--bg-subtle);
		border-radius: var(--radius-sm);
		border-left: 3px solid var(--border-strong);
	}
	.attempt.rejected {
		border-left-color: rgba(220, 38, 38, 0.3);
	}
	.attempt.accepted {
		border-left-color: var(--green);
		background: var(--green-bg);
	}

	.attempt-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.attempt-status {
		font-weight: 700;
		font-size: 0.85rem;
	}
	.attempt.accepted .attempt-status {
		color: var(--green);
	}
	.attempt.rejected .attempt-status {
		color: var(--red);
		opacity: 0.5;
	}

	.attempt-iter {
		font-family: var(--font-mono);
		font-weight: 600;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}

	.attempt-bpb {
		font-family: var(--font-mono);
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--text);
	}

	.attempt-delta {
		font-family: var(--font-mono);
		font-size: 0.78rem;
		font-weight: 600;
	}

	.attempt-pct {
		font-size: 0.72rem;
		font-weight: 500;
	}

	.delta-good {
		color: var(--green);
	}
	.delta-bad {
		color: var(--red);
		opacity: 0.7;
	}

	.attempt-reasoning {
		margin-top: 0.35rem;
	}

	.attempt-intent {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text);
		line-height: 1.4;
	}

	.attempt-hypothesis {
		font-size: 0.75rem;
		color: var(--text-secondary);
		margin-top: 0.1rem;
		line-height: 1.4;
		font-style: italic;
	}

	/* Param change pills */
	.param-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-top: 0.4rem;
	}

	.param-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.15rem 0.5rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 999px;
		font-size: 0.7rem;
		font-family: var(--font-mono);
	}

	.pill-key {
		color: var(--text-dim);
		font-weight: 500;
	}

	.pill-from {
		color: var(--red);
		opacity: 0.7;
	}

	.pill-arrow {
		color: var(--text-dim);
		font-size: 0.6rem;
	}

	.pill-to {
		color: var(--accent);
		font-weight: 600;
	}

	/* Diff toggle */
	.diff-toggle {
		margin-top: 0.4rem;
		padding: 0.25rem 0.6rem;
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		font-size: 0.72rem;
		font-weight: 500;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.15s ease;
	}
	.diff-toggle:hover {
		background: var(--bg-hover);
		border-color: var(--border-strong);
		color: var(--text);
	}

	.attempt-diff {
		margin-top: 0.5rem;
	}

	.empty {
		color: var(--text-dim);
		font-size: 0.85rem;
		padding: 2rem;
		text-align: center;
	}
</style>
