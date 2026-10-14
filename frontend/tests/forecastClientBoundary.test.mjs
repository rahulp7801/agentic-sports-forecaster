import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const roots=['lib/fetchForecasts.ts','lib/forecastDisplayPacket.ts','lib/forecastDisplayAuthority.ts',
  'lib/signalDisplay.ts','components/Arbitrage.tsx'];
const reviewed=new Set([...roots,'lib/displayMath.ts','lib/types.ts']);
const packages=new Set(['react']);
const privateSources=new Set(['lib/signalMetrics.ts','lib/bestPicks.ts','lib/forecastPage.ts',
  'lib/forecastDisplayProducer.ts','lib/forecastDisplayPacketProducer.ts','lib/pickBoard.ts',
  'lib/python.ts','lib/database.ts','lib/metricCohort.ts','lib/publicBenchmarks.ts','lib/backtestLab.ts',
  'lib/forecastHistory.ts','lib/contextWindow.ts','lib/recentParticipation.ts',
  'data/week-one-demo-history.json','data/nfl-week1-2026.json']);

function importClosure(root,includeTypes) {
  const visited=new Set(),queue=[root];
  while(queue.length) {
    const name=queue.shift();
    if(visited.has(name)) continue;
    assert.ok(!privateSources.has(name),'Private forecast source reached: '+name);
    assert.ok(reviewed.has(name),'Unreviewed forecast client source: '+name);
    visited.add(name);
    if(!/\.tsx?$/.test(name)) continue;
    const file=path.join(frontend,name);
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,
      name.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    function inspect(node) {
      let specifier,typeOnly=false;
      if(ts.isImportDeclaration(node)) {
        specifier=node.moduleSpecifier;
        const clause=node.importClause;
        typeOnly=Boolean(clause?.isTypeOnly||clause&&!clause.name&&clause.namedBindings
          &&ts.isNamedImports(clause.namedBindings)&&clause.namedBindings.elements.length>0
          &&clause.namedBindings.elements.every(item=>item.isTypeOnly));
      }
      if(ts.isExportDeclaration(node)) {
        specifier=node.moduleSpecifier;
        typeOnly=Boolean(node.isTypeOnly||node.exportClause&&ts.isNamedExports(node.exportClause)
          &&node.exportClause.elements.length>0&&node.exportClause.elements.every(item=>item.isTypeOnly));
      }
      if(ts.isImportEqualsDeclaration(node)&&ts.isExternalModuleReference(node.moduleReference)) {
        specifier=node.moduleReference.expression;typeOnly=node.isTypeOnly;
      }
      if(ts.isCallExpression(node)&&(node.expression.kind===ts.SyntaxKind.ImportKeyword||
        ts.isIdentifier(node.expression)&&node.expression.text==='require')) {
        assert.equal(node.arguments.length,1,'Computed forecast client import in '+name);
        specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)) {
        assert.ok(ts.isLiteralTypeNode(node.argument),'Computed forecast client type import in '+name);
        specifier=node.argument.literal;typeOnly=true;
      }
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier),'Computed forecast client import in '+name);
        if(includeTypes||!typeOnly) {
          const target=specifier.text;
          if(target.startsWith('.')||target.startsWith('@/')) {
            const base=target.startsWith('@/') ? path.join(frontend,target.slice(2)) : path.resolve(path.dirname(file),target);
            const candidates=[base,...['.ts','.tsx','.d.ts','.json','.css','.js','.mjs','.cjs'].map(ext=>base+ext),
              ...['.ts','.tsx','.js'].map(ext=>path.join(base,'index'+ext))];
            const resolved=candidates.find(candidate=>fs.existsSync(candidate)&&fs.statSync(candidate).isFile());
            assert.ok(resolved,'Unresolved forecast client import: '+target);
            assert.equal(fs.lstatSync(resolved).isSymbolicLink(),false,'Symlink forecast client import: '+target);
            const relative=path.relative(frontend,fs.realpathSync(resolved)).split(path.sep).join('/');
            assert.ok(!relative.startsWith('../')&&!path.isAbsolute(relative),'Forecast client import escapes frontend: '+target);
            queue.push(relative);
          } else assert.ok(packages.has(target),'Unreviewed forecast client package: '+target);
        }
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  return [...visited].sort();
}

for(const includeTypes of [false,true]) {
  test(`reviewed forecast clients keep ${includeTypes ? 'runtime and type source' : 'runtime'} import closures public`,()=>{
    const closure=new Set(roots.flatMap(root=>importClosure(root,includeTypes)));
    assert.deepEqual([...closure].sort(),[...reviewed].filter(name=>includeTypes||name!=='lib/types.ts').sort());
  });
}

test('forecast output type declarations add no runtime implementation',()=>{
  const file=path.join(frontend,'lib/types.ts');
  const emitted=ts.transpileModule(fs.readFileSync(file,'utf8'),{
    compilerOptions:{target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext},fileName:file,
  }).outputText;
  assert.equal(emitted.trim(),'export {};');
});
