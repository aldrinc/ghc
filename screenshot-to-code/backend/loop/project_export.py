import json
import re
import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path

from prompts.prompt_types import Stack


@dataclass(frozen=True)
class ProjectExportPaths:
    project_dir: str
    app_file_path: str


def export_project_artifact(
    *,
    stack: Stack,
    code: str,
    project_dir: Path,
) -> ProjectExportPaths | None:
    if stack != "react_tailwind":
        return None

    exported = _export_react_tailwind_project(code=code, project_dir=project_dir)
    return ProjectExportPaths(
        project_dir=str(project_dir),
        app_file_path=str(exported / "src" / "App.tsx"),
    )


def _export_react_tailwind_project(*, code: str, project_dir: Path) -> Path:
    title = _extract_title(code)
    head_links = _extract_head_links(code)
    body_class = _extract_body_class(code)
    style_blocks = _extract_style_blocks(code)
    tailwind_config = _extract_tailwind_config(code)
    jsx_source = _extract_babel_source(code)

    jsx_source = _strip_react_dom_bootstrap(jsx_source).rstrip()
    if "const App" not in jsx_source and "function App" not in jsx_source:
        raise ValueError(
            "React Tailwind export could not find an App component in the generated output."
        )

    if project_dir.exists():
        shutil.rmtree(project_dir)
    (project_dir / "src").mkdir(parents=True, exist_ok=True)

    _write_file(project_dir / "package.json", _build_package_json())
    _write_file(project_dir / "tsconfig.json", _build_tsconfig())
    _write_file(project_dir / "tsconfig.node.json", _build_tsconfig_node())
    _write_file(project_dir / "vite.config.ts", _build_vite_config())
    _write_file(project_dir / "postcss.config.js", _build_postcss_config())
    _write_file(
        project_dir / "tailwind.config.js",
        _build_tailwind_config_file(tailwind_config),
    )
    _write_file(project_dir / "index.html", _build_index_html(title, head_links, body_class))
    _write_file(project_dir / "src" / "vite-env.d.ts", '/// <reference types="vite/client" />\n')
    _write_file(project_dir / "src" / "main.tsx", _build_main_tsx())
    _write_file(project_dir / "src" / "index.css", _build_index_css(style_blocks))
    _write_file(project_dir / "src" / "App.tsx", _build_app_tsx(jsx_source))

    return project_dir


def _write_file(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _extract_title(code: str) -> str:
    match = re.search(r"<title>(.*?)</title>", code, re.IGNORECASE | re.DOTALL)
    if match is None:
        return "Generated App"
    return html_unescape(match.group(1).strip()) or "Generated App"


def _extract_head_links(code: str) -> list[str]:
    links = re.findall(r"(<link\b[^>]*?>)", code, re.IGNORECASE)
    filtered: list[str] = []
    for link in links:
        lower_link = link.lower()
        if "tailwindcss.com" in lower_link:
            continue
        if "react-dom" in lower_link or "react.development.js" in lower_link:
            continue
        if "@babel/standalone" in lower_link:
            continue
        filtered.append(link.strip())
    return filtered


def _extract_body_class(code: str) -> str:
    match = re.search(r"<body\b[^>]*class=[\"']([^\"']*)[\"']", code, re.IGNORECASE)
    if match is None:
        return ""
    return match.group(1).strip()


def _extract_style_blocks(code: str) -> list[str]:
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", code, re.IGNORECASE | re.DOTALL)
    return [textwrap.dedent(block).strip() for block in blocks if block.strip()]


def _extract_tailwind_config(code: str) -> str:
    marker = "tailwind.config"
    marker_index = code.find(marker)
    if marker_index == -1:
        raise ValueError(
            "React Tailwind export could not find the inline tailwind.config block."
        )
    equals_index = code.find("=", marker_index)
    brace_index = code.find("{", equals_index)
    if equals_index == -1 or brace_index == -1:
        raise ValueError(
            "React Tailwind export found tailwind.config but could not parse its object literal."
        )
    return _extract_balanced_braces(code, brace_index)


def _extract_babel_source(code: str) -> str:
    match = re.search(
        r"<script[^>]*type=[\"']text/babel[\"'][^>]*>(.*?)</script>",
        code,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise ValueError(
            "React Tailwind export could not find a <script type=\"text/babel\"> block."
        )
    return textwrap.dedent(match.group(1)).strip()


def _strip_react_dom_bootstrap(source: str) -> str:
    stripped = source
    bootstrap_pattern = re.compile(
        r"\n?\s*const\s+root\s*=\s*ReactDOM\.createRoot\([\s\S]*?$",
        re.MULTILINE,
    )
    stripped = re.sub(bootstrap_pattern, "", stripped).rstrip()
    stripped = re.sub(
        r"\n?\s*ReactDOM\.render\([\s\S]*?$",
        "",
        stripped,
        flags=re.MULTILINE,
    ).rstrip()
    return stripped


def _extract_balanced_braces(source: str, brace_start: int) -> str:
    depth = 0
    in_single = False
    in_double = False
    in_template = False
    in_line_comment = False
    in_block_comment = False
    escape = False

    for index in range(brace_start, len(source)):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
            continue

        if in_single:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_single = False
            continue

        if in_double:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_double = False
            continue

        if in_template:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "`":
                in_template = False
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            continue
        if char == "'":
            in_single = True
            continue
        if char == '"':
            in_double = True
            continue
        if char == "`":
            in_template = True
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start : index + 1]

    raise ValueError("Could not find the end of a balanced object literal.")


def _build_package_json() -> str:
    payload = {
        "name": "validated-loop-react-export",
        "private": True,
        "version": "0.0.0",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "tsc && vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "react": "^18.2.0",
            "react-dom": "^18.2.0",
        },
        "devDependencies": {
            "@types/react": "^18.2.15",
            "@types/react-dom": "^18.2.7",
            "@vitejs/plugin-react": "^4.0.3",
            "autoprefixer": "^10.4.16",
            "postcss": "^8.4.31",
            "tailwindcss": "^3.3.5",
            "typescript": "^5.0.2",
            "vite": "^4.4.5",
        },
    }
    return json.dumps(payload, indent=2)


