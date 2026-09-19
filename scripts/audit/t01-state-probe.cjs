// Independent source-level probe, NOT a React/browser integration test.
// Executes the actual ProjectDetail pre-render code with hook adapters and
// the installed TanStack QueryClient. No product logic is copied here.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const fromFrontend = createRequire(path.join(root, 'frontend/package.json'));
const ts = fromFrontend('typescript');
const { QueryClient } = fromFrontend('@tanstack/react-query');
const file = 'frontend/src/research/Workspace.tsx';
const source = process.argv[2] ? execFileSync('git', ['show', process.argv[2]+':'+file], {cwd:root,encoding:'utf8'}) : fs.readFileSync(path.join(root,file),'utf8');
const start = source.indexOf('export function ProjectDetail(');
const finish = source.indexOf('\n  return (', start);
assert(start>=0 && finish>start);
const fragment = source.slice(start,finish).replace('export function','function') + '\nreturn {values, base, draft, conflict, edit, submit, adoptLatest};\n}';
const code = ts.transpileModule(fragment, {compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS}}).outputText;
function fixture() {
  const client = new QueryClient({defaultOptions:{queries:{gcTime:Infinity,retry:false}}});
  const original={id:'p',name:'Probe',description:'',stage:'active',status_note:'OLD',next_step:'',revision:1};
  client.setQueryData(['projects'],[original]);
  let cursor=0, slots=[], mutation, query, apiImpl=async()=>[], requests=[];
  const context={exports:{},require:fromFrontend,console, Math,
    useQueryClient:()=>client,
    useRef:(initial)=>{const i=cursor++; if(!(i in slots))slots[i]={current:initial}; return slots[i];},
    useState:(initial)=>{const i=cursor++; if(!(i in slots))slots[i]=initial; return [slots[i], value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];},
    useQuery:(opts)=>{if(opts.queryKey[0]==='projects'){query=opts; return {data:client.getQueryData(['projects']),isPending:false,error:null,refetch:()=>Promise.resolve()};} return {data:[],isPending:false,error:null};},
    useMutation:(opts)=>{mutation=opts; return {mutate:body=>requests.push(body),isPending:false};},
    api:(...args)=>apiImpl(...args), isApiError:(e,status)=>e.status===status,
    toast:{success:()=>{},error:()=>{}}, window:{confirm:()=>true}
  };
  vm.createContext(context); vm.runInContext(code,context);
  return {client,original,requests,render(){cursor=0;return context.ProjectDetail({id:'p'});},success(saved,body){mutation.onSuccess(saved,body);},error(e){mutation.onError(e);},query(){return query.queryFn();},setApi(fn){apiImpl=fn;}};
}
let failed=0;
async function run(name,test){try{await test(); console.log('PASS '+name);}catch(e){failed++;console.log('FAIL '+name+': '+e.message);}}
(async()=>{
await run('successful save updates shown state before slow GET completes',()=>{
 const h=fixture();let s=h.render();s.edit({...s.values,status_note:'SAVED'});s=h.render();s.submit({preventDefault(){}});const body=h.requests.at(-1);h.success({...h.original,...body,revision:2},body);s=h.render();assert.equal(s.values.status_note,'SAVED');assert.equal(s.base,2);s.submit({preventDefault(){}});assert.equal(h.requests.at(-1).status_note,'SAVED');assert.equal(h.requests.at(-1).revision,2);
});
await run('captured old GET response cannot undo successful save',async()=>{
 const h=fixture();let s=h.render();let release;h.setApi(()=>new Promise(resolve=>release=resolve));const pending=h.query();s.edit({...s.values,status_note:'SAVED'});s=h.render();s.submit({preventDefault(){}});const body=h.requests.at(-1);h.success({...h.original,...body,revision:2},body);h.render();release([h.original]);h.client.setQueryData(['projects'],await pending);s=h.render();assert.equal(s.values.status_note,'SAVED');assert.equal(h.client.getQueryData(['projects'])[0].revision,2);
});
await run('typing while PUT waits survives and next save uses new base',()=>{
 const h=fixture();let s=h.render();s.edit({...s.values,status_note:'SENT'});s=h.render();s.submit({preventDefault(){}});const body=h.requests.at(-1);s.edit({...s.values,status_note:'AFTER_SUBMIT'});h.render();h.success({...h.original,...body,revision:2},body);s=h.render();assert.equal(s.values.status_note,'AFTER_SUBMIT');s.submit({preventDefault(){}});assert.equal(h.requests.at(-1).revision,2);assert.equal(h.requests.at(-1).status_note,'AFTER_SUBMIT');
});
await run('new edit after save while GET waits pins saved revision',()=>{
 const h=fixture();let s=h.render();s.edit({...s.values,status_note:'SAVED'});s=h.render();s.submit({preventDefault(){}});const body=h.requests.at(-1);h.success({...h.original,...body,revision:2},body);s=h.render();s.edit({...s.values,next_step:'NEXT'});s=h.render();s.submit({preventDefault(){}});assert.equal(h.requests.at(-1).revision,2);assert.equal(h.requests.at(-1).status_note,'SAVED');
});
await run('409 plus background newer cache preserves draft and baseline',()=>{
 const h=fixture();let s=h.render();s.edit({...s.values,status_note:'DRAFT'});h.render();h.client.setQueryData(['projects'],[{...h.original,status_note:'REMOTE',revision:2}]);h.error({status:409});s=h.render();assert.equal(s.values.status_note,'DRAFT');assert.equal(s.base,1);assert.equal(s.conflict,true);
});
await run('network error callback preserves draft',()=>{
 const h=fixture();let s=h.render();s.edit({...s.values,status_note:'OFFLINE_DRAFT'});h.render();h.error({status:0,message:'Offline'});s=h.render();assert.equal(s.values.status_note,'OFFLINE_DRAFT');assert.equal(s.base,1);
});
console.log(JSON.stringify({source:process.argv[2]||'working-tree',failed}));process.exitCode=failed?1:0;
})();