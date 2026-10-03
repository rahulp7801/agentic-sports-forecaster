import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const reviewed=new Set(['components/PickResults.tsx','components/PickResults.module.css',
  'components/PlayerPortrait.tsx','components/ResearchViews.module.css',
  'lib/pickLabels.ts','lib/pickBoardTypes.ts','lib/pickContext.ts','lib/types.ts']);
const packages=new Set(['react','lucide-react','next/image']);

test('pick results keep both runtime and type source imports inside the reviewed display boundary',()=>{
  const visited=new Set(),queue=['components/PickResults.tsx'];
  while(queue.length) {
    const name=queue.shift();
    if(visited.has(name)) continue;
    assert.ok(reviewed.has(name),'Unreviewed pick results source: '+name);
    visited.add(name);
    if(!/\.tsx?$/.test(name)) continue;
    const file=path.join(frontend,name);
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,
      name.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    function inspect(node) {
      let specifier;
      if(ts.isImportDeclaration(node)||ts.isExportDeclaration(node)) specifier=node.moduleSpecifier;
      if(ts.isImportEqualsDeclaration(node)&&ts.isExternalModuleReference(node.moduleReference))
        specifier=node.moduleReference.expression;
      if(ts.isCallExpression(node)&&(node.expression.kind===ts.SyntaxKind.ImportKeyword||
        ts.isIdentifier(node.expression)&&node.expression.text==='require')) {
        assert.equal(node.arguments.length,1,'Computed pick results import');
        specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)) {
        assert.ok(ts.isLiteralTypeNode(node.argument),'Computed pick results type import');
        specifier=node.argument.literal;
      }
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier),'Computed pick results import');
        const target=specifier.text;
        if(target.startsWith('.')||target.startsWith('@/')) {
          const base=target.startsWith('@/') ? path.join(frontend,target.slice(2)) : path.resolve(path.dirname(file),target);
          const resolved=[base,...['.ts','.tsx','.json','.css'].map(ext=>base+ext)]
            .find(candidate=>fs.existsSync(candidate)&&fs.statSync(candidate).isFile());
          assert.ok(resolved,'Unresolved pick results import: '+target);
          queue.push(path.relative(frontend,resolved).split(path.sep).join('/'));
        } else assert.ok(packages.has(target),'Unreviewed pick results package: '+target);
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  assert.deepEqual([...visited].sort(),[...reviewed].sort());
});

test('the recorded board output declarations emit no runtime imports or logic',()=>{
  const file=path.join(frontend,'lib/pickBoardTypes.ts');
  const emitted=ts.transpileModule(fs.readFileSync(file,'utf8'),{
    compilerOptions:{target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext},fileName:file,
  }).outputText;
  assert.equal(emitted.trim(),'export {};');
});
