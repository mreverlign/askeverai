export type MessageRole = "user" | "assistant";

export interface TrajectoryStep {
  type: "thought" | "action" | "answer";
  content: string;
  tool?: string;
  input?: string;
  output?: {
    success: boolean;
    message?: string;
    error?: string;
  } | null;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  isLoading?: boolean;
  generatedSql?: string;
  formattedSql?: string[];
  sqlQueries?: string[];
  results?: QueryResult;
  answer?: string;
  queryId?: number | null;
  dbSource?: string | null;
  fallbackUsed?: boolean;
  recommendedDb?: string | null;
  relevantTables?: string[];
  trajectory?: TrajectoryStep[];
  metadata?: {
    total_time?: number;
    iterations?: number;
    row_count?: number;
  };
}

export interface QueryResult {
  rows: number;
  columns: number;
  data: Record<string, unknown>[] | null;
  csvBlob?: Blob;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}

export interface SessionUser {
  name: string;
  username: string;
  token: string;
  expiresAt: number;
  createdAt: number;
}
