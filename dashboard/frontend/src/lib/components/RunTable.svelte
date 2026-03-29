<script lang="ts">
	import type { Run } from '$lib/types';

	let { runs = [], onSelect = (_r: Run) => {} }: { runs: Run[]; onSelect?: (r: Run) => void } = $props();

	let sortKey: keyof Run = 'iteration';
	let sortDir: 'asc' | 'desc' = 'desc';

	function sort(key: keyof Run) {
		if (sortKey === key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortDir = key === 'val_bpb' ? 'asc' : 'desc';
		}
	}

	let sorted = $derived.by(() => {
		const arr = [...runs];
		arr.sort((a, b) => {
			const av = a[sortKey] ?? 0;
			const bv = b[sortKey] ?? 0;
			if (av < bv) return sortDir === 'asc' ? -1 : 1;
			if (av > bv) return sortDir === 'asc' ? 1 : -1;
			return 0;
		});
		return arr;
	});

	function fmt(v: number | null, decimals = 4): string {
		if (v == null) return '-';
		return v.toFixed(decimals);
	}

	function statusLabel(r: Run): string {
		if (r.accepted === 1) return 'accepted';
		if (r.accepted === 0) return 'rejected';
		return r.status;
	}

	function statusClass(r: Run): string {
		if (r.accepted === 1) return 'accepted';
		if (r.accepted === 0) return 'rejected';
		if (r.status === 'failed') return 'failed';
		return 'running';
	}

	function deltaBpb(r: Run): string {
		if (r.val_bpb == null) return '-';
		const parent = runs.find(p => p.run_id === r.parent_run_id);
		if (!parent?.val_bpb) return '-';
		const d = r.val_bpb - parent.val_bpb;
		return (d >= 0 ? '+' : '') + d.toFixed(6);
	}

	function deltaClass(r: Run): string {
		if (r.val_bpb == null) return '';
		const parent = runs.find(p => p.run_id === r.parent_run_id);
		if (!parent?.val_bpb) return '';
		const d = r.val_bpb - parent.val_bpb;
		return d < 0 ? 'delta-good' : d > 0 ? 'delta-bad' : '';
	}

	const cols: { key: keyof Run; label: string }[] = [
		{ key: 'iteration', label: '#' },
		{ key: 'val_bpb', label: 'val_bpb' },
		{ key: 'accepted', label: 'status' },
		{ key: 'depth', label: 'depth' },
		{ key: 'matrix_lr', label: 'matrix_lr' },
		{ key: 'total_batch_size', label: 'batch' },
		{ key: 'window_pattern', label: 'window' },
		{ key: 'num_steps', label: 'steps' },
		{ key: 'training_seconds', label: 'time(s)' },
	];
</script>

<div class="table-wrap">
	<table>
		<thead>
			<tr>
				{#each cols as col}
					<th onclick={() => sort(col.key)} class:sorted={sortKey === col.key}>
						{col.label}
						{#if sortKey === col.key}
							<span class="arrow">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
						{/if}
					</th>
				{/each}
				<th>delta</th>
			</tr>
		</thead>
		<tbody>
			{#each sorted as run (run.run_id)}
				<tr onclick={() => onSelect(run)} class="clickable">
					<td class="iteration-cell">{run.iteration}</td>
					<td class="mono">{fmt(run.val_bpb, 6)}</td>
					<td><span class="badge {statusClass(run)}">{statusLabel(run)}</span></td>
					<td>{run.depth ?? '-'}</td>
					<td class="mono">{fmt(run.matrix_lr, 4)}</td>
					<td>{run.total_batch_size ?? '-'}</td>
					<td>{run.window_pattern ?? '-'}</td>
					<td>{run.num_steps ?? '-'}</td>
					<td>{fmt(run.training_seconds, 1)}</td>
					<td class="mono delta {deltaClass(run)}">{deltaBpb(run)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.table-wrap {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.82rem;
	}
	th, td {
		padding: 0.55rem 0.75rem;
		text-align: left;
		white-space: nowrap;
	}
	th {
		color: var(--text-dim);
		font-weight: 600;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		cursor: pointer;
		user-select: none;
		border-bottom: 2px solid var(--border);
		transition: color 0.15s ease;
	}
	th:hover {
		color: var(--text-secondary);
	}
	td {
		border-bottom: 1px solid var(--bg-hover);
	}
	.sorted {
		color: var(--accent);
	}
	.arrow {
		font-size: 0.6rem;
		margin-left: 0.25rem;
	}
	.iteration-cell {
		font-family: var(--font-mono);
		font-weight: 600;
		color: var(--text-secondary);
	}
	.clickable {
		cursor: pointer;
		transition: background 0.1s ease;
	}
	.clickable:hover {
		background: var(--bg-hover);
	}
	.mono {
		font-family: var(--font-mono);
		font-size: 0.78rem;
	}
	.delta {
		color: var(--text-dim);
	}
	.delta-good {
		color: var(--green);
	}
	.delta-bad {
		color: var(--red);
	}
	.badge {
		display: inline-block;
		padding: 0.15rem 0.5rem;
		border-radius: var(--radius-sm);
		font-size: 0.68rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.badge.accepted {
		background: var(--green-bg);
		color: var(--green);
	}
	.badge.rejected {
		background: var(--red-bg);
		color: var(--red);
	}
	.badge.running {
		background: var(--amber-bg);
		color: var(--amber);
	}
	.badge.failed {
		background: var(--red-bg);
		color: var(--red);
	}
</style>
