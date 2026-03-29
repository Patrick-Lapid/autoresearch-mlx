<script lang="ts">
	import type { Run, AgentNote, Plateau } from '$lib/types';
	import { HYPERPARAM_KEYS } from '$lib/types';

	let { runs = [], notes = [], plateaus = [] }: { runs: Run[]; notes: AgentNote[]; plateaus: Plateau[] } = $props();

	let completed = $derived(runs.filter(r => r.status === 'completed'));
	let accepted = $derived(completed.filter(r => r.accepted === 1));
	let rejected = $derived(completed.filter(r => r.accepted === 0));

	let acceptRate = $derived(
		completed.length > 0 ? ((accepted.length / completed.length) * 100).toFixed(0) : '-'
	);

	// Rolling acceptance rate (last 10 runs)
	let recentRuns = $derived(
		[...completed].sort((a, b) => b.iteration - a.iteration).slice(0, 10)
	);
	let recentAcceptRate = $derived(
		recentRuns.length > 0
			? ((recentRuns.filter(r => r.accepted === 1).length / recentRuns.length) * 100).toFixed(0)
			: '-'
	);

	// Attempts per breakthrough
	let attemptsPerBreakthrough = $derived.by(() => {
		if (plateaus.length === 0) return [];
		return plateaus.map(p => ({
			iter: p.parent.iteration,
			attempts: p.children.length,
			found: p.children.some(c => c.run.accepted === 1),
		}));
	});

	let avgAttempts = $derived.by(() => {
		const withBreakthrough = attemptsPerBreakthrough.filter(a => a.found);
		if (withBreakthrough.length === 0) return '-';
		const avg = withBreakthrough.reduce((s, a) => s + a.attempts, 0) / withBreakthrough.length;
		return avg.toFixed(1);
	});

	// Strategy categories: detect what changed and track hit rates
	interface Strategy {
		name: string;
		accepted: number;
		rejected: number;
	}

	let strategies = $derived.by(() => {
		const cats = new Map<string, { accepted: number; rejected: number }>();

		for (const p of plateaus) {
			for (const child of p.children) {
				if (child.paramChanges.length === 0) continue;
				// Categorize by the primary change
				for (const change of child.paramChanges) {
					let cat = 'other';
					if (['depth', 'aspect_ratio', 'head_dim', 'window_pattern'].includes(change.key)) {
						cat = 'architecture';
					} else if (change.key.endsWith('_lr') || change.key === 'final_lr_frac') {
						cat = 'learning rate';
					} else if (change.key.includes('batch')) {
						cat = 'batch size';
					} else if (['warmup_ratio', 'warmdown_ratio'].includes(change.key)) {
						cat = 'scheduling';
					} else if (change.key === 'weight_decay') {
						cat = 'regularization';
					}

					if (!cats.has(cat)) cats.set(cat, { accepted: 0, rejected: 0 });
					const entry = cats.get(cat)!;
					if (child.run.accepted === 1) entry.accepted++;
					else entry.rejected++;
				}
			}
		}

		const result: Strategy[] = [];
		for (const [name, { accepted, rejected }] of cats) {
			result.push({ name, accepted, rejected });
		}
		return result.sort((a, b) => (b.accepted + b.rejected) - (a.accepted + a.rejected));
	});

	// Repeated failures: same intent tried multiple times
	let repeatedFailures = $derived.by(() => {
		const intentCounts = new Map<string, number>();
		for (const p of plateaus) {
			for (const child of p.children) {
				if (child.run.accepted === 0 && child.note?.intent) {
					// Normalize intent for grouping (lowercase, trim)
					const normalized = child.note.intent.toLowerCase().trim();
					// Group by key phrases
					for (const phrase of extractKeyPhrases(normalized)) {
						intentCounts.set(phrase, (intentCounts.get(phrase) || 0) + 1);
					}
				}
			}
		}
		return [...intentCounts.entries()]
			.filter(([, count]) => count >= 2)
			.sort((a, b) => b[1] - a[1])
			.slice(0, 5)
			.map(([phrase, count]) => ({ phrase, count }));
	});

	function extractKeyPhrases(intent: string): string[] {
		const phrases: string[] = [];
		// Look for specific param mentions
		if (intent.includes('depth') || intent.includes('layer')) phrases.push('depth/layers');
		if (intent.includes('learning rate') || intent.includes('lr')) phrases.push('learning rate');
		if (intent.includes('batch')) phrases.push('batch size');
		if (intent.includes('warmup') || intent.includes('warmdown')) phrases.push('scheduling');
		if (intent.includes('weight decay')) phrases.push('regularization');
		if (intent.includes('window') || intent.includes('attention')) phrases.push('attention');
		if (phrases.length === 0) phrases.push('other');
		return phrases;
	}

	// Best BPB
	let bestBpb = $derived.by(() => {
		const vals = accepted.filter(r => r.val_bpb != null).map(r => r.val_bpb!);
		return vals.length > 0 ? Math.min(...vals).toFixed(4) : '-';
	});

	// Total improvement
	let totalImprovement = $derived.by(() => {
		const sorted = [...accepted].filter(r => r.val_bpb != null).sort((a, b) => a.iteration - b.iteration);
		if (sorted.length < 2) return null;
		const first = sorted[0].val_bpb!;
		const last = sorted[sorted.length - 1].val_bpb!;
		const delta = last - first;
		const pct = ((delta / first) * 100).toFixed(1);
		return { delta: delta.toFixed(4), pct };
	});
