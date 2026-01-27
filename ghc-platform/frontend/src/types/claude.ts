export interface ClaudeContextFile {
  id: string;
  doc_key?: string | null;
  doc_title?: string | null;
  source_kind?: string | null;
  step_key?: string | null;
  claude_file_id: string;
  filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  drive_url?: string | null;
  created_at?: string | null;
}

export type ClaudeStreamEvent =
  | { type: "start"; model?: string; docsAttached?: number }
  | { type: "text"; text: string }
  | { type: "done"; stop_reason?: string | null; output_tokens?: number | null }
  | { type: "error"; message: string };

export type ClaudeChatRequestPayload = {
  prompt: string;
  ideaWorkspaceId: string;
  clientId?: string;
  campaignId?: string;
  fileIds?: string[];
  model?: string;
  maxTokens?: number;
  temperature?: number;
};
