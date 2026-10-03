import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import {contextWindowText,recentParticipationText} from '../lib/participationDisplay.ts';

test('missing retained windows remain explicitly unknown rather than creating recent evidence',()=>{
  assert.deepEqual(contextWindowText({}),[
    'Dates for these participation groups were not retained in this forecast; their recency is unknown.',
  ]);
  assert.equal(recentParticipationText({}),'A separate 30-day participation summary was not retained in this forecast.');
  assert.deepEqual(contextWindowText({sample_window:{cutoff:'2026-10-14',active:null,absent:null,unknown:null}}),[]);
});

test('recorded participation dates preserve group order, singular days and the existing recency disclosure',()=>{
  const split={sample_window:{cutoff:'2026-10-14',
    active:{oldest:'2026-10-01',newest:'2026-10-13'},
    absent:{oldest:'2026-09-01',newest:'2026-09-14'},
    unknown:{oldest:'2026-09-01',newest:'2026-09-13'}}};
  assert.deepEqual(contextWindowText(split),[
    'Recorded participation: 2026-10-01 to 2026-10-13; latest 1 day before the target game.',
    'Recorded zero minutes: 2026-09-01 to 2026-09-14; latest 30 days before the target game.',
    'Unknown participation: 2026-09-01 to 2026-09-13; latest 31 days before the target game. This group does not establish current form.',
  ]);
});

test('recent summaries retain unknown-game exclusions and incomplete-schedule disclosure',()=>{
  const recent={since:'2026-09-14',cutoff:'2026-10-14',active:{games:1},absent:{games:0},unknown_games:1};
  assert.equal(recentParticipationText({recent_window:recent}),
    '2026-09-14 to 2026-10-14 (exclusive): 2 retrieved games; 1 with unknown participation, excluded from hit rates. Only the latest 40 eligible history games were checked; this is not a complete schedule audit.');
  assert.equal(recentParticipationText({recent_window:{...recent,unknown_games:0}}),
    '2026-09-14 to 2026-10-14 (exclusive): 1 retrieved game; 0 with unknown participation, excluded from hit rates. Only the latest 40 eligible history games were checked; this is not a complete schedule audit.');
});

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const reviewed=new Set(['lib/participationDisplay.ts','lib/types.ts']);

test('participation display runtime and type source closure excludes private validators and research',()=>{
  const visited=new Set(),queue=['lib/participationDisplay.ts'];
  while(queue.length) {
    const name=queue.shift();if(visited.has(name)) continue;
    assert.ok(reviewed.has(name),'Unreviewed participation display source: '+name);visited.add(name);
    const file=path.join(frontend,name);
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
    function inspect(node) {
      let specifier;
      if(ts.isImportDeclaration(node)||ts.isExportDeclaration(node)) specifier=node.moduleSpecifier;
      if(ts.isImportEqualsDeclaration(node)&&ts.isExternalModuleReference(node.moduleReference)) specifier=node.moduleReference.expression;
      if(ts.isCallExpression(node)&&(node.expression.kind===ts.SyntaxKind.ImportKeyword||
        ts.isIdentifier(node.expression)&&node.expression.text==='require')) {
        assert.equal(node.arguments.length,1,'Computed participation display import');specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)) {
        assert.ok(ts.isLiteralTypeNode(node.argument),'Computed participation display type import');specifier=node.argument.literal;
      }
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier),'Computed participation display import');
        const target=specifier.text;
        assert.ok(target.startsWith('.')||target.startsWith('@/'),'Unreviewed participation display package: '+target);
        const base=target.startsWith('@/') ? path.join(frontend,target.slice(2)) : path.resolve(path.dirname(file),target);
        const resolved=[base,...['.ts','.tsx','.json','.css'].map(ext=>base+ext)]
          .find(candidate=>fs.existsSync(candidate)&&fs.statSync(candidate).isFile());
        assert.ok(resolved,'Unresolved participation display import: '+target);
        queue.push(path.relative(frontend,resolved).split(path.sep).join('/'));
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  assert.deepEqual([...visited].sort(),[...reviewed].sort());
});

test('participation display emits no runtime imports and output types emit no implementation',()=>{
  for(const name of reviewed) {
    const file=path.join(frontend,name),emitted=ts.transpileModule(fs.readFileSync(file,'utf8'),{
      compilerOptions:{target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext},fileName:file,
    }).outputText;
    if(name==='lib/types.ts') assert.equal(emitted.trim(),'export {};');
    const source=ts.createSourceFile(name,emitted,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
    function inspect(node) {
      assert.equal(ts.isImportDeclaration(node)||ts.isExportDeclaration(node)&&Boolean(node.moduleSpecifier),false,
        'Runtime participation display import');
      if(ts.isCallExpression(node)) assert.equal(node.expression.kind===ts.SyntaxKind.ImportKeyword||
        ts.isIdentifier(node.expression)&&node.expression.text==='require',false,'Dynamic participation display import');
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
});
