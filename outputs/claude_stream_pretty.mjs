import readline from "node:readline";

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
const seenText = new Set();

function write(line = "") {
  process.stdout.write(`${line}\n`);
}

for await (const line of rl) {
  if (!line.trim()) continue;
  let event;
  try {
    event = JSON.parse(line);
  } catch {
    write(line);
    continue;
  }

  if (event.type === "system" && event.subtype === "init") {
    write(`[init] model=${event.model} apiKeySource=${event.apiKeySource} cwd=${event.cwd}`);
    continue;
  }

  if (event.type === "assistant" && event.message?.content) {
    for (const part of event.message.content) {
      if (part.type === "thinking") {
        write("[thinking]");
      }
      if (part.type === "tool_use") {
        write(`[tool] ${part.name}`);
      }
      if (part.type === "text" && part.text && !seenText.has(part.text)) {
        seenText.add(part.text);
        write(part.text);
      }
    }
    continue;
  }

  if (event.type === "user" && event.message?.content) {
    for (const part of event.message.content) {
      if (part.type === "tool_result") {
        write(`[tool-result] ${part.tool_use_id ?? ""}`);
      }
    }
    continue;
  }

  if (event.type === "result") {
    if (event.is_error) {
      write(`[result:error] ${event.result ?? ""}`);
    } else {
      write(`[result:success] turns=${event.num_turns} duration_ms=${event.duration_ms}`);
      if (event.result && !seenText.has(event.result)) {
        write(event.result);
      }
    }
  }
}
