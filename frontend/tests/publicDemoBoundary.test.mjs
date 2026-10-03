import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const reviewed=new Set(['components/HistoricalFlowDemo.tsx','components/HistoricalFlowDemo.module.css',
  'lib/weekOneDemo.ts','data/week-one-demo-display.json']);

test('the public historical walkthrough imports only its reviewed display sources',()=>{
  const visited=new Set(),queue=['components/HistoricalFlowDemo.tsx'];
  while(queue.length) {
    const name=queue.shift();
    if(visited.has(name)) continue;
    assert.ok(reviewed.has(name),'Unreviewed public demo source: '+name);
    visited.add(name);
    if(!/\.tsx?$/.test(name)) continue;
    const file=path.join(frontend,name);
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,
      name.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    function inspect(node) {
      let specifier;
      if(ts.isImportDeclaration(node)||ts.isExportDeclaration(node)) specifier=node.moduleSpecifier;
      if(ts.isCallExpression(node)&&(node.expression.kind===ts.SyntaxKind.ImportKeyword||
        ts.isIdentifier(node.expression)&&node.expression.text==='require')) {
        assert.equal(node.arguments.length,1,'Computed public demo import');
        specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)&&ts.isLiteralTypeNode(node.argument)) specifier=node.argument.literal;
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier),'Computed public demo import');
        const target=specifier.text;
        if(target.startsWith('.')||target.startsWith('@/')) {
          const base=target.startsWith('@/') ? path.join(frontend,target.slice(2)) : path.resolve(path.dirname(file),target);
          const resolved=[base,...['.ts','.tsx','.json','.css'].map(ext=>base+ext)]
            .find(candidate=>fs.existsSync(candidate)&&fs.statSync(candidate).isFile());
          assert.ok(resolved,'Unresolved public demo import: '+target);
          const relative=path.relative(frontend,resolved).split(path.sep).join('/');
          queue.push(relative);
        }
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  assert.deepEqual([...visited].sort(),[...reviewed].sort());
});
