import { JSDOM } from "jsdom";
import vm from "node:vm";
import { describe, expect, it } from "vitest";
import {
  buildImportedRuntimeSrcDoc,
  normalizeImportedHeadAssets,
  normalizeImportedRuntimeSectionTypes,
} from "./importedRuntime";

describe("normalizeImportedHeadAssets", () => {
  it("coerces missing values into a stable head asset shape", () => {
    expect(normalizeImportedHeadAssets(null)).toEqual({
      scriptSrcs: [],
      stylesheetHrefs: [],
      inlineStyles: [],
      inlineScripts: [],
      bodyClassName: "",
    });
  });
});

describe("normalizeImportedRuntimeSectionTypes", () => {
  it("maps imported runtime blocks to the generic frontend renderer", () => {
    const data = {
      content: [
        {
          type: "ImportedHeroSection",
          props: {
            id: "section-1",
            runtimeSource: "const ImportedSection = () => <div />;",
          },
        },
      ],
    };

    expect(normalizeImportedRuntimeSectionTypes(data)).toBe(true);
    expect(data).toEqual({
      content: [
        {
          type: "ImportedRuntimeSection",
          props: {
            id: "section-1",
            runtimeSource: "const ImportedSection = () => <div />;",
            originalType: "ImportedHeroSection",
          },
        },
      ],
    });
  });

  it("leaves non-imported blocks unchanged", () => {
    const data = {
      content: [
        {
          type: "Section",
          props: {
            id: "section-1",
          },
        },
      ],
    };

    expect(normalizeImportedRuntimeSectionTypes(data)).toBe(false);
    expect(data.content[0].type).toBe("Section");
  });
});

