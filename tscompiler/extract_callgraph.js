const fs = require("fs");
const path = require("path");
const ts = require("typescript");

function parseArgs(argv) {
  const args = { project: ".", out: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--project" || a === "-p") {
      args.project = argv[i + 1];
      i++;
      continue;
    }
    if (a === "--out" || a === "-o") {
      args.out = argv[i + 1];
      i++;
      continue;
    }
    if (a === "--help" || a === "-h") {
      args.help = true;
      continue;
    }
  }
  return args;
}

function isInNodeModules(filePath) {
  return filePath.split(path.sep).includes("node_modules");
}

function isProbablyGenerated(filePath) {
  const parts = filePath.split(path.sep);
  const deny = new Set(["dist", "build", "out", ".next", ".turbo", "coverage"]);
  return parts.some((p) => deny.has(p));
}

function createProgram(projectRoot) {
  const configPath = ts.findConfigFile(projectRoot, ts.sys.fileExists, "tsconfig.json");
  if (configPath) {
    const read = ts.readConfigFile(configPath, ts.sys.readFile);
    if (read.error) {
      throw new Error(ts.formatDiagnosticsWithColorAndContext([read.error], {
        getCanonicalFileName: (f) => f,
        getCurrentDirectory: () => projectRoot,
        getNewLine: () => "\n",
      }));
    }
    const parsed = ts.parseJsonConfigFileContent(read.config, ts.sys, path.dirname(configPath), undefined, configPath);
    const host = ts.createCompilerHost(parsed.options, true);
    const program = ts.createProgram(parsed.fileNames, parsed.options, host);
    return { program, rootDir: path.dirname(configPath) };
  }

  const files = ts.sys.readDirectory(projectRoot, [".ts", ".tsx"], undefined, undefined);
  const fileNames = files
    .map((f) => path.resolve(f))
    .filter((f) => !f.endsWith(".d.ts"))
    .filter((f) => !isInNodeModules(f))
    .filter((f) => !isProbablyGenerated(f));

  const options = {
    allowJs: false,
    checkJs: false,
    skipLibCheck: true,
    noResolve: false,
    target: ts.ScriptTarget.ESNext,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.NodeJs,
    jsx: ts.JsxEmit.Preserve,
    esModuleInterop: true,
    allowSyntheticDefaultImports: true,
    resolveJsonModule: true,
    strict: false,
  };
  const host = ts.createCompilerHost(options, true);
  const program = ts.createProgram(fileNames, options, host);
  return { program, rootDir: projectRoot };
}

function getLine(sourceFile, pos) {
  return sourceFile.getLineAndCharacterOfPosition(pos).line + 1;
}

function getNodeText(sourceFile, node) {
  return sourceFile.text.slice(node.getStart(sourceFile), node.getEnd());
}

function nearestNamedClass(node) {
  let cur = node;
  while (cur) {
    if (ts.isClassDeclaration(cur) && cur.name) {
      return cur.name.text;
    }
    cur = cur.parent;
  }
  return null;
}

function exportFlags(node) {
  const flags = ts.getCombinedModifierFlags(node);
  const isExported = (flags & ts.ModifierFlags.Export) !== 0;
  const isDefaultExport = (flags & ts.ModifierFlags.Default) !== 0;
  return { isExported, isDefaultExport };
}

function makeId(relFile, start, end, kind, name) {
  return `${relFile}:${start}:${end}:${kind}:${name}`;
}

function shouldIncludeSourceFile(sf) {
  if (sf.isDeclarationFile) return false;
  const fp = sf.fileName;
  if (isInNodeModules(fp)) return false;
  if (isProbablyGenerated(fp)) return false;
  return true;
}

