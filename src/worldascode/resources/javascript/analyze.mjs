import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const {parse}=await import(pathToFileURL(resolve(process.argv[2],'acorn/dist/acorn.mjs')).href);
const source=readFileSync(0,'utf8');
const tree=parse(source,{ecmaVersion:'latest',sourceType:'module'});
const walk=(node,visit)=>{
  if(!node||typeof node!=='object')return;
  if(typeof node.type==='string')visit(node);
  for(const [key,value] of Object.entries(node)){
    if(key==='start'||key==='end')continue;
    if(Array.isArray(value))value.forEach(item=>walk(item,visit));
    else if(value&&typeof value==='object')walk(value,visit);
  }
};
const memberName=node=>!node.computed&&node.property.type==='Identifier'?node.property.name:
  node.computed&&node.property.type==='Literal'&&typeof node.property.value==='string'?node.property.value:null;
const methods=Object.create(null),api=new Set(),imports=[],dynamic=[];
walk(tree,node=>{
  if(node.type==='ImportDeclaration')imports.push(node.source.value);
  if(node.type==='ClassDeclaration'&&node.id?.name==='Builder'){
    const members=node.body.body;
    for(let i=0;i<members.length;i++){
      const method=members[i];
      if(method.type!=='MethodDefinition'||method.static||method.computed)throw Error('UNSUPPORTED_KIT_CLASS_MEMBER');
      const name=method.key.name;
      if(methods[name])throw Error('DUPLICATE_KIT_METHOD');
      const lineStart=source.lastIndexOf('\n',method.start-1)+1;
      const start=source.slice(lineStart,method.start).trim()===''?lineStart:method.start;
      const next=members[i+1];
      let end=method.end;
      if(next){const nextLine=source.lastIndexOf('\n',next.start-1)+1;end=source.slice(nextLine,next.start).trim()===''?nextLine:next.start;}
      const dependencies=new Set();
      walk(method.value,n=>{if(n.type==='MemberExpression'&&n.object.type==='ThisExpression'){const dep=memberName(n);if(dep)dependencies.add(dep);}});
      methods[name]={start,end,dependencies:[...dependencies].sort()};
    }
  }
  if(node.type==='MemberExpression'&&node.object.type==='Identifier'&&node.object.name==='b'){
    const name=memberName(node);
    if(name)api.add(name);else dynamic.push({start:node.start,end:node.end});
  }
});
console.log(JSON.stringify({methods,public_methods:Object.keys(methods).filter(n=>n!=='constructor'&&!n.startsWith('_')&&n!=='finish'),
  api_methods:[...api].sort(),dynamic_api_access:dynamic.length>0,imports}));
