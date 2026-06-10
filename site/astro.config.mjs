// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// The repo is served as a GitHub *project* site under a subpath.
const BASE = '/ftl_bench';

// Astro does NOT prepend `base` to root-absolute links written in markdown (e.g. `[x](/foo)`),
// so under a project subpath those links 404. This rehype pass prefixes the base onto internal
// root-absolute links, leaving external, protocol-relative, anchor, and already-based links alone.
function rehypeBaseLinks() {
	return (tree) => {
		const visit = (node) => {
			if (node.tagName === 'a' && node.properties) {
				const href = node.properties.href;
				if (
					typeof href === 'string' &&
					href.startsWith('/') &&
					!href.startsWith('//') &&
					href !== BASE &&
					!href.startsWith(BASE + '/')
				) {
					node.properties.href = BASE + href;
				}
			}
			if (Array.isArray(node.children)) node.children.forEach(visit);
		};
		visit(tree);
	};
}

// https://astro.build/config
export default defineConfig({
	// GitHub Pages (project site): served under https://ogabrielluiz.github.io/ftl_bench/
	site: 'https://ogabrielluiz.github.io',
	base: BASE,
	markdown: { rehypePlugins: [rehypeBaseLinks] },
	integrations: [
		starlight({
			title: 'ftl_bench',
			description:
				'A long-horizon game benchmark for LLM agents playing FTL: Faster Than Light ' +
				'through a paused, intent-level interface.',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/ogabrielluiz/ftl_bench' },
			],
			sidebar: [
				{
					label: 'Introduction',
					items: [
						{ label: 'The benchmark', slug: 'introduction/the-benchmark' },
						{ label: 'Benchmark protocol', slug: 'introduction/protocol' },
						{ label: 'How scoring works', slug: 'introduction/scoring' },
					],
				},
				{
					label: 'Evaluate your model',
					items: [
						{ label: 'Quickstart', slug: 'evaluate/quickstart' },
						{ label: 'Bring your model or agent', slug: 'evaluate/bring-your-model' },
						{ label: 'Running & results', slug: 'evaluate/running' },
					],
				},
				{
					label: 'Install the game',
					items: [
						{ label: 'PC - native x86 (recommended)', slug: 'install/pc', badge: 'recommended' },
						{ label: 'macOS - Rosetta', slug: 'install/macos' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'Observation schema', slug: 'reference/observation' },
						{ label: 'Action set', slug: 'reference/actions' },
						{ label: 'Play-to-game-over mode', slug: 'reference/play-to-gameover' },
					],
				},
				{
					label: 'Project',
					items: [
						{ label: 'Architecture', slug: 'project/architecture' },
						{ label: 'Results & baselines', slug: 'project/status' },
					],
				},
			],
		}),
	],
});
