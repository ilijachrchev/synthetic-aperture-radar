// Hard rule for this project: no en dash or em dash anywhere in what we ship.
// Walks the web app's own files (source, scripts, public text files, config, readme) and fails on any character of
// the dash family other than the plain hyphen, and on their HTML entities. The characters are written as code
// points so this file holds none of them itself. Runs before every build (prebuild) and on demand (check:dashes).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const BANNED = [0x2012, 0x2013, 0x2014, 0x2015, 0x2e3a, 0x2e3b, 0xfe58, 0xfe31, 0xfe32].map((c) => String.fromCharCode(c))
const ENTITY = /&(?:ndash|mdash|horbar|#821[1-3];|#x201[2-5]);?/gi
const TEXT = new Set(['.ts', '.tsx', '.js', '.mjs', '.cjs', '.css', '.json', '.md', '.mdx', '.txt', '.svg', '.html', '.py', '.yaml', '.yml'])
const SKIP_DIRS = new Set(['node_modules', '.next', '.git', 'out', 'radar', 'img', 'video'])
// AGENTS.md is written by `next dev` itself and is not committed (see .gitignore).
const SKIP_FILES = new Set(['AGENTS.md', 'pnpm-lock.yaml', 'next-env.d.ts'])

function walk(dir, out = []) {
	for (const name of readdirSync(dir)) {
		const full = join(dir, name)
		if (statSync(full).isDirectory()) {
			if (!SKIP_DIRS.has(name)) walk(full, out)
		} else if (TEXT.has(extname(name)) && !SKIP_FILES.has(name)) {
			out.push(full)
		}
	}
	return out
}

const hits = []
for (const file of walk(ROOT)) {
	const lines = readFileSync(file, 'utf8').split('\n')
	lines.forEach((line, i) => {
		const found = BANNED.some((ch) => line.includes(ch)) || ENTITY.test(line)
		ENTITY.lastIndex = 0
		if (found) hits.push(`${relative(ROOT, file)}:${i + 1}: ${line.trim().slice(0, 120)}`)
	})
}

if (hits.length) {
	console.error(`No en or em dashes allowed. Found ${hits.length}:\n` + hits.join('\n'))
	process.exit(1)
}
console.log('check:dashes ok, no en or em dashes')
