import * as esbuild from 'esbuild';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const [mode,source,output]=process.argv.slice(2);
const root=path.dirname(fileURLToPath(import.meta.url));
await esbuild.build({entryPoints:[path.join(root,`urban-${mode}.mjs`)],bundle:true,format:'iife',platform:'browser',outfile:output,
  nodePaths:[path.resolve(root,'../node_modules')],
  alias:source?{'generated-city':path.resolve(source)}:{},
  plugins:[{name:'generated-import-boundary',setup(b){b.onResolve({filter:/.*/},args=>{
    if(args.importer && path.resolve(args.importer)===path.resolve(source) && args.path!=='three')
      return {errors:[{text:'Generated code may import only three'}]};
  });}}]});
