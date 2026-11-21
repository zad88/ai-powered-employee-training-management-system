import assert from "node:assert/strict";
import fs from "node:fs";
import Module from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const filename = path.resolve(__dirname, "../src/components/esco-job-skill-review.tsx");
const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const component = new Module(filename);
component.filename = filename;
component.paths = Module._nodeModulePaths(path.dirname(filename));
const originalRequire = component.require.bind(component);
component.require = (name) =>
  name === "../lib/api" ? { authenticatedFetch: () => {} } : originalRequire(name);
component._compile(compiled, filename);
const { EscoJobSkillReview, selectedSkills } = component.exports;

test("review panel labels ESCO suggestions and company titles", () => {
  const html = renderToStaticMarkup(
    React.createElement(EscoJobSkillReview, {
      requirements: [],
      onCreated: () => {},
    })
  );
  assert.match(html, /Company employee job title/);
  assert.match(html, /ESCO skills are suggestions, not approved company requirements/);
});

test("only included skills and their reviewed settings are submitted", () => {
  assert.deepEqual(selectedSkills({
    10: { included: true, required_proficiency: 4, importance: "High" },
    11: { included: false, required_proficiency: 3, importance: "Medium" },
    12: { included: true, required_proficiency: 1, importance: "Low" },
  }), [
    { skill_id: 10, required_proficiency: 4, importance: "High" },
    { skill_id: 12, required_proficiency: 1, importance: "Low" },
  ]);
});

test("no skills are submitted when none are included", () => {
  assert.deepEqual(selectedSkills({
    4: { included: false, required_proficiency: 5, importance: "Critical" },
  }), []);
});
