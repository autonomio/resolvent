import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { boundedBytes, compatibility, INDEX, loadWorkflow, manifestSchema, parseJson, SOURCE } from '../src/workflow.ts';

const text = '# Workflow\n\nPreserve evidence and explicit user authority.\n';
const bytes = Buffer.from(text);
const manifest = {
  format_version: '1.0', client_protocol: '1.0', workflow_version: '1.0.1',
  source_commit: 'a'.repeat(40), entrypoint: 'WORKFLOW.md',
  files: {'WORKFLOW.md': {
    size: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'),
    git_blob_sha1: createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`), bytes])).digest('hex'),
  }},
};

test('pins all content reads to the one retrieved manifest revision', async () => {
  const seen = [];
  const result = await loadWorkflow(async (url, limit) => {
    seen.push([url, limit]);
    return url === INDEX ? Buffer.from(JSON.stringify(manifest)) : bytes;
  });
  assert.deepEqual(seen, [[INDEX, 65536], [SOURCE + 'a'.repeat(40) + '/workflows/resolvent/WORKFLOW.md', bytes.length]]);
  assert.equal(result.files['WORKFLOW.md'], text);
});

for (const [name, change] of [
  ['unknown fields', m => { m.extra = true; }],
  ['unsupported client', m => { m.client_protocol = '2.0'; }],
  ['branch instead of commit', m => { m.source_commit = 'main'; }],
  ['oversized file', m => { m.files['WORKFLOW.md'].size = 262145; }],
  ['fractional size', m => { m.files['WORKFLOW.md'].size = 1.5; }],
  ['traversal', m => { m.files['../other.md'] = m.files['WORKFLOW.md']; }],
  ['encoded path', m => { m.files['%2e%2e/other.md'] = m.files['WORKFLOW.md']; }],
  ['unlisted entrypoint', m => { m.entrypoint = 'OTHER.md'; }],
  ['unknown file metadata', m => { m.files['WORKFLOW.md'].url = 'https://example.com'; }],
]) test('rejects ' + name, () => {
  const candidate = structuredClone(manifest); change(candidate);
  assert.throws(() => manifestSchema.parse(candidate));
});

test('rejects duplicate keys, including escaped spellings and nested keys', () => {
  for (const input of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"x":{"a":1,"a":2}}'])
    assert.throws(() => parseJson(input));
  assert.deepEqual(parseJson('{"a":[{"a":"{} : \\" key"}],"b":2}'), {a:[{a:'{} : " key'}],b:2});
});

for (const [name, replacement] of [
  ['changed bytes', Buffer.from(text.replace('Preserve', 'Suppress'))],
  ['truncation', bytes.subarray(0, -1)],
  ['extra bytes', Buffer.concat([bytes, Buffer.from('x')])],
]) test('rejects ' + name, async () => {
  await assert.rejects(loadWorkflow(async url => url === INDEX ? Buffer.from(JSON.stringify(manifest)) : replacement));
});

test('checks SHA-256 and Git blob identity independently', async () => {
  for (const field of ['sha256', 'git_blob_sha1']) {
    const candidate = structuredClone(manifest); candidate.files['WORKFLOW.md'][field] = '0'.repeat(field === 'sha256' ? 64 : 40);
    await assert.rejects(loadWorkflow(async url => url === INDEX ? Buffer.from(JSON.stringify(candidate)) : bytes));
  }
});

test('rejects invalid UTF-8 even when content digests match', async () => {
  const invalid = Buffer.from([255]); const candidate = structuredClone(manifest);
  candidate.files['WORKFLOW.md'] = {size:1,sha256:createHash('sha256').update(invalid).digest('hex'),git_blob_sha1:createHash('sha1').update(Buffer.concat([Buffer.from('blob 1\0'),invalid])).digest('hex')};
  await assert.rejects(loadWorkflow(async url => url === INDEX ? Buffer.from(JSON.stringify(candidate)) : invalid));
});

test('bounds streamed response bodies without trusting Content-Length', async () => {
  assert.equal((await boundedBytes(new Response('abcd'), 4)).length, 4);
  await assert.rejects(boundedBytes(new Response('abcde', {headers:{'Content-Length':'1'}}), 4));
});

test('reports supported legacy protocols and unsupported versions without migrating anything', () => {
  for (const version of ['1.0','1.1','1.2']) assert.equal(compatibility('1.0', version).world_protocol_supported, true);
  assert.equal(compatibility('2.0','1.2').client_compatible, false);
  assert.equal(compatibility('1.0','9.0').world_protocol_supported, false);
});
