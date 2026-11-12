// Compile only: model-generated code is NEVER executed by Node.
import * as esbuild from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
const [source, output] = process.argv.slice(2);
const mode = process.argv[4] || 'worker';
const root = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(?=[A-Za-z]:)/, ''));
const entry = path.join(root, mode === 'viewer' ? 'viewer.mjs' : 'worker.mjs');
await esbuild.build({entryPoints:[entry], bundle:true, format:'iife', platform:'browser', outfile:output,
  alias: {'generated-building': path.resolve(source)},
  plugins: [{name:'limit-generated-imports', setup(build) {
    build.onResolve({filter:/.*/}, args => {
      if (path.resolve(args.importer || '.') === path.resolve(source) && args.path !== 'three') {
        return {errors:[{text:'Generated code may import only three'}]};
      }
    });
  }}]});