describe("buildImportedRuntimeSrcDoc", () => {
  it("embeds the runtime bridge, frame assets, and compiled source", () => {
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-123",
      sectionLabel: "Hero",
      compiledSource: "const ImportedSection = () => React.createElement('div', null, 'Hero');",
      reactUmdSource: "window.React = { createElement: () => null, Fragment: 'fragment' };",
      reactDomUmdSource: "window.ReactDOM = { createRoot: () => ({ render: () => null }) };",
      componentName: "HeroSection",
      sectionTargetId: "hero-section",
      headAssets: {
        stylesheetHrefs: ["https://example.com/styles.css"],
        inlineStyles: ["body { color: red; }"],
      },
    });

    expect(srcDoc).toContain('source: "mos-imported-runtime"');
    expect(srcDoc).toContain("frame-123");
    expect(srcDoc).toContain("https://example.com/styles.css");
    expect(srcDoc).toContain("const ImportedSection = () => React.createElement('div', null, 'Hero');");
    expect(srcDoc).toContain("<title>Hero</title>");
    expect(srcDoc).toContain('source !== "mos-imported-runtime-host"');
    expect(srcDoc).toContain('payload.type === "request-height"');
    expect(srcDoc).toContain('const runtimeFrameId = "frame-123"');
    expect(srcDoc).toContain('const componentName = "HeroSection"');
    expect(srcDoc).toContain('const sectionTargetId = "hero-section"');
    expect(srcDoc).toContain('let textOverrides = [];');
    expect(srcDoc).toContain('let buttonOverrides = [];');
    expect(srcDoc).toContain('let imageOverrides = [];');
    expect(srcDoc).toContain('payload.type !== "update-overrides"');
  });

  it("emits inline scripts that parse cleanly", () => {
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-parse",
      sectionLabel: "Hero",
      compiledSource:
        "const ImportedSection = () => React.createElement('div', {'data-section-id': 'hero'}, 'Hero');",
      reactUmdSource: "window.React = { createElement: () => null, Fragment: 'fragment' };",
      reactDomUmdSource: "window.ReactDOM = { createRoot: () => ({ render: () => null }) };",
      componentName: "ImportedSection",
      sectionTargetId: "hero",
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    expect(scripts.length).toBeGreaterThan(0);

    for (const script of scripts) {
      expect(() => new vm.Script(script)).not.toThrow();
    }
  });

  it("applies text, button, and image overrides to rendered source sections", () => {
    const reactStubSource = `
      var React = window.React = {
        Fragment: Symbol.for("react.fragment"),
        createElement(type, props, ...children) {
          return { type, props: props || {}, children };
        },
      };
    `;
    const reactDomStubSource = `
      var ReactDOM = window.ReactDOM = {
        createRoot(container) {
          const renderNode = (node) => {
            if (node == null || node === false) {
              return document.createTextNode("");
            }
            if (typeof node === "string" || typeof node === "number") {
              return document.createTextNode(String(node));
            }
            if (Array.isArray(node)) {
              const fragment = document.createDocumentFragment();
              node.forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            if (typeof node.type === "function") {
              return renderNode(node.type({ ...(node.props || {}), children: node.children || [] }));
            }
            if (node.type === React.Fragment) {
              const fragment = document.createDocumentFragment();
              (node.children || []).forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            const element = document.createElement(node.type);
            Object.entries(node.props || {}).forEach(([key, value]) => {
              if (value == null || key === "children") return;
              if (key === "className") {
                element.setAttribute("class", String(value));
                return;
              }
              element.setAttribute(key, String(value));
            });
            (node.children || []).flat().forEach((child) => element.appendChild(renderNode(child)));
            return element;
          };
          return {
            render(node) {
              container.replaceChildren(renderNode(node));
            },
          };
        },
      };
    `;
    const compiledSource = `
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "hero-section" },
          React.createElement(
            "h1",
            null,
            "Creatine For ",
            React.createElement("span", null, "Body & Mind"),
          ),
          React.createElement("a", { href: "/buy" }, "TRY OMNI TODAY"),
          React.createElement("img", {
            src: "https://example.com/original.png",
            alt: "Original alt",
          }),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-dom",
      sectionLabel: "Hero",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "hero-section",
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = { postMessage: () => {} };
    context.requestAnimationFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };
    context.cancelAnimationFrame = () => {};
    context.queueMicrotask = (callback: VoidFunction) => callback();
    context.ResizeObserver = undefined;

    for (const script of scripts) {
      new vm.Script(script).runInContext(context);
    }

    dom.window.dispatchEvent(
      new dom.window.MessageEvent("message", {
        data: {
          source: "mos-imported-runtime-host",
          frameId: "frame-dom",
          type: "update-overrides",
          revision: "2",
          textOverrides: [{ originalText: "Creatine For Body & Mind", text: "Power For Recovery\nEvery Day" }],
          buttonOverrides: [{ originalText: "TRY OMNI TODAY", text: "SHOP NOW", href: "/shop" }],
          imageOverrides: [
            {
              originalSrc: "https://example.com/original.png",
              src: "https://example.com/updated.png",
              alt: "Updated alt",
            },
          ],
        },
      }),
    );

    const root = dom.window.document.getElementById("root");
    const heading = root?.querySelector("h1");
    expect(heading?.childNodes[0]?.textContent?.trim()).toBe("Power For Recovery");
    expect(heading?.querySelector("span")?.textContent).toBe("Every Day");

    const link = root?.querySelector("a");
    expect(link?.textContent).toBe("SHOP NOW");
    expect(link?.getAttribute("href")).toBe("/shop");

    const image = root?.querySelector("img");
    expect(image?.getAttribute("src")).toBe("https://example.com/updated.png");
    expect(image?.getAttribute("alt")).toBe("Updated alt");
  });

  it("preserves dynamic price suffixes and emits Medusa buy-now actions for imported purchase buttons", () => {
    const reactStubSource = `
      var React = window.React = {
        Fragment: Symbol.for("react.fragment"),
        createElement(type, props, ...children) {
          return { type, props: props || {}, children };
        },
      };
    `;
    const reactDomStubSource = `
      var ReactDOM = window.ReactDOM = {
        createRoot(container) {
          const renderNode = (node) => {
            if (node == null || node === false) return document.createTextNode("");
            if (typeof node === "string" || typeof node === "number") return document.createTextNode(String(node));
            if (Array.isArray(node)) {
              const fragment = document.createDocumentFragment();
              node.forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            if (typeof node.type === "function") {
              return renderNode(node.type({ ...(node.props || {}), children: node.children || [] }));
            }
            if (node.type === React.Fragment) {
              const fragment = document.createDocumentFragment();
              (node.children || []).forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            const element = document.createElement(node.type);
            Object.entries(node.props || {}).forEach(([key, value]) => {
              if (value == null || key === "children") return;
              if (key === "className") {
                element.setAttribute("class", String(value));
                return;
              }
              element.setAttribute(key, String(value));
            });
            (node.children || []).flat().forEach((child) => element.appendChild(renderNode(child)));
            return element;
          };
          return {
            render(node) {
              container.replaceChildren(renderNode(node));
            },
          };
        },
      };
    `;
    const compiledSource = `
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "product-purchase-section" },
          React.createElement(
            "div",
            { className: "border-primary bg-bg-card" },
            React.createElement("h3", null, "3 Pouches"),
          ),
          React.createElement("button", null, "ADD TO CART - $117"),
        );
    `;
    const postedMessages = [];
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-buy-now",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "product-purchase-section",
      initialButtonOverrides: [
        {
          originalText: "ADD TO CART -",
          text: "BUY NOW -",
          href: "",
          action: "medusa_buy_now",
          selectionStrategy: "omni_selected_tier",
          replaceCart: true,
        },
      ],
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = {
      postMessage(payload: unknown) {
        postedMessages.push(payload);
      },
    };
    context.requestAnimationFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };
    context.cancelAnimationFrame = () => {};
    context.queueMicrotask = (callback: VoidFunction) => callback();
    context.ResizeObserver = undefined;

    for (const script of scripts) {
      new vm.Script(script).runInContext(context);
    }

    const button = dom.window.document.querySelector("button");
    expect(button?.textContent).toBe("BUY NOW");

    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));

    const commerceActionMessage = postedMessages.find(
      (payload) =>
        typeof payload === "object" &&
        payload !== null &&
        (payload as { type?: unknown }).type === "commerce-action",
    ) as Record<string, unknown> | undefined;

    expect(commerceActionMessage).toMatchObject({
      source: "mos-imported-runtime",
      frameId: "frame-buy-now",
      type: "commerce-action",
      action: "medusa_buy_now",
      selectionStrategy: "omni_selected_tier",
      replaceCart: true,
      selectedOfferTitle: "3 Pouches",
      buttonText: "BUY NOW",
    });
  });

  it("applies repeated live text updates to the same composed heading", () => {
    const reactStubSource = `
      var React = window.React = {
        Fragment: Symbol.for("react.fragment"),
        createElement(type, props, ...children) {
          return { type, props: props || {}, children };
        },
      };
    `;
    const reactDomStubSource = `
      var ReactDOM = window.ReactDOM = {
        createRoot(container) {
          const renderNode = (node) => {
            if (node == null || node === false) {
              return document.createTextNode("");
            }
            if (typeof node === "string" || typeof node === "number") {
              return document.createTextNode(String(node));
            }
            if (Array.isArray(node)) {
              const fragment = document.createDocumentFragment();
              node.forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            if (typeof node.type === "function") {
              return renderNode(node.type({ ...(node.props || {}), children: node.children || [] }));
            }
            if (node.type === React.Fragment) {
              const fragment = document.createDocumentFragment();
              (node.children || []).forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            const element = document.createElement(node.type);
            Object.entries(node.props || {}).forEach(([key, value]) => {
              if (value == null || key === "children") return;
              if (key === "className") {
                element.setAttribute("class", String(value));
                return;
              }
              element.setAttribute(key, String(value));
            });
            (node.children || []).flat().forEach((child) => element.appendChild(renderNode(child)));
            return element;
          };
          return {
            render(node) {
              container.replaceChildren(renderNode(node));
            },
            unmount() {
              container.replaceChildren();
            },
          };
        },
      };
    `;
    const compiledSource = `
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "hero-section" },
          React.createElement(
            "h1",
            null,
            "Creatine For ",
            React.createElement("span", null, "Body & Mind"),
          ),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-repeat",
      sectionLabel: "Hero",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "hero-section",
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = { postMessage: () => {} };
    context.requestAnimationFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };
    context.cancelAnimationFrame = () => {};
    context.queueMicrotask = (callback: VoidFunction) => callback();
    context.ResizeObserver = undefined;

    for (const script of scripts) {
      new vm.Script(script).runInContext(context);
    }

    const dispatchUpdate = (text: string) => {
      dom.window.dispatchEvent(
        new dom.window.MessageEvent("message", {
          data: {
            source: "mos-imported-runtime-host",
            frameId: "frame-repeat",
            type: "update-overrides",
            revision: text,
            textOverrides: [{ originalText: "Creatine For Body & Mind", text }],
            buttonOverrides: [],
            imageOverrides: [],
          },
        }),
      );
    };

    dispatchUpdate("Creatine For Body");
    let heading = dom.window.document.querySelector("h1");
    expect(heading?.textContent).toBe("Creatine For Body");

    dispatchUpdate("Creatine");
    heading = dom.window.document.querySelector("h1");
    expect(heading?.textContent).toBe("Creatine");
  });

  it("posts parent hash navigation events for non-commerce Omni CTAs", () => {
    const reactStubSource = `
      var React = window.React = {
        Fragment: Symbol.for("react.fragment"),
        createElement(type, props, ...children) {
          return { type, props: props || {}, children };
        },
      };
    `;
    const reactDomStubSource = `
      var ReactDOM = window.ReactDOM = {
        createRoot(container) {
          const renderNode = (node) => {
            if (node == null || node === false) return document.createTextNode("");
            if (typeof node === "string" || typeof node === "number") return document.createTextNode(String(node));
            if (Array.isArray(node)) {
              const fragment = document.createDocumentFragment();
              node.forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            if (typeof node.type === "function") {
              return renderNode(node.type({ ...(node.props || {}), children: node.children || [] }));
            }
            if (node.type === React.Fragment) {
              const fragment = document.createDocumentFragment();
              (node.children || []).forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            const element = document.createElement(node.type);
            Object.entries(node.props || {}).forEach(([key, value]) => {
              if (value == null || key === "children") return;
              if (key === "className") {
                element.setAttribute("class", String(value));
                return;
              }
              element.setAttribute(key, String(value));
            });
            (node.children || []).flat().forEach((child) => element.appendChild(renderNode(child)));
            return element;
          };
          return { render(node) { container.replaceChildren(renderNode(node)); } };
        },
      };
    `;
    const compiledSource = `
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "hero-section" },
          React.createElement("button", null, "TRY OMNI TODAY"),
        );
    `;
    const postedMessages = [];
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-hash-nav",
      sectionLabel: "Hero",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "hero-section",
      initialButtonOverrides: [
        {
          originalText: "TRY OMNI TODAY",
          text: "TRY OMNI TODAY",
          href: "",
        },
      ],
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = { postMessage(payload: unknown) { postedMessages.push(payload); } };
    context.requestAnimationFrame = (callback: FrameRequestCallback) => { callback(0); return 1; };
    context.cancelAnimationFrame = () => {};
    context.queueMicrotask = (callback: VoidFunction) => callback();
    context.ResizeObserver = undefined;

    for (const script of scripts) {
      new vm.Script(script).runInContext(context);
    }

    const button = dom.window.document.querySelector("button");
    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));

    const navigationMessage = postedMessages.find(
      (payload) => typeof payload === "object" && payload !== null && (payload as { type?: unknown }).type === "navigate-hash",
    ) as Record<string, unknown> | undefined;

    expect(navigationMessage).toMatchObject({
      source: "mos-imported-runtime",
      frameId: "frame-hash-nav",
      type: "navigate-hash",
      hash: "#shop",
    });
  });

  it("matches composed heading text split by line breaks", () => {
    const reactStubSource = `
      var React = window.React = {
        Fragment: Symbol.for("react.fragment"),
        createElement(type, props, ...children) {
          return { type, props: props || {}, children };
        },
      };
    `;
    const reactDomStubSource = `
      var ReactDOM = window.ReactDOM = {
        createRoot(container) {
          const renderNode = (node) => {
            if (node == null || node === false) return document.createTextNode("");
            if (typeof node === "string" || typeof node === "number") return document.createTextNode(String(node));
            if (Array.isArray(node)) {
              const fragment = document.createDocumentFragment();
              node.forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            if (typeof node.type === "function") {
              return renderNode(node.type({ ...(node.props || {}), children: node.children || [] }));
            }
            if (node.type === React.Fragment) {
              const fragment = document.createDocumentFragment();
              (node.children || []).forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            const element = document.createElement(node.type);
            Object.entries(node.props || {}).forEach(([key, value]) => {
              if (value == null || key === "children") return;
              element.setAttribute(key === "className" ? "class" : key, String(value));
            });
            (node.children || []).flat().forEach((child) => element.appendChild(renderNode(child)));
            return element;
          };
          return { render(node) { container.replaceChildren(renderNode(node)); } };
        },
      };
    `;
    const compiledSource = `
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "hero-section" },
          React.createElement(
            "h1",
            null,
            "Creatine For",
            React.createElement("br", null),
            "Body & Mind",
          ),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-linebreak",
      sectionLabel: "Hero",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "hero-section",
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = { postMessage: () => {} };
    context.requestAnimationFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };
    context.cancelAnimationFrame = () => {};
    context.queueMicrotask = (callback: VoidFunction) => callback();
    context.ResizeObserver = undefined;

    for (const script of scripts) {
      new vm.Script(script).runInContext(context);
    }

    dom.window.dispatchEvent(
      new dom.window.MessageEvent("message", {
        data: {
          source: "mos-imported-runtime-host",
          frameId: "frame-linebreak",
          type: "update-overrides",
          revision: "2",
          textOverrides: [{ originalText: "Creatine For Body & Mind", text: "Creatine For Body" }],
        },
      }),
    );

    const heading = dom.window.document.querySelector("h1");
    expect(heading?.textContent).toBe("Creatine For Body");
  });

  it("isolates app-backed target sections instead of leaving the full app mounted", () => {
    const reactStubSource = `
      var React = window.React = {
        Fragment: Symbol.for("react.fragment"),
        createElement(type, props, ...children) {
          return { type, props: props || {}, children };
        },
      };
    `;
    const reactDomStubSource = `
      var ReactDOM = window.ReactDOM = {
        createRoot(container) {
          const renderNode = (node) => {
            if (node == null || node === false) return document.createTextNode("");
            if (typeof node === "string" || typeof node === "number") return document.createTextNode(String(node));
            if (Array.isArray(node)) {
              const fragment = document.createDocumentFragment();
              node.forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            if (typeof node.type === "function") {
              return renderNode(node.type({ ...(node.props || {}), children: node.children || [] }));
            }
            if (node.type === React.Fragment) {
              const fragment = document.createDocumentFragment();
              (node.children || []).forEach((child) => fragment.appendChild(renderNode(child)));
              return fragment;
            }
            const element = document.createElement(node.type);
            Object.entries(node.props || {}).forEach(([key, value]) => {
              if (value == null || key === "children") return;
              element.setAttribute(key === "className" ? "class" : key, String(value));
            });
            (node.children || []).flat().forEach((child) => element.appendChild(renderNode(child)));
            return element;
          };
          return {
            render(node) {
              container.replaceChildren(renderNode(node));
            },
            unmount() {
              container.replaceChildren();
            },
          };
        },
      };
    `;
    const compiledSource = `
      const HeroSection = () => React.createElement("section", { "data-section-id": "hero-section" }, "Hero");
      const FeatureMarquee = () => React.createElement("section", { "data-section-id": "feature-marquee-1-inner" }, "Marquee");
      const FooterSection = () => React.createElement("footer", { "data-section-id": "global-footer" }, "Footer");
      const App = () =>
        React.createElement(
          "div",
          { className: "app-shell" },
          React.createElement(HeroSection, null),
          React.createElement("div", { "data-section-id": "feature-marquee-1" }, React.createElement(FeatureMarquee, null)),
          React.createElement(FooterSection, null),
        );
      const ImportedSection = App;
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-app-isolation",
      sectionLabel: "Feature marquee",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "App",
      sectionTargetId: "feature-marquee-1",
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = { postMessage: () => {} };
    context.requestAnimationFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };
    context.cancelAnimationFrame = () => {};
    context.queueMicrotask = (callback: VoidFunction) => callback();
    context.ResizeObserver = undefined;

    for (const script of scripts) {
      new vm.Script(script).runInContext(context);
    }

    const root = dom.window.document.getElementById("root");
    const sectionIds = Array.from(root?.querySelectorAll("[data-section-id]") ?? []).map((node) =>
      node.getAttribute("data-section-id"),
    );
    expect(sectionIds).toEqual(["feature-marquee-1", "feature-marquee-1-inner"]);
    expect(root?.textContent).toContain("Marquee");
    expect(root?.textContent).not.toContain("Hero");
    expect(root?.textContent).not.toContain("Footer");
  });

  it("stabilizes viewport units against the host viewport height", () => {
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-viewport",
      sectionLabel: "Hero",
      compiledSource: "const ImportedSection = () => React.createElement('div', null, 'Hero');",
      reactUmdSource: "window.React = { createElement: () => null, Fragment: 'fragment' };",
      reactDomUmdSource: "window.ReactDOM = { createRoot: () => ({ render: () => null }) };",
      viewportHeightPx: 812,
      headAssets: {
        inlineStyles: [
          ".hero{min-height:100vh}.hero-mobile{min-height:100dvh}.hero-offset{min-height:calc(100vh - 80px)}",
        ],
      },
    });

    expect(srcDoc).toContain("--mos-imported-vh:812px");
    expect(srcDoc).toContain(".hero{min-height:var(--mos-imported-vh)}");
    expect(srcDoc).toContain(".hero-mobile{min-height:var(--mos-imported-vh)}");
    expect(srcDoc).toContain(".hero-offset{min-height:calc(var(--mos-imported-vh) - 80px)}");
  });
});
