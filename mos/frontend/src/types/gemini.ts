export interface GeminiContextFile {
  id: string;
  doc_key?: string | null;
  doc_title?: string | null;
  source_kind?: string | null;
  step_key?: string | null;
  gemini_store_name?: string | null;
  gemini_file_name?: string | null;
  gemini_document_name: string;
  filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  drive_url?: string | null;
  created_at?: string | null;
}

export interface GeminiCitation {
  title?: string | null;
  uri?: string | null;
  source_kind?: string | null;
  document_name?: string | null;
  start_index?: number | null;
  end_index?: number | null;
}

export type GeminiStreamEvent =
  | { type: "start"; model?: string; docsAttached?: number; storesAttached?: number }
  | { type: "text"; text: string }
  | {
      type: "done";
      stop_reason?: string | null;
      output_tokens?: number | null;
      citations?: GeminiCitation[] | null;
    }
  | { type: "error"; message: string };

export type GeminiChatRequestPayload = {
  prompt: string;
  ideaWorkspaceId: string;
  clientId?: string;
  productId?: string;
  campaignId?: string;
  fileIds?: string[];
  model?: string;
  maxTokens?: number;
  temperature?: number;
};

