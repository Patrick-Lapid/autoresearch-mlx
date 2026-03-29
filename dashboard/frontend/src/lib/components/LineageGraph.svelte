<script lang="ts">
	import type { Run } from '$lib/types';

	let { run, allRuns = [] }: { run: Run; allRuns: Run[] } = $props();

	let chain = $derived.by(() => {
		const result: Run[] = [];
		let current: Run | undefined = run;
		const seen = new Set<string>();
		while (current && !seen.has(current.run_id)) {
			seen.add(current.run_id);
			result.unshift(current);
			current = allRuns.find(r => r.run_id === current!.parent_run_id);
		}
		return result;
	});
</script>

<div class="lineage">
	{#each chain as node, i (node.run_id)}
		{#if i > 0}
			<span class="connector">
				<svg width="20" height="12" viewBox="0 0 20 12">
					<path d="M0 6h14l-4-4M14 6l-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
				</svg>
			</span>
		{/if}
		<span class="node" class:current={node.run_id === run.run_id}>
			<span class="node-num">#{node.iteration}</span>
			{#if node.val_bpb != null}
				<span class="bpb">{node.val_bpb.toFixed(4)}</span>
			{/if}
		</span>
	{/each}
</div>

<style>
	.lineage {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.85rem;
		flex-wrap: wrap;
	}
	.connector {
		color: var(--text-dim);
		display: flex;
		align-items: center;
	}
	.node {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.25rem 0.6rem;
		border-radius: var(--radius-sm);
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		font-family: var(--font-mono);
		font-size: 0.78rem;
		transition: all 0.15s ease;
	}
	.node:hover {
		border-color: var(--border-strong);
		box-shadow: var(--shadow-sm);
	}
	.node.current {
		border-color: var(--accent);
		background: var(--accent-light);
		box-shadow: 0 0 0 3px var(--accent-light);
	}
	.node-num {
		font-weight: 600;
		color: var(--text);
	}
	.bpb {
		color: var(--text-dim);
	}
</style>