</script>

<div class="sidebar">
	<!-- Overview stats -->
	<div class="section">
		<h4>Overview</h4>
		<div class="stat-row">
			<span class="stat-label">Best BPB</span>
			<span class="stat-value accent">{bestBpb}</span>
		</div>
		{#if totalImprovement}
			<div class="stat-row">
				<span class="stat-label">Improvement</span>
				<span class="stat-value good">{totalImprovement.delta} ({totalImprovement.pct}%)</span>
			</div>
		{/if}
		<div class="stat-row">
			<span class="stat-label">Total runs</span>
			<span class="stat-value">{completed.length}</span>
		</div>
		<div class="stat-row">
			<span class="stat-label">Plateaus</span>
			<span class="stat-value">{plateaus.length}</span>
		</div>
	</div>

	<!-- Acceptance rate -->
	<div class="section">
		<h4>Acceptance Rate</h4>
		<div class="rate-bar-wrap">
			<div class="rate-bar">
				<div class="rate-fill" style="width: {acceptRate === '-' ? 0 : acceptRate}%"></div>
			</div>
			<span class="rate-label">{acceptRate}%</span>
		</div>
		<div class="rate-detail">
			<span>{accepted.length} accepted</span>
			<span class="dim">/</span>
			<span>{completed.length} total</span>
		</div>
		{#if recentRuns.length >= 3}
			<div class="rate-recent">
				Last {recentRuns.length}: <strong>{recentAcceptRate}%</strong>
			</div>
		{/if}
	</div>

	<!-- Attempts per breakthrough -->
	<div class="section">
		<h4>Breakthrough Velocity</h4>
		<div class="stat-row">
			<span class="stat-label">Avg attempts</span>
			<span class="stat-value">{avgAttempts}</span>
		</div>
		<div class="plateau-bars">
			{#each attemptsPerBreakthrough as p}
				<div class="plateau-bar-row" title="Plateau #{p.iter}: {p.attempts} attempts">
					<span class="pb-label">#{p.iter}</span>
					<div class="pb-bar">
						{#each { length: Math.min(p.attempts, 12) } as _, i}
							<span
								class="pb-dot"
								class:success={p.found && i === p.attempts - 1}
								class:fail={!(p.found && i === p.attempts - 1)}
							></span>
						{/each}
						{#if p.attempts > 12}
							<span class="pb-more">+{p.attempts - 12}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>

	<!-- Strategy breakdown -->
	{#if strategies.length > 0}
		<div class="section">
			<h4>Strategy Hit Rate</h4>
			{#each strategies as strat}
				{@const total = strat.accepted + strat.rejected}
				{@const rate = total > 0 ? Math.round((strat.accepted / total) * 100) : 0}
				<div class="strat-row">
					<span class="strat-name">{strat.name}</span>
					<span class="strat-ratio">{strat.accepted}/{total}</span>
					<div class="strat-bar">
						<div class="strat-fill" style="width: {rate}%"></div>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Repeated failures -->
	{#if repeatedFailures.length > 0}
		<div class="section">
			<h4>Repeat Alerts</h4>
			{#each repeatedFailures as item}
				<div class="repeat-item">
					<span class="repeat-phrase">{item.phrase}</span>
					<span class="repeat-count">failed {item.count}x</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.sidebar {
		display: flex;
		flex-direction: column;
		gap: 0;
	}

	.section {
		padding: 1rem 0;
		border-bottom: 1px solid var(--border);
	}
	.section:first-child {
		padding-top: 0;
	}
	.section:last-child {
		border-bottom: none;
	}

	h4 {
		font-size: 0.65rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		margin-bottom: 0.6rem;
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.2rem 0;
	}

	.stat-label {
		font-size: 0.78rem;
		color: var(--text-secondary);
	}

	.stat-value {
		font-family: var(--font-mono);
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--text);
	}

	.stat-value.accent {
		color: var(--accent);
	}

	.stat-value.good {
		color: var(--green);
	}

	/* Acceptance rate bar */
	.rate-bar-wrap {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}

	.rate-bar {
		flex: 1;
		height: 6px;
		background: var(--bg-hover);
		border-radius: 3px;
		overflow: hidden;
	}

	.rate-fill {
		height: 100%;
		background: var(--green);
		border-radius: 3px;
		transition: width 0.3s ease;
	}

	.rate-label {
		font-family: var(--font-mono);
		font-size: 0.85rem;
		font-weight: 700;
		color: var(--text);
		min-width: 2.5rem;
		text-align: right;
	}

	.rate-detail {
		font-size: 0.72rem;
		color: var(--text-dim);
		margin-top: 0.3rem;
		display: flex;
		gap: 0.25rem;
	}

	.dim {
		opacity: 0.5;
	}

	.rate-recent {
		font-size: 0.72rem;
		color: var(--text-dim);
		margin-top: 0.2rem;
	}
	.rate-recent strong {
		color: var(--text-secondary);
	}

	/* Plateau bars (dot chart) */
	.plateau-bars {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		margin-top: 0.4rem;
	}

	.plateau-bar-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.pb-label {
		font-family: var(--font-mono);
		font-size: 0.68rem;
		color: var(--text-dim);
		width: 2rem;
		text-align: right;
	}

	.pb-bar {
		display: flex;
		gap: 0.2rem;
		align-items: center;
	}

	.pb-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
	.pb-dot.fail {
		background: rgba(220, 38, 38, 0.3);
	}
	.pb-dot.success {
		background: var(--green);
	}

	.pb-more {
		font-size: 0.62rem;
		color: var(--text-dim);
	}

	/* Strategy bars */
	.strat-row {
		display: grid;
		grid-template-columns: 1fr auto 50px;
		align-items: center;
		gap: 0.5rem;
		padding: 0.2rem 0;
	}

	.strat-name {
		font-size: 0.75rem;
		color: var(--text-secondary);
		text-transform: capitalize;
	}

	.strat-ratio {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		color: var(--text-dim);
	}

	.strat-bar {
		height: 4px;
		background: var(--bg-hover);
		border-radius: 2px;
		overflow: hidden;
	}

	.strat-fill {
		height: 100%;
		background: var(--accent);
		border-radius: 2px;
	}

	/* Repeated failures */
	.repeat-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.25rem 0;
	}

	.repeat-phrase {
		font-size: 0.75rem;
		color: var(--text-secondary);
		text-transform: capitalize;
	}

	.repeat-count {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		color: var(--amber);
		font-weight: 500;
	}
</style>
