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

  it("applies text, button, and image overrides to rendered source sections", async () => {
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
    await Promise.resolve();

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

  it("binds icon-only navigation buttons by aria-label without replacing their contents", async () => {
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
      const AccountIcon = () => React.createElement("svg", { "data-icon": "account" });
      const ImportedSection = () =>
        React.createElement(
          "header",
          { "data-section-id": "global-header" },
          React.createElement(
            "button",
            { type: "button", "aria-label": "Account" },
            React.createElement(AccountIcon),
          ),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-icon",
      sectionLabel: "Header",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "global-header",
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const postedMessages: unknown[] = [];
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = { postMessage: (payload: unknown) => postedMessages.push(payload) };
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
          frameId: "frame-icon",
          type: "update-overrides",
          revision: "2",
          textOverrides: [],
          buttonOverrides: [{ originalText: "Account", text: "Account", href: "account" }],
          imageOverrides: [],
        },
      }),
    );
    await Promise.resolve();

    const button = dom.window.document.querySelector("button");
    expect(button?.getAttribute("aria-label")).toBe("Account");
    expect(button?.querySelector("svg")?.getAttribute("data-icon")).toBe("account");

    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    expect(postedMessages).toContainEqual(
      expect.objectContaining({
        source: "mos-imported-runtime",
        frameId: "frame-icon",
        type: "navigate",
        href: "account",
      }),
    );
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
    expect(button?.textContent).toBe("BUY NOW - $117");

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
      buttonText: "BUY NOW - $117",
    });
  });

  it("preserves the original offer title when copy overrides rewrite the selected tier heading", async () => {
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
      frameId: "frame-buy-now-copy-overrides",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "product-purchase-section",
      initialTextOverrides: [
        {
          originalText: "3 Pouches",
          text: "Reclaim Your Brain with Creatine-Powered Energy",
        },
      ],
      initialButtonOverrides: [
        {
          originalText: "ADD TO CART -",
          text: "RESTORE CLARITY NOW",
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
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(button?.textContent).toBe("RESTORE CLARITY NOW $117");

    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    await Promise.resolve();

    const commerceActionMessage = postedMessages.find(
      (payload) =>
        typeof payload === "object" &&
        payload !== null &&
        (payload as { type?: unknown }).type === "commerce-action",
    ) as Record<string, unknown> | undefined;

    expect(commerceActionMessage).toMatchObject({
      source: "mos-imported-runtime",
      frameId: "frame-buy-now-copy-overrides",
      type: "commerce-action",
      action: "medusa_buy_now",
      selectionStrategy: "omni_selected_tier",
      replaceCart: true,
      selectedOfferTitle: "3 Pouches",
      buttonText: "RESTORE CLARITY NOW $117",
    });
  });

  it("hydrates imported purchase cards with live runtime variant pricing", async () => {
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
            { className: "relative cursor-pointer border-2 rounded-[16px] p-5 transition-all flex justify-between items-center border-primary bg-bg-card" },
            React.createElement("div", null, React.createElement("h3", null, "2-Book Bundle")),
            React.createElement(
              "div",
              { className: "text-right" },
              React.createElement("div", null, "$177"),
              React.createElement("div", null, "$117"),
            ),
          ),
          React.createElement(
            "div",
            { className: "relative cursor-pointer border-2 rounded-[16px] p-5 transition-all flex justify-between items-center border-black/10 bg-surface" },
            React.createElement("div", null, React.createElement("h3", null, "Single Book")),
            React.createElement(
              "div",
              { className: "text-right" },
              React.createElement("div", null, "$49"),
            ),
          ),
          React.createElement("button", null, "Get Your Handbook $117"),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-purchase-runtime",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ProductPurchaseSection",
      sectionTargetId: "product-purchase-section",
      initialButtonOverrides: [
        {
          originalText: "Get Your Handbook",
          text: "Get Your Handbook",
          href: "",
          action: "medusa_buy_now",
          selectionStrategy: "omni_selected_tier",
          replaceCart: true,
        },
      ],
      purchaseRuntimeData: {
        ctaBaseLabel: "Get Your Handbook",
        variants: [
          { title: "Single Book", priceLabel: "$49" },
          { title: "2-Book Bundle", priceLabel: "$88", compareAtLabel: "$98" },
          { title: "3-Book Bundle", priceLabel: "$119", compareAtLabel: "$147" },
        ],
      },
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

    await new Promise((resolve) => setTimeout(resolve, 100));
    const bodyText = dom.window.document.body.textContent || "";
    expect(bodyText).toContain("$88");
    expect(bodyText).toContain("$98");
    expect(bodyText).toContain("Get Your Handbook $88");
    expect(bodyText).not.toContain("$177");
  });

  it("matches translated purchase tier labels to runtime variants", async () => {
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
            { className: "relative cursor-pointer border-2 rounded-[16px] p-5 transition-all flex justify-between items-center border-primary bg-bg-card" },
            React.createElement("div", null, React.createElement("h3", null, "2-Book Bundle")),
            React.createElement("div", { className: "text-right" }, React.createElement("div", null, "$117")),
          ),
          React.createElement(
            "div",
            { className: "relative cursor-pointer border-2 rounded-[16px] p-5 transition-all flex justify-between items-center border-black/10 bg-surface" },
            React.createElement("div", null, React.createElement("h3", null, "3-Book Bundle")),
            React.createElement("div", { className: "text-right" }, React.createElement("div", null, "$204")),
          ),
          React.createElement("button", null, "Get Your Handbook $117"),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-purchase-runtime-translated",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ProductPurchaseSection",
      sectionTargetId: "product-purchase-section",
      initialTextOverrides: [
        {
          originalText: "OMNI Gummies",
          text: "2-Book Bundle",
        },
      ],
      initialButtonOverrides: [
        {
          originalText: "Get Your Handbook",
          text: "Get Your Handbook",
          href: "",
          action: "medusa_buy_now",
          selectionStrategy: "omni_selected_tier",
          replaceCart: true,
        },
      ],
      purchaseRuntimeData: {
        ctaBaseLabel: "Get Your Handbook",
        variants: [
          { title: "Single Book", priceLabel: "$49" },
          { title: "2-Book Bundle", priceLabel: "$88", compareAtLabel: "$98" },
          { title: "3-Book Bundle", priceLabel: "$119", compareAtLabel: "$147" },
        ],
      },
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

    await new Promise((resolve) => setTimeout(resolve, 100));
    const bodyText = dom.window.document.body.textContent || "";
    expect(bodyText).toContain("Get Your Handbook $88");

    const tierCard = Array.from(dom.window.document.querySelectorAll("div")).find((candidate) => {
      const className = candidate.getAttribute("class") || "";
      if (!className.includes("cursor-pointer")) return false;
      const heading = candidate.querySelector("h3");
      return heading?.textContent?.trim() === "3-Book Bundle";
    });
    expect(tierCard).toBeTruthy();
    tierCard?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    const bodyTextAfterClick = dom.window.document.body.textContent || "";
    expect(bodyTextAfterClick).toContain("Get Your Handbook $119");
  });

  it("emits the selected purchase tier title when imported cards contain nested headings", async () => {
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
          };
        },
      };
    `;
    const compiledSource = `
      const PurchaseCard = ({ title, badge, selected }) =>
        React.createElement(
          "div",
          {
            className: selected
              ? "relative cursor-pointer border-2 rounded-[16px] p-5 transition-all flex justify-between items-center border-primary bg-bg-card"
              : "relative cursor-pointer border-2 rounded-[16px] p-5 transition-all flex justify-between items-center border-black/10 bg-surface",
          },
          React.createElement(
            "div",
            { className: "flex flex-col gap-2" },
            React.createElement("div", { className: "badge-wrap" }, React.createElement("h3", null, badge)),
            React.createElement("h3", null, title),
          ),
          React.createElement("div", { className: "text-right" }, React.createElement("div", null, "$117")),
        );
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "product-purchase-section" },
          React.createElement(PurchaseCard, { title: "2-Book Bundle", badge: "Safety-First", selected: false }),
          React.createElement(PurchaseCard, { title: "3-Book Bundle", badge: "6 Pouches", selected: true }),
          React.createElement("button", null, "Get Your Handbook $117"),
        );
    `;
    const postedMessages: Array<Record<string, unknown>> = [];
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-purchase-runtime-nested-heading",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ProductPurchaseSection",
      sectionTargetId: "product-purchase-section",
      initialButtonOverrides: [
        {
          originalText: "Get Your Handbook",
          text: "Get Your Handbook",
          href: "",
          action: "medusa_buy_now",
          selectionStrategy: "omni_selected_tier",
          replaceCart: true,
        },
      ],
      purchaseRuntimeData: {
        ctaBaseLabel: "Get Your Handbook",
        variants: [
          { title: "2-Book Bundle", priceLabel: "$88", compareAtLabel: "$98" },
          { title: "3-Book Bundle", priceLabel: "$119", compareAtLabel: "$147" },
        ],
      },
    });

    const scripts = [...srcDoc.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
      runScripts: "outside-only",
      url: "http://localhost/imported-runtime",
    });
    const context = dom.getInternalVMContext();
    context.parent = {
      postMessage(payload: unknown) {
        if (payload && typeof payload === "object") {
          postedMessages.push(payload as Record<string, unknown>);
        }
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

    await new Promise((resolve) => setTimeout(resolve, 100));
    const button = dom.window.document.querySelector("button");
    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    await Promise.resolve();

    const commerceActionMessage = postedMessages.find(
      (payload) => payload.type === "commerce-action",
    );
    expect(commerceActionMessage).toMatchObject({
      type: "commerce-action",
      action: "medusa_buy_now",
      selectedOfferTitle: "3-Book Bundle",
      buttonText: "Get Your Handbook $119",
    });
  });

  it("emits parent navigation events for overridden internal CTA links", () => {
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
          };
        },
      };
    `;
    const compiledSource = `
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "hero-section" },
          React.createElement("button", null, "TRY OMNI NOW"),
        );
    `;
    const postedMessages = [];
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-nav",
      sectionLabel: "Hero",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "hero-section",
      initialButtonOverrides: [
        {
          originalText: "TRY OMNI NOW",
          text: "TRY OMNI NOW",
          href: "#product-purchase-section",
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
    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));

    const navigationMessage = postedMessages.find(
      (payload) =>
        typeof payload === "object" &&
        payload !== null &&
        (payload as { type?: unknown }).type === "navigate",
    ) as Record<string, unknown> | undefined;

    expect(navigationMessage).toMatchObject({
      source: "mos-imported-runtime",
      frameId: "frame-nav",
      type: "navigate",
      href: "#product-purchase-section",
      buttonText: "TRY OMNI NOW",
    });
  });

  it("appends unmatched generated policy links into imported global footers", () => {
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
          "footer",
          { "data-section-id": "global-footer" },
          React.createElement(
            "div",
            null,
            React.createElement("a", { href: "/" }, "The Honest Herbalist"),
            React.createElement(
              "div",
              { className: "nav" },
              React.createElement("a", { href: "policies/contact-support", className: "footer-link" }, "Contact Support"),
              React.createElement("a", { href: "#product-purchase-section", className: "footer-link" }, "Start Reading"),
              React.createElement("a", { href: "account", className: "footer-link" }, "Log In"),
            ),
          ),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-footer-nav",
      sectionLabel: "Footer",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "GlobalFooter",
      sectionTargetId: "global-footer",
      initialButtonOverrides: [
        { originalText: "Contact Support", text: "Contact Support", href: "policies/contact-support" },
        { originalText: "Start Reading", text: "Start Reading", href: "#product-purchase-section" },
        { originalText: "Log In", text: "Log In", href: "account" },
        { originalText: "Privacy Policy", text: "Privacy Policy", href: "policies/privacy-policy" },
        { originalText: "Terms of Service", text: "Terms of Service", href: "policies/terms-of-service" },
      ],
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

    const links = Array.from(dom.window.document.querySelectorAll("a")).map((node) => ({
      text: node.textContent?.trim(),
      href: node.getAttribute("href"),
    }));
    expect(links).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ text: "Privacy Policy", href: "policies/privacy-policy" }),
        expect.objectContaining({ text: "Terms of Service", href: "policies/terms-of-service" }),
      ]),
    );
  });

  it("keeps imported section interactions alive after isolating the requested section", () => {
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
              if (key.startsWith("on") && typeof value === "function") {
                element.addEventListener(key.slice(2).toLowerCase(), value);
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
          React.Fragment,
          null,
          React.createElement("section", { "data-section-id": "hero-section" }, "Hero"),
          React.createElement(
            "section",
            { "data-section-id": "product-purchase-section" },
            React.createElement(
              "button",
              { onClick: (event) => { event.currentTarget.textContent = "Selected"; } },
              "Select Bundle",
            ),
          ),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-section-isolation",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "product-purchase-section",
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

    const hero = dom.window.document.querySelector('[data-section-id="hero-section"]') as HTMLElement | null;
    const button = dom.window.document.querySelector("button");
    expect(hero?.style.display).toBe("none");
    expect(button?.textContent).toBe("Select Bundle");

    button?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    expect(button?.textContent).toBe("Selected");
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
          href: "#shop",
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
      (payload) => typeof payload === "object" && payload !== null && (payload as { type?: unknown }).type === "navigate",
    ) as Record<string, unknown> | undefined;

    expect(navigationMessage).toMatchObject({
      source: "mos-imported-runtime",
      frameId: "frame-hash-nav",
      type: "navigate",
      href: "#shop",
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

  it("hides emptied styled heading child elements when split heading overrides clear a trailing segment", () => {
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
            "Creatine For ",
            React.createElement("span", { className: "underline" }, "Body & Mind"),
          ),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-hide-empty",
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
          frameId: "frame-hide-empty",
          type: "update-overrides",
          revision: "2",
          textOverrides: [
            { originalText: "Creatine For", text: "Honest Herbalist Reference Only" },
            { originalText: "Body & Mind", text: "" },
          ],
          buttonOverrides: [],
          imageOverrides: [],
        },
      }),
    );

    const heading = dom.window.document.querySelector("h1");
    const lineBreak = heading?.querySelector("br") as HTMLBRElement | null;
    const trailingSpan = heading?.querySelector("span") as HTMLElement | null;
    expect(heading?.textContent).toBe("Honest Herbalist Reference Only");
    expect(trailingSpan?.textContent).toBe("");
    expect(trailingSpan?.hidden).toBe(true);
    expect(trailingSpan?.style.display).toBe("none");
    expect(lineBreak == null || lineBreak.hidden || lineBreak.style.display === "none").toBe(true);
  });

  it("replaces repeated exact text matches across an isolated section", () => {
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
      const ImportedSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "marquee" },
          React.createElement("p", null, "FRESH & LIGHT TASTE"),
          React.createElement("p", null, "FRESH & LIGHT TASTE"),
          React.createElement("p", null, "FRESH & LIGHT TASTE"),
        );
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-duplicates",
      sectionLabel: "Marquee",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ImportedSection",
      sectionTargetId: "marquee",
      initialTextOverrides: [{ originalText: "FRESH & LIGHT TASTE", text: "SYMPTOM INDEX" }],
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

    const paragraphs = Array.from(dom.window.document.querySelectorAll("p"));
    expect(paragraphs).toHaveLength(3);
    expect(paragraphs.every((node) => node.textContent === "SYMPTOM INDEX")).toBe(true);
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
    expect(sectionIds).toEqual(["hero-section", "feature-marquee-1", "feature-marquee-1-inner", "global-footer"]);
    const heroSection = root?.querySelector('[data-section-id="hero-section"]') as HTMLElement | null;
    const marqueeWrapper = root?.querySelector('[data-section-id="feature-marquee-1"]') as HTMLElement | null;
    const marqueeSection = root?.querySelector('[data-section-id="feature-marquee-1-inner"]') as HTMLElement | null;
    const footerSection = root?.querySelector('[data-section-id="global-footer"]') as HTMLElement | null;
    expect(heroSection?.style.display).toBe("none");
    expect(marqueeWrapper?.style.display).not.toBe("none");
    expect(marqueeSection?.style.display).not.toBe("none");
    expect(marqueeSection?.hidden).toBe(false);
    expect(footerSection?.style.display).toBe("none");
    expect(root?.textContent).toContain("Marquee");
  });

  it("reports the isolated app-backed section height instead of the full document height", () => {
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
      const App = () =>
        React.createElement(
          "div",
          { className: "app-shell" },
          React.createElement(HeroSection, null),
          React.createElement("div", { "data-section-id": "feature-marquee-1" }, React.createElement(FeatureMarquee, null)),
        );
      const ImportedSection = App;
    `;
    const postedMessages: Array<{ type?: string; height?: number }> = [];
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-height-target",
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
    context.parent = {
      postMessage: (message: { type?: string; height?: number }) => postedMessages.push(message),
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

    const target = dom.window.document.querySelector('[data-section-id="feature-marquee-1"]') as HTMLElement | null;
    expect(target).not.toBeNull();
    Object.defineProperty(dom.window.document.body, "scrollHeight", { configurable: true, value: 1200 });
    Object.defineProperty(dom.window.document.body, "offsetHeight", { configurable: true, value: 1200 });
    Object.defineProperty(dom.window.document.documentElement, "scrollHeight", { configurable: true, value: 1200 });
    Object.defineProperty(dom.window.document.documentElement, "offsetHeight", {
      configurable: true,
      value: 1200,
    });
    Object.defineProperty(target!, "scrollHeight", { configurable: true, value: 82 });
    Object.defineProperty(target!, "offsetHeight", { configurable: true, value: 82 });
    target!.getBoundingClientRect = () =>
      ({
        height: 82,
        width: 1000,
        top: 0,
        left: 0,
        right: 1000,
        bottom: 82,
        x: 0,
        y: 0,
        toJSON: () => "",
      }) as DOMRect;

    dom.window.__notifyImportedRuntimeHeight();

    const lastHeightMessage = [...postedMessages].reverse().find((message) => message.type === "height");
    expect(lastHeightMessage?.height).toBe(82);
  });

  it("hides legacy flavor selectors and restores the safety badge layout in purchase sections", () => {
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
      const ProductPurchaseSection = () =>
        React.createElement(
          "section",
          { "data-section-id": "product-purchase-section" },
          React.createElement(
            "div",
            null,
            React.createElement("span", null, "Get Your Copy:"),
            React.createElement(
              "div",
              { id: "legacy-selector" },
              React.createElement("button", null, "Watermelon"),
              React.createElement("button", null, "Peach"),
            ),
            React.createElement(
              "div",
              { className: "relative cursor-pointer border-primary bg-bg-card" },
              React.createElement("div", { className: "absolute -top-3 left-1/2" }, "Safety-First"),
              React.createElement(
                "div",
                null,
                React.createElement("h3", null, "2-Book Bundle"),
                React.createElement("p", null, "PDF + Printable Checklist"),
              ),
              React.createElement(
                "div",
                null,
                React.createElement("span", null, "$117"),
              ),
            ),
          ),
        );
      globalThis.__mosImportedRuntimeComponents = { ProductPurchaseSection };
      const ImportedSection = ProductPurchaseSection;
    `;
    const srcDoc = buildImportedRuntimeSrcDoc({
      frameId: "frame-purchase-runtime",
      sectionLabel: "Purchase",
      compiledSource,
      reactUmdSource: reactStubSource,
      reactDomUmdSource: reactDomStubSource,
      componentName: "ProductPurchaseSection",
      sectionTargetId: "product-purchase-section",
      initialTextOverrides: [{ label: "Text 17", originalText: "BEST VALUE", text: "Safety-First" }],
      purchaseRuntimeData: {
        ctaBaseLabel: "Get Your Handbook",
        variants: [
          { title: "Single Book", priceLabel: "$49" },
          { title: "2-Book Bundle", priceLabel: "$88", compareAtLabel: "$98" },
        ],
      },
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

    const flavorSelector = dom.window.document.getElementById("legacy-selector") as HTMLElement | null;
    const purchaseCard = dom.window.document.querySelector('[class*="cursor-pointer"]') as HTMLElement | null;
    const badge = Array.from(dom.window.document.querySelectorAll("*")).find((candidate) => {
      return candidate instanceof dom.window.HTMLElement && candidate.textContent?.trim() === "Safety-First";
    }) as HTMLElement | undefined;

    expect(flavorSelector?.style.display).toBe("none");
    expect(purchaseCard?.style.marginTop).toBe("0.9rem");
    expect(badge?.style.top).toBe("-0.95rem");
    expect(badge?.style.whiteSpace).toBe("nowrap");
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