def _build_tsconfig() -> str:
    return textwrap.dedent(
        """
        {
          "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": true,
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "skipLibCheck": true,
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": true,
            "resolveJsonModule": true,
            "isolatedModules": true,
            "noEmit": true,
            "jsx": "react-jsx",
            "strict": true,
            "noUnusedLocals": false,
            "noUnusedParameters": false,
            "noFallthroughCasesInSwitch": true
          },
          "include": ["src"],
          "references": [{ "path": "./tsconfig.node.json" }]
        }
        """
    ).strip()


def _build_tsconfig_node() -> str:
    return textwrap.dedent(
        """
        {
          "compilerOptions": {
            "composite": true,
            "skipLibCheck": true,
            "module": "ESNext",
            "moduleResolution": "bundler",
            "allowSyntheticDefaultImports": true
          },
          "include": ["vite.config.ts"]
        }
        """
    ).strip()


def _build_vite_config() -> str:
    return textwrap.dedent(
        """
        import { defineConfig } from "vite";
        import react from "@vitejs/plugin-react";

        export default defineConfig({
          plugins: [react()],
        });
        """
    ).strip()


def _build_postcss_config() -> str:
    return textwrap.dedent(
        """
        export default {
          plugins: {
            tailwindcss: {},
            autoprefixer: {},
          },
        };
        """
    ).strip()


def _build_tailwind_config_file(tailwind_config: str) -> str:
    return textwrap.dedent(
        f"""
        /** @type {{import('tailwindcss').Config}} */
        const generatedTailwindConfig = {tailwind_config};

        export default {{
          content: ["./index.html", "./src/**/*{{ts,tsx}}"],
          ...generatedTailwindConfig,
        }};
        """
    ).strip()


def _build_index_html(title: str, head_links: list[str], body_class: str) -> str:
    links_block = "\n".join(f"    {link}" for link in head_links)
    body_class_attr = f' class="{body_class}"' if body_class else ""
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "  <head>",
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f"    <title>{html_escape(title)}</title>",
    ]
    if links_block:
        parts.append(links_block)
    parts.extend(
        [
            "  </head>",
            f"  <body{body_class_attr}>",
            '    <div id="root"></div>',
            '    <script type="module" src="/src/main.tsx"></script>',
            "  </body>",
            "</html>",
        ]
    )
    return "\n".join(parts)


def _build_main_tsx() -> str:
    return textwrap.dedent(
        """
        import React from "react";
        import ReactDOM from "react-dom/client";
        import App from "./App.tsx";
        import "./index.css";

        ReactDOM.createRoot(document.getElementById("root")!).render(
          <React.StrictMode>
            <App />
          </React.StrictMode>
        );
        """
    ).strip()


def _build_index_css(style_blocks: list[str]) -> str:
    parts = [
        "@tailwind base;",
        "@tailwind components;",
        "@tailwind utilities;",
    ]
    if style_blocks:
        parts.append("")
        parts.append("\n\n".join(style_blocks))
    return "\n".join(parts)


def _build_app_tsx(jsx_source: str) -> str:
    app_source = jsx_source.rstrip()
    if not app_source.endswith("export default App;"):
        app_source = app_source + "\n\nexport default App;"
    return textwrap.dedent(
        f"""
        // @ts-nocheck
        import React from "react";

        {app_source}
        """
    ).strip()


def html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def html_unescape(value: str) -> str:
    return (
        value.replace("&quot;", '"')
        .replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
    )
