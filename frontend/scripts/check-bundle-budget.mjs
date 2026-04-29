import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const assetsRoot = join(frontendRoot, 'dist', 'assets')

const budgets = {
  totalGzipKb: Number(process.env.BUNDLE_TOTAL_GZIP_KB ?? 900),
  assetGzipKb: Number(process.env.BUNDLE_ASSET_GZIP_KB ?? 350),
  graphVendorGzipKb: Number(process.env.BUNDLE_GRAPH_VENDOR_GZIP_KB ?? 250),
}

function walkFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    return entry.isDirectory() ? walkFiles(path) : [path]
  })
}

function kb(bytes) {
  return bytes / 1024
}

if (!existsSync(assetsRoot)) {
  console.error(`Missing build assets at ${assetsRoot}. Run npm run build first.`)
  process.exit(1)
}

const assets = walkFiles(assetsRoot)
  .filter((path) => /\.(js|css)$/.test(path))
  .map((path) => {
    const rawBytes = statSync(path).size
    const gzipBytes = gzipSync(readFileSync(path)).length
    return {
      name: relative(assetsRoot, path).replace(/\\/g, '/'),
      rawKb: kb(rawBytes),
      gzipKb: kb(gzipBytes),
    }
  })
  .sort((a, b) => b.gzipKb - a.gzipKb)

const totalGzipKb = assets.reduce((total, asset) => total + asset.gzipKb, 0)
const graphVendor = assets.find((asset) => asset.name.startsWith('graph-vendor-'))
const failures = []

if (totalGzipKb > budgets.totalGzipKb) {
  failures.push(`total gzip ${totalGzipKb.toFixed(2)}KB > ${budgets.totalGzipKb}KB`)
}

for (const asset of assets) {
  if (asset.gzipKb > budgets.assetGzipKb) {
    failures.push(`${asset.name} gzip ${asset.gzipKb.toFixed(2)}KB > ${budgets.assetGzipKb}KB`)
  }
}

if (graphVendor && graphVendor.gzipKb > budgets.graphVendorGzipKb) {
  failures.push(`${graphVendor.name} gzip ${graphVendor.gzipKb.toFixed(2)}KB > ${budgets.graphVendorGzipKb}KB`)
}

console.log('Bundle gzip budget report')
console.log(`total=${totalGzipKb.toFixed(2)}KB budget=${budgets.totalGzipKb}KB`)
for (const asset of assets.slice(0, 8)) {
  console.log(`${asset.name}: raw=${asset.rawKb.toFixed(2)}KB gzip=${asset.gzipKb.toFixed(2)}KB`)
}

if (failures.length) {
  console.error('Bundle budget exceeded:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}
