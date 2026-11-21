import assert from "node:assert/strict";
import fs from "node:fs";
import Module from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
let role = "Training Manager";

function loadComponent(relativePath) {
  const filename = path.join(root, relativePath);
  const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const component = new Module(filename);
  component.filename = filename;
  component.paths = Module._nodeModulePaths(path.dirname(filename));
  const originalRequire = component.require.bind(component);
  component.require = (name) => {
    if (name.endsWith("auth-provider")) return {
      useAuth: () => ({ activeMembership: { role }, user: { id: 1, full_name: "Test User" }, signOut() {} }),
    };
    if (name === "../../lib/api") return { authenticatedFetch() {} };
    if (name === "next/navigation") return { usePathname: () => "/users" };
    if (name === "next/link") return {
      default: ({ children, href, ...props }) => React.createElement("a", { href, ...props }, children),
    };
    return originalRequire(name);
  };
  component._compile(compiled, filename);
  return component.exports;
}

const UserManagementPage = loadComponent("app/users/page.tsx").default;
const { WorkspaceSidebar } = loadComponent("components/workspace-sidebar.tsx");
const AcceptInvitationPage = loadComponent("app/accept-invitation/page.tsx").default;

test("only Training Managers see the management page and navigation", () => {
  for (const candidate of ["Training Manager", "Director", "Manager", "Employee"]) {
    role = candidate;
    const page = renderToStaticMarkup(React.createElement(UserManagementPage));
    const sidebar = renderToStaticMarkup(React.createElement(WorkspaceSidebar));
    assert.equal(page.includes("Invite user"), candidate === "Training Manager");
    assert.equal(sidebar.includes('href="/users"'), candidate === "Training Manager");
    assert.doesNotMatch(sidebar, /<select/);
  }
});

test("invitation page initially announces verification without showing a password form", () => {
  const html = renderToStaticMarkup(React.createElement(AcceptInvitationPage));
  assert.match(html, /role="status"/);
  assert.match(html, /Verifying invitation/);
  assert.doesNotMatch(html, /type="password"/);
});