function collectFunctions(program, projectRoot) {
  const checker = program.getTypeChecker();
  const symbols = new Map();
  const declKeyToId = new Map();

  function addMapping(sf, declNode, id) {
    const key = `${path.resolve(sf.fileName)}:${declNode.getStart(sf)}:${declNode.getEnd()}`;
    declKeyToId.set(key, id);
  }

  function record(sf, recordNode, declNodes, name, kind, container) {
    const relFile = path.relative(projectRoot, sf.fileName);
    const start = recordNode.getStart(sf);
    const end = recordNode.getEnd();
    const startLine = getLine(sf, start);
    const endLine = getLine(sf, Math.max(start, end - 1));
    const ef = exportFlags(recordNode);
    const id = makeId(relFile, startLine, endLine, kind, name);
    const code = getNodeText(sf, recordNode);
    symbols.set(id, {
      id,
      name,
      kind,
      container,
      file: relFile,
      start_line: startLine,
      end_line: endLine,
      is_exported: ef.isExported,
      is_default_export: ef.isDefaultExport,
      code,
      calls: [],
    });
    for (const dn of declNodes) addMapping(sf, dn, id);
    return id;
  }

  for (const sf of program.getSourceFiles()) {
    if (!shouldIncludeSourceFile(sf)) continue;

    const visit = (node) => {
      if (ts.isFunctionDeclaration(node) && node.body && node.name) {
        record(sf, node, [node], node.name.text, "function", null);
      } else if (ts.isMethodDeclaration(node) && node.body && node.name) {
        const name = node.name.getText(sf);
        const cls = nearestNamedClass(node);
        record(sf, node, [node], name, "method", cls);
      } else if (ts.isVariableStatement(node)) {
        for (const decl of node.declarationList.declarations) {
          if (!ts.isIdentifier(decl.name)) continue;
          if (!decl.initializer) continue;
          if (!ts.isArrowFunction(decl.initializer) && !ts.isFunctionExpression(decl.initializer)) continue;
          const name = decl.name.text;
          record(sf, node, [decl, decl.initializer], name, "variable_function", null);
        }
      } else if (ts.isPropertyAssignment(node)) {
        const init = node.initializer;
        if (init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) {
          const name = node.name.getText(sf);
          record(sf, node, [node, init], name, "property_function", null);
        }
      }
      ts.forEachChild(node, visit);
    };
    ts.forEachChild(sf, visit);
  }

  function resolveCallTargetIds(sf, expr) {
    let sym = null;
    if (ts.isIdentifier(expr)) sym = checker.getSymbolAtLocation(expr);
    else if (ts.isPropertyAccessExpression(expr)) {
      sym = checker.getSymbolAtLocation(expr.name) || checker.getSymbolAtLocation(expr);
    } else {
      sym = checker.getSymbolAtLocation(expr);
    }
    if (!sym) return [];
    if ((sym.flags & ts.SymbolFlags.Alias) !== 0) {
      const aliased = checker.getAliasedSymbol(sym);
      if (aliased) sym = aliased;
    }
    const decls = sym.getDeclarations() || [];
    const ids = [];
    for (const d of decls) {
      const df = d.getSourceFile();
      if (!shouldIncludeSourceFile(df)) continue;
      const key = `${path.resolve(df.fileName)}:${d.getStart(df)}:${d.getEnd()}`;
      const id = declKeyToId.get(key);
      if (id) ids.push(id);
    }
    return ids;
  }

  for (const sf of program.getSourceFiles()) {
    if (!shouldIncludeSourceFile(sf)) continue;
    const relFile = path.relative(projectRoot, sf.fileName);

    function attachCalls(fnId, bodyNode) {
      const seen = new Set();
      const walk = (node) => {
        if (ts.isCallExpression(node)) {
          const exprText = node.expression.getText(sf);
          const targets = resolveCallTargetIds(sf, node.expression);
          for (const tid of targets) {
            const k = `${exprText}::${tid}`;
            if (seen.has(k)) continue;
            seen.add(k);
            const fn = symbols.get(fnId);
            if (fn) fn.calls.push({ expr: exprText, target_id: tid });
          }
        }
        ts.forEachChild(node, walk);
      };
      ts.forEachChild(bodyNode, walk);
    }

    const visit = (node) => {
      if (ts.isFunctionDeclaration(node) && node.body && node.name) {
        const startLine = getLine(sf, node.getStart(sf));
        const endLine = getLine(sf, Math.max(node.getStart(sf), node.getEnd() - 1));
        const fnId = makeId(relFile, startLine, endLine, "function", node.name.text);
        attachCalls(fnId, node.body);
      } else if (ts.isMethodDeclaration(node) && node.body && node.name) {
        const name = node.name.getText(sf);
        const startLine = getLine(sf, node.getStart(sf));
        const endLine = getLine(sf, Math.max(node.getStart(sf), node.getEnd() - 1));
        const fnId = makeId(relFile, startLine, endLine, "method", name);
        attachCalls(fnId, node.body);
      } else if (ts.isVariableStatement(node)) {
        for (const decl of node.declarationList.declarations) {
          if (!ts.isIdentifier(decl.name)) continue;
          if (!decl.initializer) continue;
          if (!ts.isArrowFunction(decl.initializer) && !ts.isFunctionExpression(decl.initializer)) continue;
          const name = decl.name.text;
          const startLine = getLine(sf, node.getStart(sf));
          const endLine = getLine(sf, Math.max(node.getStart(sf), node.getEnd() - 1));
          const fnId = makeId(relFile, startLine, endLine, "variable_function", name);
          if (decl.initializer.body) attachCalls(fnId, decl.initializer.body);
        }
      } else if (ts.isPropertyAssignment(node)) {
        const init = node.initializer;
        if (init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) {
          const name = node.name.getText(sf);
          const startLine = getLine(sf, node.getStart(sf));
          const endLine = getLine(sf, Math.max(node.getStart(sf), node.getEnd() - 1));
          const fnId = makeId(relFile, startLine, endLine, "property_function", name);
          if (init.body) attachCalls(fnId, init.body);
        }
      }
      ts.forEachChild(node, visit);
    };
    ts.forEachChild(sf, visit);
  }

  return Array.from(symbols.values());
}

function writeJsonl(records, outPath) {
  const writer = outPath ? fs.createWriteStream(outPath, { encoding: "utf8" }) : process.stdout;
  for (const r of records) {
    writer.write(JSON.stringify(r) + "\n");
  }
  if (outPath) writer.end();
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    process.stdout.write("Usage: node extract_callgraph.js --project <repo_root> --out <out.jsonl>\\n");
    process.exit(0);
  }
  const projectRoot = path.resolve(args.project);
  const { program, rootDir } = createProgram(projectRoot);
  const records = collectFunctions(program, rootDir);
  writeJsonl(records, args.out);
}

main();

