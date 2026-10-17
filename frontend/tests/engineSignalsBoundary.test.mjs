import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const displaySources=['lib/engineSignals.ts','lib/engineTransport.ts','lib/publicCache.ts',
  'lib/publicRequest.ts','lib/forecastDisplayPacket.ts','lib/forecastDisplayAuthority.ts','lib/signalDisplay.ts'];
const accessSources=['lib/ownerEngineRead.ts','lib/ownerAccess.ts','lib/ownerPolicy.ts'];

// Keep the exact reviewed source graph: no private producers, raw records, SQL,
// history reconstruction, qualification/ranking helpers or model artifacts.
function importClosure(root,includeTypes,reviewed,packages) {
  const visited=new Set(),queue=[root];
  while(queue.length) {
    const name=queue.shift();if(visited.has(name)) continue;
    assert.ok(reviewed.has(name),'Unreviewed engine display source: '+name);
    visited.add(name);
    const file=path.join(frontend,name);
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,
      name.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    assert.equal(source.parseDiagnostics.length,0,'Invalid engine display source: '+name);
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
        assert.equal(node.arguments.length,1,'Computed engine display import in '+name);
        specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)) {
        assert.ok(ts.isLiteralTypeNode(node.argument),'Computed engine display type import in '+name);
        specifier=node.argument.literal;typeOnly=true;
      }
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier),'Computed engine display import in '+name);
        if(includeTypes||!typeOnly) {
          const target=specifier.text;
          if(target.startsWith('.')||target.startsWith('@/')) {
            const base=target.startsWith('@/') ? path.join(frontend,target.slice(2)) : path.resolve(path.dirname(file),target);
            const candidates=[base,...['.ts','.tsx','.d.ts','.json','.css','.js','.mjs','.cjs'].map(ext=>base+ext),
              ...['.ts','.tsx','.js'].map(ext=>path.join(base,'index'+ext))];
            const resolved=candidates.find(candidate=>fs.existsSync(candidate)&&fs.statSync(candidate).isFile());
            assert.ok(resolved,'Unresolved engine display import: '+target);
            assert.equal(fs.lstatSync(resolved).isSymbolicLink(),false,'Symlink engine display import: '+target);
            const relative=path.relative(frontend,fs.realpathSync(resolved)).split(path.sep).join('/');
            assert.ok(!relative.startsWith('../')&&!path.isAbsolute(relative),'Engine display import escapes frontend: '+target);
            queue.push(relative);
          } else assert.ok(packages.has(target),'Unreviewed engine display package: '+target);
        }
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  return [...visited].sort();
}

for(const includeTypes of [false,true]) {
  const label=includeTypes ? 'runtime and type source' : 'runtime';
  test(`the signals engine adapter keeps its ${label} closure inside the public display contract`,()=>{
    const reviewed=new Set([...displaySources,...(includeTypes ? ['lib/types.ts'] : [])]);
    assert.deepEqual(importClosure('lib/engineSignals.ts',includeTypes,reviewed,new Set()),[...reviewed].sort());
  });
  test(`the owner engine wrapper keeps its ${label} closure inside reviewed access and display sources`,()=>{
    const reviewed=new Set([...displaySources,...accessSources,...(includeTypes ? ['lib/types.ts'] : [])]);
    const packages=new Set(['server-only','next/server.js','next-auth/jwt']);
    assert.deepEqual(importClosure('lib/ownerEngineRead.ts',includeTypes,reviewed,packages),[...reviewed].sort());
  });
}
