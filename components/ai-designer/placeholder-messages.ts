import type { ChatMessage } from "./types";

export const INITIAL_CHAT_MESSAGES: ChatMessage[] = [
  {
    id: "welcome",
    role: "ai",
    text:
      "שלום! אני מעצב המבנים החכם של eyesteel. תאר את המבנה שברצונך ליצור — למשל: «מסגרת פלדה 12×8 מ׳, עמודים HEB300, קורות ראשיות IPE400» — ואכין עבורך מודל IFC לתצוגה.",
    timestamp: new Date("2026-01-01T09:00:00"),
  },
];
