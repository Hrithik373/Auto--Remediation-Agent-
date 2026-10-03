// Compiles frontend/schemas/pydantic-schemas.json (written by ../../scripts/export_schemas.py) into
// src/api/types.ts. Part of `npm run types` / `make types`. See CLAUDE.md's frontend addendum:
// types.ts is generated, never hand-edited.
import { compile } from "json-schema-to-typescript";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const schemaPath = path.join(__dirname, "..", "schemas", "pydantic-schemas.json");
const outPath = path.join(__dirname, "..", "src", "api", "types.ts");

const banner = `/**
 * GENERATED FILE -- do not hand-edit.
 * Source: src/sentinel/schemas/*.py (Pydantic v2)
 * Regenerate: \`npm run types\` (frontend/) or \`make types\` (repo root).
 */

`;

async function main() {
  const schema = JSON.parse(readFileSync(schemaPath, "utf-8"));

  const ts = await compile(schema, "SentinelSchemas", {
    unreachableDefinitions: true, // emit an interface for every model, not just ones the (empty) root references
    additionalProperties: false,
    bannerComment: "",
    style: { singleQuote: false },
  });

  mkdirSync(path.dirname(outPath), { recursive: true });
  writeFileSync(outPath, banner + ts);
  console.log(`wrote ${outPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
