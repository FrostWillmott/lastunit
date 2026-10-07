// `npm audit --audit-level=high` with a reviewed allow-list. npm has no way to
// accept a single advisory, so this fails on every high/critical advisory except
// the ones below. Each entry needs a reason and is removed once a fix ships.
import { execFileSync } from 'node:child_process'

const ALLOWED = {
  // braces <= 3.0.3, no patched release exists. Reached only through the linter
  // (@vue/eslint-config-typescript -> fast-glob -> micromatch); not in the bundle.
  'GHSA-vfj7-8cjw-p6xm': 'braces DoS, dev-only lint tooling, no fix upstream',
}
const FAILING = new Set(['high', 'critical'])

let raw
try {
  raw = execFileSync('npm', ['audit', '--json'], { encoding: 'utf8' })
} catch (error) {
  // npm audit exits non-zero whenever it finds anything; the JSON is still on stdout.
  raw = error.stdout
}
const report = JSON.parse(raw)
if (report.error) {
  console.error(`npm audit failed: ${report.error.summary}`)
  process.exit(1)
}

const advisories = new Map()
for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vuln.via) {
    // String entries are packages that inherit an advisory listed elsewhere.
    if (typeof via === 'object' && FAILING.has(via.severity)) {
      const id = via.url.split('/').pop()
      advisories.set(id, `${via.name}: ${via.title} (${via.severity}) ${via.url}`)
    }
  }
}

let failed = false
for (const [id, line] of advisories) {
  if (id in ALLOWED) {
    console.log(`allowed  ${line} — ${ALLOWED[id]}`)
  } else {
    console.log(`FAIL     ${line}`)
    failed = true
  }
}
for (const id of Object.keys(ALLOWED)) {
  if (!advisories.has(id)) console.log(`stale    ${id} no longer reported — drop it`)
}
console.log(
  `${advisories.size} high/critical advisories, ${failed ? 'failing' : 'all allowed'}`,
)
process.exit(failed ? 1 : 0)
