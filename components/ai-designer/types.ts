export type ChatRole = "user" | "ai";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  timestamp: Date;
}

/** Payload sent to the chat-to-IFC API. */
export interface ChatToIfcHistoryMessage {
  role: ChatRole;
  text: string;
}

export interface ChatToIfcRequestBody {
  prompt: string;
  history: ChatToIfcHistoryMessage[];
  /** Legacy alias accepted by the Next.js proxy and Python backend. */
  messages?: ChatToIfcHistoryMessage[];
}
