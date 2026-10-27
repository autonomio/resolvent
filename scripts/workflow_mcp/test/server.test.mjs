import test, { mock } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mcpResponse } from '../src/server.ts';
const worker = { fetch: mcpResponse };
import { INDEX } from '../src/workflow.ts';

const url = 'https://resolvent.autonom.io/mcp';
async function rpc(method, params, headers={}) {
  const response = await worker.fetch(new Request(url, {
    method: 'POST', headers: {Host:'resolvent.autonom.io','Content-Type':'application/json',Accept:'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25',...headers},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method,...(params?{params}:{})}),
  }));
  assert.equal(response.status, 200);
  const raw = await response.text();
  return response.headers.get('Content-Type').includes('application/json') ? JSON.parse(raw) :
    raw.split('\n').filter(s=>s.startsWith('data: ')).map(s=>JSON.parse(s.slice(6))).find(p=>p.id===1);
}

test('supports real MCP initialization and lists only the two bounded read tools', async () => {
  const initialized = await rpc('initialize',{protocolVersion:'2025-11-25',capabilities:{},clientInfo:{name:'Resolvent-test',version:'1.0.0'}});
  assert.equal(initialized.result.serverInfo.name,'resolvent-workflows');
  const listed = await rpc('tools/list');
  assert.deepEqual(listed.result.tools.map(t=>t.name).sort(),['check_resolvent_compatibility','get_resolvent_workflow']);
  for (const tool of listed.result.tools) {
    assert.equal(tool.annotations.readOnlyHint,true);
    assert.equal(tool.annotations.destructiveHint,false);
    assert.equal(tool.inputSchema.additionalProperties,false);
  }
});

test('compatibility calls preserve old protocols and expose incompatibility without writes', async () => {
  for (const [client,world,expectedClient,expectedWorld] of [
    ['1.0','1.2',true,true],['1.0','1.0',true,true],['2.0','1.2',false,true],['1.0','9.0',true,false],
  ]) {
    const response = await rpc('tools/call',{name:'check_resolvent_compatibility',arguments:{client_protocol:client,world_submission_protocol:world}});
    assert.equal(response.result.structuredContent.client_compatible,expectedClient);
    assert.equal(response.result.structuredContent.world_protocol_supported,expectedWorld);
  }
});

test('returns only a completely verified workflow packet through the MCP transport', async () => {
  const bytes = Buffer.from('# Public test workflow\n');
  const manifest = {format_version:'1.0',client_protocol:'1.0',workflow_version:'1.0.1',source_commit:'a'.repeat(40),entrypoint:'WORKFLOW.md',files:{'WORKFLOW.md':{
    size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),git_blob_sha1:createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`),bytes])).digest('hex'),
  }}};
  const fetched=[];
  const stub=mock.method(globalThis,'fetch',async (address,options)=>{
    fetched.push(address);assert.equal(options.redirect,'manual');
    assert.equal(Object.hasOwn(options.headers,'Authorization'),false);
    return new Response(address===INDEX?JSON.stringify(manifest):bytes);
  });
  try {
    const result=await rpc('tools/call',{name:'get_resolvent_workflow',arguments:{}});
    assert.equal(result.result.structuredContent.files['WORKFLOW.md'],bytes.toString());
    assert.equal(fetched[1],`https://raw.githubusercontent.com/autonomio/resolvent/${'a'.repeat(40)}/workflows/resolvent/WORKFLOW.md`);
  } finally {stub.mock.restore();}
});

test('upstream redirects fail closed and disclose no partial guidance',async()=>{
  const stub=mock.method(globalThis,'fetch',async()=>new Response(null,{status:302,headers:{Location:'https://example.invalid/other'}}));
  try {
    const result=await rpc('tools/call',{name:'get_resolvent_workflow',arguments:{}});
    assert.equal(result.result.isError,true);
    assert.equal(result.result.structuredContent,undefined);
  } finally {stub.mock.restore();}
});

test('rejects repository/chat arguments and unknown tools before fetching anything',async()=>{
  const stub=mock.method(globalThis,'fetch',async()=>{throw new Error('Unexpected network request');});
  try {
    for (const params of [
      {name:'get_resolvent_workflow',arguments:{repository:'PRIVATE'}},
      {name:'check_resolvent_compatibility',arguments:{client_protocol:'1.0',world_submission_protocol:'1.2',question:'PRIVATE'}},
      {name:'write_world_model',arguments:{}},
    ]) {
      const result=await rpc('tools/call',params);
      assert.ok(result.error || result.result.isError);
    }
    assert.equal(stub.mock.callCount(),0);
  } finally {stub.mock.restore();}
});

test('bounds HTTP bodies and rejects credentials',async()=>{
  const oversized=await worker.fetch(new Request(url,{method:'POST',headers:{Host:'resolvent.autonom.io','Content-Type':'application/json',Accept:'application/json, text/event-stream'},body:'x'.repeat(4097)}));
  assert.equal(oversized.status,413);
  const credentials=await worker.fetch(new Request(url,{headers:{Host:'resolvent.autonom.io',Authorization:'Bearer synthetic-test-only'}}));
  assert.equal(credentials.status,400);
});
